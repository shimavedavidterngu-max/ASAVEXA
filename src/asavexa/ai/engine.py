"""AiEngine: Explain, Detect, Recommend, Prove over one organisation's records.

Pure: no database, no web framework, no clock of its own (the caller passes `now`), no network and
no language model. The API layer gathers the records (the same `PassportInputs` the Financial
Passport uses) and hands them in. Nothing here writes, posts, matches or verifies anything; where
it proposes an action, the proposal is marked as not applied.
"""
from __future__ import annotations

import hashlib
import json
import re
import statistics
import uuid
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Dict, List, Optional, Tuple

from ..passport import builder as B
from ..passport.builder import PassportInputs
from ..standards import catalog as CAT
from . import knowledge as K
from .errors import AiSubjectNotFoundError, AiValidationError
from .grounding import (HIGH, LOW, MEDIUM, confidence, human_review, refusal, source_record, unavailable,
                        validate_item)

SCHEMA = "asavexa-ai/1"
DISCLOSURE = ("Produced by ASAVEXA's rule-based reasoning over your own records. It uses no outside AI model, "
              "cannot see anything that is not in your records, and changes nothing.")
MODES = ("EXPLAIN", "DETECT", "RECOMMEND", "PROVE")
ZERO = Decimal("0.00")
MAX_ITEMS = 50
BACKDATE_DAYS = 45
DUPLICATE_WINDOW_DAYS = 7
OUTLIER_MIN_SAMPLE = 8
OUTLIER_Z = 3.5
WIDE_MATCH_DAYS = 14
FIGURES = {"revenue": "revenue", "expenses": "expenses", "net_income": "net_income", "assets": "assets", "liabilities": "liabilities"}
FIGURE_TYPES = {"revenue": ("REVENUE",), "expenses": ("EXPENSE",), "assets": ("ASSET",), "liabilities": ("LIABILITY",),
                "net_income": ("REVENUE", "EXPENSE")}
UUID_RE = re.compile(r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}")
JRN_RE = re.compile(r"\bJRN-\d{3,}\b", re.I)
EVIDENCE_LABEL = {"VERIFIED": "verified", "UNVERIFIED": "uploaded but not yet verified",
                  "DEFECTIVE": "rejected or defective", "MISSING": "missing"}


def _d(x) -> Decimal:
    return Decimal(str(x))


def _canonical(obj) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), default=str)


class AiEngine:
    def __init__(self, inp: PassportInputs, now: datetime):
        self.inp = inp
        self.now = B._aware(now)
        self.accounts = {a.id: a for a in inp.accounts}
        self.periods = {p.id: p for p in inp.periods}
        self.journals = list(inp.journals)
        self.posted = [j for j in self.journals if B._val(j.status) != "DRAFT"]
        self.by_id = {j.id: j for j in self.journals}
        self.by_number = {j.journal_number.upper(): j for j in self.journals}
        self.ev_by_id = {e.id: e for e in inp.evidence}
        self.ev_by_journal: Dict[str, list] = {}
        self.ev_by_tx: Dict[str, list] = {}
        for e in inp.evidence:
            if e.linked_journal_id:
                self.ev_by_journal.setdefault(e.linked_journal_id, []).append(e)
            if e.linked_transaction_ref:
                self.ev_by_tx.setdefault(e.linked_transaction_ref, []).append(e)
        self.txs = {t.id: t for t in inp.bank_transactions}
        self.txs_by_journal: Dict[str, list] = {}
        for t in inp.bank_transactions:
            if t.matched_journal_id:
                self.txs_by_journal.setdefault(t.matched_journal_id, []).append(t)
        self.recons = {r.id: r for r in inp.reconciliations}
        self.standards = inp.standards or {"configured": False}
        self.policies = {p["code"]: p for p in (self.standards.get("policies") or [])}

    # ------------------------------------------------------------- small helpers
    def _who(self, uid: Optional[str]) -> Optional[str]:
        return B._who(self.inp, uid)

    def _acct(self, aid: str):
        return self.accounts.get(aid)

    def _acct_label(self, aid: str) -> str:
        a = self._acct(aid)
        return f"{a.code} {a.name}" if a else f"unknown account {aid[:8]}"

    def _atype(self, aid: str) -> str:
        a = self._acct(aid)
        return B._val(a.type) if a else "UNKNOWN"

    def _amount(self, j) -> Decimal:
        return _d(j.total_debits())

    def _ev(self, j):
        rec = B.evidence_for_journal(j, self.ev_by_journal, self.ev_by_id, self.ev_by_tx)
        if rec is None:
            return "MISSING", None
        s = B._val(rec.status)
        return ("VERIFIED" if s == "VERIFIED" else "UNVERIFIED" if s == "UPLOADED" else "DEFECTIVE"), rec

    def _ev_row(self, e) -> dict:
        return {"id": e.id, "type": B._val(e.type), "status": B._val(e.status), "filename": e.original_filename,
                "sha256": e.file_hash, "size_bytes": e.size_bytes, "uploaded_by": self._who(e.uploaded_by),
                "uploaded_at": B._iso(e.uploaded_at), "verified_by": self._who(e.verified_by),
                "verified_at": B._iso(e.verified_at), "verification_note": e.verification_note,
                "rejection_reason": e.rejection_reason, "path": f"/evidence/{e.id}"}

    def _all_evidence_for(self, j) -> list:
        cands = list(self.ev_by_journal.get(j.id, []))
        if j.evidence_ref and j.evidence_ref in self.ev_by_id and self.ev_by_id[j.evidence_ref] not in cands:
            cands.append(self.ev_by_id[j.evidence_ref])
        if j.transaction_ref:
            for e in self.ev_by_tx.get(j.transaction_ref, []):
                if e not in cands:
                    cands.append(e)
        return cands

    # ------------------------------------------------------------- journal facts
    def _facts(self, j) -> dict:
        lines = sorted(j.lines, key=lambda l: l.line_no)
        dr = [(l, self._atype(l.account_id)) for l in lines if _d(l.debit_amount) > 0]
        cr = [(l, self._atype(l.account_id)) for l in lines if _d(l.credit_amount) > 0]
        reversal = bool(j.reversal_of_journal_id)
        nature = K.classify_nature([t for _, t in dr], [t for _, t in cr], reversal)
        implied, words = K.implied_type(j.description)
        types_present = {t for _, t in dr + cr}
        if reversal:
            consistency = {"status": "NOT_APPLICABLE", "implied_type": None, "words": [],
                           "detail": "A reversal copies the original entry the other way round, so its wording is not tested."}
        elif implied is None:
            consistency = {"status": "NO_SIGNAL", "implied_type": None, "words": words,
                           "detail": "The description gives no clear hint about the kind of account to use."}
        elif implied in types_present:
            consistency = {"status": "CONSISTENT", "implied_type": implied, "words": words,
                           "detail": f"The wording ({', '.join(repr(w) for w in words)}) points to {implied.lower()} accounts, and the entry uses one."}
        else:
            consistency = {"status": "MISMATCH", "implied_type": implied, "words": words,
                           "detail": f"The wording ({', '.join(repr(w) for w in words)}) points to {implied.lower()} accounts, "
                                     f"but the entry uses only {', '.join(sorted(t.lower() for t in types_present))} accounts."}
        contra = (not reversal) and (any(t == "REVENUE" for _, t in dr) or any(t == "EXPENSE" for _, t in cr))
        state, rec = self._ev(j)
        period = self.periods.get(j.period_id)
        sod = bool(j.posted_by and j.posted_by == j.created_by)
        return {"lines": lines, "dr": dr, "cr": cr, "nature": nature, "implied": implied, "consistency": consistency,
                "contra": contra, "ev_state": state, "ev_rec": rec, "period": period, "sod": sod,
                "amount": self._amount(j), "reversal": reversal}

    def _policies_for(self, j, f) -> List[dict]:
        pairs = [(self._acct(l.account_id).name, t) for l, t in f["dr"] + f["cr"] if self._acct(l.account_id)]
        out = []
        for code, why in K.policy_codes_for(pairs, j.description):
            p = self.policies.get(code)
            if p is None:
                continue
            label = next((o["label"] for o in p["options"] if o["code"] == p["effective"]), p["effective"])
            out.append({"code": code, "name": p["name"], "effective": p["effective"], "effective_label": label,
                        "locked": p["locked"], "overridden": p["overridden"], "why_relevant": why, "note": p["note"]})
        return out

    # ------------------------------------------------------------- chain stages
    def _stage_framework(self, types_touched: List[str]) -> dict:
        s = self.standards
        if not s.get("configured"):
            return unavailable("No reporting framework has been configured for this organisation, so ASAVEXA cannot say which "
                               "standard applies. Set it under Standards & Policies.")
        fw = CAT.FRAMEWORKS.get(s["framework"], {}).get("name", s["framework"])
        stmts = sorted({K.STATEMENT_FOR_TYPE[t] for t in types_touched if t in K.STATEMENT_FOR_TYPE})
        return {"available": True, "framework_code": s["framework"], "framework": fw,
                "jurisdiction": CAT.JURISDICTIONS.get(s.get("jurisdiction"), s.get("jurisdiction")),
                "entity_type": CAT.ENTITY_TYPES.get(s.get("entity_type"), s.get("entity_type")),
                "statements_affected": stmts,
                "note": (s.get("disclaimer") or "Suggested defaults, not legal advice."),
                "path": "/standards"}

    def _stage_journal(self, j) -> dict:
        f = self._facts(j)
        lines = []
        for l in f["lines"]:
            a = self._acct(l.account_id)
            lines.append({"line_no": l.line_no, "account_id": l.account_id, "account_code": a.code if a else None,
                          "account_name": a.name if a else None, "account_type": self._atype(l.account_id),
                          "debit": B._money(_d(l.debit_amount)), "credit": B._money(_d(l.credit_amount)),
                          "description": l.description or None})
        p = f["period"]
        return {"available": True, "id": j.id, "number": j.journal_number, "date": B._iso(j.date),
                "status": B._val(j.status), "description": j.description, "currency": j.currency,
                "amount": B._money(f["amount"]), "lines": lines,
                "period": {"id": p.id, "name": p.name, "status": B._val(p.status)} if p else None,
                "created_by": self._who(j.created_by), "created_at": B._iso(j.created_at),
                "posted_by": self._who(j.posted_by), "posted_at": B._iso(j.posted_at),
                "reversal_of": j.reversal_of_journal_id, "reversed_by": j.reversed_by_journal_id,
                "path": f"/accounting/journals/{j.id}"}

    def _stage_evidence(self, j, f) -> dict:
        recs = self._all_evidence_for(j)
        expected = list(K.expected_evidence(f["nature"]["code"], j.description))
        if not recs:
            return {"available": False, "state": "MISSING", "records": [], "expected_types": expected,
                    "note": f"MISSING EVIDENCE: no evidence record is linked to journal {j.journal_number}. "
                            f"For this kind of transaction a person would normally expect: {', '.join(t.lower().replace('_', ' ') for t in expected)}."}
        rows = [self._ev_row(e) for e in recs]
        s = f["ev_state"]
        return {"available": True, "state": s, "records": rows, "expected_types": expected,
                "note": f"Best supporting evidence is {EVIDENCE_LABEL[s]}."}

    def _stage_treatment(self, j, f) -> dict:
        n = f["nature"]
        pol = self._policies_for(j, f)

        def side(pairs, key):
            return [{"account": self._acct_label(l.account_id), "type": t, "amount": B._money(_d(getattr(l, key)))} for l, t in pairs]
        if not self.standards.get("configured"):
            note = "No framework is configured, so no accounting policy can be cited for this entry."
        elif not pol:
            note = "None of this framework's configurable policies is clearly touched by the accounts used."
        else:
            note = "The policies below govern how an item like this is measured or recognised under the configured framework."
        return {"available": True, "classification": n, "debits": side(f["dr"], "debit_amount"),
                "credits": side(f["cr"], "credit_amount"), "policies": pol, "description_check": f["consistency"],
                "note": note}

    def _standard_factors(self, f, framework_ok: bool) -> Tuple[List[dict], List[str]]:
        fac: List[dict] = []
        why: List[str] = []
        j_draft = False
        s = f["ev_state"]
        fac.append({"factor": "Supporting evidence", "effect": {"VERIFIED": 0, "UNVERIFIED": -15, "DEFECTIVE": -30, "MISSING": -35}[s],
                    "detail": f"Evidence is {EVIDENCE_LABEL[s]}."})
        if s != "VERIFIED":
            why.append(f"Supporting evidence is {EVIDENCE_LABEL[s]}.")
        c = f["consistency"]
        eff = {"MISMATCH": -20, "NO_SIGNAL": -5}.get(c["status"], 0)
        fac.append({"factor": "Description matches the accounts used", "effect": eff, "detail": c["detail"]})
        if c["status"] == "MISMATCH":
            why.append("The description does not match the kind of accounts used.")
        if f["contra"] or not f["nature"]["usual"]:
            fac.append({"factor": "Unusual debit/credit pattern", "effect": -15,
                        "detail": f"This is {f['nature']['meaning']}, which is not the usual direction."})
            why.append("The debit/credit pattern is unusual.")
        if f["sod"]:
            fac.append({"factor": "Same person prepared and posted", "effect": -10, "detail": "The preparer and the poster are the same person."})
            why.append("The same person prepared and posted this journal.")
        if not framework_ok:
            fac.append({"factor": "Reporting framework configured", "effect": -10, "detail": "No framework is configured."})
        return fac, why

    # ------------------------------------------------------------- assemble a journal-based item
    def _journal_item(self, j, title: str, summary: str, points: List[str], extra_factors=None, extra_reasons=None,
                      force_review: bool = False, extra_sources=None, extra: Optional[dict] = None) -> dict:
        f = self._facts(j)
        fw = self._stage_framework([t for _, t in f["dr"] + f["cr"]])
        fac, why = self._standard_factors(f, fw["available"])
        fac += list(extra_factors or [])
        why += list(extra_reasons or [])
        if B._val(j.status) == "DRAFT":
            fac.append({"factor": "Journal is a draft", "effect": -25, "detail": "A draft is not yet part of the ledger."})
            why.append("The journal is still a draft.")
        conf = confidence(fac)
        if conf["level"] != HIGH:
            why.append(f"Confidence is {conf['level']} ({conf['score']}).")
        sources = [source_record("JOURNAL", j.id, f"Journal {j.journal_number}", j.description, f"/accounting/journals/{j.id}")]
        seen = set()
        for l, _t in f["dr"] + f["cr"]:
            if l.account_id not in seen:
                seen.add(l.account_id)
                sources.append(source_record("ACCOUNT", l.account_id, self._acct_label(l.account_id), self._atype(l.account_id)))
        for e in self._all_evidence_for(j):
            sources.append(source_record("EVIDENCE", e.id, e.original_filename, f"{B._val(e.type)}, {B._val(e.status)}", f"/evidence/{e.id}"))
        for t in self.txs_by_journal.get(j.id, []):
            sources.append(source_record("BANK_TRANSACTION", t.id, f"Bank line {B._iso(t.transaction_date)}: {t.description}",
                                         B._val(t.status)))
        if f["period"]:
            sources.append(source_record("PERIOD", f["period"].id, f"Period {f['period'].name}", B._val(f["period"].status)))
        have = {(r["kind"], r["id"]) for r in sources}
        sources += [r for r in (extra_sources or []) if (r["kind"], r["id"]) not in have]
        item = {
            "title": title,
            "conclusion": {"summary": summary, "points": points},
            "source_records": sources,
            "evidence": self._stage_evidence(j, f),
            "journal": self._stage_journal(j),
            "accounting_treatment": self._stage_treatment(j, f),
            "reporting_framework": fw,
            "confidence": conf,
            "human_review": human_review(force_review or bool(why), why or ["Advisory output; always read-only."],
                                         "an approver or finance officer" if why else None),
        }
        if extra:
            item.update(extra)
        return validate_item(item)

    # ------------------------------------------------------------- envelope
    def _envelope(self, mode: str, question: str, interpreted: dict, summary: str, items: List[dict],
                  limitations: List[str], extra: Optional[dict] = None) -> dict:
        body = {"mode": mode, "interpreted_as": interpreted, "summary": summary, "items": items, "limitations": limitations}
        if extra:
            body.update(extra)
        fp = hashlib.sha256(_canonical(body).encode()).hexdigest()
        return {"schema": SCHEMA, "response_id": str(uuid.uuid4()), "generated_at": self.now.isoformat(),
                "question": question, "fingerprint": fp, "disclosure": DISCLOSURE, "grounded": True, **body}

    def _lookup_journal(self, ref: str):
        ref = (ref or "").strip()
        if not ref:
            raise AiValidationError("Say which journal (its number, like JRN-000003, or its id).")
        j = self.by_id.get(ref) or self.by_number.get(ref.upper())
        if j is None:
            raise AiSubjectNotFoundError(f"There is no journal {ref!r} in this organisation.")
        return j

    def _lookup_tx(self, ref: str):
        t = self.txs.get((ref or "").strip())
        if t is None:
            raise AiSubjectNotFoundError(f"There is no bank transaction {ref!r} in this organisation.")
        return t

    # =============================================================== EXPLAIN
    def explain(self, subject_type: str, subject_id: str, question: Optional[str] = None) -> dict:
        st = (subject_type or "").lower()
        q = question or "Why was this transaction classified this way?"
        if st == "journal":
            j = self._lookup_journal(subject_id)
            item = self._explain_journal(j)
            interp = {"mode": "EXPLAIN", "subject_type": "journal", "subject_id": j.id, "subject_label": j.journal_number}
            return self._envelope("EXPLAIN", q, interp, item["conclusion"]["summary"], [item], self._limits("explain"))
        if st == "bank_transaction":
            t = self._lookup_tx(subject_id)
            item = self._explain_bank_tx(t)
            interp = {"mode": "EXPLAIN", "subject_type": "bank_transaction", "subject_id": t.id, "subject_label": t.description}
            return self._envelope("EXPLAIN", q, interp, item["conclusion"]["summary"], [item], self._limits("explain"))
        raise AiValidationError("subject_type must be 'journal' or 'bank_transaction'.")

    def _limits(self, mode: str) -> List[str]:
        base = ["ASAVEXA does not choose accounts automatically. It explains the choice recorded by the person who prepared the entry.",
                "Wording checks use a fixed list of common words and are hints, not verdicts.",
                "Suggested accounting standards are defaults, not legal advice; confirm with a qualified accountant."]
        if mode == "detect":
            base.insert(0, "A flag means 'worth a look', not 'wrong'. Nothing here is a finding of error or fraud.")
        if mode == "recommend":
            base.insert(0, "Every recommendation is a proposal. ASAVEXA applies nothing; a person must act on it and approve it.")
        if mode == "prove":
            base.insert(0, "'Proven' means the records in ASAVEXA support the claim. It does not authenticate the documents themselves.")
        return base

    def _explain_journal(self, j) -> dict:
        f = self._facts(j)
        n = f["nature"]
        dr = "; ".join(f"{self._acct_label(l.account_id)} ({t.lower()}) {B._money(_d(l.debit_amount))}" for l, t in f["dr"])
        cr = "; ".join(f"{self._acct_label(l.account_id)} ({t.lower()}) {B._money(_d(l.credit_amount))}" for l, t in f["cr"])
        summary = (f"Journal {j.journal_number} ('{j.description}', {B._iso(j.date)}, {j.currency} {B._money(f['amount'])}) is classified as "
                   f"{n['meaning']}.")
        pts = [f"Why: {n['rule']}", f"Debited: {dr or 'nothing'}.", f"Credited: {cr or 'nothing'}.",
               f"Who chose this: prepared by {self._who(j.created_by) or 'unknown'}"
               + (f" and posted by {self._who(j.posted_by)}" if j.posted_by else " (not yet posted)")
               + ". The accounts are their choice; ASAVEXA explains it rather than deciding it.",
               f"Wording check: {f['consistency']['detail']}"]
        if not n["usual"] or f["contra"]:
            pts.append("This is not the usual direction for these account types, so it deserves a second look.")
        pol = self._policies_for(j, f)
        if pol:
            pts += [f"Policy: {p['name']} is '{p['effective_label']}'" + (" (fixed by the framework)" if p["locked"] else "")
                    + f" because {p['why_relevant']}." for p in pol]
        elif self.standards.get("configured"):
            pts.append("No configurable accounting policy is clearly involved.")
        else:
            pts.append("No framework is configured, so no policy is cited.")
        ev = f["ev_state"]
        pts.append(f"Evidence: {EVIDENCE_LABEL[ev]}.")
        types = [t for _, t in f["dr"] + f["cr"]]
        if self.standards.get("configured"):
            pts.append("Reported in: " + "; ".join(sorted({K.STATEMENT_FOR_TYPE[t] for t in types if t in K.STATEMENT_FOR_TYPE})) + ".")
        return self._journal_item(j, f"Why journal {j.journal_number} is classified this way", summary, pts)

    def _explain_bank_tx(self, t) -> dict:
        st = B._val(t.status)
        amt = _d(t.debit_amount) or _d(t.credit_amount)
        direction = "money in (a debit on the bank account)" if _d(t.debit_amount) else "money out (a credit on the bank account)"
        rec = self.recons.get(t.reconciliation_id)
        stage_text = {
            "IMPORTED": "has been imported but not yet matched to the ledger",
            "MATCHED": "has been matched to a ledger journal, awaiting approval",
            "APPROVED": "has been matched and individually approved by a checker",
            "RECONCILED": "is matched, approved and locked in a finalised reconciliation",
            "REVIEW_REQUIRED": "was left for a person to decide because more than one ledger entry fits",
            "UNMATCHED": "has no ledger entry that fits",
            "REJECTED": "had its proposed match rejected by a checker",
        }.get(st, st.lower())
        j = self.by_id.get(t.matched_journal_id) if t.matched_journal_id else None
        pts = [f"Direction: {direction}, {t.currency} {B._money(amt)} on {B._iso(t.transaction_date)}.",
               f"Status {st}: this line {stage_text}."]
        if t.match_reason:
            pts.append(f"Recorded reason: {t.match_reason}")
        if t.match_rule:
            pts.append(f"Rule applied: {t.match_rule}.")
        if t.match_history:
            last = t.match_history[-1]
            pts.append("Latest decision in the line's own history: " + _canonical({k: last.get(k) for k in ("outcome", "decided_by", "at") if k in last}))
        if rec:
            pts.append(f"Part of reconciliation '{rec.name}' ({B._val(rec.status)}).")
        summary = f"Bank line '{t.description}' ({B._iso(t.transaction_date)}, {t.currency} {B._money(amt)}) {stage_text}."
        sources = [source_record("BANK_TRANSACTION", t.id, f"Bank line {B._iso(t.transaction_date)}: {t.description}", st)]
        if rec:
            sources.append(source_record("RECONCILIATION", rec.id, f"Reconciliation {rec.name}", B._val(rec.status), f"/reconciliation/{rec.id}"))
        if j is not None:
            item = self._journal_item(
                j, f"Why bank line '{t.description}' is {st}", summary, pts,
                extra_factors=[] if st in ("MATCHED", "APPROVED", "RECONCILED") else [
                    {"factor": "Bank match not final", "effect": -15, "detail": f"The match is {st}."}],
                extra_reasons=[] if st in ("MATCHED", "APPROVED", "RECONCILED") else [f"The bank match is {st}."],
                extra_sources=sources)
            return item
        cands = self._evidence_for_tx(t)
        fw = self._stage_framework([])
        fac = [{"factor": "No ledger journal behind this line", "effect": -30, "detail": "It is not matched to any journal."}]
        if not fw["available"]:
            fac.append({"factor": "Reporting framework configured", "effect": -10, "detail": "No framework is configured."})
        conf = confidence(fac)
        why = [f"The bank line is {st} and has no ledger journal."]
        if conf["level"] != HIGH:
            why.append(f"Confidence is {conf['level']} ({conf['score']}).")
        ev = ({"available": True, "state": "UNVERIFIED", "records": [self._ev_row(e) for e in cands], "expected_types": ["BANK_STATEMENT"],
               "note": "Evidence is linked to this bank line."} if cands else
              {"available": False, "state": "MISSING", "records": [], "expected_types": ["BANK_STATEMENT"],
               "note": "MISSING EVIDENCE: nothing is linked to this bank line."})
        return validate_item({
            "title": f"Why bank line '{t.description}' is {st}",
            "conclusion": {"summary": summary, "points": pts},
            "source_records": sources, "evidence": ev,
            "journal": unavailable("This bank line is not matched to a journal, so no ledger entry exists for it yet."),
            "accounting_treatment": unavailable("With no journal there is no recorded accounting treatment. See Recommend for a proposed entry."),
            "reporting_framework": fw, "confidence": conf,
            "human_review": human_review(True, why, "the person doing the bank reconciliation"),
        })

    def _evidence_for_tx(self, t) -> list:
        out = []
        for key in (t.external_ref, t.id):
            if key:
                out += [e for e in self.ev_by_tx.get(key, []) if e not in out]
        return out

    # =============================================================== DETECT
    DETECT_RULES = (
        ("CONTRA_PAIRING", "Income debited or expense credited", "FACT", True),
        ("DUPLICATE_POSSIBLE", "Possible duplicate of another journal", "FACT", True),
        ("PERIOD_MISMATCH", "Journal date falls outside its accounting period", "FACT", True),
        ("BACKDATED_POSTING", f"Posted more than {BACKDATE_DAYS} days after its date", "FACT", True),
        ("FUTURE_DATED", "Dated after the day it was posted", "FACT", True),
        ("SAME_PERSON_PREPARED_AND_POSTED", "Prepared and posted by the same person", "FACT", True),
        ("OWNER_MOVEMENT", "Money moving between the owners and the business", "FACT", True),
        ("DESCRIPTION_MISMATCH", "Description does not match the accounts used", "FACT", True),
        ("AMOUNT_OUTLIER", "Unusually large amount compared with the other journals", "STATISTICAL", True),
        ("BANK_LINE_UNMATCHED", "Bank line with no matching ledger entry", "FACT", True),
        ("BANK_LINE_NEEDS_REVIEW", "Bank line left for a person to decide", "FACT", True),
        ("BANK_LINE_REJECTED", "Bank line whose proposed match was rejected", "FACT", True),
        ("BANK_AMOUNT_OUTLIER", "Unusually large bank line", "STATISTICAL", True),
        ("REVERSAL", "Reversed journal or reversal entry", "FACT", False),
        ("WEEKEND_DATE", "Dated on a weekend", "FACT", False),
        ("ROUND_AMOUNT", "Large round-number amount", "FACT", False),
        ("EVIDENCE_GAP", "Evidence missing, unverified or defective", "FACT", False),
    )

    @staticmethod
    def _flag(rule: str, label: str, detail: str, points: int, primary: bool, kind: str) -> dict:
        return {"rule": rule, "label": label, "detail": detail, "points": points, "primary": primary, "kind": kind}

    @staticmethod
    def _outliers(values: Dict[str, Decimal]) -> Dict[str, float]:
        """Modified z-score (median / MAD). {id: z} for values that are clearly above the rest."""
        if len(values) < OUTLIER_MIN_SAMPLE:
            return {}
        xs = [float(v) for v in values.values()]
        med = statistics.median(xs)
        mad = statistics.median([abs(x - med) for x in xs])
        out = {}
        for k, v in values.items():
            x = float(v)
            if mad > 0:
                z = 0.6745 * (x - med) / mad
                if z > OUTLIER_Z and x > 2 * med:
                    out[k] = round(z, 1)
        return out

    def detect(self, period_id: Optional[str] = None, limit: int = 20, question: Optional[str] = None) -> dict:
        q = question or "Find unusual transactions."
        if not isinstance(limit, int) or isinstance(limit, bool) or not (1 <= limit <= MAX_ITEMS):
            raise AiValidationError(f"limit must be a whole number from 1 to {MAX_ITEMS}.")
        period = None
        if period_id:
            period = self.periods.get(period_id)
            if period is None:
                raise AiSubjectNotFoundError("There is no such accounting period in this organisation.")
        in_scope = [j for j in self.posted if not period or j.period_id == period.id]
        sample = [j for j in self.posted if not j.reversal_of_journal_id]
        outl: Dict[str, float] = {}
        for cur in {j.currency for j in sample}:
            outl.update(self._outliers({j.id: self._amount(j) for j in sample if j.currency == cur}))

        flags: Dict[str, List[dict]] = {}

        def add(jid, fl):
            flags.setdefault(jid, []).append(fl)

        dup_groups: Dict[tuple, list] = {}
        for j in sample:
            if B._val(j.status) == "REVERSED":
                continue
            f = self._facts(j)
            key = (j.currency, str(f["amount"]), tuple(sorted((l.account_id, "D" if _d(l.debit_amount) > 0 else "C") for l in f["lines"])))
            dup_groups.setdefault(key, []).append(j)
        dup_of: Dict[str, object] = {}
        for grp in dup_groups.values():
            grp.sort(key=lambda x: (x.date, x.journal_number))
            for i in range(1, len(grp)):
                for k in range(i - 1, -1, -1):
                    if (grp[i].date - grp[k].date).days <= DUPLICATE_WINDOW_DAYS:
                        dup_of[grp[i].id] = grp[k]
                        break

        for j in in_scope:
            f = self._facts(j)
            n = f["nature"]
            if f["contra"]:
                add(j.id, self._flag("CONTRA_PAIRING", "Income debited or expense credited",
                                     f"This is {n['meaning']}: the opposite of how these accounts normally move.", 30, True, "FACT"))
            if j.id in dup_of:
                o = dup_of[j.id]
                add(j.id, self._flag("DUPLICATE_POSSIBLE", "Possible duplicate",
                                     f"Same amount ({j.currency} {B._money(f['amount'])}) on the same accounts and sides as {o.journal_number} "
                                     f"({B._iso(o.date)}), within {DUPLICATE_WINDOW_DAYS} days.", 40, True, "FACT"))
            p = f["period"]
            if p is None or not (p.start_date <= j.date <= p.end_date):
                add(j.id, self._flag("PERIOD_MISMATCH", "Date outside its period",
                                     "The journal date is not inside its accounting period" + (f" {p.name} ({B._iso(p.start_date)} to {B._iso(p.end_date)})." if p else " (the period is missing)."),
                                     35, True, "FACT"))
            if j.posted_at is not None:
                gap = (B._aware(j.posted_at).date() - j.date).days
                if gap > BACKDATE_DAYS:
                    add(j.id, self._flag("BACKDATED_POSTING", "Posted long after its date", f"Dated {B._iso(j.date)} but posted {gap} days later.", 20, True, "FACT"))
                elif gap < -1:
                    add(j.id, self._flag("FUTURE_DATED", "Dated after it was posted", f"Dated {B._iso(j.date)}, {-gap} days after it was posted.", 15, True, "FACT"))
            if f["sod"]:
                add(j.id, self._flag("SAME_PERSON_PREPARED_AND_POSTED", "Prepared and posted by the same person",
                                     f"{self._who(j.created_by)} both prepared and posted it.", 15, True, "FACT"))
            if n["code"] in ("OWNER_CONTRIBUTION", "OWNER_DISTRIBUTION", "EXPENSE_BY_OWNERS"):
                add(j.id, self._flag("OWNER_MOVEMENT", "Owner-related movement", f"This is {n['meaning']}.", 20, True, "FACT"))
            if f["consistency"]["status"] == "MISMATCH":
                add(j.id, self._flag("DESCRIPTION_MISMATCH", "Description does not match the accounts", f["consistency"]["detail"], 20, True, "FACT"))
            if j.id in outl:
                add(j.id, self._flag("AMOUNT_OUTLIER", "Unusually large amount",
                                     f"{j.currency} {B._money(f['amount'])} is far above the typical journal (robust score {outl[j.id]}).", 25, True, "STATISTICAL"))
            if B._val(j.status) == "REVERSED" or f["reversal"]:
                add(j.id, self._flag("REVERSAL", "Reversal", "A reversed journal or the reversal itself; worth confirming the reason.", 8, False, "FACT"))
            if j.date.weekday() >= 5:
                add(j.id, self._flag("WEEKEND_DATE", "Weekend date", f"{B._iso(j.date)} is a {j.date.strftime('%A')}.", 5, False, "FACT"))
            if f["amount"] >= 10000 and f["amount"] % 10000 == 0:
                add(j.id, self._flag("ROUND_AMOUNT", "Round amount", f"{j.currency} {B._money(f['amount'])} is an exact multiple of 10,000.", 5, False, "FACT"))
            if f["ev_state"] != "VERIFIED":
                add(j.id, self._flag("EVIDENCE_GAP", "Evidence gap", f"Evidence is {EVIDENCE_LABEL[f['ev_state']]}.",
                                     {"MISSING": 10, "UNVERIFIED": 5, "DEFECTIVE": 15}[f["ev_state"]], False, "FACT"))

        items: List[Tuple[int, str, dict]] = []
        for j in in_scope:
            fl = flags.get(j.id, [])
            if not any(x["primary"] for x in fl):
                continue
            score = min(100, sum(x["points"] for x in fl))
            sev = "HIGH" if score >= 60 else "MEDIUM" if score >= 35 else "LOW"
            stat = any(x["kind"] == "STATISTICAL" for x in fl)
            reasons = [f"Flagged: {x['label']}." for x in fl if x["primary"]]
            pts = [f"{x['label']}: {x['detail']}" for x in sorted(fl, key=lambda x: -x["points"])]
            summary = (f"Journal {j.journal_number} ('{j.description}', {B._iso(j.date)}, {j.currency} {B._money(self._amount(j))}) "
                       f"is worth a look: {len([x for x in fl if x['primary']])} unusual signal(s), {sev} priority.")
            item = self._journal_item(
                j, f"Unusual: journal {j.journal_number}", summary, pts,
                extra_factors=[{"factor": "Statistical flag", "effect": -25,
                                "detail": "Outlier detection depends on the other journals in the sample."}] if stat else [],
                extra_reasons=reasons, force_review=True,
                extra={"flags": fl, "score": score, "severity": sev, "kind": "JOURNAL"})
            items.append((score, j.journal_number, item))

        # bank lines
        txs = [t for t in self.inp.bank_transactions
               if not period or (period.start_date <= t.transaction_date <= period.end_date)]
        bank_out: Dict[str, float] = {}
        for cur in {t.currency for t in self.inp.bank_transactions}:
            bank_out.update(self._outliers({t.id: (_d(t.debit_amount) or _d(t.credit_amount))
                                            for t in self.inp.bank_transactions if t.currency == cur}))
        for t in txs:
            st = B._val(t.status)
            fl = []
            amt = _d(t.debit_amount) or _d(t.credit_amount)
            if st == "UNMATCHED":
                fl.append(self._flag("BANK_LINE_UNMATCHED", "No matching ledger entry", t.match_reason or "No ledger entry has the same amount and direction nearby.", 25, True, "FACT"))
            elif st == "REVIEW_REQUIRED":
                fl.append(self._flag("BANK_LINE_NEEDS_REVIEW", "Left for a person to decide", t.match_reason or "More than one ledger entry fits.", 20, True, "FACT"))
            elif st == "REJECTED":
                fl.append(self._flag("BANK_LINE_REJECTED", "Proposed match rejected", t.match_reason or "A checker rejected the proposed match.", 25, True, "FACT"))
            if t.id in bank_out:
                fl.append(self._flag("BANK_AMOUNT_OUTLIER", "Unusually large bank line", f"{t.currency} {B._money(amt)} is far above the typical bank line (robust score {bank_out[t.id]}).", 20, True, "STATISTICAL"))
            if not fl:
                continue
            score = min(100, sum(x["points"] for x in fl))
            sev = "HIGH" if score >= 60 else "MEDIUM" if score >= 35 else "LOW"
            base = self._explain_bank_tx(t)
            base["title"] = f"Unusual: bank line '{t.description}'"
            base["conclusion"] = {"summary": f"Bank line '{t.description}' ({B._iso(t.transaction_date)}, {t.currency} {B._money(amt)}) is worth a look: "
                                             f"{len(fl)} signal(s), {sev} priority.",
                                  "points": [f"{x['label']}: {x['detail']}" for x in fl]}
            rs = [f"Flagged: {x['label']}." for x in fl] + list(base["human_review"]["reasons"])
            base["human_review"] = human_review(True, rs, "the person doing the bank reconciliation")
            base.update({"flags": fl, "score": score, "severity": sev, "kind": "BANK_TRANSACTION"})
            items.append((score, t.id, validate_item(base)))

        items.sort(key=lambda x: (-x[0], x[1]))
        total = len(items)
        shown = [x[2] for x in items[:limit]]
        sev_counts = {s: sum(1 for x in items if x[2]["severity"] == s) for s in ("HIGH", "MEDIUM", "LOW")}
        scope = f"period {period.name}" if period else "all periods"
        if total:
            summary = (f"Scanned {len(in_scope)} posted journal(s) and {len(txs)} bank line(s) in {scope}: {total} worth a look "
                       f"({sev_counts['HIGH']} high, {sev_counts['MEDIUM']} medium, {sev_counts['LOW']} low priority)."
                       + (f" Showing the top {len(shown)}." if total > len(shown) else ""))
        else:
            summary = (f"Scanned {len(in_scope)} posted journal(s) and {len(txs)} bank line(s) in {scope}: nothing looked unusual under the "
                       "rules listed below. That is not a guarantee that nothing is wrong.")
        lim = self._limits("detect")
        if len(sample) < OUTLIER_MIN_SAMPLE:
            lim.append(f"Outlier detection needs at least {OUTLIER_MIN_SAMPLE} journals to be meaningful and was not applied.")
        interp = {"mode": "DETECT", "subject_type": "period" if period else "organisation",
                  "subject_id": period.id if period else self.inp.org_id, "subject_label": period.name if period else "All periods"}
        return self._envelope("DETECT", q, interp, summary, shown, lim, {
            "scanned": {"journals": len(in_scope), "bank_transactions": len(txs)}, "total_flagged": total, "severity_counts": sev_counts,
            "rules": [{"code": c, "label": l, "kind": k, "can_flag_alone": p} for c, l, k, p in self.DETECT_RULES]})

    # =============================================================== RECOMMEND
    RECOMMEND_SCOPES = ("all", "reconciliation", "adjustment", "evidence")

    def _ledger_lines_on(self, account_id: str) -> List[dict]:
        out = []
        for j in self.posted:
            if B._val(j.status) == "REVERSED":
                continue
            for l in j.lines:
                if l.account_id == account_id:
                    out.append({"journal": j, "debit": _d(l.debit_amount).quantize(Decimal("0.01")),
                                "credit": _d(l.credit_amount).quantize(Decimal("0.01"))})
        return out

    def _accounts_named(self, words: List[str], typ: Optional[str]) -> list:
        out = []
        for a in self.inp.accounts:
            if typ and B._val(a.type) != typ:
                continue
            if getattr(a, "is_active", True) and K.words_hit(a.name, words):
                out.append(a)
        return out

    def _proposed_treatment(self, lines: List[dict]) -> dict:
        if any(l["account"] is None for l in lines):
            return unavailable("The counter account has not been chosen, so no accounting treatment can be stated yet.")
        dr = [self._atype(l["account"].id) for l in lines if l["side"] == "debit"]
        cr = [self._atype(l["account"].id) for l in lines if l["side"] == "credit"]
        n = K.classify_nature(dr, cr)
        return {"available": True, "proposed": True, "classification": n,
                "debits": [{"account": f"{l['account'].code} {l['account'].name}", "type": self._atype(l["account"].id), "amount": l["amount"]} for l in lines if l["side"] == "debit"],
                "credits": [{"account": f"{l['account'].code} {l['account'].name}", "type": self._atype(l["account"].id), "amount": l["amount"]} for l in lines if l["side"] == "credit"],
                "policies": [], "note": "Proposed treatment only; nothing has been recorded."}

    def _rec_item(self, base: dict, title: str, summary: str, points: List[str], proposal: dict, priority: int,
                  extra_factors: Optional[List[dict]] = None, extra_reasons: Optional[List[str]] = None) -> dict:
        """Turns an already-grounded base item into a recommendation (always requires a person)."""
        if extra_factors:
            fac = list(base["confidence"]["factors"]) + extra_factors
            base["confidence"] = confidence(fac)
        reasons = ["ASAVEXA never posts, matches or changes records itself; a person must carry this out and approve it."]
        reasons += (extra_reasons or []) + [r for r in base["human_review"]["reasons"] if r not in reasons and not r.startswith("Advisory")]
        if base["confidence"]["level"] != HIGH and not any(r.startswith("Confidence is") for r in reasons):
            reasons.append(f"Confidence is {base['confidence']['level']} ({base['confidence']['score']}).")
        base["title"] = title
        base["conclusion"] = {"summary": summary, "points": points}
        base["human_review"] = human_review(True, reasons, "an approver or finance officer")
        base["proposal"] = {**proposal, "applied": False}
        base["priority"] = priority
        return validate_item(base)

    def recommend(self, scope: str = "all", period_id: Optional[str] = None, limit: int = 15, question: Optional[str] = None) -> dict:
        q = question or "Suggest a reconciliation or adjustment."
        scope = (scope or "all").lower()
        if scope not in self.RECOMMEND_SCOPES:
            raise AiValidationError("scope must be one of: " + ", ".join(self.RECOMMEND_SCOPES) + ".")
        if not isinstance(limit, int) or isinstance(limit, bool) or not (1 <= limit <= MAX_ITEMS):
            raise AiValidationError(f"limit must be a whole number from 1 to {MAX_ITEMS}.")
        period = None
        if period_id:
            period = self.periods.get(period_id)
            if period is None:
                raise AiSubjectNotFoundError("There is no such accounting period in this organisation.")
        items: List[dict] = []
        if scope in ("all", "reconciliation"):
            items += self._rec_reconciliation(period)
        if scope in ("all", "adjustment"):
            items += self._rec_adjustments(period)
        if scope in ("all", "evidence"):
            items += self._rec_evidence(period)
        items.sort(key=lambda i: (-i["priority"], i["title"]))
        total = len(items)
        shown = items[:limit]
        by_kind: Dict[str, int] = {}
        for i in items:
            by_kind[i["proposal"]["kind"]] = by_kind.get(i["proposal"]["kind"], 0) + 1
        label = period.name if period else "all periods"
        if total:
            summary = (f"{total} recommendation(s) for {label}"
                       + (f" (showing the top {len(shown)})" if total > len(shown) else "")
                       + ". Each is a proposal for a person to carry out; none has been applied.")
        else:
            summary = (f"No recommendation for {label}: every bank line is matched, no entry looks misclassified and "
                       "evidence is verified, as far as the records show.")
        interp = {"mode": "RECOMMEND", "subject_type": "period" if period else "organisation",
                  "subject_id": period.id if period else self.inp.org_id, "subject_label": label, "scope": scope}
        return self._envelope("RECOMMEND", q, interp, summary, shown, self._limits("recommend"),
                              {"total_recommendations": total, "by_kind": by_kind})

    # -- reconciliation proposals
    def _rec_reconciliation(self, period) -> List[dict]:
        out: List[dict] = []
        claimed = {t.matched_journal_id for t in self.inp.bank_transactions
                   if t.matched_journal_id and B._val(t.status) in ("MATCHED", "APPROVED", "RECONCILED")}
        for t in sorted(self.inp.bank_transactions, key=lambda t: (t.transaction_date, t.id)):
            st = B._val(t.status)
            if st not in ("IMPORTED", "UNMATCHED", "REVIEW_REQUIRED", "REJECTED"):
                continue
            if period and not (period.start_date <= t.transaction_date <= period.end_date):
                continue
            q2 = Decimal("0.01")
            td, tc = _d(t.debit_amount).quantize(q2), _d(t.credit_amount).quantize(q2)
            amt = td or tc
            exact, near = [], []
            for e in self._ledger_lines_on(t.bank_account_id):
                j = e["journal"]
                if j.id in claimed or j.id == t.matched_journal_id and st == "REJECTED":
                    continue
                dd = abs((j.date - t.transaction_date).days)
                if dd > WIDE_MATCH_DAYS:
                    continue
                if e["debit"] == td and e["credit"] == tc:
                    exact.append((dd, j))
                elif (td and e["debit"] > 0 and not tc and e["credit"] == 0) or (tc and e["credit"] > 0 and not td and e["debit"] == 0):
                    la = e["debit"] or e["credit"]
                    if la != amt and abs(la - amt) <= amt * Decimal("0.02"):
                        near.append((dd, j, la))
            exact.sort(key=lambda x: (x[0], x[1].journal_number))
            near.sort(key=lambda x: (x[0], x[1].journal_number))
            rec = self.recons.get(t.reconciliation_id)
            tx_src = source_record("BANK_TRANSACTION", t.id, f"Bank line {B._iso(t.transaction_date)}: {t.description}", st)
            path = f"/reconciliation/{rec.id}" if rec else "/reconciliation"
            if exact:
                dd, j = exact[0]
                fac, why, pts = [], [], []
                if len(exact) > 1:
                    fac.append({"factor": "More than one journal fits", "effect": -25, "detail": f"{len(exact)} journals have this exact amount nearby."})
                    why.append(f"{len(exact)} journals fit; a person must choose.")
                if dd > 3:
                    fac.append({"factor": "Date gap", "effect": -10, "detail": f"{dd} days apart, beyond the usual 3-day tolerance."})
                if st == "REJECTED":
                    fac.append({"factor": "Earlier match rejected", "effect": -15, "detail": "A checker rejected a previous proposed match for this line."})
                    why.append("A checker previously rejected a match for this line.")
                pts = [f"Bank line: {t.currency} {B._money(amt)} {'in' if td else 'out'} on {B._iso(t.transaction_date)} ('{t.description}').",
                       f"Closest ledger entry: {j.journal_number} ('{j.description}', {B._iso(j.date)}) with the identical amount and direction on the same bank account, {dd} day(s) apart."]
                if len(exact) > 1:
                    pts.append("Other journals that also fit: " + ", ".join(f"{x[1].journal_number} ({B._iso(x[1].date)})" for x in exact[1:5]) + ".")
                base = self._journal_item(j, "", "x", ["x"], extra_sources=[tx_src] + ([source_record("RECONCILIATION", rec.id, f"Reconciliation {rec.name}", B._val(rec.status), path)] if rec else [])
                                          + [source_record("JOURNAL", x[1].id, f"Journal {x[1].journal_number}", x[1].description, f"/accounting/journals/{x[1].id}") for x in exact[1:5]])
                out.append(self._rec_item(
                    base, f"Match bank line '{t.description}' to journal {j.journal_number}",
                    f"Match the bank line '{t.description}' ({t.currency} {B._money(amt)}) to journal {j.journal_number}: same amount and direction, {dd} day(s) apart.",
                    pts, {"kind": "MATCH_BANK_TRANSACTION", "action": f"Match bank line {t.id[:8]} to journal {j.journal_number}",
                          "bank_transaction_id": t.id, "journal_id": j.id, "where": path, "proposed_entry": None,
                          "expected_effect": "The line becomes MATCHED; after a checker approves it and the reconciliation is finalised it is RECONCILED."},
                    72 if len(exact) == 1 else 58, fac, why))
                continue
            if near:
                dd, j, la = near[0]
                diff = (amt - la).copy_abs()
                bank_bigger = amt > la
                bank_acct = self._acct(t.bank_account_id)
                counter_words = ["bank", "charge", "fee", "interest"]
                cands = self._accounts_named(counter_words, "EXPENSE")
                same_side = "credit" if tc else "debit"
                opp = "debit" if same_side == "credit" else "credit"
                side_for_bank = same_side if bank_bigger else opp
                counter = cands[0] if len(cands) == 1 else None
                lines = [{"account": bank_acct, "side": side_for_bank, "amount": B._money(diff)},
                         {"account": counter, "side": "debit" if side_for_bank == "credit" else "credit", "amount": B._money(diff)}]
                pts = [f"Bank line: {t.currency} {B._money(amt)} {'in' if td else 'out'} on {B._iso(t.transaction_date)}.",
                       f"Journal {j.journal_number} is on the same account and direction for {B._money(la)}: a difference of {B._money(diff)} "
                       f"({'the bank shows more' if bank_bigger else 'the ledger shows more'}).",
                       "A small difference like this is often a bank charge, rounding or a part-payment. This is a guess from the amounts only."]
                base = self._journal_item(j, "", "x", ["x"], extra_sources=[tx_src])
                it = self._rec_item(
                    base, f"Resolve a {B._money(diff)} difference on bank line '{t.description}'",
                    f"The bank line '{t.description}' differs from journal {j.journal_number} by {t.currency} {B._money(diff)}; an adjusting entry may be needed.",
                    pts, {"kind": "ADJUST_DIFFERENCE", "action": f"Review the {B._money(diff)} difference and, if confirmed, record an adjusting journal",
                          "bank_transaction_id": t.id, "journal_id": j.id, "where": "/accounting/journals/new",
                          "proposed_entry": {"lines": [{"account": f"{l['account'].code} {l['account'].name}" if l["account"] else None,
                                                        "account_id": l["account"].id if l["account"] else None,
                                                        "side": l["side"], "amount": l["amount"]} for l in lines],
                                             "needs_account_choice": counter is None, "currency": t.currency},
                          "expected_effect": "Once recorded and posted, the ledger would agree with the bank for this line."},
                    60, [{"factor": "Amounts differ", "effect": -25, "detail": "No exact ledger entry exists; the match is by near amount only."}],
                    ["No exact match exists; the cause of the difference is a guess."])
                it["accounting_treatment"] = self._proposed_treatment(lines)
                out.append(validate_item(it))
                continue
            # nothing fits: propose recording the line
            implied, words = K.implied_type(t.description)
            counter = None
            if implied:
                cs = self._accounts_named(words, implied)
                counter = cs[0] if len(cs) == 1 else None
            bank_acct = self._acct(t.bank_account_id)
            bank_side = "debit" if td else "credit"
            counter_side = "credit" if td else "debit"
            lines = [{"account": bank_acct, "side": bank_side, "amount": B._money(amt)},
                     {"account": counter, "side": counter_side, "amount": B._money(amt)}]
            pts = [f"Bank line: {t.currency} {B._money(amt)} {'in' if td else 'out'} on {B._iso(t.transaction_date)} ('{t.description}'); no posted journal on this bank account has that amount within {WIDE_MATCH_DAYS} days.",
                   "The bank has recorded a movement that the ledger has not. It may be a missing entry, a timing difference or an error at the bank."]
            if counter:
                pts.append(f"The wording points to {implied.lower()} accounts; '{counter.code} {counter.name}' is the only one whose name fits. This is a hint, not a decision.")
            else:
                pts.append("ASAVEXA cannot tell from the description which account the other side belongs to; a person must choose it.")
            base = self._explain_bank_tx(t)
            base["accounting_treatment"] = self._proposed_treatment(lines)
            out.append(self._rec_item(
                base, f"Record bank line '{t.description}' in the ledger",
                f"The bank line '{t.description}' ({t.currency} {B._money(amt)}) has no ledger entry. Consider recording a journal for it after checking what it was for.",
                pts, {"kind": "RECORD_BANK_LINE", "action": "Check the source of this bank line and, if valid, draft a journal for it",
                      "bank_transaction_id": t.id, "journal_id": None, "where": "/accounting/journals/new",
                      "proposed_entry": {"lines": [{"account": f"{l['account'].code} {l['account'].name}" if l["account"] else None,
                                                    "account_id": l["account"].id if l["account"] else None,
                                                    "side": l["side"], "amount": l["amount"]} for l in lines],
                                         "needs_account_choice": counter is None, "currency": t.currency},
                      "expected_effect": "A drafted, evidenced and approved journal would let this line be matched."},
                55 if counter else 50,
                [{"factor": "Counter account guessed from wording", "effect": -20 if counter else -30,
                  "detail": "The other side of the entry is inferred from words in the bank description." if counter else "The other side of the entry is unknown."}],
                ["The proposed entry rests on the bank description alone."]))
        out += self._rec_recon_gaps(period)
        return out

    def _rec_recon_gaps(self, period) -> List[dict]:
        out = []
        for r in self.inp.reconciliations:
            if B._val(r.status) == "RECONCILED":
                continue
            if period and (r.period_end < period.start_date or r.period_start > period.end_date):
                continue
            txs = [t for t in self.inp.bank_transactions if t.reconciliation_id == r.id]
            if not txs:
                continue
            bank_net = sum((_d(t.debit_amount) - _d(t.credit_amount) for t in txs), Decimal("0"))
            matched_ids = {t.matched_journal_id for t in self.inp.bank_transactions
                           if t.matched_journal_id and B._val(t.status) in ("MATCHED", "APPROVED", "RECONCILED")}
            led = [e for e in self._ledger_lines_on(r.bank_account_id) if r.period_start <= e["journal"].date <= r.period_end]
            led_net = sum((e["debit"] - e["credit"] for e in led), Decimal("0"))
            bank_un = sum((_d(t.debit_amount) - _d(t.credit_amount) for t in txs
                           if not (t.matched_journal_id and B._val(t.status) in ("MATCHED", "APPROVED", "RECONCILED"))), Decimal("0"))
            led_un = sum((e["debit"] - e["credit"] for e in led if e["journal"].id not in matched_ids), Decimal("0"))
            diff = bank_net - led_net
            if diff == 0 and bank_un == 0 and led_un == 0:
                continue
            residual = diff - (bank_un - led_un)
            acct = self._acct(r.bank_account_id)
            pts = [f"Bank statement net movement: {B._money(bank_net)}. Ledger net movement on {self._acct_label(r.bank_account_id)} for the same dates: {B._money(led_net)}. Difference: {B._money(diff)}.",
                   f"Bank lines not yet matched total {B._money(bank_un)}; ledger entries on this account not matched to any bank line total {B._money(led_un)}.",
                   ("These unmatched amounts fully explain the difference." if residual == 0
                    else f"After allowing for the unmatched items, {B._money(residual)} remains unexplained; a matched pair must differ in amount, or something is out of date range.")]
            fac = [] if residual == 0 else [{"factor": "Unexplained remainder", "effect": -30, "detail": f"{B._money(residual)} cannot be explained from the records."}]
            fw = self._stage_framework(["ASSET"])
            fac.append({"factor": "Bank lines not final", "effect": -10, "detail": "The reconciliation is not yet finalised."})
            if not fw["available"]:
                fac.append({"factor": "Reporting framework configured", "effect": -10, "detail": "No framework is configured."})
            conf = confidence(fac)
            ev = self.ev_by_id.get(r.evidence_ref) if r.evidence_ref else None
            evid = ({"available": True, "state": "VERIFIED" if B._val(ev.status) == "VERIFIED" else "UNVERIFIED", "records": [self._ev_row(ev)],
                     "expected_types": ["BANK_STATEMENT"], "note": "Statement evidence is linked to this reconciliation."} if ev else
                    {"available": False, "state": "MISSING", "records": [], "expected_types": ["BANK_STATEMENT"],
                     "note": "MISSING EVIDENCE: no bank statement is linked to this reconciliation."})
            if not ev:
                conf = confidence(fac + [{"factor": "Statement evidence", "effect": -15, "detail": "No bank statement is linked."}])
            sources = [source_record("RECONCILIATION", r.id, f"Reconciliation {r.name}", B._val(r.status), f"/reconciliation/{r.id}")]
            if acct:
                sources.append(source_record("ACCOUNT", acct.id, f"{acct.code} {acct.name}", "ASSET"))
            sources += [source_record("BANK_TRANSACTION", t.id, f"Bank line {B._iso(t.transaction_date)}: {t.description}", B._val(t.status))
                        for t in txs[:10]]
            reasons = ["ASAVEXA never posts, matches or changes records itself; a person must carry this out and approve it."]
            if conf["level"] != HIGH:
                reasons.append(f"Confidence is {conf['level']} ({conf['score']}).")
            out.append(validate_item({
                "title": f"Reconciliation '{r.name}' does not yet agree with the ledger",
                "conclusion": {"summary": f"Reconciliation '{r.name}' ({B._iso(r.period_start)} to {B._iso(r.period_end)}) differs from the ledger by {B._money(diff)}.",
                               "points": pts},
                "source_records": sources, "evidence": evid,
                "journal": unavailable("This concerns a whole reconciliation, not one journal. See the matching recommendations for individual journals."),
                "accounting_treatment": unavailable("A reconciliation compares records; it does not change an accounting treatment."),
                "reporting_framework": fw, "confidence": conf,
                "human_review": human_review(True, reasons, "an approver or finance officer"),
                "proposal": {"kind": "RECONCILE_DIFFERENCE", "action": "Work through the unmatched items listed, then submit the reconciliation for approval",
                             "where": f"/reconciliation/{r.id}", "proposed_entry": None, "applied": False,
                             "expected_effect": "When every line is matched or explained the reconciliation can be finalised."},
                "priority": 65}))
        return out

    # -- adjustment proposals
    def _rec_adjustments(self, period) -> List[dict]:
        out = []
        for j in sorted(self.posted, key=lambda x: (x.date, x.journal_number)):
            if period and j.period_id != period.id:
                continue
            f = self._facts(j)
            if f["consistency"]["status"] == "MISMATCH" and not f["reversal"] and B._val(j.status) == "POSTED":
                implied = f["implied"]
                cands = self._accounts_named(f["consistency"]["words"], implied)
                two = len(f["lines"]) == 2
                entry, pts = None, [f["consistency"]["detail"]]
                fac = [{"factor": "Wording-based suggestion", "effect": -25, "detail": "The suggestion rests on keywords in the description."}]
                target_line = None
                natural = f["dr"] if implied in ("EXPENSE", "ASSET") else f["cr"]
                if two and len(natural) == 1 and natural[0][1] != implied:
                    target_line = natural[0][0]
                if target_line is not None and len(cands) == 1 and cands[0].id != target_line.account_id:
                    amt = _d(target_line.debit_amount) or _d(target_line.credit_amount)
                    wrong = self._acct(target_line.account_id)
                    new, side_new = cands[0], ("debit" if _d(target_line.debit_amount) > 0 else "credit")
                    side_old = "credit" if side_new == "debit" else "debit"
                    entry = {"lines": [{"account": f"{new.code} {new.name}", "account_id": new.id, "side": side_new, "amount": B._money(amt)},
                                       {"account": f"{wrong.code} {wrong.name}", "account_id": wrong.id, "side": side_old, "amount": B._money(amt)}],
                             "needs_account_choice": False, "currency": j.currency}
                    pts.append(f"If the wording is right, moving {B._money(amt)} from '{wrong.code} {wrong.name}' to '{new.code} {new.name}' would fix it.")
                else:
                    entry = None
                    pts.append("ASAVEXA cannot name a single better account from the wording, so a person must decide whether the description or the accounts are wrong.")
                    fac.append({"factor": "No single replacement account", "effect": -10, "detail": "Zero or several accounts fit."})
                base = self._journal_item(j, "", "x", ["x"])
                it = self._rec_item(
                    base, f"Check the classification of journal {j.journal_number}",
                    f"Journal {j.journal_number} ('{j.description}') may be classified under the wrong kind of account.",
                    pts, {"kind": "RECLASSIFY", "action": "Confirm the intended account; if wrong, post a correcting journal (reverse and rebook) with a reason",
                          "journal_id": j.id, "where": f"/accounting/journals/{j.id}", "proposed_entry": entry,
                          "expected_effect": "The amount would move to the account type the description implies; period totals change accordingly."},
                    50, fac, ["The wording check is a hint; the description itself may simply be loose."])
                if entry:
                    it["accounting_treatment"] = self._proposed_treatment([
                        {"account": self._acct(l["account_id"]), "side": l["side"], "amount": l["amount"]} for l in entry["lines"]])
                out.append(validate_item(it))
            if f["contra"] and B._val(j.status) == "POSTED":
                base = self._journal_item(j, "", "x", ["x"])
                out.append(self._rec_item(
                    base, f"Confirm the direction of journal {j.journal_number}",
                    f"Journal {j.journal_number} moves {'income down' if any(t == 'REVENUE' for _, t in f['dr']) else 'an expense down'}; confirm it is a refund, credit note or correction.",
                    [f"This is {f['nature']['meaning']}.", "If it is a genuine refund or credit note, attach the credit note as evidence. If it is a mistake, reverse it with a reason."],
                    {"kind": "CONFIRM_DIRECTION", "action": "Attach the credit note or reverse the journal with a reason", "journal_id": j.id,
                     "where": f"/accounting/journals/{j.id}", "proposed_entry": None,
                     "expected_effect": "The record either becomes supported by evidence or is corrected."}, 55))
        return out

    # -- evidence proposals
    def _rec_evidence(self, period) -> List[dict]:
        out = []
        rows = [(self._amount(j), j) for j in self.posted if (not period or j.period_id == period.id)]
        rows.sort(key=lambda x: (-x[0], x[1].journal_number))
        for amt, j in rows:
            f = self._facts(j)
            s = f["ev_state"]
            if s == "VERIFIED":
                continue
            exp = [t.lower().replace("_", " ") for t in K.expected_evidence(f["nature"]["code"], j.description)]
            rec = f["ev_rec"]
            if s == "MISSING":
                action, kind = f"Attach {' or '.join(exp)} evidence", "ATTACH_EVIDENCE"
                text = f"Journal {j.journal_number} has no evidence. Attach {' or '.join(exp)}."
                pri = 45
            elif s == "UNVERIFIED":
                up = self._who(rec.uploaded_by)
                action, kind = f"Have someone other than {up or 'the uploader'} verify '{rec.original_filename}'", "VERIFY_EVIDENCE"
                text = f"Evidence '{rec.original_filename}' for journal {j.journal_number} is uploaded but not verified."
                pri = 42
            else:
                action, kind = f"Replace the {B._val(rec.status).lower()} evidence '{rec.original_filename}'", "REPLACE_EVIDENCE"
                text = f"Evidence for journal {j.journal_number} is {B._val(rec.status).lower()}."
                pri = 48
            base = self._journal_item(j, "", "x", ["x"])
            out.append(self._rec_item(
                base, f"{action} (journal {j.journal_number})", text,
                [text, f"Amount at stake: {j.currency} {B._money(amt)}.",
                 "Evidence is the proof behind a number; until it is verified the figure rests on the preparer's word."],
                {"kind": kind, "action": action, "journal_id": j.id, "evidence_id": rec.id if rec else None,
                 "where": f"/evidence/{rec.id}" if rec else "/evidence", "proposed_entry": None,
                 "expected_effect": "The journal becomes supported by verified evidence and its confidence rises."},
                pri + (3 if amt >= 100000 else 0)))
        return out

    # =============================================================== PROVE
    @staticmethod
    def _check(key: str, label: str, result: str, detail: str, critical: bool = False) -> dict:
        return {"key": key, "label": label, "result": result, "detail": detail, "critical": critical}

    def prove(self, subject_type: str, subject_id: Optional[str] = None, metric: Optional[str] = None,
              period_id: Optional[str] = None, question: Optional[str] = None) -> dict:
        q = question or "Show the evidence supporting your answer."
        st = (subject_type or "").lower()
        if st == "journal":
            j = self._lookup_journal(subject_id)
            item = self._prove_journal(j)
            interp = {"mode": "PROVE", "subject_type": "journal", "subject_id": j.id, "subject_label": j.journal_number}
        elif st == "bank_transaction":
            t = self._lookup_tx(subject_id)
            item = self._prove_bank_tx(t)
            interp = {"mode": "PROVE", "subject_type": "bank_transaction", "subject_id": t.id, "subject_label": t.description}
        elif st == "figure":
            if metric not in FIGURES:
                raise AiValidationError("metric must be one of: " + ", ".join(FIGURES) + ".")
            if not period_id:
                raise AiValidationError("Say which accounting period the figure is for.")
            p = self.periods.get(period_id)
            if p is None:
                raise AiSubjectNotFoundError("There is no such accounting period in this organisation.")
            item = self._prove_figure(metric, p)
            interp = {"mode": "PROVE", "subject_type": "figure", "subject_id": p.id, "subject_label": f"{metric.replace('_', ' ')} for {p.name}", "metric": metric}
        else:
            raise AiValidationError("subject_type must be 'journal', 'bank_transaction' or 'figure'.")
        return self._envelope("PROVE", q, interp, item["conclusion"]["summary"], [item], self._limits("prove"), {"verdict": item["verdict"]})

    def _verdict_text(self, v: str) -> str:
        return {"PROVEN": "PROVEN", "PARTIALLY_PROVEN": "PARTIALLY PROVEN", "NOT_PROVEN": "NOT PROVEN"}[v]

    def _prove_journal(self, j) -> dict:
        f = self._facts(j)
        checks = []
        bal = _d(j.total_debits()) == _d(j.total_credits())
        checks.append(self._check("BALANCED", "Debits equal credits", "PASS" if bal else "FAIL",
                                  f"Debits {B._money(_d(j.total_debits()))}, credits {B._money(_d(j.total_credits()))} (recomputed from the lines).", True))
        posted = B._val(j.status) != "DRAFT"
        checks.append(self._check("POSTED", "Part of the ledger", "PASS" if posted else "FAIL",
                                  f"Status is {B._val(j.status)}." + ("" if posted else " A draft is not part of the ledger."), True))
        p = f["period"]
        inside = bool(p and p.start_date <= j.date <= p.end_date)
        checks.append(self._check("DATE_IN_PERIOD", "Dated inside its accounting period", "PASS" if inside else "FAIL",
                                  (f"{B._iso(j.date)} is within {p.name} ({B._iso(p.start_date)} to {B._iso(p.end_date)})." if inside else
                                   "The journal date is not inside its period or the period is missing."), True))
        s, rec = f["ev_state"], f["ev_rec"]
        checks.append(self._check("HAS_EVIDENCE", "Evidence is attached", "PASS" if rec else "FAIL",
                                  f"{len(self._all_evidence_for(j))} evidence record(s) linked." if rec else "MISSING EVIDENCE: nothing is linked.", True))
        checks.append(self._check("EVIDENCE_VERIFIED", "Evidence has been verified", "PASS" if s == "VERIFIED" else "FAIL",
                                  f"Best evidence is {EVIDENCE_LABEL[s]}.", True))
        if rec:
            hashed = bool(rec.file_hash) and len(rec.file_hash) == 64
            checks.append(self._check("EVIDENCE_HASH", "A file fingerprint (SHA-256) is stored", "PASS" if hashed else "FAIL",
                                      f"{rec.file_hash}" if hashed else "No valid fingerprint is stored."))
            if B._val(rec.status) == "VERIFIED":
                indep = bool(rec.verified_by) and rec.verified_by != rec.uploaded_by
                checks.append(self._check("VERIFIER_INDEPENDENT", "Verified by someone other than the uploader", "PASS" if indep else "FAIL",
                                          f"Uploaded by {self._who(rec.uploaded_by)}, verified by {self._who(rec.verified_by)}."))
        else:
            checks.append(self._check("EVIDENCE_HASH", "A file fingerprint (SHA-256) is stored", "NOT_APPLICABLE", "There is no evidence file."))
        if j.posted_by:
            checks.append(self._check("POSTER_INDEPENDENT", "Posted by someone other than the preparer", "FAIL" if f["sod"] else "PASS",
                                      f"Prepared by {self._who(j.created_by)}, posted by {self._who(j.posted_by)}."))
        bank_ids = {r.bank_account_id for r in self.inp.reconciliations}
        touches = [l for l in j.lines if l.account_id in bank_ids]
        if touches:
            txs = self.txs_by_journal.get(j.id, [])
            final = [t for t in txs if B._val(t.status) in ("APPROVED", "RECONCILED")]
            checks.append(self._check("BANK_AGREES", "Agrees to the bank", "PASS" if final else "FAIL",
                                      f"Matched to {len(txs)} bank line(s); {len(final)} approved or reconciled." if txs else "It touches a bank account but no bank line is matched to it."))
        else:
            checks.append(self._check("BANK_AGREES", "Agrees to the bank", "NOT_APPLICABLE", "The journal does not touch a reconciled bank account."))
        crit_ok = all(c["result"] == "PASS" for c in checks if c["critical"])
        integrity_ok = all(c["result"] == "PASS" for c in checks if c["key"] in ("BALANCED", "POSTED", "DATE_IN_PERIOD"))
        verdict = "PROVEN" if crit_ok else "PARTIALLY_PROVEN" if (integrity_ok and s == "UNVERIFIED") else "NOT_PROVEN"
        soft_fail = [c for c in checks if not c["critical"] and c["result"] == "FAIL"]
        failed = [c["label"] for c in checks if c["result"] == "FAIL"]
        summary = f"Journal {j.journal_number}: {self._verdict_text(verdict)}. " + (
            ("Every check passes." if not soft_fail else "Every critical check passes, but not: " + "; ".join(c["label"] for c in soft_fail) + ".")
            if verdict == "PROVEN" else "Not passing: " + "; ".join(failed) + ".")
        pts = [f"[{c['result']}] {c['label']}: {c['detail']}" for c in checks]
        reasons = [] if verdict == "PROVEN" and not soft_fail else ([f"Verdict is {self._verdict_text(verdict)}."] if verdict != "PROVEN" else []) + [f"Check not passed: {c['label']}." for c in soft_fail]
        item = self._journal_item(j, f"Proof for journal {j.journal_number}", summary, pts, extra_reasons=reasons,
                                  extra={"verdict": verdict, "checks": checks})
        if verdict != "PROVEN":
            item["human_review"] = human_review(True, item["human_review"]["reasons"] or reasons, "an approver or finance officer")
        return validate_item(item)

    def _prove_bank_tx(self, t) -> dict:
        st = B._val(t.status)
        j = self.by_id.get(t.matched_journal_id) if t.matched_journal_id else None
        checks = []
        checks.append(self._check("MATCHED", "Linked to a ledger journal", "PASS" if j else "FAIL",
                                  f"Matched to {j.journal_number}." if j else "No journal is linked to this bank line.", True))
        checks.append(self._check("RULE_RECORDED", "The reason for the match is recorded", "PASS" if (t.match_rule and t.match_reason) else "FAIL",
                                  f"{t.match_rule}: {t.match_reason}" if t.match_rule else "No match rule is recorded."))
        agree = False
        if j is not None:
            q2 = Decimal("0.01")
            for l in j.lines:
                if l.account_id == t.bank_account_id and _d(l.debit_amount).quantize(q2) == _d(t.debit_amount).quantize(q2) \
                        and _d(l.credit_amount).quantize(q2) == _d(t.credit_amount).quantize(q2):
                    agree = True
        checks.append(self._check("AMOUNT_AGREES", "Amount and direction agree with the journal", "PASS" if agree else "FAIL",
                                  "A journal line on the bank account has the identical amount and direction." if agree else "No line on the bank account agrees." if j else "There is no journal to compare.", True))
        checks.append(self._check("STATUS_FINAL", "Match approved by a checker", "PASS" if st in ("APPROVED", "RECONCILED") else "FAIL",
                                  f"Status is {st}.", True))
        rec = self.recons.get(t.reconciliation_id)
        checks.append(self._check("RECON_FINAL", "Reconciliation is finalised", "PASS" if rec and B._val(rec.status) == "RECONCILED" else "FAIL",
                                  f"Reconciliation is {B._val(rec.status)}." if rec else "No reconciliation found."))
        jp = None
        if j is not None:
            jp = self._prove_journal(j)
            checks.append(self._check("JOURNAL_PROVEN", "The linked journal is itself proven", "PASS" if jp["verdict"] == "PROVEN" else "FAIL",
                                      f"Journal {j.journal_number} is {self._verdict_text(jp['verdict'])}."))
        crit_ok = all(c["result"] == "PASS" for c in checks if c["critical"])
        verdict = "PROVEN" if crit_ok and (jp is None or jp["verdict"] == "PROVEN") else "PARTIALLY_PROVEN" if (j is not None and agree) else "NOT_PROVEN"
        failed = [c["label"] for c in checks if c["result"] == "FAIL"]
        summary = f"Bank line '{t.description}': {self._verdict_text(verdict)}. " + ("Every check passes." if verdict == "PROVEN" else "Not passing: " + "; ".join(failed) + ".")
        pts = [f"[{c['result']}] {c['label']}: {c['detail']}" for c in checks]
        if jp is not None:
            item = jp
            item["title"] = f"Proof for bank line '{t.description}'"
            item["conclusion"] = {"summary": summary, "points": pts}
            item["checks"] = checks
            item["verdict"] = verdict
            item["source_records"] += [r for r in [source_record("BANK_TRANSACTION", t.id, f"Bank line {B._iso(t.transaction_date)}: {t.description}", st)]
                                       if (r["kind"], r["id"]) not in {(x["kind"], x["id"]) for x in item["source_records"]}]
            if verdict != "PROVEN":
                item["human_review"] = human_review(True, [f"Verdict is {self._verdict_text(verdict)}."] + item["human_review"]["reasons"], "the person doing the bank reconciliation")
            return validate_item(item)
        item = self._explain_bank_tx(t)
        item.update({"title": f"Proof for bank line '{t.description}'", "conclusion": {"summary": summary, "points": pts},
                     "checks": checks, "verdict": verdict})
        item["human_review"] = human_review(True, [f"Verdict is {self._verdict_text(verdict)}."] + item["human_review"]["reasons"], "the person doing the bank reconciliation")
        return validate_item(item)

    def _contribution(self, j, types: Tuple[str, ...], metric: str) -> Decimal:
        total = Decimal("0")
        for l in j.lines:
            t = self._atype(l.account_id)
            net_dr = _d(l.debit_amount) - _d(l.credit_amount)
            if metric == "net_income":
                if t == "REVENUE":
                    total += -net_dr
                elif t == "EXPENSE":
                    total -= net_dr
            elif t in types:
                total += net_dr if t in ("EXPENSE", "ASSET") else -net_dr
        return total

    def _prove_figure(self, metric: str, p) -> dict:
        hist = B.build_financial_history(self.inp)
        row = next((r for r in hist["periods"] if r["period_id"] == p.id), None)
        types = FIGURE_TYPES[metric]
        js = [j for j in self.posted if j.period_id == p.id]
        contrib = [(j, self._contribution(j, types, metric)) for j in js]
        contrib = [(j, c) for j, c in contrib if c != 0]
        reported = _d(row[metric]) if row and row.get("has_activity") and metric in row else Decimal("0.00")
        total = sum((c for _, c in contrib), Decimal("0"))
        counts = {"VERIFIED": 0, "UNVERIFIED": 0, "DEFECTIVE": 0, "MISSING": 0}
        amt_by = {k: Decimal("0") for k in counts}
        rows = []
        for j, c in contrib:
            s, rec = self._ev(j)
            counts[s] += 1
            amt_by[s] += abs(c)
            rows.append({"journal_id": j.id, "journal_number": j.journal_number, "date": B._iso(j.date), "description": j.description,
                         "contribution": B._money(c), "evidence_state": s, "evidence_id": rec.id if rec else None,
                         "evidence_file": rec.original_filename if rec else None, "path": f"/accounting/journals/{j.id}"})
        rows.sort(key=lambda r: (-abs(_d(r["contribution"])), r["journal_number"]))
        n = len(contrib)
        gross = sum(amt_by.values(), Decimal("0"))
        share = (amt_by["VERIFIED"] * 100 / gross) if gross else Decimal("0")
        agrees = total.quantize(Decimal("0.01")) == reported.quantize(Decimal("0.01"))
        if n == 0:
            verdict = "NOT_PROVEN"
        elif counts["VERIFIED"] == n and agrees:
            verdict = "PROVEN"
        elif counts["VERIFIED"] > 0 or counts["UNVERIFIED"] > 0:
            verdict = "PARTIALLY_PROVEN"
        else:
            verdict = "NOT_PROVEN"
        name = metric.replace("_", " ")
        cur = hist.get("currency") or ""
        checks = [self._check("SUM_AGREES", "The listed journals add up to the reported figure", "PASS" if agrees else "FAIL",
                              f"Journals sum to {B._money(total)}; the report shows {B._money(reported)}.", True),
                  self._check("ALL_VERIFIED", "Every contributing journal has verified evidence", "PASS" if n and counts["VERIFIED"] == n else "FAIL",
                              f"{counts['VERIFIED']} of {n} journal(s) verified; {counts['UNVERIFIED']} unverified, {counts['DEFECTIVE']} defective, {counts['MISSING']} without evidence.", True)]
        if n == 0:
            summary = f"Nothing to prove: no posted journal contributes to {name} in {p.name}. NOT PROVEN."
        else:
            summary = (f"{name.capitalize()} for {p.name} is {cur} {B._money(reported)}, built from {n} journal(s). {self._verdict_text(verdict)}: "
                       f"{counts['VERIFIED']} of {n} journal(s) ({share.quantize(Decimal('0.1'))}% of the amount) have verified evidence.")
        pts = [f"[{c['result']}] {c['label']}: {c['detail']}" for c in checks]
        pts.append("Largest contributions: " + "; ".join(f"{r['journal_number']} {r['contribution']} ({EVIDENCE_LABEL[r['evidence_state']]})" for r in rows[:5]) + "." if rows else "No contributing journals.")
        fac = []
        if n:
            lost = int(round(float(100 - share) * 0.6))
            fac.append({"factor": "Share of the amount with verified evidence", "effect": -lost, "detail": f"{share.quantize(Decimal('0.1'))}% verified."})
        else:
            fac.append({"factor": "No contributing journals", "effect": -60, "detail": "There is nothing behind this figure."})
        if not agrees:
            fac.append({"factor": "Journals do not add up to the report", "effect": -30, "detail": "A reconciliation problem inside ASAVEXA."})
        fw = self._stage_framework(list(types) if metric != "net_income" else ["REVENUE", "EXPENSE"])
        if not fw["available"]:
            fac.append({"factor": "Reporting framework configured", "effect": -10, "detail": "No framework is configured."})
        conf = confidence(fac)
        reasons = []
        if verdict != "PROVEN":
            reasons.append(f"Verdict is {self._verdict_text(verdict)}.")
        if conf["level"] != HIGH:
            reasons.append(f"Confidence is {conf['level']} ({conf['score']}).")
        sources = [source_record("PERIOD", p.id, f"Period {p.name}", B._val(p.status))] + [
            source_record("JOURNAL", r["journal_id"], f"Journal {r['journal_number']}", r["description"], r["path"]) for r in rows[:15]]
        ev_rows, seen = [], set()
        for j, _c in contrib[:30]:
            for e in self._all_evidence_for(j):
                if e.id not in seen:
                    seen.add(e.id)
                    ev_rows.append(self._ev_row(e))
                    sources.append(source_record("EVIDENCE", e.id, e.original_filename, B._val(e.status), f"/evidence/{e.id}"))
        evid = {"available": bool(ev_rows), "state": "VERIFIED" if n and counts["VERIFIED"] == n else "MIXED" if ev_rows else "MISSING",
                "records": ev_rows, "expected_types": [], "coverage": {**{k.lower(): v for k, v in counts.items()}, "journals": n, "verified_amount_percent": float(share.quantize(Decimal("0.1")))},
                "note": "Evidence behind every contributing journal; see 'contributions' for each journal's own status." if ev_rows else
                        "MISSING EVIDENCE: none of the contributing journals has evidence."}
        policies = []
        return validate_item({
            "title": f"Proof for {name} in {p.name}",
            "conclusion": {"summary": summary, "points": pts}, "source_records": sources, "evidence": evid,
            "journal": unavailable(f"A figure is built from {n} journal(s); open each from the contributions list."),
            "accounting_treatment": {"available": True, "classification": {"code": "AGGREGATE", "meaning": f"{name} is the net of posted lines on {', '.join(t.lower() for t in types)} accounts in the period",
                                                                            "usual": True, "rule": "Same calculation as the Reporting module and the Financial Passport."},
                                      "debits": [], "credits": [], "policies": policies, "note": "Figures are computed from posted journals only; drafts are excluded."},
            "reporting_framework": fw, "confidence": conf, "human_review": human_review(bool(reasons), reasons or ["Advisory output; always read-only."], "an approver or finance officer" if reasons else None),
            "verdict": verdict, "checks": checks, "contributions": rows[:50],
            "figure": {"metric": metric, "period": p.name, "reported": B._money(reported), "currency": cur}})

    # =============================================================== ASK
    MODE_WORDS = {
        "PROVE": ("prove", "proof", "evidence", "support", "supporting", "verify", "substantiate", "back up", "documentation"),
        "DETECT": ("unusual", "anomal", "suspicious", "suspect", "detect", "outlier", "duplicate", "odd ", "strange", "irregular", "red flag", "look wrong"),
        "RECOMMEND": ("recommend", "suggest", "reconcil", "adjust", "correct", "fix", "what should", "propose", "next step"),
        "EXPLAIN": ("why", "explain", "classif", "how come", "reason", "what is", "what was", "treated", "treatment", "categor"),
    }
    MODE_PRIORITY = ("PROVE", "DETECT", "RECOMMEND", "EXPLAIN")
    FIGURE_WORDS = (("net income", "net_income"), ("net profit", "net_income"), ("profit", "net_income"), ("revenue", "revenue"),
                    ("sales", "revenue"), ("income", "revenue"), ("expenses", "expenses"), ("expense", "expenses"),
                    ("assets", "assets"), ("liabilities", "liabilities"))

    def _cannot(self, mode: Optional[str], question: str, why: str, can_do: List[str]) -> dict:
        r = refusal(question, why, can_do)
        env = self._envelope(mode or "ASK", question, {"mode": mode, "understood": False}, r["title"] + ": " + why, [], self._limits("explain"),
                             {"refusal": r})
        env["grounded"] = False
        return env

    def _recent_hint(self) -> List[str]:
        recent = sorted(self.posted, key=lambda j: (j.date, j.journal_number), reverse=True)[:5]
        return [f"{j.journal_number} ({j.description})" for j in recent]

    def ask(self, question: str) -> dict:
        qtext = (question or "").strip()
        if not qtext:
            raise AiValidationError("Type a question first.")
        if len(qtext) > 500:
            raise AiValidationError("Please keep the question under 500 characters.")
        low = " " + qtext.lower() + " "
        scores = {m: sum(1 for w in ws if w in low) for m, ws in self.MODE_WORDS.items()}
        # "why ... evidence" is still a question about classification unless it asks to show/prove
        best = max(scores.values())
        mode = None
        if best > 0:
            mode = next(m for m in self.MODE_PRIORITY if scores[m] == best)
        # the opening word is the strongest clue about what is being asked
        first = low.split()[0] if low.split() else ""
        lead = {"suggest": "RECOMMEND", "recommend": "RECOMMEND", "propose": "RECOMMEND", "why": "EXPLAIN", "explain": "EXPLAIN",
                "find": "DETECT", "detect": "DETECT", "flag": "DETECT", "spot": "DETECT", "prove": "PROVE", "show": "PROVE"}.get(first)
        if lead:
            mode = lead
        help_list = ["Explain: 'Why was JRN-000002 classified this way?'", "Detect: 'Find unusual transactions.'",
                     "Recommend: 'Suggest a reconciliation or adjustment.'", "Prove: 'Show the evidence for JRN-000002.'"]
        if mode is None:
            return self._cannot(None, qtext, "I could not tell whether you want an explanation, unusual transactions, a recommendation or proof.", help_list)
        ref = None
        m = JRN_RE.search(qtext)
        if m and m.group(0).upper() in self.by_number:
            ref = ("journal", self.by_number[m.group(0).upper()].id)
        elif m:
            return self._cannot(mode, qtext, f"There is no journal {m.group(0).upper()} in this organisation.", self._recent_hint())
        for u in UUID_RE.findall(qtext):
            if u in self.by_id:
                ref = ("journal", u)
                break
            if u in self.txs:
                ref = ("bank_transaction", u)
                break
        period = next((p for p in sorted(self.inp.periods, key=lambda p: -len(p.name)) if p.name.lower() in low), None)
        if mode == "EXPLAIN":
            if ref is None:
                return self._cannot("EXPLAIN", qtext, "Tell me which transaction (a journal number like JRN-000002, or a bank line id).", self._recent_hint())
            return self.explain(ref[0], ref[1], qtext)
        if mode == "DETECT":
            return self.detect(period.id if period else None, 20, qtext)
        if mode == "RECOMMEND":
            scope = "evidence" if "evidence" in low else "reconciliation" if "reconcil" in low else "adjustment" if ("adjust" in low or "correct" in low) else "all"
            return self.recommend(scope, period.id if period else None, 15, qtext)
        # PROVE
        if ref is not None:
            return self.prove(ref[0], ref[1], question=qtext)
        metric = next((m2 for w, m2 in self.FIGURE_WORDS if w in low), None)
        if metric:
            if period is None:
                active = [p for p in self.inp.periods if any(j.period_id == p.id for j in self.posted)]
                if len(active) == 1:
                    period = active[0]
                else:
                    return self._cannot("PROVE", qtext, "Which period? Name it, for example: 'Prove revenue for " + (self.inp.periods[0].name if self.inp.periods else "FY2026-M01") + "'.",
                                        [p.name for p in sorted(self.inp.periods, key=lambda p: p.start_date)][:8])
            return self.prove("figure", metric=metric, period_id=period.id, question=qtext)
        return self._cannot("PROVE", qtext, "Tell me what to prove: a journal number like JRN-000002, or a figure such as 'revenue for FY2026-M01'.", self._recent_hint())
