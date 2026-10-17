"""Data governance (records and evidence)."""
from ..security.errors import SecurityError


class DatagovError(SecurityError): status = 400
class DatagovNotFoundError(DatagovError): status = 404
class DatagovStateError(DatagovError): status = 409
class DatagovForbiddenError(DatagovError): status = 403
