"""Connects the projects service to the platform's audit trail."""


def make_log(security):
    def log(action, actor, entity_id, org, reason=""):
        security.log(action, actor, entity_id, org_id=org, entity_type="Projects", reason=reason)
    return log
