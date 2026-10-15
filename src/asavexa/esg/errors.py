"""ESG and carbon (records and evidence): emission records, verification by a different person and reduction targets."""
from ..security.errors import SecurityError


class EsgError(SecurityError): status = 400
class EsgNotFoundError(EsgError): status = 404
class EsgStateError(EsgError): status = 409
class EsgForbiddenError(EsgError): status = 403
