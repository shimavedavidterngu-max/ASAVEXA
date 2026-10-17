# Stage 41 — Approval workflows

A general approval workflow: an organisation defines named approval **policies**, and **requests** move through them step by step.

## What it does
- A policy has a name, a kind of request (payment, purchase, contract, expense, access, exception, other), a description and one to three steps. Each step has a label and the number of different people (1 to 5) who must approve it.
- A policy is proposed by one person and activated or rejected by a different person. It is never edited; an approver can retire it with a reason.
- A request is submitted against an active policy with a title, a reference code, an optional exact amount with its currency, and a description. The policy's steps are copied into the request, so retiring a policy never changes a request already under way.
- Steps run in order. A step passes when enough different people have approved it. After the last step the request is Approved. Anyone deciding can reject instead, with a reason.
- The person who submitted a request can never decide it, and nobody can decide the same request twice. Only the submitter can withdraw it.
- Amounts of different currencies are never added together. Overview flags requests that have waited too long (your own setting).

## What it does not do
- An approval is a record. Nothing is paid, bought, signed or changed anywhere else because of it, and no other part of ASAVEXA waits for it.
- It does not check that the approvers are the right people, or check amounts against any invoice, contract or payment system.

## Access
Routes under `/approvals`. Viewing needs `audit:read`; proposing policies, submitting and withdrawing need `approvals:prepare` (Owner, Administrator, Manager, Auditor); activating, rejecting or retiring policies, deciding request steps and the setting need `approvals:approve` (Owner, Approver, Manager). Audit logs reference numbers only.

Status: VERIFIED IN TEST ENVIRONMENT, NOT DEPLOYED.
