from ..security.errors import SecurityError


class AigovError(SecurityError): status = 400
class AigovNotFoundError(AigovError): status = 404
class AigovStateError(AigovError): status = 409
class AigovForbiddenError(AigovError): status = 403
