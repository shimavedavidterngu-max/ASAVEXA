from ..security.errors import SecurityError


class ItAuditError(SecurityError): status = 400
class ItAuditNotFoundError(ItAuditError): status = 404
class ItAuditStateError(ItAuditError): status = 409
class ItAuditForbiddenError(ItAuditError): status = 403
