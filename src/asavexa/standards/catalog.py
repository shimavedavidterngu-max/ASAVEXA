"""The standards catalog — data only.

IMPORTANT (stated in the product too): every jurisdiction rule below is a
SUGGESTED DEFAULT, not legal advice. Regulators change requirements; an
organisation must confirm its framework with its local regulator or a
qualified accountant. Each rule carries a `confidence`:
  "established"  - a widely known, stable requirement
  "confirm"      - commonly applied, but depends on size/sector/law that
                   the organisation should confirm
Extending the engine to a new country or framework means adding data
here, not changing engine code.
"""

FRAMEWORKS = {
    "IFRS": {"name": "IFRS (full)", "description": "IFRS Accounting Standards as issued by the IASB."},
    "IFRS_FOR_SMES": {"name": "IFRS for SMEs", "description": "Simplified IFRS for small and medium-sized entities without public accountability."},
    "US_GAAP": {"name": "US GAAP", "description": "United States Generally Accepted Accounting Principles (FASB ASC)."},
    "IPSAS": {"name": "IPSAS (accrual)", "description": "International Public Sector Accounting Standards, accrual basis."},
    "LOCAL_GAAP": {"name": "Local GAAP / national standards", "description": "A national framework (for example FRS 102, ASPE, Ind AS, GRAP)."},
    "NONPROFIT": {"name": "Non-profit / fund reporting", "description": "Sector framework with fund and restriction reporting."},
    "CASH_BASIS": {"name": "Cash basis", "description": "Receipts and payments reporting; no accruals."},
    "OTHER": {"name": "Other framework", "description": "A framework not listed; configure policies manually."},
}

JURISDICTIONS = {
    "NG": "Nigeria", "GH": "Ghana", "KE": "Kenya", "ZA": "South Africa",
    "GB": "United Kingdom", "US": "United States", "CA": "Canada",
    "AU": "Australia", "IN": "India", "OTHER": "Other jurisdiction",
}

ENTITY_TYPES = {
    "PUBLIC_INTEREST": "Listed company, financial institution or other public-interest entity",
    "PRIVATE_COMPANY": "Private company (larger, not an SME)",
    "SME": "Small or medium-sized entity",
    "MICRO": "Micro-entity or sole trader",
    "NONPROFIT": "Non-profit organisation, NGO, charity or school",
    "PUBLIC_SECTOR": "Government or public-sector body",
}

# (jurisdiction, entity_type) -> (default, alternatives, rationale, confidence)
# jurisdiction "*" is the generic fallback used when no specific rule exists.
_E, _C = "established", "confirm"
RULES = {
    # ---- generic fallbacks
    ("*", "PUBLIC_INTEREST"): ("IFRS", ["US_GAAP", "LOCAL_GAAP"], "Public-interest entities are most commonly required to use full IFRS.", _C),
    ("*", "PRIVATE_COMPANY"): ("IFRS", ["IFRS_FOR_SMES", "LOCAL_GAAP"], "Larger private companies commonly use IFRS or a national framework.", _C),
    ("*", "SME"): ("IFRS_FOR_SMES", ["LOCAL_GAAP", "IFRS"], "IFRS for SMEs is designed for entities without public accountability.", _C),
    ("*", "MICRO"): ("IFRS_FOR_SMES", ["CASH_BASIS", "LOCAL_GAAP"], "Very small entities often use a simplified or cash-based basis where the law allows.", _C),
    ("*", "NONPROFIT"): ("IFRS_FOR_SMES", ["NONPROFIT", "IFRS", "LOCAL_GAAP"], "Non-profits commonly use IFRS for SMEs or a sector framework with fund reporting.", _C),
    ("*", "PUBLIC_SECTOR"): ("IPSAS", ["CASH_BASIS", "LOCAL_GAAP"], "IPSAS is the international accrual standard for public-sector bodies.", _C),
    # ---- Nigeria
    ("NG", "PUBLIC_INTEREST"): ("IFRS", [], "The Financial Reporting Council of Nigeria requires IFRS for public-interest entities.", _E),
    ("NG", "PRIVATE_COMPANY"): ("IFRS", ["IFRS_FOR_SMES"], "Companies are generally expected to prepare IFRS-based statements; IFRS for SMEs is available to qualifying entities.", _C),
    ("NG", "SME"): ("IFRS_FOR_SMES", ["IFRS"], "IFRS for SMEs is the framework for small and medium entities without public accountability.", _C),
    ("NG", "MICRO"): ("IFRS_FOR_SMES", ["CASH_BASIS"], "Confirm the exemptions available to small companies under company law.", _C),
    ("NG", "NONPROFIT"): ("IFRS_FOR_SMES", ["NONPROFIT", "IFRS"], "NGOs commonly use IFRS for SMEs; donors may also require fund-based reporting.", _C),
    ("NG", "PUBLIC_SECTOR"): ("IPSAS", ["CASH_BASIS"], "Nigerian federal and many state governments have adopted IPSAS (accrual).", _C),
    # ---- Ghana, Kenya (IFRS and IFRS for SMEs adopted nationally)
    ("GH", "PUBLIC_INTEREST"): ("IFRS", [], "Ghana requires IFRS for public-interest entities.", _E),
    ("GH", "PRIVATE_COMPANY"): ("IFRS", ["IFRS_FOR_SMES"], "IFRS, with IFRS for SMEs available to qualifying entities.", _C),
    ("GH", "SME"): ("IFRS_FOR_SMES", ["IFRS"], "IFRS for SMEs is adopted for entities without public accountability.", _C),
    ("GH", "PUBLIC_SECTOR"): ("IPSAS", ["CASH_BASIS"], "Ghana is implementing accrual IPSAS in the public sector.", _C),
    ("KE", "PUBLIC_INTEREST"): ("IFRS", [], "Kenya requires IFRS for public-interest entities.", _E),
    ("KE", "PRIVATE_COMPANY"): ("IFRS", ["IFRS_FOR_SMES"], "IFRS, with IFRS for SMEs available to qualifying entities.", _C),
    ("KE", "SME"): ("IFRS_FOR_SMES", ["IFRS"], "IFRS for SMEs is adopted for entities without public accountability.", _C),
    ("KE", "PUBLIC_SECTOR"): ("IPSAS", ["CASH_BASIS"], "Kenya's national and county governments use IPSAS (accrual or cash basis).", _C),
    # ---- South Africa
    ("ZA", "PUBLIC_INTEREST"): ("IFRS", [], "Listed companies must use IFRS.", _E),
    ("ZA", "PRIVATE_COMPANY"): ("IFRS", ["IFRS_FOR_SMES"], "IFRS or IFRS for SMEs depending on the company's public-interest score.", _C),
    ("ZA", "SME"): ("IFRS_FOR_SMES", ["IFRS"], "IFRS for SMEs has been adopted nationally.", _C),
    ("ZA", "PUBLIC_SECTOR"): ("LOCAL_GAAP", ["IPSAS"], "Public bodies use GRAP, South Africa's national public-sector standards.", _E),
    # ---- United Kingdom
    ("GB", "PUBLIC_INTEREST"): ("IFRS", [], "UK-adopted international accounting standards apply to listed groups.", _E),
    ("GB", "PRIVATE_COMPANY"): ("LOCAL_GAAP", ["IFRS"], "Most private companies use FRS 102; UK-adopted IFRS is an option.", _E),
    ("GB", "SME"): ("LOCAL_GAAP", ["IFRS_FOR_SMES", "IFRS"], "FRS 102 (or FRS 105 for micro-entities) is the usual framework.", _E),
    ("GB", "MICRO"): ("LOCAL_GAAP", ["CASH_BASIS"], "FRS 105 is designed for micro-entities.", _E),
    ("GB", "NONPROFIT"): ("LOCAL_GAAP", ["IFRS"], "Charities generally follow FRS 102 with the Charities SORP.", _E),
    ("GB", "PUBLIC_SECTOR"): ("IPSAS", ["LOCAL_GAAP", "IFRS"], "UK government bodies follow an IFRS-based manual; IPSAS is a close international equivalent.", _C),
    # ---- United States
    ("US", "PUBLIC_INTEREST"): ("US_GAAP", ["IFRS"], "SEC registrants report under US GAAP.", _E),
    ("US", "PRIVATE_COMPANY"): ("US_GAAP", [], "US GAAP is the standard framework.", _E),
    ("US", "SME"): ("US_GAAP", ["CASH_BASIS"], "US GAAP; small businesses may use a tax or cash basis where lenders and law allow.", _C),
    ("US", "MICRO"): ("CASH_BASIS", ["US_GAAP"], "Very small US businesses often use a cash or tax basis.", _C),
    ("US", "NONPROFIT"): ("US_GAAP", ["NONPROFIT"], "US GAAP with ASC 958 not-for-profit presentation.", _E),
    ("US", "PUBLIC_SECTOR"): ("US_GAAP", ["IPSAS"], "State and local governments follow GASB and the federal government FASAB, both part of US GAAP.", _C),
    # ---- Canada
    ("CA", "PUBLIC_INTEREST"): ("IFRS", [], "Publicly accountable enterprises use IFRS.", _E),
    ("CA", "PRIVATE_COMPANY"): ("LOCAL_GAAP", ["IFRS"], "Most private enterprises use ASPE; IFRS is an option.", _E),
    ("CA", "SME"): ("LOCAL_GAAP", ["IFRS_FOR_SMES"], "ASPE is the usual framework.", _E),
    ("CA", "NONPROFIT"): ("LOCAL_GAAP", ["IFRS"], "Standards for not-for-profit organisations (ASNPO) or IFRS.", _E),
    ("CA", "PUBLIC_SECTOR"): ("LOCAL_GAAP", ["IPSAS"], "Public Sector Accounting Standards (PSAS).", _E),
    # ---- Australia
    ("AU", "PUBLIC_INTEREST"): ("IFRS", [], "Australian Accounting Standards are IFRS-equivalent.", _E),
    ("AU", "PRIVATE_COMPANY"): ("LOCAL_GAAP", ["IFRS"], "Australian Accounting Standards (reduced disclosure available for some entities).", _C),
    ("AU", "SME"): ("LOCAL_GAAP", ["IFRS_FOR_SMES"], "Australian Accounting Standards, with reduced disclosure where eligible.", _C),
    ("AU", "NONPROFIT"): ("LOCAL_GAAP", ["IFRS_FOR_SMES"], "Australian Accounting Standards; ACNC reporting tiers apply to charities.", _C),
    ("AU", "PUBLIC_SECTOR"): ("LOCAL_GAAP", ["IPSAS"], "Australian Accounting Standards as applied to the public sector.", _C),
    # ---- India
    ("IN", "PUBLIC_INTEREST"): ("LOCAL_GAAP", ["IFRS"], "Ind AS, which is converged with IFRS, applies to listed and larger companies.", _E),
    ("IN", "PRIVATE_COMPANY"): ("LOCAL_GAAP", ["IFRS"], "Ind AS or Accounting Standards depending on net worth thresholds.", _C),
    ("IN", "SME"): ("LOCAL_GAAP", ["IFRS_FOR_SMES"], "Accounting Standards (AS) for small and medium companies.", _C),
    ("IN", "NONPROFIT"): ("LOCAL_GAAP", ["NONPROFIT"], "Accounting Standards with ICAI guidance for non-profit entities.", _C),
    ("IN", "PUBLIC_SECTOR"): ("LOCAL_GAAP", ["IPSAS"], "Government accounting standards; IPSAS is an international reference.", _C),
}

# Policy topics. options_by_framework[fw] = {"options": [...], "default": x, "locked": bool}
# locked=True means the framework mandates that single treatment.
OPTION_LABELS = {
    "FIFO": "First-in, first-out (FIFO)",
    "WEIGHTED_AVERAGE": "Weighted average cost",
    "SPECIFIC_IDENTIFICATION": "Specific identification",
    "LIFO": "Last-in, first-out (LIFO)",
    "COST_MODEL": "Cost model (cost less depreciation and impairment)",
    "REVALUATION_MODEL": "Revaluation model (fair value less depreciation)",
    "STRAIGHT_LINE": "Straight-line",
    "REDUCING_BALANCE": "Reducing balance",
    "UNITS_OF_PRODUCTION": "Units of production",
    "EXPENSE_ALL": "Expense all development costs as incurred",
    "CAPITALISE_WHEN_CRITERIA_MET": "Capitalise when recognition criteria are met",
    "EXPENSE": "Expense borrowing costs as incurred",
    "CAPITALISE_QUALIFYING": "Capitalise costs on qualifying assets",
    "ECL_MODEL": "Expected credit loss model",
    "INCURRED_LOSS": "Incurred loss / specific provisions",
    "RIGHT_OF_USE": "Recognise right-of-use assets and lease liabilities (lessee)",
    "OPERATING_FINANCE_SPLIT": "Classify as operating or finance leases",
    "RECOGNISE_WHEN_CONDITIONS_MET": "Recognise when conditions are met",
    "RECOGNISE_ON_RECEIPT": "Recognise on receipt",
    "TRACK_FUNDS": "Track restricted and unrestricted funds separately",
    "TEMPORARY_DIFFERENCES": "Deferred tax on temporary differences",
    "NOT_APPLICABLE": "Not applicable",
}


def _opt(options, default=None, locked=False):
    return {"options": options, "default": default or options[0], "locked": locked}


_ALL_BUT_CASH = ["IFRS", "IFRS_FOR_SMES", "US_GAAP", "IPSAS", "LOCAL_GAAP", "NONPROFIT", "OTHER"]


def _spread(spec, frameworks=None):
    return {fw: dict(spec) for fw in (frameworks or _ALL_BUT_CASH)}


POLICIES = [
    {
        "code": "INVENTORY_COSTING", "name": "Inventory costing",
        "description": "How the cost of inventory sold is determined.",
        "by_framework": {
            **_spread(_opt(["FIFO", "WEIGHTED_AVERAGE", "SPECIFIC_IDENTIFICATION"], "WEIGHTED_AVERAGE"),
                      ["IFRS", "IFRS_FOR_SMES", "IPSAS", "NONPROFIT"]),
            "US_GAAP": _opt(["FIFO", "WEIGHTED_AVERAGE", "SPECIFIC_IDENTIFICATION", "LIFO"], "FIFO"),
            "LOCAL_GAAP": _opt(["FIFO", "WEIGHTED_AVERAGE", "SPECIFIC_IDENTIFICATION"], "FIFO"),
            "OTHER": _opt(["FIFO", "WEIGHTED_AVERAGE", "SPECIFIC_IDENTIFICATION", "LIFO"], "FIFO"),
        },
        "note": "LIFO is not permitted under IFRS, IFRS for SMEs or IPSAS.",
    },
    {
        "code": "PPE_MEASUREMENT", "name": "Property, plant and equipment measurement",
        "description": "Measurement basis after initial recognition.",
        "by_framework": {
            **_spread(_opt(["COST_MODEL", "REVALUATION_MODEL"], "COST_MODEL"), ["IFRS", "IFRS_FOR_SMES", "IPSAS", "LOCAL_GAAP", "OTHER"]),
            "US_GAAP": _opt(["COST_MODEL"], "COST_MODEL", locked=True),
            "NONPROFIT": _opt(["COST_MODEL"], "COST_MODEL", locked=True),
        },
        "note": "US GAAP does not allow upward revaluation of property, plant and equipment.",
    },
    {
        "code": "DEPRECIATION_METHOD", "name": "Depreciation method",
        "description": "Pattern in which an asset's benefits are consumed.",
        "by_framework": _spread(_opt(["STRAIGHT_LINE", "REDUCING_BALANCE", "UNITS_OF_PRODUCTION"], "STRAIGHT_LINE")),
        "note": "Choose the method that best reflects the pattern of consumption.",
    },
    {
        "code": "DEVELOPMENT_COSTS", "name": "Development costs",
        "description": "Treatment of internally generated development expenditure.",
        "by_framework": {
            "IFRS": _opt(["CAPITALISE_WHEN_CRITERIA_MET"], locked=True),
            "IPSAS": _opt(["CAPITALISE_WHEN_CRITERIA_MET"], locked=True),
            "IFRS_FOR_SMES": _opt(["EXPENSE_ALL", "CAPITALISE_WHEN_CRITERIA_MET"], "EXPENSE_ALL"),
            "US_GAAP": _opt(["EXPENSE_ALL"], locked=True),
            "LOCAL_GAAP": _opt(["EXPENSE_ALL", "CAPITALISE_WHEN_CRITERIA_MET"], "EXPENSE_ALL"),
            "NONPROFIT": _opt(["EXPENSE_ALL"], locked=True),
            "OTHER": _opt(["EXPENSE_ALL", "CAPITALISE_WHEN_CRITERIA_MET"], "EXPENSE_ALL"),
        },
        "note": "IFRS requires capitalisation once the criteria are met; US GAAP generally expenses development costs.",
    },
    {
        "code": "BORROWING_COSTS", "name": "Borrowing costs",
        "description": "Interest on funds borrowed to build or acquire qualifying assets.",
        "by_framework": {
            "IFRS": _opt(["CAPITALISE_QUALIFYING"], locked=True),
            "US_GAAP": _opt(["CAPITALISE_QUALIFYING"], locked=True),
            "IFRS_FOR_SMES": _opt(["EXPENSE"], locked=True),
            "IPSAS": _opt(["EXPENSE", "CAPITALISE_QUALIFYING"], "EXPENSE"),
            "LOCAL_GAAP": _opt(["EXPENSE", "CAPITALISE_QUALIFYING"], "EXPENSE"),
            "NONPROFIT": _opt(["EXPENSE", "CAPITALISE_QUALIFYING"], "EXPENSE"),
            "OTHER": _opt(["EXPENSE", "CAPITALISE_QUALIFYING"], "EXPENSE"),
        },
        "note": "IFRS for SMEs requires borrowing costs to be expensed.",
    },
    {
        "code": "RECEIVABLES_IMPAIRMENT", "name": "Impairment of receivables",
        "description": "How credit losses on receivables are estimated.",
        "by_framework": {
            "IFRS": _opt(["ECL_MODEL"], locked=True),
            "US_GAAP": _opt(["ECL_MODEL"], locked=True),
            "IPSAS": _opt(["ECL_MODEL"], locked=True),
            "IFRS_FOR_SMES": _opt(["INCURRED_LOSS"], locked=True),
            "LOCAL_GAAP": _opt(["INCURRED_LOSS", "ECL_MODEL"], "INCURRED_LOSS"),
            "NONPROFIT": _opt(["INCURRED_LOSS", "ECL_MODEL"], "INCURRED_LOSS"),
            "OTHER": _opt(["INCURRED_LOSS", "ECL_MODEL"], "INCURRED_LOSS"),
        },
        "note": "Expected-loss models (IFRS 9, CECL) require forward-looking estimates.",
    },
    {
        "code": "LEASES", "name": "Leases (as lessee)",
        "description": "Balance-sheet treatment of leases.",
        "by_framework": {
            "IFRS": _opt(["RIGHT_OF_USE"], locked=True),
            "US_GAAP": _opt(["RIGHT_OF_USE"], locked=True),
            "IPSAS": _opt(["RIGHT_OF_USE"], locked=True),
            "IFRS_FOR_SMES": _opt(["OPERATING_FINANCE_SPLIT"], locked=True),
            "LOCAL_GAAP": _opt(["OPERATING_FINANCE_SPLIT", "RIGHT_OF_USE"], "OPERATING_FINANCE_SPLIT"),
            "NONPROFIT": _opt(["OPERATING_FINANCE_SPLIT", "RIGHT_OF_USE"], "OPERATING_FINANCE_SPLIT"),
            "OTHER": _opt(["OPERATING_FINANCE_SPLIT", "RIGHT_OF_USE"], "OPERATING_FINANCE_SPLIT"),
        },
        "note": "IFRS 16, ASC 842 and IPSAS 43 put most leases on the balance sheet.",
    },
    {
        "code": "DEFERRED_TAX", "name": "Deferred tax",
        "description": "Recognition of tax effects of timing differences.",
        "by_framework": {
            **_spread(_opt(["TEMPORARY_DIFFERENCES"], locked=True), ["IFRS", "IFRS_FOR_SMES", "US_GAAP"]),
            "LOCAL_GAAP": _opt(["TEMPORARY_DIFFERENCES", "NOT_APPLICABLE"], "TEMPORARY_DIFFERENCES"),
            "NONPROFIT": _opt(["NOT_APPLICABLE"], locked=True),
            "IPSAS": _opt(["NOT_APPLICABLE"], locked=True),
            "OTHER": _opt(["TEMPORARY_DIFFERENCES", "NOT_APPLICABLE"], "TEMPORARY_DIFFERENCES"),
        },
        "note": "Tax-exempt and public-sector bodies usually do not account for deferred tax.",
    },
    {
        "code": "GRANTS_AND_DONATIONS", "name": "Grants and donations",
        "description": "When grant and donation income is recognised.",
        "by_framework": {
            "NONPROFIT": _opt(["RECOGNISE_WHEN_CONDITIONS_MET", "RECOGNISE_ON_RECEIPT"], "RECOGNISE_WHEN_CONDITIONS_MET"),
            "IPSAS": _opt(["RECOGNISE_WHEN_CONDITIONS_MET"], locked=True),
            "IFRS": _opt(["RECOGNISE_WHEN_CONDITIONS_MET"], locked=True),
            "IFRS_FOR_SMES": _opt(["RECOGNISE_WHEN_CONDITIONS_MET"], locked=True),
            "LOCAL_GAAP": _opt(["RECOGNISE_WHEN_CONDITIONS_MET", "RECOGNISE_ON_RECEIPT"], "RECOGNISE_WHEN_CONDITIONS_MET"),
            "US_GAAP": _opt(["RECOGNISE_WHEN_CONDITIONS_MET"], locked=True),
            "OTHER": _opt(["RECOGNISE_WHEN_CONDITIONS_MET", "RECOGNISE_ON_RECEIPT"], "RECOGNISE_WHEN_CONDITIONS_MET"),
        },
        "note": "Grants with performance conditions are recognised as the conditions are met.",
    },
    {
        "code": "FUND_ACCOUNTING", "name": "Fund accounting",
        "description": "Separating restricted and unrestricted resources.",
        "by_framework": {"NONPROFIT": _opt(["TRACK_FUNDS"], locked=True)},
        "note": "Required for sector reporting where donors restrict how funds may be used.",
    },
]

# Reporting requirements. report_key = the ASAVEXA report that supports it
# today ("trial-balance", "income-statement", "balance-sheet", "general-ledger")
# or None when ASAVEXA cannot yet produce it.
def _req(code, name, description, report_key=None, mandatory=True, entity_types=None):
    return {"code": code, "name": name, "description": description, "report_key": report_key,
            "mandatory": mandatory, "entity_types": entity_types}


_TB = _req("TRIAL_BALANCE", "Trial balance", "Supporting schedule proving debits equal credits.", "trial-balance", mandatory=False)
_GL = _req("GENERAL_LEDGER", "General ledger", "Account-level detail supporting every figure.", "general-ledger", mandatory=False)

REQUIREMENTS = {
    "IFRS": [
        _req("SFP", "Statement of financial position", "Assets, liabilities and equity at the reporting date.", "balance-sheet"),
        _req("PL_OCI", "Statement of profit or loss and other comprehensive income", "Performance for the period.", "income-statement"),
        _req("SOCE", "Statement of changes in equity", "Movements in each component of equity."),
        _req("SCF", "Statement of cash flows", "Cash movements from operating, investing and financing activities."),
        _req("NOTES", "Notes, including significant accounting policies", "Policies and explanatory information."),
        _req("COMPARATIVES", "Comparative information", "Prior-period figures for every amount presented."),
        _req("EPS", "Earnings per share", "Required for entities with publicly traded shares.", mandatory=True, entity_types=["PUBLIC_INTEREST"]),
        _req("SEGMENTS", "Operating segments", "Required for entities with publicly traded securities.", mandatory=True, entity_types=["PUBLIC_INTEREST"]),
        _req("RELATED_PARTIES", "Related-party disclosures", "Transactions and balances with related parties."),
        _TB, _GL,
    ],
    "IFRS_FOR_SMES": [
        _req("SFP", "Statement of financial position", "Assets, liabilities and equity at the reporting date.", "balance-sheet"),
        _req("PL", "Statement of comprehensive income (or income statement)", "Performance for the period.", "income-statement"),
        _req("SOCE", "Statement of changes in equity", "Or a statement of income and retained earnings where permitted."),
        _req("SCF", "Statement of cash flows", "Cash movements for the period."),
        _req("NOTES", "Notes, including significant accounting policies", "Policies and explanatory information."),
        _req("COMPARATIVES", "Comparative information", "Prior-period figures."),
        _TB, _GL,
    ],
    "US_GAAP": [
        _req("BS", "Balance sheet", "Assets, liabilities and equity at the reporting date.", "balance-sheet"),
        _req("IS", "Income statement (statement of operations)", "Performance for the period.", "income-statement"),
        _req("CI", "Statement of comprehensive income", "Required where other comprehensive income exists."),
        _req("SE", "Statement of stockholders' equity", "Movements in equity."),
        _req("SCF", "Statement of cash flows", "Cash movements for the period."),
        _req("NOTES", "Notes to the financial statements", "Policies and disclosures."),
        _req("EPS", "Earnings per share", "Required for public entities.", entity_types=["PUBLIC_INTEREST"]),
        _TB, _GL,
    ],
    "IPSAS": [
        _req("SFP", "Statement of financial position", "Assets, liabilities and net assets/equity.", "balance-sheet"),
        _req("SFPERF", "Statement of financial performance", "Revenue and expenses for the period.", "income-statement"),
        _req("SCNA", "Statement of changes in net assets/equity", "Movements in net assets."),
        _req("SCF", "Cash flow statement", "Cash movements for the period."),
        _req("BUDGET", "Comparison of budget and actual amounts", "Required where the approved budget is made publicly available."),
        _req("NOTES", "Notes, including significant accounting policies", "Policies and explanatory information."),
        _TB, _GL,
    ],
    "LOCAL_GAAP": [
        _req("BS", "Balance sheet / statement of financial position", "Assets, liabilities and equity.", "balance-sheet"),
        _req("PL", "Profit and loss account / income statement", "Performance for the period.", "income-statement"),
        _req("SCF", "Cash flow statement", "Required unless a small-entity exemption applies.", mandatory=False),
        _req("SOCE", "Statement of changes in equity", "Where required by the national framework.", mandatory=False),
        _req("NOTES", "Notes to the accounts", "Policies and disclosures."),
        _TB, _GL,
    ],
    "NONPROFIT": [
        _req("SFP", "Statement of financial position", "Assets, liabilities and net assets, split by restriction.", "balance-sheet"),
        _req("ACTIVITIES", "Statement of activities (income and expenditure)", "Income and expenditure by fund and restriction.", "income-statement"),
        _req("SCF", "Statement of cash flows", "Cash movements for the period."),
        _req("FUNCTIONAL", "Expenses by function", "Programme, fundraising and administration costs."),
        _req("FUND_SCHEDULE", "Restricted fund schedule", "Opening, income, spent and closing balance for each restricted fund."),
        _req("NOTES", "Notes", "Policies and disclosures."),
        _TB, _GL,
    ],
    "CASH_BASIS": [
        _req("RECEIPTS_PAYMENTS", "Statement of cash receipts and payments", "All cash received and paid in the period."),
        _req("CASH_POSITION", "Statement of cash position", "Opening and closing cash and bank balances."),
        _req("NOTES", "Notes", "Basis of preparation and outstanding commitments."),
        _TB, _GL,
    ],
    "OTHER": [
        _req("BS", "Statement of financial position", "Assets, liabilities and equity.", "balance-sheet"),
        _req("PL", "Statement of performance", "Income and expenses for the period.", "income-statement"),
        _req("NOTES", "Notes and policies", "Basis of preparation and policies."),
        _TB, _GL,
    ],
}
