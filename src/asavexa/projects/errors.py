"""Projects and grants (records and evidence): a project with a typed award and budget lines, spending and receipts approved by a different person."""
from ..security.errors import SecurityError


class ProjectsError(SecurityError): status = 400
class ProjectsNotFoundError(ProjectsError): status = 404
class ProjectsStateError(ProjectsError): status = 409
class ProjectsForbiddenError(ProjectsError): status = 403
