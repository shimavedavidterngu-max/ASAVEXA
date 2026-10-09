"""OpenID Connect sign-in (authorisation-code flow with PKCE). Works with any standards-compliant provider (Google, Microsoft Entra,
Okta, Auth0, Keycloak ...).

Safety rules built in: the ID token's signature is checked against the provider's published keys with an allow-list of
asymmetric algorithms (never 'none', never a shared-secret algorithm); issuer, audience, expiry and nonce must all match; the
email must be verified by the provider; and only people who ALREADY have an ASAVEXA account can sign in (no automatic account
creation). The one-time 'state' carries the nonce, PKCE verifier and a browser-binding value, sealed so it cannot be read or edited."""
from __future__ import annotations

import base64
import hashlib
import json
import os
import secrets
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Callable, List, Optional

import jwt
from jwt import PyJWKClient  # noqa: F401  (documented dependency)

from .crypto import KeyProvider, open_text, seal_text
from .errors import DecryptionError, OidcError
from .store import DocStore

ALLOWED_ALGS = ["RS256", "RS384", "RS512", "ES256", "ES384", "PS256"]
STATE_SECONDS = 600
CLOCK_SKEW = 60


@dataclass
class OidcConfig:
    issuer: str
    client_id: str
    client_secret: str
    redirect_uri: str
    allowed_domains: Optional[List[str]] = None
    scopes: str = "openid email profile"

    @classmethod
    def from_env(cls, env=None) -> Optional["OidcConfig"]:
        env = os.environ if env is None else env
        if not env.get("ASAVEXA_OIDC_ISSUER"):
            return None
        need = ["ASAVEXA_OIDC_CLIENT_ID", "ASAVEXA_OIDC_CLIENT_SECRET", "ASAVEXA_OIDC_REDIRECT_URI"]
        miss = [n for n in need if not env.get(n)]
        if miss:
            raise OidcError("OIDC is partly configured; missing: " + ", ".join(miss))
        doms = [d.strip().lower() for d in (env.get("ASAVEXA_OIDC_ALLOWED_DOMAINS") or "").split(",") if d.strip()]
        return cls(env["ASAVEXA_OIDC_ISSUER"].rstrip("/"), env["ASAVEXA_OIDC_CLIENT_ID"], env["ASAVEXA_OIDC_CLIENT_SECRET"],
                   env["ASAVEXA_OIDC_REDIRECT_URI"], doms or None)


def _b64u(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).decode().rstrip("=")


def _default_get(url: str) -> dict:
    with urllib.request.urlopen(urllib.request.Request(url, headers={"Accept": "application/json"}), timeout=10) as r:
        return json.loads(r.read())


def _default_post(url: str, form: dict) -> dict:
    data = urllib.parse.urlencode(form).encode()
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/x-www-form-urlencoded", "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        return {"error": "http_" + str(e.code)}


class OidcService:
    def __init__(self, cfg: OidcConfig, keys: KeyProvider, store: DocStore, users, now: Callable[[], float] = time.time,
                 http_get: Callable[[str], dict] = _default_get, http_post: Callable[[str, dict], dict] = _default_post):
        """users: the identity UserRepository (get_by_email / get)."""
        self.cfg, self.keys, self.store, self.users, self.now, self.get, self.post = cfg, keys, store, users, now, http_get, http_post
        self._disc = None
        self._jwks = None

    # --- discovery / keys
    def discovery(self) -> dict:
        if self._disc is None:
            try:
                d = self.get(self.cfg.issuer + "/.well-known/openid-configuration")
            except Exception:
                raise OidcError("The sign-in provider could not be reached.")
            if d.get("issuer", "").rstrip("/") != self.cfg.issuer:
                raise OidcError("The sign-in provider reported a different issuer than configured.")
            for k in ("authorization_endpoint", "token_endpoint", "jwks_uri"):
                if not str(d.get(k, "")).startswith("https://") and not str(d.get(k, "")).startswith("http://localhost") and not str(d.get(k, "")).startswith("http://127.0.0.1"):
                    raise OidcError("The provider's endpoints must use HTTPS.")
            self._disc = d
        return self._disc

    def _signing_key(self, kid: Optional[str], refresh: bool = False):
        if self._jwks is None or refresh:
            try:
                self._jwks = self.get(self.discovery()["jwks_uri"])
            except OidcError:
                raise
            except Exception:
                raise OidcError("The provider's signing keys could not be fetched.")
        for k in self._jwks.get("keys", []):
            if (kid is None or k.get("kid") == kid) and k.get("use", "sig") == "sig":
                return jwt.PyJWK(k).key
        if not refresh:
            return self._signing_key(kid, refresh=True)       # keys may have rotated
        raise OidcError("The ID token was signed with an unknown key.")

    # --- step 1
    def start(self, binding: str, return_to: str = "") -> dict:
        if not binding or len(binding) < 16:
            raise OidcError("Missing browser binding value.")
        verifier = _b64u(secrets.token_bytes(48))
        nonce = _b64u(secrets.token_bytes(16))
        state = seal_text(self.keys, json.dumps({"n": nonce, "v": verifier, "b": hashlib.sha256(binding.encode()).hexdigest(), "exp": self.now() + STATE_SECONDS,
                                                 "id": secrets.token_hex(8)}), "oidc-state")
        q = {"response_type": "code", "client_id": self.cfg.client_id, "redirect_uri": self.cfg.redirect_uri, "scope": self.cfg.scopes, "state": state,
             "nonce": nonce, "code_challenge": _b64u(hashlib.sha256(verifier.encode()).digest()), "code_challenge_method": "S256"}
        return {"url": self.discovery()["authorization_endpoint"] + "?" + urllib.parse.urlencode(q)}

    # --- step 2
    def finish(self, code: str, state: str, binding: str) -> dict:
        """Returns {'user': User, 'subject', 'mfa_by_provider': bool}. Raises OidcError for anything wrong."""
        try:
            st = json.loads(open_text(self.keys, state, "oidc-state"))
        except (DecryptionError, ValueError):
            raise OidcError("This sign-in attempt is not valid. Please start again.")
        if self.now() > st["exp"] or self.store.get("oidc_state_used", st["id"]):
            raise OidcError("This sign-in attempt expired or was already used. Please start again.")
        if not secrets.compare_digest(st["b"], hashlib.sha256((binding or "").encode()).hexdigest()):
            raise OidcError("This sign-in was started in a different browser. Please start again.")
        self.store.put("oidc_state_used", st["id"], {"at": self.now()})
        tok = self.post(self.discovery()["token_endpoint"], {"grant_type": "authorization_code", "code": code, "redirect_uri": self.cfg.redirect_uri,
                                                              "client_id": self.cfg.client_id, "client_secret": self.cfg.client_secret, "code_verifier": st["v"]})
        if not isinstance(tok, dict) or "id_token" not in tok:
            raise OidcError("The provider did not accept the sign-in.")
        claims = self.verify_id_token(tok["id_token"], st["n"])
        email = (claims.get("email") or "").strip().lower()
        if not email or claims.get("email_verified") is not True:
            raise OidcError("The provider has not verified your email address.")
        if self.cfg.allowed_domains and email.rsplit("@", 1)[-1] not in self.cfg.allowed_domains:
            raise OidcError("Your email domain is not allowed to sign in here.")
        link_key = hashlib.sha256(f"{self.cfg.issuer}|{claims['sub']}".encode()).hexdigest()
        link = self.store.get("oidc_link", link_key)
        user = self.users.get(link["user_id"]) if link else self.users.get_by_email(email)
        if user is None:       # also try a case-insensitive match for stored mixed-case emails
            user = next((u for u in [self.users.get_by_email(claims["email"])] if u), None)
        if user is None or not user.is_active:
            raise OidcError("There is no active ASAVEXA account for this email. Ask an owner of your organisation to invite you.")
        if link is None:
            self.store.put("oidc_link", link_key, {"user_id": user.id, "issuer": self.cfg.issuer, "linked_at": self.now()})
        amr = claims.get("amr") or []
        return {"user": user, "subject": claims["sub"], "mfa_by_provider": any(a in ("mfa", "otp", "hwk", "swk", "pop") for a in amr)}

    def verify_id_token(self, token: str, nonce: str) -> dict:
        try:
            header = jwt.get_unverified_header(token)
        except jwt.PyJWTError:
            raise OidcError("The ID token is malformed.")
        if header.get("alg") not in ALLOWED_ALGS:
            raise OidcError("The ID token uses a signing method that is not allowed.")
        key = self._signing_key(header.get("kid"))
        try:
            claims = jwt.decode(token, key, algorithms=ALLOWED_ALGS, audience=self.cfg.client_id, issuer=self.cfg.issuer, leeway=CLOCK_SKEW,
                                options={"require": ["exp", "iat", "iss", "aud", "sub"]})
        except jwt.ExpiredSignatureError:
            raise OidcError("The ID token has expired.")
        except jwt.PyJWTError as e:
            raise OidcError("The ID token could not be verified.")
        if not secrets.compare_digest(str(claims.get("nonce", "")), nonce):
            raise OidcError("The ID token does not belong to this sign-in attempt.")
        if isinstance(claims.get("aud"), list) and len(claims["aud"]) > 1 and claims.get("azp") != self.cfg.client_id:
            raise OidcError("The ID token was issued for a different application.")
        return claims
