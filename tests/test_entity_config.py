"""Stage 15: organisation type, subtype and enabled workspaces."""
import re
import unittest
from datetime import datetime, timezone

from asavexa.entities import catalog as C
from asavexa.entities.service import EntityConfigConflictError, EntityConfigError, EntityConfigService
from asavexa.security.store import MemoryDocStore
from asavexa.workspaces import WORKSPACES

ORG, OTHER = "org-1", "org-2"
IDS = [w["id"] for w in WORKSPACES]


def make(ids=None, events=None):
    ev = events if events is not None else []
    return EntityConfigService(MemoryDocStore(), lambda: list(ids or IDS), log=lambda *a, **k: ev.append(a), now=lambda: datetime(2026, 10, 1, tzinfo=timezone.utc)), ev


class CatalogTests(unittest.TestCase):
    def test_codes_are_unique_and_every_suggested_workspace_really_exists(self):
        codes = [t["code"] for t in C.ENTITY_TYPES]
        self.assertEqual(len(codes), len(set(codes)))
        for t in C.ENTITY_TYPES:
            self.assertTrue(t["suggested_workspaces"], t["code"])
            self.assertTrue(set(t["suggested_workspaces"]) <= set(IDS), (t["code"], set(t["suggested_workspaces"]) - set(IDS)))
            sub = [s["code"] for s in t["subtypes"]]
            self.assertTrue(sub and len(sub) == len(set(sub)), t["code"])

    def test_every_onboarding_category_maps_to_a_type(self):
        js = open("frontend/src/lib/onboarding.js", encoding="utf-8").read()
        block = re.search(r"export const CATEGORIES = \[(.*?)\];", js, re.S).group(1)
        cats = re.findall(r'"([^"]+)"', block)
        self.assertEqual(len(cats), 8)
        for c in cats:
            self.assertIn(c, C.LEGACY_TO_TYPE, c)
            self.assertIn(C.LEGACY_TO_TYPE[c], C.BY_CODE)

    def test_the_document_s_organisation_kinds_are_all_represented(self):
        labels = " ".join(s["label"].lower() for t in C.ENTITY_TYPES for s in t["subtypes"])
        for word in ("sole trader", "startup", "holding", "bank", "insurer", "fund", "ministry", "municipality", "utility", "charity", "humanitarian", "church",
                     "association", "school", "university", "hospital", "pharmacy", "construction", "manufacturing", "agriculture", "retail", "logistics", "energy",
                     "hospitality", "regulator", "certification", "donor", "investor", "law firm", "social enterprise", "cooperative"):
            self.assertIn(word, labels, word)

    def test_the_note_says_it_changes_no_access(self):
        self.assertIn("does not change anyone's access", C.NOTE)


class SavingTests(unittest.TestCase):
    def setUp(self):
        self.s, self.ev = make()

    def test_an_unconfigured_organisation_shows_everything(self):
        v = self.s.get_entity_config(ORG)
        self.assertFalse(v["configured"]); self.assertEqual(v["shown_workspaces"], IDS)
        self.assertTrue(all(self.s.workspace_enabled(ORG, w) for w in IDS))

    def test_first_save_defaults_to_the_suggested_workspaces_and_is_audited(self):
        v = self.s.save_entity_config(ORG, "u1", "HEALTH", "HOSPITAL")
        self.assertTrue(v["configured"]); self.assertEqual(v["version"], 1)
        self.assertEqual(v["shown_workspaces"], [w for w in IDS if w in C.BY_CODE["HEALTH"]["suggested_workspaces"]])
        self.assertEqual([h["event"] for h in v["history"]], ["CONFIGURED"])
        self.assertEqual(self.ev[-1][0], "ENTITY_CONFIG_SAVED")
        self.assertFalse(self.s.workspace_enabled(ORG, "forensic"))
        self.assertTrue(self.s.workspace_enabled(ORG, "health"))

    def test_explicit_workspaces_are_kept_in_catalogue_order_without_duplicates(self):
        v = self.s.save_entity_config(ORG, "u1", "BUSINESS", None, None, ["tax", "analysis", "tax"])
        self.assertEqual(v["shown_workspaces"], [w for w in IDS if w in ("tax", "analysis")])

    def test_an_empty_list_hides_every_workspace_on_purpose(self):
        v = self.s.save_entity_config(ORG, "u1", "BUSINESS", None, None, [])
        self.assertEqual(v["shown_workspaces"], [])

    def test_bad_input_is_refused_with_a_plain_message(self):
        bad = [dict(entity_type="NOPE"), dict(entity_type="BUSINESS", subtype="HOSPITAL"), dict(entity_type="BUSINESS", enabled_workspaces=["nope"]),
               dict(entity_type="BUSINESS", enabled_workspaces="analysis"), dict(entity_type="BUSINESS", enabled_workspaces=[1]),
               dict(entity_type="BUSINESS", languages=["english"]), dict(entity_type="BUSINESS", languages=["en", "fr", "de", "es", "pt", "it"]),
               dict(entity_type="BUSINESS", timezone_name="not a zone!"), dict(entity_type="BUSINESS", custom_subtype="x" * 81)]
        for kw in bad:
            with self.assertRaises(EntityConfigError, msg=str(kw)):
                self.s.save_entity_config(ORG, "u1", **kw)
        self.assertFalse(self.s.get_entity_config(ORG)["configured"])

    def test_custom_description_languages_and_timezone_are_cleaned_and_kept(self):
        v = self.s.save_entity_config(ORG, "u1", "NONPROFIT", "CHARITY", "  Village\x00  water\n trust ", None, ["en", "fr-CA", "en"], "Africa/Lagos")
        self.assertEqual((v["custom_subtype"], v["languages"], v["timezone"]), ("Village water trust", ["en", "fr-CA"], "Africa/Lagos"))

    def test_changing_needs_a_reason_and_records_what_changed(self):
        self.s.save_entity_config(ORG, "u1", "BUSINESS", "SME")
        with self.assertRaises(EntityConfigError):
            self.s.save_entity_config(ORG, "u1", "FINANCIAL", "BANK")
        v = self.s.save_entity_config(ORG, "u2", "FINANCIAL", "BANK", note="We are a bank")
        self.assertEqual((v["version"], v["history"][-1]["event"], v["history"][-1]["by"]), (2, "CHANGED", "u2"))
        self.assertEqual(v["history"][-1]["changes"]["entity_type"], ["BUSINESS", "FINANCIAL"])
        self.assertEqual(len(v["history"]), 2)

    def test_a_save_that_changes_nothing_is_refused(self):
        self.s.save_entity_config(ORG, "u1", "BUSINESS", "SME")
        with self.assertRaises(EntityConfigConflictError):
            self.s.save_entity_config(ORG, "u1", "BUSINESS", "SME", note="again")

    def test_one_organisation_never_sees_or_changes_another(self):
        self.s.save_entity_config(ORG, "u1", "HEALTH")
        self.assertFalse(self.s.get_entity_config(OTHER)["configured"])
        self.s.save_entity_config(OTHER, "u9", "BUSINESS")
        self.assertEqual(self.s.get_entity_config(ORG)["entity_type"], "HEALTH")
        self.assertEqual(self.s.get_entity_config(OTHER)["entity_type"], "BUSINESS")

    def test_a_workspace_removed_from_the_product_drops_out_quietly(self):
        s, _ = make(ids=["analysis", "tax"]); s.save_entity_config(ORG, "u1", "BUSINESS", None, None, ["analysis", "tax"])
        s.workspace_ids = lambda: ["analysis"]
        self.assertEqual(s.get_entity_config(ORG)["shown_workspaces"], ["analysis"])

    def test_the_stored_record_holds_no_role_or_permission(self):
        self.s.save_entity_config(ORG, "u1", "BUSINESS")
        d = self.s.store.get("ent_config", f"{ORG}:config")
        self.assertFalse({"role", "roles", "permission", "permissions"} & set(d))
        import inspect
        from asavexa.entities import service
        self.assertNotIn("identity", inspect.getsource(service).split('"""', 2)[2])      # it never touches roles or the identity service

    def test_history_keeps_only_the_latest_twenty_in_the_view(self):
        self.s.save_entity_config(ORG, "u1", "BUSINESS", "SME")
        kinds = [("FINANCIAL", "BANK"), ("BUSINESS", "SME")] * 12
        for i, (t, st) in enumerate(kinds):
            self.s.save_entity_config(ORG, "u1", t, st, note=f"change {i}")
        v = self.s.get_entity_config(ORG)
        self.assertEqual(len(v["history"]), 20); self.assertEqual(v["version"], 25)


class RouterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import importlib, harness_security_routers  # noqa: F401
        cls.r = importlib.import_module("asavexa.api.routers.entity_config")

    def test_round_trip_and_status_codes(self):
        r, (s, _) = self.r, make()
        self.assertFalse(r.read(ORG, s)["configured"])
        self.assertTrue(r.catalog(ORG)["types"])
        v = r.save(r.EntityConfigBody(entity_type="EDUCATION", subtype="SCHOOL"), ORG, "u1", s)
        self.assertTrue(v["configured"])
        with self.assertRaises(Exception) as cm:
            r.save(r.EntityConfigBody(entity_type="EDUCATION", subtype="SCHOOL", note="x"), ORG, "u1", s)
        self.assertEqual(getattr(cm.exception, "status_code", None), 409)
        with self.assertRaises(Exception) as cm:
            r.save(r.EntityConfigBody(entity_type="NOPE"), ORG, "u1", s)
        self.assertEqual(getattr(cm.exception, "status_code", None), 400)

    def test_only_changing_needs_org_manage_settings(self):
        import inspect
        src = inspect.getsource(self.r)
        head = src[:src.index("def save(")].rsplit("@router", 1)[1]
        self.assertIn("ORG_MANAGE_SETTINGS", head)
        read_head = src[:src.index("def read(")].rsplit("@router", 1)[1]
        self.assertNotIn("require_permission", read_head)


if __name__ == "__main__":
    unittest.main()
