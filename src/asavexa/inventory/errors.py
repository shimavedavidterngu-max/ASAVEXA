from ..security.errors import SecurityError


class InventoryError(SecurityError): status = 400
class InventoryNotFoundError(InventoryError): status = 404
class InventoryStateError(InventoryError): status = 409
class InventoryForbiddenError(InventoryError): status = 403
