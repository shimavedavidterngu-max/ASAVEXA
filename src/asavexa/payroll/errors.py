"""Payroll and workforce cost (records and evidence): payroll runs worked out from typed pay lines and reviewed by a different person."""
from ..security.errors import SecurityError


class PayrollError(SecurityError): status = 400
class PayrollNotFoundError(PayrollError): status = 404
class PayrollStateError(PayrollError): status = 409
class PayrollForbiddenError(PayrollError): status = 403
