"""Connects the validation service to the platform's audit trail."""


def make_log(security):
    def log(action, actor, entity_id, org, reason=""):
        kind = "ValidationReviewer" if ("REVIEWER" in action and "ASSIGNED" not in action) or "CREDENTIAL" in action else "ValidationEngagement"
        security.log(action, actor, entity_id, org_id=org, entity_type=kind, reason=reason)
    return log
