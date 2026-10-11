from ..security.errors import SecurityError


class PubFinError(SecurityError): status = 400
class PubFinNotFoundError(PubFinError): status = 404
class PubFinStateError(PubFinError): status = 409
class PubFinForbiddenError(PubFinError): status = 403
