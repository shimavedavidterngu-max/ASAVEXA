from ..security.errors import SecurityError


class NetworkError(SecurityError): status = 400
class NetworkNotFoundError(NetworkError): status = 404
class NetworkStateError(NetworkError): status = 409
class NetworkForbiddenError(NetworkError): status = 403
