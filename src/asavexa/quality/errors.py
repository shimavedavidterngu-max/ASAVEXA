from ..security.errors import SecurityError


class QualityError(SecurityError): status = 400
class QualityNotFoundError(QualityError): status = 404
class QualityStateError(QualityError): status = 409
class QualityForbiddenError(QualityError): status = 403
