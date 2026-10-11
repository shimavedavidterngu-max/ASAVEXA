from ..security.errors import SecurityError


class CyberError(SecurityError): status = 400
class CyberNotFoundError(CyberError): status = 404
class CyberStateError(CyberError): status = 409
class CyberForbiddenError(CyberError): status = 403
