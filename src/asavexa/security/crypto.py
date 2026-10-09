"""Envelope encryption and key management.

Each stored file gets its own random data key (DEK, AES-256-GCM). The DEK is wrapped by a key-encryption key (KEK) that
lives in a Keyring (or, in production, a cloud KMS that implements the same wrap/unwrap interface). Rotating the KEK
re-wraps the small DEKs only; the files are not touched. Every ciphertext is bound to its owner (org + record id) through
AES-GCM associated data, so a blob copied onto another record or another organisation cannot be decrypted."""
from __future__ import annotations

import base64
import hashlib
import hmac
import os
import secrets
from typing import Dict, Optional, Protocol, Tuple

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from .errors import DecryptionError, KeysNotConfiguredError

ALG = "AES-256-GCM"


def _b64(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).decode().rstrip("=")


def _unb64(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


class KeyProvider(Protocol):
    """What a KMS must offer. LocalKeyring below is the built-in implementation."""
    current_key_id: str
    def wrap(self, dek: bytes, aad: bytes, key_id: Optional[str] = None) -> Tuple[str, str]: ...
    def unwrap(self, key_id: str, wrapped: str, aad: bytes) -> bytes: ...
    def key_ids(self) -> list: ...
    def mac(self, purpose: str, data: bytes, key_id: Optional[str] = None) -> Tuple[str, str]: ...
    def verify_mac(self, purpose: str, data: bytes, key_id: str, tag: str) -> bool: ...


class LocalKeyring:
    def __init__(self, keys: Dict[str, bytes], current: str):
        if not keys:
            raise KeysNotConfiguredError("No encryption keys are configured.")
        for k, v in keys.items():
            if len(v) != 32:
                raise KeysNotConfiguredError(f"Key {k!r} must be exactly 32 bytes (256 bits).")
        if current not in keys:
            raise KeysNotConfiguredError(f"The current key {current!r} is not in the keyring.")
        self._keys, self.current_key_id = dict(keys), current

    @classmethod
    def from_env(cls, env=None) -> "LocalKeyring":
        """ASAVEXA_KEYS="2026-10:<base64url 32 bytes>,2026-04:<...>"  and  ASAVEXA_CURRENT_KEY="2026-10"."""
        env = os.environ if env is None else env
        raw = (env.get("ASAVEXA_KEYS") or "").strip()
        if not raw:
            raise KeysNotConfiguredError("ASAVEXA_KEYS is not set. Generate keys with: python -m asavexa.security.keygen")
        keys = {}
        for part in raw.split(","):
            try:
                kid, val = part.strip().split(":", 1)
                keys[kid.strip()] = _unb64(val.strip())
            except Exception:
                raise KeysNotConfiguredError("ASAVEXA_KEYS must look like  id:base64key,id2:base64key2")
        return cls(keys, (env.get("ASAVEXA_CURRENT_KEY") or "").strip() or list(keys)[0])

    @staticmethod
    def generate_key() -> bytes:
        return AESGCM.generate_key(bit_length=256)

    def key_ids(self):
        return list(self._keys)

    def _mac_key(self, kid, purpose):
        # A separate key per purpose, derived from the key-encryption key, so a MAC key is never used for encryption.
        return hmac.new(self._keys[kid], b"asavexa-mac|" + purpose.encode(), hashlib.sha256).digest()

    def mac(self, purpose, data, key_id=None):
        kid = key_id or self.current_key_id
        return kid, hmac.new(self._mac_key(kid, purpose), data, hashlib.sha256).hexdigest()

    def verify_mac(self, purpose, data, key_id, tag):
        if key_id not in self._keys:
            return False
        return hmac.compare_digest(hmac.new(self._mac_key(key_id, purpose), data, hashlib.sha256).hexdigest(), tag or "")

    def wrap(self, dek, aad, key_id=None):
        kid = key_id or self.current_key_id
        nonce = secrets.token_bytes(12)
        return kid, _b64(nonce + AESGCM(self._keys[kid]).encrypt(nonce, dek, aad))

    def unwrap(self, key_id, wrapped, aad):
        if key_id not in self._keys:
            raise DecryptionError(f"Key {key_id!r} is not available, so this data cannot be decrypted.")
        raw = _unb64(wrapped)
        try:
            return AESGCM(self._keys[key_id]).decrypt(raw[:12], raw[12:], aad)
        except InvalidTag:
            raise DecryptionError("The data key could not be unwrapped (wrong key or the record was moved).")


def aad_for(org_id: str, record_id: str) -> bytes:
    return f"asavexa|{org_id}|{record_id}".encode()


def encrypt_blob(kp: KeyProvider, plaintext: bytes, org_id: str, record_id: str) -> Tuple[bytes, dict]:
    """Returns (ciphertext, header). The header holds no secret: key id, wrapped DEK, nonce."""
    aad = aad_for(org_id, record_id)
    dek, nonce = AESGCM.generate_key(bit_length=256), secrets.token_bytes(12)
    ct = AESGCM(dek).encrypt(nonce, plaintext, aad)
    kid, wrapped = kp.wrap(dek, aad)
    return ct, {"alg": ALG, "kid": kid, "wrapped_dek": wrapped, "nonce": _b64(nonce)}


def decrypt_blob(kp: KeyProvider, ciphertext: bytes, header: dict, org_id: str, record_id: str) -> bytes:
    aad = aad_for(org_id, record_id)
    if header.get("alg") != ALG:
        raise DecryptionError("Unsupported encryption format.")
    dek = kp.unwrap(header["kid"], header["wrapped_dek"], aad)
    try:
        return AESGCM(dek).decrypt(_unb64(header["nonce"]), ciphertext, aad)
    except InvalidTag:
        raise DecryptionError("The stored file failed its integrity check. It was changed or damaged.")


def rewrap(kp: KeyProvider, header: dict, org_id: str, record_id: str, to_key_id: Optional[str] = None) -> dict:
    """Key rotation for one record: unwrap the DEK with its old key, wrap with the new one. The file is not touched."""
    aad = aad_for(org_id, record_id)
    dek = kp.unwrap(header["kid"], header["wrapped_dek"], aad)
    kid, wrapped = kp.wrap(dek, aad, to_key_id)
    return {**header, "kid": kid, "wrapped_dek": wrapped}


def seal_text(kp: KeyProvider, text: str, purpose: str) -> str:
    """Small secrets (an MFA secret, an OIDC state): returns 'v1.<kid>.<wrapped dek>.<nonce>.<ciphertext>' using the same envelope."""
    ct, h = encrypt_blob(kp, text.encode(), "seal", purpose)
    return ".".join(["v1", h["kid"], h["wrapped_dek"], h["nonce"], _b64(ct)])


def open_text(kp: KeyProvider, sealed: str, purpose: str) -> str:
    try:
        v, kid, wrapped, nonce, ct = sealed.split(".")
    except ValueError:
        raise DecryptionError("Malformed sealed value.")
    if v != "v1":
        raise DecryptionError("Unsupported sealed value.")
    return decrypt_blob(kp, _unb64(ct), {"alg": ALG, "kid": kid, "wrapped_dek": wrapped, "nonce": nonce}, "seal", purpose).decode()
