"""Builds the security services for a request from environment settings. Nothing here has a default key or a default secret:
without ASAVEXA_KEYS the encryption-dependent features are simply off, and say so."""
import json
import logging
import os
import urllib.request
from typing import Optional

from ..security.context import SecurityContext
from ..security.crypto import LocalKeyring
from ..security.errors import KeysNotConfiguredError, OidcError, SecurityError
from ..security.objectstore import DatabaseObjectStore, LocalObjectStore, S3ObjectStore
from ..security.blobs import BlobService
from ..security.governance import ResidencyService, SettingsService
from ..security.oidc import OidcConfig
from ..security.sessions import SessionPolicy
from .db.audit_chain_hook import platform_keys
from .db.security_store import SqlAlchemyDocStore

logger = logging.getLogger("asavexa")


def _int_env(name: str, default: int) -> int:
    try:
        return max(1, int(os.environ.get(name, default)))
    except ValueError:
        return default


def session_policy() -> SessionPolicy:
    return SessionPolicy(idle_minutes=_int_env("ASAVEXA_IDLE_MINUTES", 30), max_sessions=_int_env("ASAVEXA_MAX_SESSIONS", 5))


def object_store(store):
    """ASAVEXA_STORAGE = database (default) | s3 | local | none."""
    mode = (os.environ.get("ASAVEXA_STORAGE") or "database").lower()
    region = os.environ.get("ASAVEXA_DATA_REGION", "unspecified")
    if mode == "none":
        return None
    if mode == "s3":
        return S3ObjectStore.from_env()
    if mode == "local":
        return LocalObjectStore(os.environ.get("ASAVEXA_LOCAL_STORAGE_DIR", "/tmp/asavexa-objects"), region=region)
    return DatabaseObjectStore(store, region=region)


def make_blobs(session) -> Optional[BlobService]:
    """Encrypted evidence storage, or None when keys / storage are not configured (evidence then keeps only record + fingerprint, as before)."""
    keys = platform_keys()
    if keys is None:
        return None
    store = SqlAlchemyDocStore(session)
    try:
        objects = object_store(store)
    except SecurityError:
        logger.exception("object_storage_misconfigured")
        return None
    if objects is None:
        return None
    return BlobService(store, objects, keys, residency=ResidencyService(SettingsService(store)))


def _webhook_notifier():
    url = os.environ.get("ASAVEXA_ALERT_WEBHOOK", "").strip()
    if not url.startswith("https://"):
        return None

    def send(alert: dict) -> None:
        body = json.dumps({"text": f"[ASAVEXA {alert['severity']}] {alert['title']} - {alert['detail']}"}).encode()
        urllib.request.urlopen(urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"}), timeout=5)
    return send


def build_security(session, identity) -> SecurityContext:
    from ..audit.repository import AuditRepository  # noqa: F401
    from .db.audit_sqlalchemy_repository import SqlAlchemyAuditRepository
    store = SqlAlchemyDocStore(session)
    keys = platform_keys()
    try:
        objects = object_store(store) if keys is not None else None
    except SecurityError:
        objects = None
    try:
        oidc = OidcConfig.from_env()
    except OidcError:
        logger.exception("oidc_misconfigured")
        oidc = None
    return SecurityContext(identity, SqlAlchemyAuditRepository(session), store, keys=keys, objects=objects, oidc_cfg=oidc, commit=session.commit,
                           policy=session_policy(), database_region=os.environ.get("ASAVEXA_DATA_REGION", "unspecified"), notifier=_webhook_notifier())
