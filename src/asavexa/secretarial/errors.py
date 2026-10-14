from ..security.errors import SecurityError


class SecretarialError(SecurityError): status = 400
class SecretarialNotFoundError(SecretarialError): status = 404
class SecretarialStateError(SecretarialError): status = 409
class SecretarialForbiddenError(SecretarialError): status = 403
