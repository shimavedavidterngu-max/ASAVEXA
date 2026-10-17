"""Pension and fiduciary (records and evidence)."""
from ..security.errors import SecurityError


class PensionError(SecurityError): status = 400
class PensionNotFoundError(PensionError): status = 404
class PensionStateError(PensionError): status = 409
class PensionForbiddenError(PensionError): status = 403
