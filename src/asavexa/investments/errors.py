from ..security.errors import SecurityError


class InvestmentsError(SecurityError): status = 400
class InvestmentsNotFoundError(InvestmentsError): status = 404
class InvestmentsStateError(InvestmentsError): status = 409
class InvestmentsForbiddenError(InvestmentsError): status = 403
