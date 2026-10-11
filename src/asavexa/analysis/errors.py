from ..security.errors import SecurityError


class AnalysisError(SecurityError): status = 400
class AnalysisNotFoundError(AnalysisError): status = 404
class AnalysisStateError(AnalysisError): status = 409
class AnalysisForbiddenError(AnalysisError): status = 403
