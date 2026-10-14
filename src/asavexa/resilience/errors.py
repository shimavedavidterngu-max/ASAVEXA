from ..security.errors import SecurityError


class ResilienceError(SecurityError): status = 400
class ResilienceNotFoundError(ResilienceError): status = 404
class ResilienceStateError(ResilienceError): status = 409
class ResilienceForbiddenError(ResilienceError): status = 403
