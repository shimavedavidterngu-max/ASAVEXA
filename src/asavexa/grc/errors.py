from ..security.errors import SecurityError


class GrcError(SecurityError): status = 400
class GrcNotFoundError(GrcError): status = 404
class GrcStateError(GrcError): status = 409
class GrcForbiddenError(GrcError): status = 403
