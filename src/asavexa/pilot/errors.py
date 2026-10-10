from ..security.errors import SecurityError


class PilotError(SecurityError): status = 400
class PilotNotFoundError(PilotError): status = 404
class PilotStateError(PilotError): status = 409
class PilotForbiddenError(PilotError): status = 403
