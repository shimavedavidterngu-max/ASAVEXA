# Stage 7: Agent registry and policy decisions

Status: **VERIFIED IN TEST ENVIRONMENT** (17 service and router tests, 26 screen tests, a real-browser journey). Not deployed. Nothing in ASAVEXA runs agents on its own today; this is the control point they must pass through.

Page: **Agents**. An agent is registered with a name, purpose, owner and a short list of actions it may ask to perform. Only `RULE_BASED` agents are accepted (an outside model needs its own security and cost review first).

- Decisions per request: ALLOW (low risk), REQUIRE_APPROVAL (a person must approve; one use; expires after 24 hours), DENY.
- Built-in policy (`agents/policy.py`): reading and running reviews is ALLOW; drafting a journal, proposing a match, exporting data and external messages are REQUIRE_APPROVAL; posting, verifying, approving, changing permissions or standards, closing a period and deleting are DENY for every agent and cannot be granted.
- An organisation can make a rule stricter, never looser.
- An agent is activated by someone other than who proposed it. A request is approved or rejected by someone other than who made it. Rejection needs a reason. A suspended or retired agent cannot proceed, even with an approved request.
- Every decision is stored and every step audited (`AGENT_*`).
- Permissions: view `audit:read`; propose, ask, confirm `grc:prepare`; activate, suspend, retire, tighten policy, approve or reject `grc:approve`.

The registry only decides; it never runs the action.
