class AsavexaStandardsError(Exception):
    """Base class for Standards Configuration Engine errors."""


class UnknownJurisdictionError(AsavexaStandardsError):
    pass


class UnknownEntityTypeError(AsavexaStandardsError):
    pass


class UnknownFrameworkError(AsavexaStandardsError):
    pass


class UnknownPolicyError(AsavexaStandardsError):
    pass


class InvalidPolicyChoiceError(AsavexaStandardsError):
    pass
