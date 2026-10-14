from ..security.errors import SecurityError


class FincrimeError(SecurityError): status = 400
class FincrimeNotFoundError(FincrimeError): status = 404
class FincrimeStateError(FincrimeError): status = 409
class FincrimeForbiddenError(FincrimeError): status = 403
