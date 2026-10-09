"""Extends the tamper-evident audit chain whenever an audit event is written, when encryption keys are configured.
Runs in the same database transaction as the event. A failure here is logged and isolated (savepoint), so it can never
stop the business action; the missing link then shows up as an 'unchained event' when the chain is verified."""
import logging

from ...security.auditchain import append_link
from ...security.errors import KeysNotConfiguredError
from .security_store import SqlAlchemyDocStore

logger = logging.getLogger("asavexa")
_cache = {"loaded": False, "keys": None}


def platform_keys():
    """The platform keyring from the environment, or None when not configured. Loaded once per process."""
    if not _cache["loaded"]:
        from ...security.crypto import LocalKeyring
        try:
            _cache["keys"] = LocalKeyring.from_env()
        except KeysNotConfiguredError:
            _cache["keys"] = None
        _cache["loaded"] = True
    return _cache["keys"]


def reset_for_tests():
    _cache.update(loaded=False, keys=None)


def chain_event(session, event) -> None:
    keys = platform_keys()
    if keys is None:
        return
    session.flush()                         # a failure of the audit write itself must surface, not be hidden below
    for attempt in (1, 2):
        try:
            with session.begin_nested():
                append_link(SqlAlchemyDocStore(session), keys, event)
            return
        except Exception:                   # pragma: no cover - needs a live database
            logger.exception("audit_chain_append_failed", extra={"attempt": attempt})
