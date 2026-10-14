from ..security.errors import SecurityError


class TreasuryError(SecurityError): status = 400
class TreasuryNotFoundError(TreasuryError): status = 404
class TreasuryStateError(TreasuryError): status = 409
class TreasuryForbiddenError(TreasuryError): status = 403
