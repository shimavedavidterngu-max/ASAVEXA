"""Connects the health-centre service to the platform's audit trail. Only references and amounts are logged, never patient information (none is held)."""


def make_log(security):
    def log(action, actor, entity_id, org, reason=""):
        security.log(action, actor, entity_id, org_id=org, entity_type="HealthCentre", reason=reason)
    return log
