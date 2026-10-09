class AsavexaPassportError(Exception):
    """Base class for Financial Passport errors."""


class ShareValidationError(AsavexaPassportError):
    """The sharing request is not valid (HTTP 400)."""


class ShareNotFoundError(AsavexaPassportError):
    """No such share in this organisation (HTTP 404)."""


class ShareStateError(AsavexaPassportError):
    """The share is in a state that does not allow this (HTTP 409)."""


class ShareAccessDeniedError(AsavexaPassportError):
    """A recipient could not be verified, or the access is no longer valid (HTTP 403).
    Messages are deliberately generic: they never say which part was wrong."""
