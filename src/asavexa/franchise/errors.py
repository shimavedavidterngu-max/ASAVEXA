"""Franchise and multi-location (records and evidence)."""
from ..security.errors import SecurityError


class FranchiseError(SecurityError): status = 400
class FranchiseNotFoundError(FranchiseError): status = 404
class FranchiseStateError(FranchiseError): status = 409
class FranchiseForbiddenError(FranchiseError): status = 403
