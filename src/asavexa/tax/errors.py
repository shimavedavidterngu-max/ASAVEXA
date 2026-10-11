from ..security.errors import SecurityError


class TaxError(SecurityError): status = 400
class TaxNotFoundError(TaxError): status = 404
class TaxStateError(TaxError): status = 409
class TaxForbiddenError(TaxError): status = 403
