from ..security.errors import SecurityError


class ProfessionalValidationError(SecurityError):
    status = 400


class ReviewNotFoundError(ProfessionalValidationError):
    status = 404


class ReviewStateError(ProfessionalValidationError):
    status = 409


class ReviewForbiddenError(ProfessionalValidationError):
    status = 403
