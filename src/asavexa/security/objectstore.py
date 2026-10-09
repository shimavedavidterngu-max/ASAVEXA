"""Object storage for encrypted evidence files. Stores only ciphertext. Three backends with one small interface:
  - DatabaseObjectStore: keeps ciphertext in the security document table (works with no extra service; fine for pilots)
  - S3ObjectStore: any S3-compatible service (AWS S3, Cloudflare R2, Backblaze B2, MinIO, DigitalOcean Spaces), signed with SigV4
  - LocalObjectStore / MemoryObjectStore: for development and tests"""
from __future__ import annotations

import base64
import datetime as _dt
import hashlib
import hmac
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from typing import Callable, Dict, Optional, Protocol

from .errors import NotFoundError, StorageError
from .store import DocStore

_KEY_OK = re.compile(r"^[A-Za-z0-9._/=-]{1,300}$")


def _check_key(key: str) -> str:
    if not _KEY_OK.match(key) or ".." in key.split("/") or key.startswith("/"):
        raise StorageError("Invalid storage key.")
    return key


class ObjectStore(Protocol):
    name: str
    region: str
    def put(self, key: str, data: bytes) -> None: ...
    def get(self, key: str) -> bytes: ...
    def delete(self, key: str) -> None: ...
    def exists(self, key: str) -> bool: ...


class MemoryObjectStore:
    name = "memory"

    def __init__(self, region: str = "test-region"):
        self.region, self.data_region, self.objects = region, region, {}

    def put(self, key, data): self.objects[_check_key(key)] = bytes(data)

    def get(self, key):
        try:
            return self.objects[_check_key(key)]
        except KeyError:
            raise NotFoundError("The stored file was not found.")

    def delete(self, key): self.objects.pop(_check_key(key), None)
    def exists(self, key): return _check_key(key) in self.objects


class LocalObjectStore:
    name = "local-disk"

    def __init__(self, root: str, region: str = "local"):
        self.root, self.region = os.path.abspath(root), region
        self.data_region = region
        os.makedirs(self.root, exist_ok=True)

    def _path(self, key):
        p = os.path.abspath(os.path.join(self.root, _check_key(key)))
        if not p.startswith(self.root + os.sep):
            raise StorageError("Invalid storage key.")
        return p

    def put(self, key, data):
        p = self._path(key); os.makedirs(os.path.dirname(p), exist_ok=True)
        tmp = p + ".tmp"
        with open(tmp, "wb") as f:
            f.write(data); f.flush(); os.fsync(f.fileno())
        os.replace(tmp, p)

    def get(self, key):
        try:
            with open(self._path(key), "rb") as f:
                return f.read()
        except FileNotFoundError:
            raise NotFoundError("The stored file was not found.")

    def delete(self, key):
        try:
            os.remove(self._path(key))
        except FileNotFoundError:
            pass

    def exists(self, key): return os.path.exists(self._path(key))


class DatabaseObjectStore:
    """Ciphertext kept in the database. Simple and durable with the database's own backups; use S3 for large volumes."""
    name = "database"

    def __init__(self, store: DocStore, region: str = "unspecified"):
        self.store, self.region = store, region
        self.data_region = region

    def put(self, key, data): self.store.put("object", _check_key(key), {"b64": base64.b64encode(data).decode()})

    def get(self, key):
        d = self.store.get("object", _check_key(key))
        if d is None:
            raise NotFoundError("The stored file was not found.")
        return base64.b64decode(d["b64"])

    def delete(self, key): self.store.delete("object", _check_key(key))
    def exists(self, key): return self.store.get("object", _check_key(key)) is not None


# ----------------------------------------------------------------------------------------- SigV4
def _hmac(key: bytes, msg: str) -> bytes:
    return hmac.new(key, msg.encode(), hashlib.sha256).digest()


def _uri_encode(s: str, slash: bool = False) -> str:
    return urllib.parse.quote(s, safe="-_.~" + ("" if slash else "/"))


def sign_v4(method: str, url: str, headers: Dict[str, str], payload_hash: str, access_key: str, secret_key: str,
            region: str, service: str, amz_date: str, signed_header_names: Optional[list] = None) -> str:
    """AWS Signature Version 4. Returns the Authorization header value. `headers` must already include host and x-amz-date."""
    u = urllib.parse.urlsplit(url)
    canon_uri = _uri_encode(urllib.parse.unquote(u.path) or "/", slash=False) if service != "s3" else _uri_encode(urllib.parse.unquote(u.path) or "/")
    q = sorted((_uri_encode(k, True), _uri_encode(v, True)) for k, v in urllib.parse.parse_qsl(u.query, keep_blank_values=True))
    canon_q = "&".join(f"{k}={v}" for k, v in q)
    names = sorted(h.lower() for h in (signed_header_names or headers))
    lower = {k.lower(): " ".join(v.strip().split()) for k, v in headers.items()}
    canon_h = "".join(f"{n}:{lower[n]}\n" for n in names)
    signed = ";".join(names)
    canonical = "\n".join([method, canon_uri, canon_q, canon_h, signed, payload_hash])
    date = amz_date[:8]
    scope = f"{date}/{region}/{service}/aws4_request"
    to_sign = "\n".join(["AWS4-HMAC-SHA256", amz_date, scope, hashlib.sha256(canonical.encode()).hexdigest()])
    k = _hmac(_hmac(_hmac(_hmac(("AWS4" + secret_key).encode(), date), region), service), "aws4_request")
    sig = hmac.new(k, to_sign.encode(), hashlib.sha256).hexdigest()
    return f"AWS4-HMAC-SHA256 Credential={access_key}/{scope}, SignedHeaders={signed}, Signature={sig}"


class S3ObjectStore:
    name = "s3"

    def __init__(self, endpoint: str, bucket: str, region: str, access_key: str, secret_key: str, path_style: bool = True,
                 timeout: int = 20, data_region: str = "unspecified", now: Callable[[], _dt.datetime] = lambda: _dt.datetime.now(_dt.timezone.utc)):
        if not (endpoint and bucket and access_key and secret_key):
            raise StorageError("Object storage is not fully configured.")
        self.endpoint, self.bucket, self.region = endpoint.rstrip("/"), bucket, region
        self.data_region = data_region      # where the bucket's data physically lives, as declared by the operator (a code like NG or EU)
        self.access, self.secret, self.path_style, self.timeout, self.now = access_key, secret_key, path_style, timeout, now

    @classmethod
    def from_env(cls, env=None):
        env = os.environ if env is None else env
        return cls(env.get("ASAVEXA_S3_ENDPOINT", ""), env.get("ASAVEXA_S3_BUCKET", ""), env.get("ASAVEXA_S3_REGION", "us-east-1"),
                   env.get("ASAVEXA_S3_ACCESS_KEY", ""), env.get("ASAVEXA_S3_SECRET_KEY", ""), env.get("ASAVEXA_S3_PATH_STYLE", "1") != "0",
                   data_region=env.get("ASAVEXA_DATA_REGION", "unspecified"))

    def _url(self, key):
        key = _check_key(key)
        if self.path_style:
            return f"{self.endpoint}/{self.bucket}/{urllib.parse.quote(key)}"
        u = urllib.parse.urlsplit(self.endpoint)
        return f"{u.scheme}://{self.bucket}.{u.netloc}/{urllib.parse.quote(key)}"

    def _request(self, method, key, body=b""):
        url = self._url(key)
        amz = self.now().strftime("%Y%m%dT%H%M%SZ")
        ph = hashlib.sha256(body).hexdigest()
        host = urllib.parse.urlsplit(url).netloc
        headers = {"host": host, "x-amz-date": amz, "x-amz-content-sha256": ph}
        headers["Authorization"] = sign_v4(method, url, {k: v for k, v in headers.items()}, ph, self.access, self.secret, self.region, "s3", amz)
        req = urllib.request.Request(url, data=body if method in ("PUT",) else None, method=method,
                                     headers={k: v for k, v in headers.items() if k != "host"})
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as r:
                return r.status, r.read()
        except urllib.error.HTTPError as e:
            return e.code, e.read()
        except Exception as e:
            raise StorageError(f"Could not reach object storage: {type(e).__name__}")

    def put(self, key, data):
        code, body = self._request("PUT", key, data)
        if code not in (200, 201, 204):
            raise StorageError(f"Object storage refused the upload (HTTP {code}).")

    def get(self, key):
        code, body = self._request("GET", key)
        if code == 404:
            raise NotFoundError("The stored file was not found.")
        if code != 200:
            raise StorageError(f"Object storage returned HTTP {code}.")
        return body

    def delete(self, key):
        code, _ = self._request("DELETE", key)
        if code not in (200, 202, 204, 404):
            raise StorageError(f"Object storage refused the delete (HTTP {code}).")

    def exists(self, key):
        code, _ = self._request("HEAD", key)
        if code == 200:
            return True
        if code == 404:
            return False
        raise StorageError(f"Object storage returned HTTP {code}.")
