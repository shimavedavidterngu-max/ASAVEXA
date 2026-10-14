from ..security.errors import SecurityError


class ProcurementError(SecurityError): status = 400
class ProcurementNotFoundError(ProcurementError): status = 404
class ProcurementStateError(ProcurementError): status = 409
class ProcurementForbiddenError(ProcurementError): status = 403
