"""Mergers and acquisitions (records and evidence)."""
from ..security.errors import SecurityError


class MergersError(SecurityError): status = 400
class MergersNotFoundError(MergersError): status = 404
class MergersStateError(MergersError): status = 409
class MergersForbiddenError(MergersError): status = 403
