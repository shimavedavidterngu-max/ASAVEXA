from ..security.errors import SecurityError


class HealthError(SecurityError): status = 400
class HealthNotFoundError(HealthError): status = 404
class HealthStateError(HealthError): status = 409
class HealthForbiddenError(HealthError): status = 403
