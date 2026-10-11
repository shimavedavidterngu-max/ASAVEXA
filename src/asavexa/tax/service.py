"""Tax Compliance service.

Records (all in the shared document store, per organisation):
  tax_profile     org -> the countries the organisation operates in, with its registration numbers
  tax_rule        a rule: country, tax type, method (flat rate or progressive bands), rounding, effective dates, official source, filing pattern
  tax_calc        a saved calculation, tied to the exact rule version and its source
  tax_filed       a person's record that a filing was made (ASAVEXA does not file anything)

A rule can be used only when it is APPROVED by someone other than its author and in force on the date asked. Nothing here contains a tax rate of its own."""
import calendar
import hashlib
import json
import re
import uuid
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Callable, Dict, List, Optional

from . import engine
from .countries import BY_CODE, COUNTRIES
from .errors import TaxError, TaxForbiddenError, TaxNotFoundError, TaxStateError

TAX_TYPES = {
    "VAT_GST": "VAT, GST or similar value-added tax", "SALES_TAX": "Sales or use tax", "CORPORATE_INCOME": "Corporate income tax", "PERSONAL_INCOME": "Personal income tax",
    "WITHHOLDING": "Withholding tax", "PAYROLL": "Payroll or employer contributions", "EXCISE": "Excise duty", "CUSTOMS": "Customs duty", "PROPERTY": "Property tax", "OTHER": "Other tax",
}
FREQ = {"MONTHLY": 1, "QUARTERLY": 3, "HALF_YEARLY": 6, "ANNUAL": 12}
LIMITATIONS = [
    "ASAVEXA contains no tax rates of its own. Every figure comes from a rule a person entered from an official source and a different person approved.",
    "A rule is only as right as its source and the person who read it. Check the source, and ask a qualified tax adviser before you file.",
    "Results are calculations and estimates, not tax advice, not a return, and not a filing. ASAVEXA does not submit anything to a tax authority.",
    "Deadlines are worked out from the filing pattern in the approved rule. Authorities can move dates, so confirm with the authority.",
    "Currencies are not converted.",
]
STATUS_TEXT = {"DRAFT": "Draft", "SUBMITTED": "Waiting for review", "APPROVED": "In force", "REJECTED": "Sent back", "SUPERSEDED": "Replaced"}


def _utc(): return datetime.now(timezone.utc)
def _sha(o) -> str: return hashlib.sha256(json.dumps(o, sort_keys=True, separators=(",", ":"), default=str).encode()).hexdigest()


def _txt(v, name, lo=1, hi=500, required=True) -> str:
    v = (v if isinstance(v, str) else ("" if v is None else str(v))).strip()
    if required and len(v) < lo:
        raise TaxError(f"{name} is required (at least {lo} characters).")
    if len(v) > hi:
        raise TaxError(f"{name} is too long (limit {hi} characters).")
    return v


def _date(v, name, required=True) -> Optional[date]:
    if v in (None, ""):
        if required:
            raise TaxError(f"{name} is required.")
        return None
    try:
        return date.fromisoformat(str(v))
    except ValueError:
        raise TaxError(f"{name} must be a date like 2026-01-31.")


def _add_months(d: date, n: int) -> date:
    m = d.month - 1 + n
    y, m = d.year + m // 12, m % 12 + 1
    return date(y, m, min(d.day, calendar.monthrange(y, m)[1]))


def _country(code) -> dict:
    c = BY_CODE.get(str(code or "").upper())
    if c is None:
        raise TaxNotFoundError("That country is not in the list.")
    return c


class TaxService:
    def __init__(self, store, accounting=None, log: Callable[..., None] = lambda *a, **k: None, now: Callable[[], datetime] = _utc):
        self.store, self.accounting, self.log, self.now = store, accounting, log, now

    # ------------------------------------------------------------------ countries and profile
    def _profile(self, org) -> dict:
        return self.store.get("tax_profile", org) or {"jurisdictions": {}, "version": 0}

    def _rules(self, org) -> List[dict]:
        return [d for _, d in self.store.list("tax_rule", org_id=org, prefix=f"{org}:")]

    def countries(self, org, q: str = "", region: str = "") -> dict:
        prof, rules = self._profile(org)["jurisdictions"], self._rules(org)
        q, region = (q or "").strip().lower(), (region or "").strip().lower()
        rows = []
        for code, name, cur, reg in COUNTRIES:
            if q and q not in name.lower() and q != code.lower():
                continue
            if region and region != reg.lower():
                continue
            mine = [r for r in rules if r["country"] == code]
            rows.append({"code": code, "name": name, "currency": cur, "region": reg, "selected": code in prof, "registration": (prof.get(code) or {}).get("registration", ""),
                         "rules_in_force": sum(1 for r in mine if r["status"] == "APPROVED"), "rules_waiting": sum(1 for r in mine if r["status"] == "SUBMITTED"), "rules_draft": sum(1 for r in mine if r["status"] in ("DRAFT", "REJECTED"))})
        if q:
            rows.sort(key=lambda r: (r["code"].lower() != q, not r["name"].lower().startswith(q)))
        return {"countries": rows, "total": len(COUNTRIES), "shown": len(rows), "regions": sorted({c[3] for c in COUNTRIES}),
                "with_rules": sum(1 for c in COUNTRIES if any(r["country"] == c[0] and r["status"] == "APPROVED" for r in rules)),
                "note": "A country appearing in this list does not mean ASAVEXA knows its tax rules. A country has rules only after a person enters them from an official source and a second person approves them."}

    def set_jurisdiction(self, org, code, on: bool, registration: str, actor) -> dict:
        c = _country(code)
        p = self.store.get("tax_profile", org, for_update=True) or {"jurisdictions": {}, "version": 0}
        if on:
            if len(p["jurisdictions"]) >= 60 and c["code"] not in p["jurisdictions"]:
                raise TaxError("An organisation can select at most 60 countries.")
            p["jurisdictions"][c["code"]] = {"registration": _txt(registration, "Registration number", 0, 60, required=False), "added_by": actor, "added_at": self.now().isoformat()}
        else:
            p["jurisdictions"].pop(c["code"], None)
        p["version"] += 1
        self.store.put("tax_profile", org, p, org_id=org)
        self.log("TAX_COUNTRY_" + ("ADDED" if on else "REMOVED"), actor, c["code"], org, f"{c['name']}")
        return {"code": c["code"], "selected": on}

    # ------------------------------------------------------------------ rules
    def _rule(self, org, rid, for_update=False) -> dict:
        r = self.store.get("tax_rule", f"{org}:{rid}", for_update=for_update)
        if r is None or r["org"] != org:
            raise TaxNotFoundError("Tax rule not found.")
        return r

    def _put(self, org, r): self.store.put("tax_rule", f"{org}:{r['id']}", r, org_id=org)
    def _hist(self, r, actor, action, note=""): r["history"].append({"at": self.now().isoformat(), "actor": actor, "action": action, "note": note})

    def _clean(self, body: dict) -> dict:
        c = _country(body.get("country"))
        t = str(body.get("tax_type") or "").upper()
        if t not in TAX_TYPES:
            raise TaxError("Choose a tax type from the list.")
        method = str(body.get("method") or "").upper()
        out = {"country": c["code"], "tax_type": t, "name": _txt(body.get("name"), "Rule name", 3, 120), "method": method,
               "rounding": str(body.get("rounding") or "HALF_UP").upper(), "effective_from": _date(body.get("effective_from"), "Start date").isoformat(),
               "effective_to": (lambda d: d.isoformat() if d else None)(_date(body.get("effective_to"), "End date", required=False)),
               "authority": _txt(body.get("authority"), "Tax authority", 2, 160), "source_title": _txt(body.get("source_title"), "Source (law, section or notice)", 5, 300),
               "source_url": _txt(body.get("source_url"), "Source link", 8, 500), "notes": _txt(body.get("notes"), "Notes", 0, 1000, required=False)}
        if out["rounding"] not in engine.ROUNDING:
            raise TaxError("Rounding must be half-up, down or half-even.")
        if out["effective_to"] and out["effective_to"] < out["effective_from"]:
            raise TaxError("The end date cannot be before the start date.")
        if not re.match(r"^https?://[^\s]+\.[^\s]+$", out["source_url"]):
            raise TaxError("The source link must be a web address starting with http:// or https://.")
        if method == "FLAT":
            out["rate"] = str(engine.dec(body.get("rate"), "Rate (%)", lo=0, hi=100))
        elif method == "BRACKETS":
            out["brackets"] = engine.clean_brackets(body.get("brackets"))
        else:
            raise TaxError("Choose a method: flat rate or progressive bands.")
        f = body.get("filing") or {}
        if f.get("frequency"):
            fr = str(f["frequency"]).upper()
            if fr not in FREQ:
                raise TaxError("Filing frequency must be monthly, quarterly, half-yearly or annual.")
            out["filing"] = {"frequency": fr, "due_days_after_period_end": int(engine.dec(f.get("due_days_after_period_end"), "Days after period end", lo=0, hi=400)),
                             "period_anchor": _date(f.get("period_anchor") or out["effective_from"], "First period start").isoformat(), "form": _txt(f.get("form"), "Return name", 0, 120, required=False)}
        else:
            out["filing"] = None
        return out

    def create_rule(self, org, body: dict, actor, replaces: Optional[str] = None) -> dict:
        c = self._clean(body)
        if replaces:
            old = self._rule(org, replaces)
            if old["status"] != "APPROVED":
                raise TaxStateError("Only a rule that is in force can be replaced.")
        r = {"id": str(uuid.uuid4()), "org": org, **c, "status": "DRAFT", "version": 1, "replaces": replaces, "created_by": actor, "created_at": self.now().isoformat(),
             "submitted_by": None, "decided_by": None, "decision_note": "", "history": []}
        self._hist(r, actor, "CREATED")
        self._put(org, r)
        self.log("TAX_RULE_CREATED", actor, r["id"], org, f"{c['country']} {c['tax_type']} {c['name']}")
        return self._view(r)

    def update_rule(self, org, rid, body: dict, actor) -> dict:
        r = self._rule(org, rid, for_update=True)
        if r["status"] not in ("DRAFT", "REJECTED"):
            raise TaxStateError("Only a draft or a rule that was sent back can be edited. To change a rule in force, create a replacement.")
        c = self._clean(body)
        r.update(c)
        r["version"] += 1
        r["status"] = "DRAFT"
        self._hist(r, actor, "EDITED")
        self._put(org, r)
        self.log("TAX_RULE_EDITED", actor, rid, org, f"version {r['version']}")
        return self._view(r)

    def submit_rule(self, org, rid, actor) -> dict:
        r = self._rule(org, rid, for_update=True)
        if r["status"] not in ("DRAFT", "REJECTED"):
            raise TaxStateError("Only a draft can be submitted for review.")
        r["status"], r["submitted_by"] = "SUBMITTED", actor
        self._hist(r, actor, "SUBMITTED")
        self._put(org, r)
        self.log("TAX_RULE_SUBMITTED", actor, rid, org, "")
        return self._view(r)

    @staticmethod
    def _overlap(a: dict, b: dict) -> bool:
        a_to, b_to = a["effective_to"] or "9999-12-31", b["effective_to"] or "9999-12-31"
        return a["effective_from"] <= b_to and b["effective_from"] <= a_to

    def _decide(self, org, rid, actor, approve: bool, note: str) -> dict:
        r = self._rule(org, rid, for_update=True)
        if r["status"] != "SUBMITTED":
            raise TaxStateError("Only a rule waiting for review can be approved or sent back.")
        if actor == r["submitted_by"] or actor == r["created_by"]:
            raise TaxForbiddenError("A different person must review this rule. You prepared or submitted it, so you cannot approve or reject it.")
        note = _txt(note, "Note", 0 if approve else 3, 500, required=not approve)
        if approve:
            clash = [o for o in self._rules(org) if o["id"] != rid and o["status"] == "APPROVED" and o["country"] == r["country"] and o["tax_type"] == r["tax_type"] and o["name"].lower() == r["name"].lower() and self._overlap(o, r)
                     and o["id"] != r.get("replaces")]
            if clash:
                raise TaxStateError(f"This rule overlaps in time with '{clash[0]['name']}' that is already in force. Change the dates, or create it as a replacement.")
            if r.get("replaces"):
                old = self._rule(org, r["replaces"], for_update=True)
                if old["status"] == "APPROVED":
                    old["status"] = "SUPERSEDED"
                    self._hist(old, actor, "SUPERSEDED", f"replaced by {rid}")
                    self._put(org, old)
        r["status"], r["decided_by"], r["decision_note"] = ("APPROVED" if approve else "REJECTED"), actor, note
        r["fingerprint"] = _sha({k: r[k] for k in ("country", "tax_type", "name", "method", "rate", "brackets", "rounding", "effective_from", "effective_to", "source_url", "source_title", "filing") if k in r}) if approve else r.get("fingerprint")
        self._hist(r, actor, "APPROVED" if approve else "REJECTED", note)
        self._put(org, r)
        self.log("TAX_RULE_APPROVED" if approve else "TAX_RULE_REJECTED", actor, rid, org, note)
        return self._view(r)

    def approve_rule(self, org, rid, actor, note="") -> dict: return self._decide(org, rid, actor, True, note)
    def reject_rule(self, org, rid, actor, reason) -> dict: return self._decide(org, rid, actor, False, reason)

    def delete_draft(self, org, rid, actor) -> dict:
        r = self._rule(org, rid, for_update=True)
        if r["status"] not in ("DRAFT", "REJECTED"):
            raise TaxStateError("Only a draft can be discarded. A rule that was in force stays on record.")
        r["status"] = "DISCARDED"
        self._hist(r, actor, "DISCARDED")
        self._put(org, r)
        self.log("TAX_RULE_DISCARDED", actor, rid, org, "")
        return {"id": rid, "discarded": True}

    def _view(self, r) -> dict:
        v = dict(r)
        v["status_text"] = STATUS_TEXT.get(r["status"], r["status"])
        v["country_name"] = BY_CODE[r["country"]]["name"]
        v["tax_type_text"] = TAX_TYPES[r["tax_type"]]
        v["currency"] = BY_CODE[r["country"]]["currency"]
        return v

    def get_rule(self, org, rid) -> dict: return self._view(self._rule(org, rid))

    def list_rules(self, org, country: Optional[str] = None, status: Optional[str] = None) -> List[dict]:
        rows = [self._view(r) for r in self._rules(org) if r["status"] != "DISCARDED" and (not country or r["country"] == country.upper()) and (not status or r["status"] == status.upper())]
        return sorted(rows, key=lambda r: (r["country"], r["tax_type"], r["effective_from"]))

    def rule_options(self) -> dict:
        return {"tax_types": TAX_TYPES, "frequencies": list(FREQ), "rounding": list(engine.ROUNDING), "methods": {"FLAT": "One flat percentage", "BRACKETS": "Progressive bands (each slice taxed at its own rate)"},
                "guidance": ["Copy the rate or bands from the official law or the tax authority's published notice, not from a summary website.",
                             "Record the exact section or notice and a link to it, so the reviewer can check it.",
                             "Set the date the rule starts to apply. When the law changes, create a replacement rule instead of editing history."]}

    # ------------------------------------------------------------------ calculation
    def _usable(self, org, rid, on: date) -> dict:
        r = self._rule(org, rid)
        if r["status"] != "APPROVED":
            raise TaxStateError(f"This rule is '{STATUS_TEXT.get(r['status'], r['status'])}'. Only a rule that a second person has approved can be used for a calculation.")
        if on.isoformat() < r["effective_from"] or (r["effective_to"] and on.isoformat() > r["effective_to"]):
            raise TaxStateError(f"This rule applies from {r['effective_from']}{' to ' + r['effective_to'] if r['effective_to'] else ''}. {on.isoformat()} is outside that range; use the rule in force on that date.")
        return r

    def calculate(self, org, rid, amount, on_date, inclusive: bool, actor, save: bool = True, basis: Optional[dict] = None) -> dict:
        on = _date(on_date, "Date")
        r = self._usable(org, rid, on)
        amt = engine.dec(amount, "Amount", lo=0)
        if r["method"] == "FLAT":
            res = engine.flat(amt, Decimal(r["rate"]), bool(inclusive), r["rounding"])
        else:
            if inclusive:
                raise TaxError("Progressive bands apply to an amount before tax; 'tax included' does not apply.")
            res = engine.progressive(amt, r["brackets"], r["rounding"])
        out = {"id": str(uuid.uuid4()), "rule": {"id": r["id"], "name": r["name"], "version": r["version"], "country": r["country"], "country_name": BY_CODE[r["country"]]["name"], "tax_type": r["tax_type"], "method": r["method"],
                "rate": r.get("rate"), "brackets": r.get("brackets"), "rounding": r["rounding"], "effective_from": r["effective_from"], "effective_to": r["effective_to"], "authority": r["authority"],
                "source_title": r["source_title"], "source_url": r["source_url"], "fingerprint": r.get("fingerprint")},
               "date": on.isoformat(), "inclusive": bool(inclusive), "currency": BY_CODE[r["country"]]["currency"], "input": str(amt),
               "net": str(res["net"]), "tax": str(res["tax"]), "gross": None if res["gross"] is None else str(res["gross"]), "steps": res["steps"], "bands": res.get("bands"),
               "effective_rate_pct": res.get("effective_rate_pct"), "basis": basis, "kind": "ESTIMATE (calculation, not a return and not advice)", "limitations": LIMITATIONS,
               "calculated_by": actor, "calculated_at": self.now().isoformat()}
        if res.get("above_last_band"):
            out["warnings"] = ["The amount is above the last band you entered; confirm the rule includes every band."]
        if save:
            self.store.put("tax_calc", f"{org}:{out['id']}", out, org_id=org)
            self.log("TAX_CALCULATED", actor, out["id"], org, f"{r['country']} {r['name']}: tax {out['tax']}")
        return out

    def calc_history(self, org, limit: int = 50) -> List[dict]:
        rows = [d for _, d in self.store.list("tax_calc", org_id=org, prefix=f"{org}:")]
        return sorted(rows, key=lambda d: d["calculated_at"], reverse=True)[:limit]

    def ledger_base(self, org, period_id, kind: str) -> dict:
        """A starting amount from the posted ledger for a period (revenue, expenses or net income). Read-only."""
        if self.accounting is None:
            raise TaxError("The ledger is not connected.")
        if kind not in ("revenue", "expenses", "net_income"):
            raise TaxError("Choose revenue, expenses or net income.")
        from ..analysis.figures import collect_figures
        fig = collect_figures(self.accounting, org, period_id, {})
        cur = fig["currencies"]
        return {"kind": kind, "amount": str(engine.q2(fig[kind])), "period": fig["period"], "currencies": cur,
                "warning": "Accounts use more than one currency; the amount mixes them and should not be used." if len(cur) > 1 else None,
                "note": "From posted journals only. Drafts are excluded. Tax law may adjust accounting profit; this is a starting point, not taxable income."}

    # ------------------------------------------------------------------ calendar
    def calendar(self, org, start: str, end: str) -> dict:
        s, e = _date(start, "From"), _date(end, "To")
        if e < s:
            raise TaxError("The end date cannot be before the start date.")
        if (e - s).days > 1100:
            raise TaxError("Choose a range of 3 years or less.")
        prof = self._profile(org)["jurisdictions"]
        filed = {d["key"]: d for _, d in self.store.list("tax_filed", org_id=org, prefix=f"{org}:")}
        today = self.now().date()
        items = []
        for r in self._rules(org):
            if r["status"] != "APPROVED" or not r.get("filing") or r["country"] not in prof:
                continue
            f = r["filing"]
            step = FREQ[f["frequency"]]
            ps = _date(f["period_anchor"], "anchor")
            n = 0
            while n < 400:
                pe = _add_months(ps, step) - timedelta(days=1)
                due = pe + timedelta(days=f["due_days_after_period_end"])
                lim = r["effective_to"] or "9999-12-31"
                if ps.isoformat() > lim:
                    break
                if s <= due <= e and ps.isoformat() >= r["effective_from"]:
                    key = f"{r['id']}:{pe.isoformat()}"
                    fl = filed.get(key)
                    items.append({"key": key, "rule_id": r["id"], "country": r["country"], "country_name": BY_CODE[r["country"]]["name"], "rule": r["name"], "tax_type": r["tax_type"], "form": f.get("form", ""),
                                  "period_start": ps.isoformat(), "period_end": pe.isoformat(), "due": due.isoformat(), "authority": r["authority"], "source_url": r["source_url"],
                                  "state": "FILED" if fl else ("OVERDUE" if due < today else ("DUE_SOON" if (due - today).days <= 14 else "UPCOMING")), "filed": fl})
                if due > e:
                    break
                ps = pe + timedelta(days=1)
                n += 1
        items.sort(key=lambda i: (i["due"], i["country"]))
        return {"from": s.isoformat(), "to": e.isoformat(), "items": items, "overdue": sum(1 for i in items if i["state"] == "OVERDUE"), "limitations": LIMITATIONS[3],
                "note": "Only countries you selected, with a rule in force that has a filing pattern, appear here. A country with no entry has no rule loaded, which is not the same as having no deadlines."}

    def mark_filed(self, org, rule_id, period_end, reference, actor) -> dict:
        r = self._rule(org, rule_id)
        if r["status"] not in ("APPROVED", "SUPERSEDED"):
            raise TaxStateError("A filing can only be recorded against a rule that is or was in force.")
        pe = _date(period_end, "Period end")
        key = f"{r['id']}:{pe.isoformat()}"
        d = {"key": key, "rule_id": r["id"], "period_end": pe.isoformat(), "reference": _txt(reference, "Filing reference", 2, 120), "filed_by": actor, "recorded_at": self.now().isoformat(),
             "note": "Recorded by a person. ASAVEXA did not submit this to the authority."}
        self.store.put("tax_filed", f"{org}:{key}", d, org_id=org)
        self.log("TAX_FILING_RECORDED", actor, rule_id, org, f"period ending {pe.isoformat()} ref {d['reference']}")
        return d

    def overview(self, org) -> dict:
        prof, rules = self._profile(org)["jurisdictions"], self._rules(org)
        return {"selected": len(prof), "rules_in_force": sum(1 for r in rules if r["status"] == "APPROVED"), "rules_waiting": sum(1 for r in rules if r["status"] == "SUBMITTED"),
                "selected_without_rules": [{"code": c, "name": BY_CODE[c]["name"]} for c in prof if not any(r["country"] == c and r["status"] == "APPROVED" for r in rules)],
                "limitations": LIMITATIONS}
