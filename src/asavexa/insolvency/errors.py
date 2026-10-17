"""Insolvency (records and evidence)."""
from ..security.errors import SecurityError


class InsolvencyError(SecurityError): status = 400
class InsolvencyNotFoundError(InsolvencyError): status = 404
class InsolvencyStateError(InsolvencyError): status = 409
class InsolvencyForbiddenError(InsolvencyError): status = 403
