from ..security.errors import SecurityError


class FixedAssetError(SecurityError): status = 400
class FixedAssetNotFoundError(FixedAssetError): status = 404
class FixedAssetStateError(FixedAssetError): status = 409
class FixedAssetForbiddenError(FixedAssetError): status = 403
