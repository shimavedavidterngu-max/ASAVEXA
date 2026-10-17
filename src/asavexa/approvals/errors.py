"""Approval workflows (records and evidence)."""
from ..security.errors import SecurityError


class ApprovalsError(SecurityError): status = 400
class ApprovalsNotFoundError(ApprovalsError): status = 404
class ApprovalsStateError(ApprovalsError): status = 409
class ApprovalsForbiddenError(ApprovalsError): status = 403
