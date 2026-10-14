from ..security.errors import SecurityError


class FpaError(SecurityError): status = 400
class FpaNotFoundError(FpaError): status = 404
class FpaStateError(FpaError): status = 409
class FpaForbiddenError(FpaError): status = 403
