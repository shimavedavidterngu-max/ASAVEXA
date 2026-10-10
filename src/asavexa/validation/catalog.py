"""Static reference data for professional validation: the review pipeline, who may review, and what each stage looks at.

The checklists are prompts to help a reviewer plan their work. They are NOT exhaustive and NOT a standard; the reviewer's own
professional judgement and the applicable framework (IFRS, IFRS for SMEs, IPSAS, local GAAP, ISA, ...) always govern."""

STAGES = [
    {"id": "ACCOUNTING_TREATMENT", "label": "Accounting treatment", "order": 1,
     "question": "Are transactions recognised, measured and presented under the right framework and policies?",
     "specialisms": ["IFRS", "IPSAS", "LOCAL_GAAP", "TAX"],
     "checklist": ["Which framework applies (full IFRS, IFRS for SMEs, IPSAS, local GAAP) and is it applied consistently?",
                   "Chart of accounts mapping to statement lines; classification of assets, liabilities, revenue and expenses.",
                   "Revenue recognition, leases, provisions, financial instruments, foreign currency where relevant.",
                   "Tax treatment: VAT/GST, withholding, income tax and deferred tax where relevant.",
                   "Cut-off, period locking and reversal practice."]},
    {"id": "CONTROLS", "label": "Controls", "order": 2,
     "question": "Are the controls over recording and approval designed well and do they operate?",
     "specialisms": ["INTERNAL_AUDIT", "AUDIT"],
     "checklist": ["Segregation of duties (who creates, who approves, who posts).",
                   "Design of the built-in checks and whether failures are followed up and closed.",
                   "Approval limits, period close and reconciliation reviews.",
                   "Evidence that controls ran on time and who reviewed the results."]},
    {"id": "EVIDENCE", "label": "Evidence", "order": 3,
     "question": "Does each number trace to sufficient, appropriate, authentic evidence?",
     "specialisms": ["AUDIT", "INTERNAL_AUDIT"],
     "checklist": ["Sample transactions through to source documents; compare file fingerprints.",
                   "Proportion of evidence verified, missing, rejected or conflicting.",
                   "Whether verification was independent of the person who uploaded.",
                   "Retention, legal-hold and disposal practice."]},
    {"id": "REPORTING", "label": "Reporting", "order": 4,
     "question": "Do the statements agree to the ledger, and are presentation and disclosure appropriate?",
     "specialisms": ["IFRS", "IPSAS", "LOCAL_GAAP", "ACADEMIC"],
     "checklist": ["Trial balance agrees to the statements; comparatives and sign conventions.",
                   "Presentation and disclosure against the framework's requirements.",
                   "Reconciliations (bank and others) are complete and approved.",
                   "Management commentary and key figures are supported."]},
    {"id": "AUDIT_WORKFLOW", "label": "Audit workflow", "order": 5,
     "question": "Does the audit trail and review workflow support an external audit?",
     "specialisms": ["AUDIT", "INTERNAL_AUDIT"],
     "checklist": ["Completeness and readability of the audit trail for sampled items.",
                   "Maker-checker is enforced and visible; approvals are attributable.",
                   "Findings and remediation are tracked to closure.",
                   "Auditor access is read-only and scoped."]},
    {"id": "SECURITY", "label": "Security", "order": 6,
     "question": "Is the platform that holds the records adequately protected for this use?",
     "specialisms": ["CYBERSECURITY", "SOFTWARE_ARCHITECTURE"],
     "checklist": ["Access control, multi-factor sign-in and session management.",
                   "Encryption, key management and backup/restore evidence (ask for a restore drill result).",
                   "Tamper-evidence of the audit trail; the threat model and its residual risks.",
                   "Vendor risk, data location and privacy controls; independent penetration test status."]},
    {"id": "PROFESSIONAL_JUDGEMENT", "label": "Professional judgement", "order": 7,
     "question": "Are the significant judgements and estimates reasonable, documented and free from bias?",
     "specialisms": ["IFRS", "IPSAS", "AUDIT", "REGULATORY", "ACADEMIC"],
     "checklist": ["Significant estimates (impairment, provisions, expected credit losses, useful lives, going concern).",
                   "Management bias indicators and consistency with prior periods.",
                   "Sector or regulatory requirements specific to this entity (NGO, school, government, regulated sector).",
                   "Matters the software cannot decide: the reviewer records their own conclusion."]},
]

STAGE_IDS = [s["id"] for s in STAGES]

SPECIALISMS = {
    "IFRS": "IFRS / IFRS for SMEs", "IPSAS": "IPSAS (public sector)", "LOCAL_GAAP": "Local GAAP / national standards",
    "TAX": "Tax", "AUDIT": "External audit (ISA)", "INTERNAL_AUDIT": "Internal audit / risk",
    "CYBERSECURITY": "Cybersecurity", "SOFTWARE_ARCHITECTURE": "Software architecture", "DATA_SCIENCE": "Data science / analytics",
    "ACADEMIC": "Accounting academia", "REGULATORY": "Regulator / sector specialist",
}

BODIES = {"ICAN": "Institute of Chartered Accountants of Nigeria", "ACCA": "Association of Chartered Certified Accountants",
          "CPA": "Certified Public Accountant (state/national body)", "CA": "Chartered Accountant (other institute)",
          "CIMA": "Chartered Institute of Management Accountants", "IIA": "Institute of Internal Auditors",
          "ISACA": "ISACA (CISA/CISM)", "CISSP": "ISC2 (CISSP)", "OTHER": "Other professional or academic qualification"}

CONCLUSIONS = {
    "CONCURS": "Concurs: nothing found that needs to change.",
    "CONCURS_WITH_COMMENTS": "Concurs, with comments that management should consider.",
    "DISAGREES": "Disagrees: a significant matter is, in the reviewer's judgement, wrong or unsupported.",
    "UNABLE_TO_ASSESS": "Unable to assess: the reviewer could not form a conclusion (explain the limitation).",
}
SEVERITIES = ["CRITICAL", "MAJOR", "MINOR", "ADVISORY"]
RESPONSES = ["ACCEPTED", "DISPUTED", "REMEDIATED"]

DISCLAIMER = ("This is a record of professional review carried out by the named individuals, each on their own responsibility. It is not an audit "
              "opinion, not an assurance engagement report, and not a certification by ASAVEXA. ASAVEXA records what reviewers concluded and "
              "when; it cannot judge whether a conclusion is right. Professional credentials shown as 'declared' have not been checked by "
              "the platform.")
