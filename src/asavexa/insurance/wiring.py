"""Connects the insurance service to the platform's audit trail."""


def make_log(security):
    def log(action, actor, entity_id, org, reason=""):
        security.log(action, actor, entity_id, org_id=org, entity_type="Insurance", reason=reason)
    return log
