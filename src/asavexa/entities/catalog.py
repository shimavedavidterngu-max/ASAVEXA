"""What kind of organisation this is, as plain data (Stage 15).

Types and subtypes are a starting list, not a rigid global hierarchy: an organisation can also describe itself in its own words (a custom subtype).
Choosing a type changes only (a) the suggested set of workspaces and (b) which menu items are shown. It never changes anyone's permissions, and it
does not decide an accounting or legal framework: country, currency, fiscal year and reporting framework stay in the organisation profile.

`workspaces` are ids from `asavexa.workspaces.WORKSPACES`. A type never lists a workspace that does not exist; a test enforces that."""
from typing import Dict, List

CORE = ("analysis",)      # offered to every kind of organisation as a starting point

# code -> (label, legacy onboarding category, subtypes [(code, label)], suggested workspaces)
_T = [
    ("INDIVIDUAL", "Individuals and professional practices", "Individual professional",
     [("SOLE_TRADER", "Sole trader"), ("FREELANCER", "Freelancer or consultant"), ("PRACTICE", "Professional practice")], ["analysis", "tax"]),
    ("BUSINESS", "Businesses", "Business or SME",
     [("STARTUP", "Startup, incubator or accelerator"), ("SME", "Small or medium enterprise"), ("CORPORATION", "Corporation"), ("SUBSIDIARY", "Subsidiary"),
      ("HOLDING", "Holding company or group"), ("FRANCHISE", "Franchise or multi-location business"), ("SUPPLIER", "Supplier, contractor or service provider")],
     ["analysis", "tax", "grc", "bizdev", "cyber", "itaudit", "resilience", "aigov", "treasury", "procurement", "fpa"]),
    ("INDUSTRY", "Industry and commerce", "Business or SME",
     [("CONSTRUCTION", "Construction, property or real estate"), ("MANUFACTURING", "Manufacturing or industrial"), ("AGRICULTURE", "Agriculture or food processing"),
      ("RETAIL", "Retail, wholesale, e-commerce or marketplace"), ("LOGISTICS", "Transport, freight, aviation or logistics"), ("TECHNOLOGY", "Telecoms, cloud or technology"),
      ("ENERGY", "Energy, mining or natural resources"), ("HOSPITALITY", "Hospitality, restaurants or tourism")], ["analysis", "tax", "grc", "cyber", "itaudit", "resilience", "aigov", "treasury", "procurement", "fpa"]),
    ("PROFESSIONAL_FIRM", "Accounting, legal and advisory firms", "Accounting or audit firm",
     [("ACCOUNTING_FIRM", "Accounting, audit or advisory firm"), ("LAW_FIRM", "Law firm or corporate-service provider"), ("CONSULTING", "Consulting, engineering or project-management firm")],
     ["analysis", "tax", "forensic", "grc"]),
    ("FINANCIAL", "Financial institutions", "Business or SME",
     [("BANK", "Commercial, microfinance or digital bank"), ("PAYMENTS", "Payment provider or processor"), ("FINTECH", "Fintech or embedded finance"), ("INSURER", "Insurer or reinsurer"),
      ("FUND", "Asset manager or investment fund"), ("CREDIT_UNION", "Cooperative, credit union or microfinance institution"), ("BROKER", "Stockbroker, investment adviser or market operator"),
      ("MORTGAGE", "Mortgage or housing-finance lender"), ("CREDIT_BUREAU", "Credit bureau or credit-risk provider")], ["analysis", "grc", "forensic", "cyber", "itaudit", "resilience", "aigov", "treasury", "procurement", "fpa", "fincrime"]),
    ("GOVERNMENT", "Government and public bodies", "Government or public institution",
     [("MINISTRY", "Ministry, department or agency"), ("LOCAL_GOVERNMENT", "Local government, municipality or regional authority"), ("PROCUREMENT_UNIT", "Public procurement authority or project unit"),
      ("STATE_ENTERPRISE", "State-owned enterprise or public utility"), ("STATUTORY_FUND", "Pension body, social-security body or statutory fund")], ["public_finance", "analysis", "grc", "forensic", "treasury", "procurement", "fpa", "fincrime"]),
    ("NONPROFIT", "Nonprofits and mission-driven organisations", "NGO or nonprofit",
     [("CHARITY", "Charity, foundation or philanthropic organisation"), ("HUMANITARIAN", "International development or humanitarian agency"), ("COMMUNITY", "Community-based organisation or cooperative"),
      ("MEMBERSHIP", "Professional association, trade body or membership organisation"), ("SPORTS", "Sports club, league, federation or event organiser"),
      ("CULTURE", "Cultural institution, museum, library or arts organisation"), ("SOCIAL_ENTERPRISE", "Social enterprise or impact-investment organisation"),
      ("CLIMATE", "Community development or climate-project organisation")], ["public_finance", "analysis", "grc", "treasury", "procurement", "fpa"]),
    ("FAITH", "Faith-based organisations", "Church or faith-based organisation",
     [("CONGREGATION", "Church, mosque, temple or congregation"), ("DENOMINATION", "Denomination, diocese or religious network"), ("FAITH_CHARITY", "Faith-based charity")], ["public_finance", "analysis", "grc"]),
    ("EDUCATION", "Education and research", "University or educational institution",
     [("SCHOOL", "School"), ("COLLEGE", "College, university or vocational institute"), ("RESEARCH", "Research institution or policy institute"),
      ("SCHOLARSHIP", "Examination board, education foundation or scholarship programme")], ["public_finance", "analysis", "grc", "treasury", "procurement", "fpa"]),
    ("HEALTH", "Health and care", "Health centre or healthcare facility",
     [("HOSPITAL", "Hospital, clinic, health centre or laboratory"), ("PHARMACY", "Pharmacy, medical supplier or healthcare distributor"), ("HEALTH_INSURER", "Health insurer or healthcare administrator")],
     ["health", "analysis", "grc", "treasury", "procurement", "fpa"]),
    ("ESSENTIAL_SERVICES", "Essential and emergency services", "Government or public institution",
     [("UTILITY_PROJECT", "Water, sanitation, housing or community-service provider"), ("EMERGENCY", "Emergency-response or disaster-relief organisation")], ["public_finance", "analysis", "grc"]),
    ("ASSURANCE_PROVIDER", "Assurance, regulators and verifiers", "Accounting or audit firm",
     [("REGULATOR", "Regulator or supervisory authority"), ("VERIFIER", "Independent verification or assurance provider"), ("CERTIFIER", "Accreditation, certification or inspection body")],
     ["analysis", "forensic", "grc"]),
    ("FUNDER", "Funders and investors", "Business or SME",
     [("BANK_FUNDER", "Bank or grantmaker"), ("DONOR", "Donor or institutional funder"), ("INVESTOR", "Investor, lender or development-finance institution"),
      ("CREDITOR", "Creditor, debt administrator or restructuring stakeholder")], ["analysis", "grc"]),
]

ENTITY_TYPES: List[dict] = [
    {"code": c, "label": label, "legacy_category": legacy, "subtypes": [{"code": sc, "label": sl} for sc, sl in subs], "suggested_workspaces": list(ws)}
    for c, label, legacy, subs, ws in _T
]
BY_CODE: Dict[str, dict] = {t["code"]: t for t in ENTITY_TYPES}
LEGACY_TO_TYPE = {}
for _t in ENTITY_TYPES:
    LEGACY_TO_TYPE.setdefault(_t["legacy_category"], _t["code"])

NOTE = ("These lists are a starting point. Choosing a type changes which workspaces are suggested and shown in the menu. It does not change anyone's access, "
        "it does not choose an accounting or legal framework, and it makes no claim that the organisation complies with anything.")
