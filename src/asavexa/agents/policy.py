"""The fixed policy for what an agent may do (Stage 7). Data, not code paths.

Three decisions, ordered by strictness: ALLOW < REQUIRE_APPROVAL < DENY.
An organisation may make a rule STRICTER (for example turn ALLOW into REQUIRE_APPROVAL) but can never loosen it, and a DENY action can never be
granted to any agent. Actions that need an independent human (posting, verifying, approving, changing permissions or standards, closing a period,
deleting) are DENY for every agent: a person must do them.
"""
ALLOW, REQUIRE_APPROVAL, DENY = "ALLOW", "REQUIRE_APPROVAL", "DENY"
ORDER = {ALLOW: 0, REQUIRE_APPROVAL: 1, DENY: 2}

ACTIONS = {
    "READ_LEDGER": ("Read the ledger and reports", ALLOW),
    "READ_EVIDENCE": ("Read evidence records", ALLOW),
    "RUN_EVIDENCE_REVIEW": ("Run an Evidence Review (read-only)", ALLOW),
    "DRAFT_JOURNAL": ("Prepare a draft journal for a person to review", REQUIRE_APPROVAL),
    "PROPOSE_MATCH": ("Propose a bank reconciliation match", REQUIRE_APPROVAL),
    "EXPORT_DATA": ("Export data out of ASAVEXA", REQUIRE_APPROVAL),
    "SEND_EXTERNAL_MESSAGE": ("Send a message outside the organisation", REQUIRE_APPROVAL),
    "POST_JOURNAL": ("Post a journal to the ledger", DENY),
    "VERIFY_EVIDENCE": ("Verify evidence", DENY),
    "APPROVE_ANYTHING": ("Approve any record, review or outcome", DENY),
    "CHANGE_PERMISSIONS": ("Change roles or permissions", DENY),
    "CHANGE_STANDARDS": ("Change the standards or policies in use", DENY),
    "CLOSE_PERIOD": ("Lock or close an accounting period", DENY),
    "DELETE_RECORDS": ("Delete records", DENY),
}
ALLOWED_PROVIDERS = ("RULE_BASED",)   # matches ai/provider.py: no outside model is approved


def base_decision(action: str) -> str:
    return ACTIONS[action][1]


def effective_decision(action: str, overrides: dict) -> str:
    """The organisation's override applies only if it is stricter than the built-in rule."""
    base = base_decision(action)
    o = (overrides or {}).get(action)
    return o if o in ORDER and ORDER[o] > ORDER[base] else base
