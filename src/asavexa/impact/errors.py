"""Impact measurement (records and evidence)."""
from ..security.errors import SecurityError


class ImpactError(SecurityError): status = 400
class ImpactNotFoundError(ImpactError): status = 404
class ImpactStateError(ImpactError): status = 409
class ImpactForbiddenError(ImpactError): status = 403
