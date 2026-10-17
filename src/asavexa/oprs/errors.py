"""Operations research (records and evidence)."""
from ..security.errors import SecurityError


class OprsError(SecurityError): status = 400
class OprsNotFoundError(OprsError): status = 404
class OprsStateError(OprsError): status = 409
class OprsForbiddenError(OprsError): status = 403
