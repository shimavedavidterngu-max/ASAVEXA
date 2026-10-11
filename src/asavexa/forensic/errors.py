from ..security.errors import SecurityError


class ForensicError(SecurityError): status = 400
class ForensicNotFoundError(ForensicError): status = 404
class ForensicStateError(ForensicError): status = 409
class ForensicForbiddenError(ForensicError): status = 403
