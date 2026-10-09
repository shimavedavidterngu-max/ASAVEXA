"""Plain, inspectable rules the AI reasons with. Nothing here is learned or hidden: every table
below is the complete list of what the engine "knows", and every conclusion drawn from it says
which rule it used."""
from __future__ import annotations

import re
from decimal import Decimal
from typing import Dict, Iterable, List, Optional, Tuple

# ------------------------------------------------------------------ nature of a journal
# (debit side type, credit side type) -> (code, plain-English meaning, usual?)
NATURE_TABLE: Dict[Tuple[str, str], Tuple[str, str, bool]] = {
    ("EXPENSE", "ASSET"): ("EXPENSE_PAID", "an expense paid out of an asset (for example cash or bank)", True),
    ("EXPENSE", "LIABILITY"): ("EXPENSE_OWED", "an expense recorded but not yet paid (a liability was created)", True),
    ("EXPENSE", "EQUITY"): ("EXPENSE_BY_OWNERS", "an expense funded directly by the owners", False),
    ("ASSET", "REVENUE"): ("REVENUE_EARNED", "income earned (an asset such as cash or a receivable increased)", True),
    ("LIABILITY", "ASSET"): ("LIABILITY_SETTLED", "a liability being paid off from an asset", True),
    ("ASSET", "LIABILITY"): ("LIABILITY_INCURRED", "an asset obtained or cash received by taking on a liability (a loan or amount owed)", True),
    ("ASSET", "ASSET"): ("ASSET_EXCHANGE", "one asset exchanged for another (for example buying equipment with cash, or moving money between accounts)", True),
    ("ASSET", "EQUITY"): ("OWNER_CONTRIBUTION", "money or assets put in by the owners", True),
    ("EQUITY", "ASSET"): ("OWNER_DISTRIBUTION", "money or assets taken out by the owners", True),
    ("LIABILITY", "LIABILITY"): ("LIABILITY_TRANSFER", "an amount moved from one liability to another", True),
    ("EQUITY", "EQUITY"): ("EQUITY_TRANSFER", "an amount moved between equity accounts", True),
    ("LIABILITY", "REVENUE"): ("REVENUE_DEFERRED_RELEASED", "income recognised from an amount previously received in advance", True),
    ("REVENUE", "ASSET"): ("REVENUE_REDUCED", "income reduced (a refund, credit note or write-off)", False),
    ("REVENUE", "LIABILITY"): ("REVENUE_DEFERRED", "income moved into a liability (received but not yet earned)", False),
    ("ASSET", "EXPENSE"): ("EXPENSE_REDUCED", "an expense reduced or refunded (an asset increased)", False),
    ("LIABILITY", "EXPENSE"): ("EXPENSE_REDUCED", "an expense reduced by cancelling an amount owed", False),
    ("EQUITY", "REVENUE"): ("REVENUE_TO_EQUITY", "income moved directly into equity", False),
    ("LIABILITY", "EQUITY"): ("LIABILITY_TO_EQUITY", "an amount owed turned into owners' equity, or settled by the owners", False),
    ("EQUITY", "LIABILITY"): ("EQUITY_TO_LIABILITY", "equity moved into a liability (for example a dividend declared but not yet paid)", True),
    ("EQUITY", "EXPENSE"): ("EXPENSE_AGAINST_EQUITY", "an expense reduced directly against equity", False),
    ("REVENUE", "EQUITY"): ("REVENUE_FROM_EQUITY", "income reduced by a direct movement to equity (for example closing income to retained earnings)", True),
    ("EXPENSE", "REVENUE"): ("EXPENSE_AGAINST_REVENUE", "an expense set directly against income", False),
    ("REVENUE", "EXPENSE"): ("REVENUE_AGAINST_EXPENSE", "income set directly against an expense", False),
    ("EXPENSE", "EXPENSE"): ("EXPENSE_RECLASSIFIED", "an amount moved from one expense account to another", True),
    ("REVENUE", "REVENUE"): ("REVENUE_RECLASSIFIED", "an amount moved from one income account to another", True),
}

STATEMENT_FOR_TYPE = {
    "ASSET": "Balance sheet (statement of financial position)",
    "LIABILITY": "Balance sheet (statement of financial position)",
    "EQUITY": "Balance sheet (statement of financial position)",
    "REVENUE": "Income statement (profit or loss)",
    "EXPENSE": "Income statement (profit or loss)",
}

# ------------------------------------------------------------------ words in descriptions
# Each entry: account type the description most plausibly points to -> stems. A stem matches the
# start of a word, so "salar" matches salary and salaries. This is a hint, never a verdict.
KEYWORD_TYPES: Dict[str, Tuple[str, ...]] = {
    "EXPENSE": ("rent", "salar", "wage", "payroll", "utilit", "electric", "internet", "telephone", "insurance",
                "fuel", "travel", "transport", "repair", "maintenance", "stationer", "advert", "marketing",
                "subscription", "supplies", "consumable", "charge", "audit fee", "legal fee", "professional fee",
                "commission", "cleaning", "security", "training", "entertain", "meal", "refreshment"),
    "REVENUE": ("sale", "revenue", "income", "invoice to", "service fee", "consulting fee", "tuition", "subscription income",
                "commission income", "interest income", "donation received", "grant income"),
    "ASSET": ("equipment", "vehicle", "laptop", "computer", "furniture", "machinery", "machine", "inventory", "stock",
              "building", "land", "deposit paid", "prepayment", "prepaid", "receivable", "debtor"),
    "LIABILITY": ("loan", "borrow", "payable", "creditor", "overdraft", "accrual", "accrued", "vat", "tax payable", "deferred income"),
    "EQUITY": ("capital", "drawing", "dividend", "owner contribution", "owner's contribution", "retained", "share issue"),
}

# Words in an ACCOUNT NAME that point to an accounting policy the framework governs.
POLICY_HINTS: Tuple[Tuple[str, Tuple[str, ...], str], ...] = (
    ("PPE_MEASUREMENT", ("equipment", "vehicle", "machinery", "furniture", "building", "property", "plant", "land", "fixed asset", "computer"),
     "the account looks like property, plant or equipment"),
    ("DEPRECIATION_METHOD", ("equipment", "vehicle", "machinery", "furniture", "building", "plant", "fixed asset", "computer", "depreciation"),
     "the account looks like a depreciable asset or depreciation charge"),
    ("INVENTORY_COSTING", ("inventory", "stock", "cost of goods", "cost of sales"), "the account relates to inventory or the cost of goods sold"),
    ("RECEIVABLES_IMPAIRMENT", ("receivable", "debtor", "bad debt", "doubtful"), "the account relates to amounts customers owe"),
    ("BORROWING_COSTS", ("loan", "borrow", "interest", "overdraft", "finance cost"), "the account relates to borrowing or interest"),
    ("LEASES", ("lease", "rent"), "the account relates to renting or leasing"),
    ("DEFERRED_TAX", ("deferred tax", "income tax", "corporate tax", "tax expense"), "the account relates to income tax"),
    ("GRANTS_AND_DONATIONS", ("grant", "donation"), "the account relates to grants or donations"),
    ("FUND_ACCOUNTING", ("restricted", "fund balance", "designated fund"), "the account relates to funds or restrictions"),
    ("DEVELOPMENT_COSTS", ("development", "r&d", "research"), "the account relates to development costs"),
)

# Evidence a person would normally expect to see for each kind of transaction.
EXPECTED_EVIDENCE = {
    "EXPENSE_PAID": ("INVOICE", "RECEIPT"), "EXPENSE_OWED": ("INVOICE",), "REVENUE_EARNED": ("INVOICE", "CONTRACT"),
    "LIABILITY_SETTLED": ("RECEIPT", "BANK_STATEMENT"), "LIABILITY_INCURRED": ("CONTRACT",),
    "ASSET_EXCHANGE": ("INVOICE", "BANK_STATEMENT"), "OWNER_CONTRIBUTION": ("BANK_STATEMENT", "APPROVAL_RECORD"),
    "OWNER_DISTRIBUTION": ("APPROVAL_RECORD",),
}
EVIDENCE_WORD_HINTS = (("payroll", "PAYROLL_EVIDENCE"), ("salar", "PAYROLL_EVIDENCE"), ("wage", "PAYROLL_EVIDENCE"),
                       ("tax", "TAX_DOCUMENT"), ("vat", "TAX_DOCUMENT"), ("contract", "CONTRACT"), ("lease", "CONTRACT"),
                       ("loan", "CONTRACT"), ("purchase order", "PURCHASE_ORDER"), ("delivery", "DELIVERY_NOTE"))


def _norm(text: Optional[str]) -> str:
    return " " + re.sub(r"[^a-z0-9&' ]+", " ", (text or "").lower()) + " "


def words_hit(text: Optional[str], stems: Iterable[str]) -> List[str]:
    """Stems that start a word in `text` (case-insensitive)."""
    t = _norm(text)
    return [s for s in stems if (" " + s) in t]


def implied_type(description: Optional[str]) -> Tuple[Optional[str], List[str]]:
    """The account type a description most plausibly points to, and the words that say so.
    If two types tie, the description is treated as giving no clear signal."""
    hits = {typ: words_hit(description, stems) for typ, stems in KEYWORD_TYPES.items()}
    hits = {k: v for k, v in hits.items() if v}
    if not hits:
        return None, []
    best = max(len(v) for v in hits.values())
    top = [k for k, v in hits.items() if len(v) == best]
    if len(top) != 1:
        return None, sorted({w for k in top for w in hits[k]})
    return top[0], hits[top[0]]


def classify_nature(debit_types: Iterable[str], credit_types: Iterable[str], reversal: bool = False) -> dict:
    """What kind of transaction a debit/credit shape represents."""
    d, c = sorted(set(debit_types)), sorted(set(credit_types))
    if reversal:
        return {"code": "REVERSAL", "meaning": "a reversal that cancels an earlier journal", "usual": True,
                "rule": "The journal is marked as a reversal of another journal."}
    if len(d) == 1 and len(c) == 1:
        code, meaning, usual = NATURE_TABLE.get((d[0], c[0]), ("UNCLASSIFIED", "an entry between unfamiliar kinds of account", False))
        return {"code": code, "meaning": meaning, "usual": usual,
                "rule": f"Debit side is on {d[0].lower()} account(s) and credit side on {c[0].lower()} account(s)."}
    # compound entries: describe from the types involved
    if not d or not c:
        return {"code": "UNCLASSIFIED", "meaning": "an entry with no clear debit/credit pattern", "usual": False,
                "rule": "One side has no lines."}
    extra = ""
    if "ASSET" in d and "REVENUE" in c and "LIABILITY" in c:
        return {"code": "REVENUE_WITH_LIABILITY", "meaning": "income earned together with an amount owed on it (for example sales tax or VAT collected)",
                "usual": True, "rule": "Debit on assets; credit split between revenue and liability accounts."}
    if "EXPENSE" in d and "ASSET" in d and "LIABILITY" in c:
        extra = " (for example an expense with recoverable tax)"
    return {"code": "COMPOUND", "meaning": "a compound entry touching several kinds of account" + extra, "usual": True,
            "rule": f"Debit side: {', '.join(t.lower() for t in d)}; credit side: {', '.join(t.lower() for t in c)}."}


def policy_codes_for(account_names_and_types: Iterable[Tuple[str, str]], description: Optional[str]) -> List[Tuple[str, str]]:
    """[(policy_code, why)] for the accounting policies a journal could be touching."""
    found: Dict[str, str] = {}
    for name, _typ in account_names_and_types:
        for code, stems, why in POLICY_HINTS:
            if code in found:
                continue
            hit = words_hit(name, stems)
            if hit:
                found[code] = f"{why} ('{name}')"
    return list(found.items())


def expected_evidence(nature_code: str, description: Optional[str]) -> Tuple[str, ...]:
    out: List[str] = []
    for stem, typ in EVIDENCE_WORD_HINTS:
        if words_hit(description, (stem,)) and typ not in out:
            out.append(typ)
    for typ in EXPECTED_EVIDENCE.get(nature_code, ("OTHER",)):
        if typ not in out:
            out.append(typ)
    return tuple(out)
