class SecurityError(Exception):
    """Base for every security-module error. The API turns these into clear 4xx responses."""
    status = 400


class KeysNotConfiguredError(SecurityError):
    status = 503


class DecryptionError(SecurityError):
    status = 500


class MfaRequiredError(SecurityError):
    status = 403


class MfaError(SecurityError):
    status = 400


class MfaLockedError(SecurityError):
    status = 429


class SessionPolicyError(SecurityError):
    status = 401


class AccountLockedError(SecurityError):
    status = 429


class OidcError(SecurityError):
    status = 400


class StorageError(SecurityError):
    status = 502


class ResidencyError(SecurityError):
    status = 409


class RetentionError(SecurityError):
    status = 409


class LegalHoldError(RetentionError):
    pass


class NotFoundError(SecurityError):
    status = 404


class ValidationError(SecurityError):
    status = 400
