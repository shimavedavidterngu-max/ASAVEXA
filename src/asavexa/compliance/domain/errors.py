"""Error hierarchy for Controls & Compliance. Named errors.py, matching
every other module's domain package convention."""


class AsavexaComplianceError(Exception):
    """Base class for all Controls & Compliance domain errors."""


class ControlDefinitionNotFoundError(AsavexaComplianceError):
    pass


class DuplicateControlCodeError(AsavexaComplianceError):
    """Raised when defining a control whose `code` already exists for
    this organisation — codes are how humans reference a control
    ("run ACC-001"), so they must be unique per org."""


class UnknownCheckKeyError(AsavexaComplianceError):
    """Raised when a ControlDefinition names a check_key that has no
    matching built-in check function (see services/service.py's
    _CHECK_REGISTRY)."""


class InactiveControlError(AsavexaComplianceError):
    """Raised when attempting to execute a deactivated ControlDefinition."""


class CannotCreateFindingForResultError(AsavexaComplianceError):
    """Raised by create_finding_from_execution when the execution's
    result is PASS or NOT_APPLICABLE — a finding documents a problem;
    manually opening one against a control that passed (or didn't
    apply) would be nonsensical. Only WARNING and REQUIRES_REVIEW are
    eligible for manual finding creation; FAIL already gets one
    automatically in execute_control."""


class ControlExecutionNotFoundError(AsavexaComplianceError):
    pass


class FindingNotFoundError(AsavexaComplianceError):
    pass


class FindingAlreadyExistsError(AsavexaComplianceError):
    """Raised when create_finding_from_execution is called on an
    execution that already has one — one execution produces at most one
    finding."""


class RemediationNotFoundError(AsavexaComplianceError):
    pass


class InvalidFindingStateError(AsavexaComplianceError):
    """Raised on an illegal Finding status transition."""


class InvalidRemediationStateError(AsavexaComplianceError):
    """Raised on an illegal Remediation status transition."""


class RemediationRequiredError(AsavexaComplianceError):
    """Raised when attempting to verify a remediation that is not yet
    COMPLETED — a finding cannot become CLOSED merely because someone
    says it's fixed in a comment; there must be a completed, then
    independently verified, Remediation record."""
