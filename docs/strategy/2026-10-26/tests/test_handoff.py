from __future__ import annotations
import copy
import importlib.util
import json
import unittest
from pathlib import Path
import jsonschema

ROOT = Path(__file__).resolve().parents[1]

def module(name, relative):
    spec = importlib.util.spec_from_file_location(name, ROOT / relative)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod

P = module("planner", "examples/adapter/adaptive_plan.py")
V = module("validator", "scripts/validate_handoff.py")

def load(p):
    return json.loads((ROOT / p).read_text(encoding="utf-8"))

class PlannerTests(unittest.TestCase):
    def setUp(self):
        self.pack = load("examples/packs/workday.pack.json")
        self.inv = load("examples/inventory/full.json")
        self.now = "2026-10-26T12:00:10Z"
    def result(self): return P.plan(self.pack, self.inv, self.now)
    def test_full_inventory_ready(self):
        self.assertEqual(self.result()["status"], "ready")
    def test_optional_missing_degrades(self):
        self.inv = load("examples/inventory/optional-missing.json")
        self.assertEqual(self.result()["status"], "degraded")
    def test_missing_provider_is_explained_without_install_instruction(self):
        required_by_id = {binding["id"]: binding["required"] for binding in self.pack["bindings"]}
        for fixture, expected_status in (
            ("examples/inventory/required-missing.json", "blocked"),
            ("examples/inventory/optional-missing.json", "degraded"),
        ):
            with self.subTest(fixture=fixture):
                result = P.plan(self.pack, load(fixture), self.now)
                self.assertEqual(result["status"], expected_status)
                missing = [b for b in result["bindings"] if b["status"] == "missing"]
                self.assertTrue(missing)
                for binding in missing:
                    self.assertEqual(binding["reason"], "no_online_fresh_authorized_compatible_provider")
                    collection = "blockers" if required_by_id[binding["binding_id"]] else "warnings"
                    self.assertIn(binding["binding_id"] + ":missing", result[collection])
                self.assertIs(result["mutates_host"], False)
                self.assertIs(result["requires_confirmation"], True)
                serialized = json.dumps(result, ensure_ascii=False).casefold()
                self.assertNotIn("install_command", serialized)
                self.assertNotIn("download_url", serialized)
    def test_required_missing_blocks(self):
        self.inv = load("examples/inventory/required-missing.json")
        self.assertEqual(self.result()["status"], "blocked")
    def test_permission_is_not_capability(self):
        self.inv = load("examples/inventory/no-grant.json")
        self.assertEqual(self.result()["status"], "blocked")
    def test_ambiguous_does_not_choose_first(self):
        self.inv = load("examples/inventory/ambiguous.json")
        self.assertEqual(self.result()["bindings"][0]["status"], "ambiguous")
        self.assertIsNone(self.result()["bindings"][0]["provider_instance_id"])
    def test_explicit_selection(self):
        self.inv = load("examples/inventory/ambiguous.json")
        r = P.plan(self.pack, self.inv, self.now, {"agents": "board-2"})
        self.assertEqual(r["status"], "ready")
        self.assertEqual(r["bindings"][0]["provider_instance_id"], "board-2")
    def test_invalid_explicit_selection_blocks(self):
        r = P.plan(self.pack, self.inv, self.now, {"agents": "not-present"})
        self.assertEqual(r["status"], "blocked")
    def test_unknown_binding_rejected(self):
        with self.assertRaises(ValueError): P.plan(self.pack, self.inv, self.now, {"unknown":"x"})
    def test_expired_inventory_blocks(self):
        self.now = "2026-10-26T12:02:00Z"
        self.assertIn("inventory_expired", self.result()["blockers"])
    def test_stale_source_cannot_fill_required(self):
        self.inv["providers"][0]["source_updated_at"] = "2026-10-26T11:00:00Z"
        self.assertEqual(self.result()["status"], "blocked")
    def test_future_clock_is_not_silently_fresh(self):
        self.now = "2026-10-26T11:59:00Z"
        with self.assertRaises(ValueError): self.result()
    def test_naive_time_rejected(self):
        self.now = "2026-10-26T12:00:10"
        with self.assertRaises(ValueError): self.result()
    def test_duplicate_instance_rejected(self):
        self.inv["providers"].append(copy.deepcopy(self.inv["providers"][0]))
        with self.assertRaises(ValueError): self.result()
    def test_duplicate_binding_rejected(self):
        self.pack["bindings"].append(copy.deepcopy(self.pack["bindings"][0]))
        with self.assertRaises(ValueError): self.result()
    def test_provider_version_checked(self):
        self.pack["bindings"][0]["min_adapter_contract"] = 2
        self.assertEqual(self.result()["status"], "blocked")
    def test_offline_provider_not_used(self):
        self.inv["providers"][0]["state"] = "offline"
        self.assertEqual(self.result()["status"], "blocked")
    def test_deterministic_digest(self):
        self.assertEqual(self.result(), self.result())
        a = self.result()["input_digest"]
        self.inv["generation"] += 1
        self.assertNotEqual(a, self.result()["input_digest"])
    def test_input_not_mutated(self):
        before = copy.deepcopy((self.pack, self.inv))
        self.result()
        self.assertEqual(before, (self.pack, self.inv))
    def test_no_host_mutations(self):
        r = self.result()
        self.assertIs(r["mutates_host"], False)
        self.assertIs(r["requires_confirmation"], True)
    def test_external_adapter_never_executed(self):
        self.pack["adapter"] = {"kind":"external-program-reference", "id":"fixture.adapter", "reference":"fixture-only", "sha256":"0"*64, "execution":"separate-user-approval"}
        self.assertIn("external_adapter_not_executed", self.result()["warnings"])
    def test_plan_matches_schema(self):
        jsonschema.Draft202012Validator(load("contracts/resolution-plan.schema.json"), format_checker=jsonschema.FormatChecker()).validate(self.result())
    def test_top_level_secret_field_rejected(self):
        self.pack["token"] = "negative-fixture"
        with self.assertRaises(ValueError): self.result()
    def test_plan_expiry_bounded_by_source(self):
        self.inv["providers"][0]["fresh_for_seconds"] = 20
        self.assertEqual(self.result()["expires_at"], "2026-10-26T12:00:20Z")

class ContractTests(unittest.TestCase):
    def test_all_positive_and_negative_fixtures(self):
        for case in load("contracts/examples-index.json")["cases"]:
            with self.subTest(path=case["path"]):
                v = load(case["path"])
                errors = list(jsonschema.Draft202012Validator(load("contracts/"+case["schema"]+".schema.json"), format_checker=jsonschema.FormatChecker()).iter_errors(v))
                semantic = [] if errors else V.semantic_errors(case["schema"], v)
                self.assertEqual(not errors and not semantic, case["expected_valid"])
    def test_pack_rejects_provider_binary_descriptor_lease_and_install_hook(self):
        validator = jsonschema.Draft202012Validator(
            load("contracts/pack.schema.json"),
            format_checker=jsonschema.FormatChecker(),
        )
        base = load("examples/packs/workday.pack.json")
        forbidden_fields = (
            ("provider_binary", "fixture-provider.exe"),
            ("descriptor", {"token": "synthetic-negative-fixture"}),
            ("lease", {"id": "synthetic-negative-fixture"}),
            ("install_hook", "run this command"),
        )
        for key, value in forbidden_fields:
            with self.subTest(key=key):
                candidate = copy.deepcopy(base)
                candidate[key] = value
                self.assertTrue(list(validator.iter_errors(candidate)))
        adapter_payload = copy.deepcopy(base)
        adapter_payload["adapter"] = {
            "kind": "external-program-reference",
            "id": "fixture.adapter",
            "reference": "fixture-only",
            "sha256": "0" * 64,
            "execution": "separate-user-approval",
            "binary": "fixture-provider.exe",
        }
        self.assertTrue(list(validator.iter_errors(adapter_payload)))
    def test_other_not_author_supplied(self):
        v=load("examples/ephemeral/question.json")
        v["payload"]["questions"][0]["options"][1]["label"]="Other"
        self.assertTrue(V.semantic_errors("ephemeral-request",v))
    def test_recommended_only_first(self):
        v=load("examples/ephemeral/question.json")
        v["payload"]["questions"][0]["options"][1]["recommended"]=True
        self.assertTrue(V.semantic_errors("ephemeral-request",v))
    def test_duplicate_question_rejected(self):
        v=load("examples/ephemeral/question.json")
        v["payload"]["questions"].append(copy.deepcopy(v["payload"]["questions"][0]))
        self.assertTrue(V.semantic_errors("ephemeral-request",v))
    def test_path_traversal_rejected(self):
        v=load("examples/packs/workday.pack.json")
        v["blueprint"]="../../outside.json"
        self.assertTrue(V.semantic_errors("pack",v))
    def test_complete_handoff_crosslinks(self):
        report=V.check(ROOT)
        self.assertEqual(report["errors"], [], report)


class MaintenanceTests(unittest.TestCase):
    def temporary_package(self, directory):
        import shutil
        target=Path(directory)/"handoff"
        shutil.copytree(ROOT,target,ignore=shutil.ignore_patterns("__pycache__","*.pyc","evidence","MANIFEST.sha256"))
        # Link validation is not run on this intentionally partial copy.
        return target
    def render(self, target, *extra):
        import subprocess,sys
        r=subprocess.run([sys.executable,str(target/"scripts/render_plan.py"),"--date","2026-10-26",*extra],capture_output=True,text=True,encoding="utf-8",timeout=15)
        self.assertEqual(r.returncode,0,r.stderr)
    def test_translation_source_hash_ignores_crlf_checkout(self):
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            text="WinCraft source heading\nA stable translated paragraph.\n"
            lf=Path(d)/"source-lf.md"
            crlf=Path(d)/"source-crlf.md"
            lf.write_bytes(text.encode("utf-8"))
            crlf.write_bytes(text.replace("\n","\r\n").encode("utf-8"))
            self.assertEqual(V.text_sha256(lf),V.text_sha256(crlf))
    def test_renderer_preserves_unchanged_synthetic_case_result(self):
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            target=self.temporary_package(d)
            p=target/"plan/acceptance.json"
            a=json.loads(p.read_text(encoding="utf-8"));a["cases"][0]["status"]="PASS_SYNTHETIC_MAINTENANCE_TEST"
            p.write_text(json.dumps(a),encoding="utf-8")
            self.render(target)
            self.assertEqual(json.loads(p.read_text(encoding="utf-8"))["cases"][0]["status"],"PASS_SYNTHETIC_MAINTENANCE_TEST")
    def test_changed_criterion_invalidates_old_result(self):
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            target=self.temporary_package(d)
            p=target/"plan/acceptance.json"
            a=json.loads(p.read_text(encoding="utf-8"));a["cases"][0]["status"]="PASS_SYNTHETIC_MAINTENANCE_TEST";p.write_text(json.dumps(a),encoding="utf-8")
            tp=target/"plan/tasks.json"
            tasks=json.loads(tp.read_text(encoding="utf-8"));tasks["tasks"][0]["acceptance"][0]["criterion"]+=" (changed fixture)";tp.write_text(json.dumps(tasks),encoding="utf-8")
            self.render(target)
            self.assertEqual(json.loads(p.read_text(encoding="utf-8"))["cases"][0]["status"],"NOT_RUN")
    def test_explicit_reset_invalidates_results(self):
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            target=self.temporary_package(d)
            p=target/"plan/acceptance.json"
            a=json.loads(p.read_text(encoding="utf-8"));a["cases"][0]["status"]="PASS_SYNTHETIC_MAINTENANCE_TEST";p.write_text(json.dumps(a),encoding="utf-8")
            self.render(target,"--reset-results")
            self.assertEqual(json.loads(p.read_text(encoding="utf-8"))["cases"][0]["status"],"NOT_RUN")
    def test_nongit_baseline_check_is_readonly(self):
        import tempfile,subprocess,sys
        with tempfile.TemporaryDirectory() as d:
            r=subprocess.run([sys.executable,str(ROOT/"scripts/check_repo_baseline.py"),"--repo",d],capture_output=True,text=True,encoding="utf-8",timeout=20)
            self.assertEqual(r.returncode,2)
            self.assertEqual(list(Path(d).iterdir()),[])
            self.assertFalse(json.loads(r.stdout)["mutated_repository"])
    def test_synthetic_git_missing_baseline_does_not_reset(self):
        import tempfile,subprocess,sys,shutil
        if not shutil.which("git"): self.skipTest("git not present")
        with tempfile.TemporaryDirectory() as d:
            subprocess.run(["git","init","-q",d],check=True,capture_output=True)
            subprocess.run(["git","-C",d,"-c","user.name=Fixture","-c","user.email=fixture@example.invalid","commit","--allow-empty","-qm","synthetic baseline"],check=True,capture_output=True)
            before=subprocess.check_output(["git","-C",d,"rev-parse","HEAD"],text=True).strip()
            r=subprocess.run([sys.executable,str(ROOT/"scripts/check_repo_baseline.py"),"--repo",d],capture_output=True,text=True,encoding="utf-8",timeout=20)
            after=subprocess.check_output(["git","-C",d,"rev-parse","HEAD"],text=True).strip()
            self.assertEqual(r.returncode,3)
            self.assertEqual(before,after)
            self.assertEqual(json.loads(r.stdout)["relation"],"baseline-unavailable")

if __name__ == "__main__":
    unittest.main()
