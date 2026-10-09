class AsavexaAiError(Exception):
    """Base class for AI-layer errors (mapped to HTTP statuses in api/main.py)."""


class AiValidationError(AsavexaAiError):          # 400
    pass


class AiSubjectNotFoundError(AsavexaAiError):     # 404
    pass
