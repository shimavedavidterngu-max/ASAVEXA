# Evidence Vault — integration contract (not yet built)

When this module is implemented, it must integrate with the Accounting
Engine like this, and no other way:

- `Journal.evidence_ref` (already on the model in
  `accounting/domain/models.py`) is the pointer from a journal to its
  supporting evidence record. The Accounting Engine never validates the
  *content* of evidence — that is this module's job — it only stores
  the reference.
- Before a journal backing a material transaction is posted, the
  Evidence Vault should be asked "does evidence_ref point to a
  present/verified record?" and the caller (not the Accounting Engine)
  decides whether to block posting on a missing-evidence policy. The
  Accounting Engine's job stops at "is this journal balanced and is the
  period open" — evidence-completeness policy belongs here, not there
  (Blueprint Rule 19: separation of concerns).
- Every evidence item needs its own unique ID, hash, and status
  (present / missing / incomplete / duplicate / conflicting / expired /
  unverified / verified / rejected) per the blueprint's Evidence
  Verification Skill. An uploaded document is never automatically proof
  of a claim.
- Use the shared `AuditRepository` (currently in
  `accounting/repository/interfaces.py` — promote it to `asavexa/audit/`
  when this module lands, per the note in `asavexa/audit/__init__.py`)
  to log evidence uploads, verifications and deletions the same way the
  Accounting Engine logs journal postings.
