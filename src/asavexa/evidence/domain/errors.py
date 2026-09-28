"""Error hierarchy for the Evidence Vault."""


class AsavexaEvidenceError(Exception):
    """Base class for all Evidence Vault domain errors."""


class EvidenceNotFoundError(AsavexaEvidenceError):
    pass


class DuplicateEvidenceError(AsavexaEvidenceError):
    """
    Raised when uploading content whose hash already exists for this
    organisation, unless the caller explicitly passes allow_duplicate=True
    (e.g. a supplier legitimately re-sends the same invoice PDF and the
    user wants both linked). Never silently deduplicate — always make
    the caller decide (Blueprint: "never hide errors").
    """


class InvalidEvidenceStateError(AsavexaEvidenceError):
    """Raised on an illegal status transition, e.g. verifying a record
    that has already been rejected."""


class EmptyFileError(AsavexaEvidenceError):
    pass
