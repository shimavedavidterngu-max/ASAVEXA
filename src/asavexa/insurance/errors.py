"""Insurance and claims (records and evidence): a register of policies, claims, settlements decided by a different person, and amounts received."""
from ..security.errors import SecurityError


class InsuranceError(SecurityError): status = 400
class InsuranceNotFoundError(InsuranceError): status = 404
class InsuranceStateError(InsuranceError): status = 409
class InsuranceForbiddenError(InsuranceError): status = 403
