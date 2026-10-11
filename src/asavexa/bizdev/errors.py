from ..security.errors import SecurityError


class BizDevError(SecurityError): status = 400
class BizDevNotFoundError(BizDevError): status = 404
class BizDevStateError(BizDevError): status = 409
class BizDevForbiddenError(BizDevError): status = 403
