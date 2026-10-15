from ..security.errors import SecurityError


class ValuationError(SecurityError): status = 400
class ValuationNotFoundError(ValuationError): status = 404
class ValuationStateError(ValuationError): status = 409
class ValuationForbiddenError(ValuationError): status = 403
