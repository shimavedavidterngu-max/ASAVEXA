"""PostgreSQL stores an audit event's entity_id in a UUID column. Anything that is not already a UUID (an email address for a
failed sign-in, a file fingerprint, ...) is mapped to a stable UUID derived from it, so the write cannot fail and the same
value always maps to the same id."""
import uuid

_NS = uuid.UUID("6f1c2a52-8c0e-4c0b-9f5e-1c1d6a5b7e11")


def db_entity_id(value: str) -> str:
    try:
        return str(uuid.UUID(str(value)))
    except (ValueError, AttributeError, TypeError):
        return str(uuid.uuid5(_NS, str(value)))
