"""Organisation security settings, data-residency controls and the vendor-risk register."""
from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta, timezone
from typing import Callable, List, Optional

from .errors import NotFoundError, ResidencyError, ValidationError
from .store import DocStore


def _utc():
    return datetime.now(timezone.utc)


REGIONS = {"NG": "Nigeria", "GH": "Ghana", "KE": "Kenya", "ZA": "South Africa", "EU": "European Union", "UK": "United Kingdom",
           "US": "United States", "CA": "Canada", "AE": "United Arab Emirates", "SG": "Singapore", "IN": "India", "AU": "Australia"}
UNKNOWN_REGIONS = {"", "unspecified", "unknown", "local", "test-region"}


class SettingsService:
    DEFAULTS = {"require_mfa": False, "allowed_regions": []}

    def __init__(self, store: DocStore, now: Callable[[], datetime] = _utc):
        self.store, self.now = store, now

    def get(self, org_id: str) -> dict:
        return {**self.DEFAULTS, **(self.store.get("org_settings", org_id) or {})}

    def update(self, org_id: str, actor: str, require_mfa=None, allowed_regions=None) -> dict:
        s = self.get(org_id)
        if require_mfa is not None:
            if not isinstance(require_mfa, bool):
                raise ValidationError("require_mfa must be true or false.")
            s["require_mfa"] = require_mfa
        if allowed_regions is not None:
            regs = [str(r).upper() for r in allowed_regions]
            bad = [r for r in regs if r not in REGIONS]
            if bad:
                raise ValidationError(f"Unknown region code(s): {', '.join(bad)}. Use: {', '.join(REGIONS)}.")
            s["allowed_regions"] = sorted(set(regs))
        s.update(updated_by=actor, updated_at=self.now().isoformat())
        self.store.put("org_settings", org_id, s, org_id=org_id)
        return s


class ResidencyService:
    def __init__(self, settings: SettingsService, vendors: "VendorRegister" = None):
        self.settings, self.vendors = settings, vendors

    def check_storage(self, org_id: str, region: str) -> None:
        allowed = self.settings.get(org_id)["allowed_regions"]
        if not allowed:
            return
        r = (region or "").strip()
        if r.lower() in UNKNOWN_REGIONS:
            raise ResidencyError(f"This organisation requires its data to stay in {', '.join(allowed)}, but the storage location has not been "
                                 "declared (set ASAVEXA_DATA_REGION or the object-storage region). Nothing was stored.")
        if r.upper() not in allowed:
            raise ResidencyError(f"This organisation requires its data to stay in {', '.join(allowed)}; the storage is in {r}. Nothing was stored.")

    def report(self, org_id: str, storage_region: str, database_region: str) -> dict:
        allowed = self.settings.get(org_id)["allowed_regions"]

        def ok(r):
            return (not allowed) or (r or "").upper() in allowed
        rows = [{"what": "Database (records, audit log)", "region": database_region or "unspecified", "ok": ok(database_region)},
                {"what": "Evidence file storage", "region": storage_region or "unspecified", "ok": ok(storage_region)}]
        out_of_region = []
        if self.vendors is not None:
            for v in self.vendors.list(org_id):
                if v["status"] != "ACTIVE" or not v["receives_personal_or_financial_data"]:
                    continue
                if not ok(v["region"]):
                    out_of_region.append({"vendor": v["name"], "region": v["region"] or "unspecified"})
        return {"allowed_regions": allowed, "locations": rows, "vendors_outside_policy": out_of_region,
                "compliant": all(r["ok"] for r in rows) and not out_of_region, "restricted": bool(allowed),
                "note": "Regions are as declared by the operator; ASAVEXA cannot detect where a provider really keeps data. Confirm with each provider."}


TIERS = ("LOW", "MEDIUM", "HIGH", "CRITICAL")
DATA_WEIGHT = {"FINANCIAL": 3, "PERSONAL": 2, "CREDENTIALS": 4, "SOURCE_CODE": 1, "TELEMETRY": 1, "NONE": 0}
REVIEW_DAYS = {"LOW": 730, "MEDIUM": 365, "HIGH": 180, "CRITICAL": 90}


class VendorRegister:
    """Who touches our data, what they touch, where, and when we last checked them. Risk is computed from facts, never typed in."""
    def __init__(self, store: DocStore, now: Callable[[], datetime] = _utc):
        self.store, self.now = store, now

    @staticmethod
    def assess(v: dict) -> dict:
        score, reasons = 0, []
        cats = v.get("data_categories") or []
        score += max([DATA_WEIGHT.get(c, 1) for c in cats] or [0])
        if not v.get("dpa_signed") and any(c in ("FINANCIAL", "PERSONAL", "CREDENTIALS") for c in cats):
            score += 2; reasons.append("Handles sensitive data without a signed data-processing agreement.")
        if not v.get("security_attestation"):
            score += 1; reasons.append("No security report or certification on file.")
        if (v.get("region") or "").lower() in UNKNOWN_REGIONS:
            score += 1; reasons.append("Where the vendor keeps data is not confirmed.")
        if v.get("subprocessors_known") is False:
            score += 1; reasons.append("Its sub-processors are not known.")
        if not v.get("exit_plan"):
            score += 1; reasons.append("No plan for leaving this vendor.")
        tier = "CRITICAL" if score >= 7 else "HIGH" if score >= 5 else "MEDIUM" if score >= 3 else "LOW"
        return {"risk_score": score, "risk_tier": tier, "risk_reasons": reasons}

    def _norm(self, d: dict) -> dict:
        name = (d.get("name") or "").strip()
        if not name or len(name) > 120:
            raise ValidationError("Give the vendor a name (up to 120 characters).")
        cats = [str(c).upper() for c in (d.get("data_categories") or [])]
        bad = [c for c in cats if c not in DATA_WEIGHT]
        if bad:
            raise ValidationError(f"Unknown data categories: {', '.join(bad)}. Use: {', '.join(DATA_WEIGHT)}.")
        status = (d.get("status") or "ACTIVE").upper()
        if status not in ("ACTIVE", "UNDER_REVIEW", "OFFBOARDED"):
            raise ValidationError("Status must be ACTIVE, UNDER_REVIEW or OFFBOARDED.")
        last = d.get("last_reviewed")
        if last:
            try:
                date.fromisoformat(last)
            except ValueError:
                raise ValidationError("Review dates must look like 2026-10-31.")
        return {"name": name, "purpose": (d.get("purpose") or "")[:300], "data_categories": cats, "region": (d.get("region") or "").strip(),
                "dpa_signed": bool(d.get("dpa_signed")), "security_attestation": (d.get("security_attestation") or "")[:200],
                "subprocessors_known": d.get("subprocessors_known"), "exit_plan": bool(d.get("exit_plan")), "status": status,
                "last_reviewed": last or None, "owner": (d.get("owner") or "")[:120], "notes": (d.get("notes") or "")[:1000]}

    def _out(self, vid: str, d: dict) -> dict:
        d = {**d, **self.assess(d)}
        d["receives_personal_or_financial_data"] = any(c in ("FINANCIAL", "PERSONAL", "CREDENTIALS") for c in d["data_categories"])
        base = date.fromisoformat(d["last_reviewed"]) if d.get("last_reviewed") else None
        due = (base + timedelta(days=REVIEW_DAYS[d["risk_tier"]])) if base else None
        d["next_review_due"] = due.isoformat() if due else None
        d["review_overdue"] = d["status"] == "ACTIVE" and (due is None or due < self.now().date())
        d["id"] = vid
        return d

    def add(self, org_id: str, actor: str, data: dict) -> dict:
        vid = str(uuid.uuid4()); d = self._norm(data)
        d.update(created_by=actor, created_at=self.now().isoformat())
        self.store.put("vendor", f"{org_id}:{vid}", d, org_id=org_id)
        return self._out(vid, d)

    def update(self, org_id: str, vendor_id: str, actor: str, data: dict) -> dict:
        cur = self.store.get("vendor", f"{org_id}:{vendor_id}")
        if cur is None:
            raise NotFoundError("Vendor not found.")
        d = self._norm({**cur, **data}); d.update(created_by=cur.get("created_by"), created_at=cur.get("created_at"), updated_by=actor)
        self.store.put("vendor", f"{org_id}:{vendor_id}", d, org_id=org_id)
        return self._out(vendor_id, d)

    def list(self, org_id: str) -> List[dict]:
        out = [self._out(k.split(":", 1)[1], d) for k, d in self.store.list("vendor", org_id=org_id)]
        return sorted(out, key=lambda v: (-v["risk_score"], v["name"].lower()))

    def seed_platform_vendors(self, org_id: str, actor: str) -> List[dict]:
        """Starting entries for the services ASAVEXA itself runs on. Facts that only the operator can confirm are left blank,
        so they show as 'needs review' instead of being assumed."""
        have = {v["name"] for v in self.list(org_id)}
        seeds = [
            {"name": "Render", "purpose": "Hosts the API and the database", "data_categories": ["FINANCIAL", "PERSONAL", "CREDENTIALS"]},
            {"name": "Vercel", "purpose": "Hosts the web app (static files)", "data_categories": ["TELEMETRY"]},
            {"name": "GitHub", "purpose": "Source code and deployment pipeline", "data_categories": ["SOURCE_CODE"]},
        ]
        return [self.add(org_id, actor, s) for s in seeds if s["name"] not in have]
