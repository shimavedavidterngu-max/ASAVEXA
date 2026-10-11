"""Financial Analysis workspace service.

Reads the accounting ledger (never writes to it). Stores only what people add: classification of accounts, thresholds, comparison budgets, commentary, forecast scenarios and analysis reports.
Rules enforced here (and tested):
  * every figure is recomputed from the posted ledger; a stored report keeps a frozen snapshot with a fingerprint so later changes are detectable;
  * a report moves DRAFT -> SUBMITTED -> APPROVED (or REJECTED, then back to submitted): the person who submitted it can never approve or reject it;
  * an approved report cannot be edited, and only an approved report can be exported;
  * forecasts are labelled FORECAST everywhere and are never written to the ledger;
  * every change and every export is written to the organisation's audit trail."""
from __future__ import annotations

import csv
import hashlib
import io
import json
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Callable, Dict, List, Optional

from . import forecast as fc
from .errors import AnalysisError, AnalysisForbiddenError, AnalysisNotFoundError, AnalysisStateError
from .figures import ALL_TAGS, TAGS_BY_TYPE, collect_figures, previous_period
from .numbers import dec, s2
from .ratios import compute_ratios, ratio_values
from .variance import DEFAULT_THRESHOLDS, budget_variance, period_variance

STATUSES = ("DRAFT", "SUBMITTED", "APPROVED", "REJECTED")
CONFIDENTIAL = "CONFIDENTIAL - ASAVEXA financial analysis. For the organisation named below and people it has authorised."
LIMITATIONS = [
    "Figures come from posted journals only. Drafts are excluded and reversed journals stay in, as in the ledger.",
    "Balance-sheet figures are balances at the period end; revenue and expenses are movements inside the period.",
    "Ratios depend on how accounts were classified in Setup; unclassified accounts make a ratio INCOMPLETE rather than guessed.",
    "Budget figures are entered by a person for comparison; forecasts are stated assumptions, not actual results and not advice.",
    "Currencies are not converted. If accounts use more than one currency, ratios are not calculated.",
    "Approval records that a second person reviewed this analysis; it is not an audit opinion or a certification.",
]


def _utc(): return datetime.now(timezone.utc)
def _sha(o) -> str: return hashlib.sha256(json.dumps(o, sort_keys=True, separators=(",", ":"), default=str).encode()).hexdigest()


def _txt(v, name, lo=1, hi=1000, required=True) -> str:
    v = (v if isinstance(v, str) else ("" if v is None else str(v))).strip()
    if required and len(v) < lo:
        raise AnalysisError(f"{name} is required (at least {lo} characters).")
    if len(v) > hi:
        raise AnalysisError(f"{name} is too long (limit {hi} characters).")
    return v


class AnalysisService:
    def __init__(self, store, accounting, log: Callable[..., None] = lambda *a, **k: None, now: Callable[[], datetime] = _utc):
        self.store, self.accounting, self.log, self.now = store, accounting, log, now

    # ------------------------------------------------------------------ setup
    def _period(self, org, period_id):
        p = self.accounting.periods.get(org, period_id)
        if p is None:
            raise AnalysisNotFoundError("That accounting period was not found in this organisation.")
        return p

    def get_config(self, org: str) -> dict:
        c = self.store.get("analysis_config", org) or {"version": 0, "tags": {}, "thresholds": dict(DEFAULT_THRESHOLDS), "updated_by": None, "updated_at": None}
        accounts = [{"id": a.id, "code": a.code, "name": a.name, "type": a.type.value if hasattr(a.type, "value") else str(a.type), "tag": c["tags"].get(a.id)}
                    for a in sorted(self.accounting.accounts.list_for_org(org), key=lambda x: x.code)]
        return {**c, "accounts": accounts, "tag_choices": {t: dict(m) for t, m in TAGS_BY_TYPE.items()}}

    def set_config(self, org: str, tags: Optional[dict], thresholds: Optional[dict], actor: str) -> dict:
        cur = self.store.get("analysis_config", org, for_update=True) or {"version": 0, "tags": {}, "thresholds": dict(DEFAULT_THRESHOLDS)}
        accounts = {a.id: a for a in self.accounting.accounts.list_for_org(org)}
        new_tags = dict(cur["tags"])
        for aid, tag in (tags or {}).items():
            if aid not in accounts:
                raise AnalysisNotFoundError("One of the accounts was not found in this organisation.")
            t = accounts[aid].type.value if hasattr(accounts[aid].type, "value") else str(accounts[aid].type)
            if tag in (None, ""):
                new_tags.pop(aid, None)
            elif tag not in TAGS_BY_TYPE.get(t, {}):
                raise AnalysisError(f"'{tag}' is not a valid classification for {accounts[aid].code} {accounts[aid].name} (a {t.lower()} account).")
            else:
                new_tags[aid] = tag
        th = dict(cur["thresholds"])
        if thresholds:
            if "percent" in thresholds:
                th["percent"] = str(dec(thresholds["percent"], "Percent threshold", lo=0, hi=1000))
            if "amount" in thresholds:
                th["amount"] = str(dec(thresholds["amount"], "Amount threshold", lo=0))
        out = {"version": cur["version"] + 1, "tags": new_tags, "thresholds": th, "updated_by": actor, "updated_at": self.now().isoformat()}
        self.store.put("analysis_config", org, out, org_id=org)
        self.log("ANALYSIS_CONFIG_CHANGED", actor, org, org, f"version {out['version']}: {len(new_tags)} account(s) classified, thresholds {th['percent']}% / {th['amount']}")
        return self.get_config(org)

    def _cfg(self, org):
        c = self.store.get("analysis_config", org) or {"version": 0, "tags": {}, "thresholds": dict(DEFAULT_THRESHOLDS)}
        return c

    # ------------------------------------------------------------------ figures and ratios
    def figures(self, org, period_id, tags=None) -> dict:
        return collect_figures(self.accounting, org, period_id, self._cfg(org)["tags"] if tags is None else tags)

    def overview(self, org, period_id) -> dict:
        cfg = self._cfg(org)
        fig = self.figures(org, period_id)
        live = [r for r in fig["accounts"] if r["amount"] != 0]
        unclass_bs = [r for r in live if r["type"] in ("ASSET", "LIABILITY") and not r["tag"]]
        unclass_exp = [r for r in live if r["type"] == "EXPENSE" and not r["tag"]]
        prior = previous_period(self.accounting, org, self._period(org, period_id))
        issues = []
        if not live:
            issues.append("There are no posted entries for this period yet, so there is nothing to analyse.")
        if fig["period"]["status"] not in ("CLOSED", "LOCKED"):
            issues.append(f"This period is {fig['period']['status'].lower()}, so figures can still change.")
        if len(fig["currencies"]) > 1:
            issues.append(f"Accounts use more than one currency ({', '.join(fig['currencies'])}); ratios are not calculated.")
        if unclass_bs:
            issues.append(f"{len(unclass_bs)} asset or liability account(s) with a balance are not classified; liquidity ratios are incomplete.")
        if unclass_exp:
            issues.append(f"{len(unclass_exp)} expense account(s) with a balance are not classified; margin ratios are incomplete.")
        return {"period": fig["period"], "totals": {k: s2(fig[k]) for k in ("assets", "liabilities", "equity_total", "revenue", "expenses", "net_income")}, "currencies": fig["currencies"],
                "posted_entries": fig["posted_entries"], "prior_period": None if prior is None else {"id": prior.id, "name": prior.name},
                "classified": sum(1 for r in live if r["tag"]), "live_accounts": len(live), "unclassified": [{"id": r["id"], "code": r["code"], "name": r["name"], "type": r["type"]} for r in unclass_bs + unclass_exp],
                "config_version": cfg["version"], "thresholds": cfg["thresholds"], "budget": self.budget_meta(org, period_id), "issues": issues,
                "definitions": ["Balance-sheet accounts: balance at the end of the period.", "Revenue and expenses: movement inside the period.", "Total equity = assets - liabilities (includes profit not yet closed)."]}

    def ratios(self, org, period_id) -> dict:
        fig = self.figures(org, period_id)
        rs = compute_ratios(fig)
        return {"period": fig["period"], "ratios": rs, "calculated": sum(1 for r in rs if r["status"] == "CALCULATED"), "total": len(rs), "kind": "ACTUAL",
                "note": "A ratio is one input for professional judgement. Acceptable levels depend on the industry and the organisation."}

    # ------------------------------------------------------------------ commentary
    def add_comment(self, org, period_id, account_id, text, actor) -> dict:
        self._period(org, period_id)
        if not any(a.id == account_id for a in self.accounting.accounts.list_for_org(org)):
            raise AnalysisNotFoundError("That account was not found in this organisation.")
        c = {"id": str(uuid.uuid4()), "period_id": period_id, "account_id": account_id, "text": _txt(text, "Commentary", 3, 2000), "actor": actor, "at": self.now().isoformat()}
        self.store.put("analysis_comment", f"{org}:{period_id}:{account_id}:{c['id']}", c, org_id=org)
        self.log("ANALYSIS_COMMENT_ADDED", actor, c["id"], org, f"period {period_id}, account {account_id}")
        return c

    def comments_map(self, org, period_id) -> Dict[str, List[dict]]:
        out: Dict[str, List[dict]] = {}
        for _, c in self.store.list("analysis_comment", org_id=org, prefix=f"{org}:{period_id}:"):
            out.setdefault(c["account_id"], []).append(c)
        for v in out.values():
            v.sort(key=lambda c: c["at"])
        return out

    # ------------------------------------------------------------------ variance and budget
    def variance(self, org, period_id) -> dict:
        cfg = self._cfg(org)
        period = self._period(org, period_id)
        cur = self.figures(org, period_id)
        prior_p = previous_period(self.accounting, org, period)
        prior = self.figures(org, prior_p.id) if prior_p else None
        return period_variance(cur, prior, cfg["thresholds"], self.comments_map(org, period_id))

    def _budget_rows(self, org, period_id):
        rows = [d for _, d in self.store.list("analysis_budget", org_id=org, prefix=f"{org}:{period_id}:")]
        return max(rows, key=lambda d: d["version"]) if rows else None

    def budget_meta(self, org, period_id) -> Optional[dict]:
        b = self._budget_rows(org, period_id)
        return None if b is None else {"version": b["version"], "note": b["note"], "entered_by": b["by"], "entered_at": b["at"], "lines": len(b["lines"]), "kind": "BUDGET (entered by a person for comparison)"}

    def get_budget(self, org, period_id) -> dict:
        self._period(org, period_id)
        b = self._budget_rows(org, period_id)
        return {"meta": self.budget_meta(org, period_id), "lines": {} if b is None else b["lines"],
                "history": [{"version": d["version"], "by": d["by"], "at": d["at"], "note": d["note"]} for _, d in sorted(self.store.list("analysis_budget", org_id=org, prefix=f"{org}:{period_id}:"), key=lambda x: x[1]["version"])]}

    def set_budget(self, org, period_id, lines: Dict[str, object], note: str, actor: str) -> dict:
        self._period(org, period_id)
        if not isinstance(lines, dict) or not lines:
            raise AnalysisError("Enter at least one budget line.")
        accts = {a.id: a for a in self.accounting.accounts.list_for_org(org)}
        clean = {}
        for aid, amt in lines.items():
            a = accts.get(aid)
            if a is None:
                raise AnalysisNotFoundError("One of the budget accounts was not found in this organisation.")
            t = a.type.value if hasattr(a.type, "value") else str(a.type)
            if t not in ("REVENUE", "EXPENSE"):
                raise AnalysisError(f"{a.code} {a.name} is not a revenue or expense account; only those can be budgeted here.")
            clean[aid] = str(dec(amt, f"Budget for {a.code}", lo=0))
        cur = self._budget_rows(org, period_id)
        v = (cur["version"] if cur else 0) + 1
        d = {"version": v, "lines": clean, "note": _txt(note, "Note", 0, 500, required=False), "by": actor, "at": self.now().isoformat()}
        self.store.put("analysis_budget", f"{org}:{period_id}:{v:05d}", d, org_id=org)
        self.log("ANALYSIS_BUDGET_ENTERED", actor, period_id, org, f"comparison budget version {v}, {len(clean)} line(s)")
        return self.get_budget(org, period_id)

    def budget_variance(self, org, period_id) -> dict:
        cfg = self._cfg(org)
        cur = self.figures(org, period_id)
        b = self._budget_rows(org, period_id)
        return budget_variance(cur, None if b is None else {k: Decimal(v) for k, v in b["lines"].items()}, cfg["thresholds"], self.budget_meta(org, period_id), self.comments_map(org, period_id))

    # ------------------------------------------------------------------ forecast scenarios
    def suggest(self, org, period_id) -> dict:
        return fc.suggest(self.figures(org, period_id))

    def save_scenario(self, org, name, base_period_id, assumptions, actor, scenario_id=None) -> dict:
        self._period(org, base_period_id)
        a = fc.clean_assumptions(assumptions)
        key_id = scenario_id or str(uuid.uuid4())
        old = self.store.get("analysis_scenario", f"{org}:{key_id}", for_update=True) if scenario_id else None
        if scenario_id and old is None:
            raise AnalysisNotFoundError("That scenario was not found.")
        d = {"id": key_id, "name": _txt(name, "Scenario name", 2, 120), "base_period_id": base_period_id, "assumptions": a, "model": fc.MODEL, "version": (old["version"] + 1) if old else 1,
             "created_by": old["created_by"] if old else actor, "created_at": old["created_at"] if old else self.now().isoformat(), "updated_by": actor, "updated_at": self.now().isoformat(), "kind": "FORECAST"}
        self.store.put("analysis_scenario", f"{org}:{key_id}", d, org_id=org)
        self.log("ANALYSIS_SCENARIO_SAVED", actor, key_id, org, f"{d['name']} v{d['version']}")
        return d

    def list_scenarios(self, org, period_id: Optional[str] = None) -> List[dict]:
        rows = [d for _, d in self.store.list("analysis_scenario", org_id=org, prefix=f"{org}:")]
        return sorted((d for d in rows if period_id in (None, d["base_period_id"])), key=lambda d: d["created_at"])

    def run_scenario(self, org, scenario_id) -> dict:
        d = self.store.get("analysis_scenario", f"{org}:{scenario_id}")
        if d is None:
            raise AnalysisNotFoundError("That scenario was not found.")
        return {"scenario": {k: d[k] for k in ("id", "name", "base_period_id", "version", "model")}, **fc.run(d["assumptions"])}

    def breakeven(self, fixed_costs, price, variable_cost) -> dict:
        return fc.breakeven(fixed_costs, price, variable_cost)

    # ------------------------------------------------------------------ reports (workflow)
    def _report(self, org, rid, for_update=False) -> dict:
        r = self.store.get("analysis_report", f"{org}:{rid}", for_update=for_update)
        if r is None:
            raise AnalysisNotFoundError("That analysis report was not found.")
        return r

    def _put(self, org, r): self.store.put("analysis_report", f"{org}:{r['id']}", r, org_id=org)

    def _hist(self, r, actor, action, note=""): r["history"].append({"at": self.now().isoformat(), "actor": actor, "action": action, "note": note})

    def create_report(self, org, period_id, title, note, scenario_ids, evidence, actor) -> dict:
        self._period(org, period_id)
        r = {"id": str(uuid.uuid4()), "org_id": org, "period_id": period_id, "title": _txt(title, "Title", 3, 200), "note": _txt(note, "Note", 0, 4000, required=False), "status": "DRAFT", "version": 0,
             "scenario_ids": self._scenarios_ok(org, period_id, scenario_ids), "evidence": evidence or [], "snapshot": None, "fingerprint": None, "created_by": actor, "created_at": self.now().isoformat(),
             "submitted_by": None, "submitted_at": None, "decided_by": None, "decided_at": None, "decision_note": "", "history": []}
        self._hist(r, actor, "CREATED")
        self._put(org, r)
        self.log("ANALYSIS_REPORT_CREATED", actor, r["id"], org, r["title"])
        return self._view(r)

    def _scenarios_ok(self, org, period_id, ids) -> List[str]:
        out = []
        for sid in ids or []:
            s = self.store.get("analysis_scenario", f"{org}:{sid}")
            if s is None:
                raise AnalysisNotFoundError("One of the selected scenarios was not found.")
            out.append(sid)
        return out

    def update_report(self, org, rid, title, note, scenario_ids, evidence, actor) -> dict:
        r = self._report(org, rid, for_update=True)
        if r["status"] not in ("DRAFT", "REJECTED"):
            raise AnalysisStateError(f"A {r['status'].lower()} report cannot be edited.")
        r["title"] = _txt(title, "Title", 3, 200) if title is not None else r["title"]
        if note is not None:
            r["note"] = _txt(note, "Note", 0, 4000, required=False)
        if scenario_ids is not None:
            r["scenario_ids"] = self._scenarios_ok(org, r["period_id"], scenario_ids)
        if evidence is not None:
            r["evidence"] = evidence
        self._hist(r, actor, "EDITED")
        self._put(org, r)
        self.log("ANALYSIS_REPORT_EDITED", actor, rid, org, r["title"])
        return self._view(r)

    def _snapshot(self, org, r) -> dict:
        cfg = self._cfg(org)
        fig = self.figures(org, r["period_id"], cfg["tags"])
        ratios = compute_ratios(fig)
        prior_p = previous_period(self.accounting, org, self._period(org, r["period_id"]))
        prior = self.figures(org, prior_p.id, cfg["tags"]) if prior_p else None
        comments = self.comments_map(org, r["period_id"])
        b = self._budget_rows(org, r["period_id"])
        scenarios = [self.run_scenario(org, sid) for sid in r["scenario_ids"]]
        return {"generated_at": self.now().isoformat(), "kind": "ACTUALS (posted ledger) with labelled FORECASTS", "period": fig["period"],
                "config": {"version": cfg["version"], "tags": cfg["tags"], "thresholds": cfg["thresholds"]},
                "totals": {k: s2(fig[k]) for k in ("assets", "liabilities", "equity_total", "revenue", "expenses", "net_income")}, "currencies": fig["currencies"], "posted_entries": fig["posted_entries"],
                "accounts": [{**{k: v for k, v in a.items() if k != "amount"}, "amount": str(a["amount"])} for a in fig["accounts"] if a["amount"] != 0],
                "ratios": ratios, "variance": period_variance(fig, prior, cfg["thresholds"], comments),
                "budget_variance": budget_variance(fig, None if b is None else {k: Decimal(v) for k, v in b["lines"].items()}, cfg["thresholds"], self.budget_meta(org, r["period_id"]), comments),
                "scenarios": scenarios, "evidence": r["evidence"], "limitations": LIMITATIONS,
                "data_status": {"period_status": fig["period"]["status"], "ratios_calculated": sum(1 for x in ratios if x["status"] == "CALCULATED"), "ratios_total": len(ratios)}}

    def submit_report(self, org, rid, actor) -> dict:
        r = self._report(org, rid, for_update=True)
        if r["status"] not in ("DRAFT", "REJECTED"):
            raise AnalysisStateError(f"A {r['status'].lower()} report cannot be submitted.")
        snap = self._snapshot(org, r)
        r.update(snapshot=snap, fingerprint=_sha(snap), status="SUBMITTED", version=r["version"] + 1, submitted_by=actor, submitted_at=self.now().isoformat(), decided_by=None, decided_at=None, decision_note="")
        self._hist(r, actor, "SUBMITTED", f"version {r['version']}")
        self._put(org, r)
        self.log("ANALYSIS_REPORT_SUBMITTED", actor, rid, org, f"version {r['version']}, fingerprint {r['fingerprint'][:12]}")
        return self._view(r)

    def _decide(self, org, rid, actor, approve: bool, note: str) -> dict:
        r = self._report(org, rid, for_update=True)
        if r["status"] != "SUBMITTED":
            raise AnalysisStateError(f"Only a submitted report can be {'approved' if approve else 'rejected'}; this one is {r['status'].lower()}.")
        if actor == r["submitted_by"]:
            raise AnalysisForbiddenError("You cannot " + ("approve" if approve else "reject") + " an analysis you submitted yourself. A second person must review it.")
        if approve and _sha(r["snapshot"]) != r["fingerprint"]:
            raise AnalysisStateError("The stored content no longer matches its fingerprint, so it cannot be approved. Submit it again.")
        if not approve:
            note = _txt(note, "A reason", 3, 1000)
        r.update(status="APPROVED" if approve else "REJECTED", decided_by=actor, decided_at=self.now().isoformat(), decision_note=_txt(note, "Note", 0, 1000, required=False))
        self._hist(r, actor, r["status"], r["decision_note"])
        self._put(org, r)
        self.log("ANALYSIS_REPORT_APPROVED" if approve else "ANALYSIS_REPORT_REJECTED", actor, rid, org, r["decision_note"] or r["title"])
        return self._view(r)

    def approve_report(self, org, rid, actor, note="") -> dict: return self._decide(org, rid, actor, True, note)
    def reject_report(self, org, rid, actor, reason) -> dict: return self._decide(org, rid, actor, False, reason)

    def _view(self, r, with_snapshot=True) -> dict:
        out = {k: v for k, v in r.items() if k != "snapshot"}
        out["has_snapshot"] = r["snapshot"] is not None
        if with_snapshot:
            out["snapshot"] = r["snapshot"]
        out["confidentiality"] = CONFIDENTIAL
        return out

    def get_report(self, org, rid) -> dict: return self._view(self._report(org, rid))

    def list_reports(self, org) -> List[dict]:
        rows = [d for _, d in self.store.list("analysis_report", org_id=org, prefix=f"{org}:")]
        return [self._view(r, with_snapshot=False) for r in sorted(rows, key=lambda r: r["created_at"], reverse=True)]

    def verify_report(self, org, rid) -> dict:
        r = self._report(org, rid)
        if r["snapshot"] is None:
            raise AnalysisStateError("This report has not been submitted yet, so there is nothing to verify.")
        intact = _sha(r["snapshot"]) == r["fingerprint"]
        snap = r["snapshot"]
        fig = self.figures(org, r["period_id"], snap["config"]["tags"])
        now_accounts = {a["id"]: str(a["amount"]) for a in fig["accounts"] if a["amount"] != 0}
        then_accounts = {a["id"]: a["amount"] for a in snap["accounts"]}
        diffs = []
        for aid in sorted(set(now_accounts) | set(then_accounts)):
            if now_accounts.get(aid) != then_accounts.get(aid):
                code = next((a["code"] for a in fig["accounts"] if a["id"] == aid), aid)
                diffs.append({"account": code, "then": then_accounts.get(aid, "0.00"), "now": now_accounts.get(aid, "0.00")})
        then_ratios, now_ratios = ratio_values(snap["ratios"]), ratio_values(compute_ratios(fig))
        ratio_diffs = [{"ratio": k, "then": then_ratios[k], "now": now_ratios.get(k)} for k in then_ratios if then_ratios[k] != now_ratios.get(k)]
        return {"integrity_ok": intact, "matches_ledger_now": not diffs and not ratio_diffs, "account_differences": diffs, "ratio_differences": ratio_diffs, "fingerprint": r["fingerprint"], "checked_at": self.now().isoformat(),
                "meaning": ("The stored report is exactly as submitted. " if intact else "The stored report does NOT match its fingerprint; it has been altered. ")
                           + ("The ledger still gives the same figures." if not diffs and not ratio_diffs else "The ledger now gives different figures (for example, a late posting).")}

    def export_csv(self, org, rid, actor) -> dict:
        r = self._report(org, rid)
        if r["status"] != "APPROVED":
            raise AnalysisStateError("Only an approved report can be exported.")
        s = r["snapshot"]
        buf = io.StringIO()
        w = csv.writer(buf, lineterminator="\n")
        w.writerow([CONFIDENTIAL]); w.writerow(["Report", r["title"]]); w.writerow(["Period", f"{s['period']['name']} ({s['period']['start']} to {s['period']['end']})"])
        w.writerow(["Version", r["version"]]); w.writerow(["Prepared by (user id)", r["submitted_by"]]); w.writerow(["Approved by (user id)", r["decided_by"]]); w.writerow(["Approved at", r["decided_at"]])
        w.writerow(["Generated at", s["generated_at"]]); w.writerow(["Fingerprint (SHA-256)", r["fingerprint"]]); w.writerow(["Data status", f"Period {s['data_status']['period_status']}; ratios calculated {s['data_status']['ratios_calculated']} of {s['data_status']['ratios_total']}"]); w.writerow([])
        w.writerow(["RATIOS (actual)"]); w.writerow(["Ratio", "Group", "Value", "Unit", "Status", "Formula", "Numerator", "Denominator", "Note"])
        for x in s["ratios"]:
            w.writerow([x["name"], x["group"], x["value"] if x["value"] is not None else "", x["unit"], x["status"], x["formula"], x["numerator"]["amount"], x["denominator"]["amount"] if x["denominator"] else "", x["reason"]])
        w.writerow([]); w.writerow(["ACCOUNT FIGURES (actual)"]); w.writerow(["Code", "Account", "Type", "Basis", "Classification", "Amount"])
        for a in s["accounts"]:
            w.writerow([a["code"], a["name"], a["type"], a["basis"], a["tag"] or "", a["amount"]])
        v = s["variance"]
        w.writerow([]); w.writerow(["VARIANCE VS PRIOR PERIOD (actual)"])
        if v["status"] == "OK":
            w.writerow(["Code", "Account", "Current", "Prior", "Change", "Change %", "Material"])
            for x in v["rows"]:
                w.writerow([x["code"], x["name"], x["current"], x["prior"], x["change"], x["change_pct"] or "new", "yes" if x["material"] else "no"])
        else:
            w.writerow([v["message"]])
        for sc in s["scenarios"]:
            w.writerow([]); w.writerow([f"FORECAST - {sc['scenario']['name']} (not actual results)"]); w.writerow(["Month", "Revenue", "Expenses", "Net cash", "Closing cash"])
            for x in sc["rows"]:
                w.writerow([x["month"], x["revenue"], x["expenses"], x["net_cash"], x["closing_cash"]])
        w.writerow([]); w.writerow(["LIMITATIONS"]); [w.writerow([x]) for x in s["limitations"]]
        self.log("ANALYSIS_REPORT_EXPORTED", actor, rid, org, f"CSV export of version {r['version']}")
        return {"filename": f"analysis-{r['id'][:8]}-v{r['version']}.csv", "content": buf.getvalue(), "content_type": "text/csv; charset=utf-8"}
