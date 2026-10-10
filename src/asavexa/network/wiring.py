"""Connects the network service to the platform's audit trail."""


def make_log(security):
    def log(action, actor, entity_id, org, reason=""):
        kind = "NetworkProfile" if action == "NETWORK_PROFILE_SET" else "NetworkInvite" if "INVITE" in action else "NetworkConnection"
        security.log(action, actor, entity_id, org_id=org, entity_type=kind, reason=reason)
    return log
