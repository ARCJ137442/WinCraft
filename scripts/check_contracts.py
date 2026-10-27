"""Offline artifact checks, NOT a Rust compilation or native-window test."""
from __future__ import annotations
import ast
import json
import re
import subprocess
import sys
import tomllib
import importlib.util
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
checks: list[str] = []

def main() -> None:
    for file in ROOT.rglob("*.json"):
        if any(x in file.parts for x in ("node_modules", "target", "gen")):
            continue
        json.loads(file.read_text(encoding="utf-8"))
    checks.append("json_parse")
    for file in ROOT.rglob("*.toml"):
        if "target" not in file.parts:
            tomllib.loads(file.read_text(encoding="utf-8"))
    checks.append("toml_parse")
    for file in list((ROOT / "examples/python").glob("*.py")) + list((ROOT / "scripts").glob("*.py")):
        ast.parse(file.read_text(encoding="utf-8"), filename=str(file))
    checks.append("python_syntax")
    host_locales = {
        locale: json.loads((ROOT / "apps/desktop/src/locales" / f"{locale}.json").read_text(encoding="utf-8"))
        for locale in ("zh-CN", "en-US")
    }
    assert set(host_locales["zh-CN"]) == set(host_locales["en-US"]), "host locale keys differ"
    for key in host_locales["zh-CN"]:
        zh_args = set(re.findall(r"\{([^}]+)\}", host_locales["zh-CN"][key]))
        en_args = set(re.findall(r"\{([^}]+)\}", host_locales["en-US"][key]))
        assert zh_args == en_args, f"host locale placeholders differ: {key}"
    checks.append("host_locale_key_and_placeholder_parity")
    generated_locale = subprocess.run(
        ["node", str(ROOT / "scripts/generate_locales.mjs"), "--check"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert generated_locale.returncode == 0, generated_locale.stderr or generated_locale.stdout
    checks.append("generated_host_locale_catalog_is_current")
    try:
        from jsonschema import Draft202012Validator, FormatChecker
        from referencing import Registry, Resource
    except ImportError as exc:
        raise SystemExit("Install validation extra: python -m pip install jsonschema") from exc
    request_schema = json.loads((ROOT / "protocol/request.schema.json").read_text(encoding="utf-8"))
    scene_schema = json.loads((ROOT / "protocol/scene.schema.json").read_text(encoding="utf-8"))
    event_schema = json.loads((ROOT / "protocol/event.schema.json").read_text(encoding="utf-8"))
    theme_schema = json.loads((ROOT / "protocol/theme.schema.json").read_text(encoding="utf-8"))
    usage_schema = json.loads((ROOT / "protocol/usage-observation.schema.json").read_text(encoding="utf-8"))
    web_chat_schema = json.loads((ROOT / "protocol/web-chat-observation.schema.json").read_text(encoding="utf-8"))
    voice_schema = json.loads((ROOT / "protocol/voice-session.schema.json").read_text(encoding="utf-8"))
    pack_schema_path = ROOT / "docs/strategy/2026-10-26/contracts/pack.schema.json"
    pack_examples = ROOT / "docs/strategy/2026-10-26/examples"
    Draft202012Validator.check_schema(request_schema)
    Draft202012Validator.check_schema(scene_schema)
    Draft202012Validator.check_schema(event_schema)
    Draft202012Validator.check_schema(theme_schema)
    Draft202012Validator.check_schema(usage_schema)
    Draft202012Validator.check_schema(web_chat_schema)
    Draft202012Validator.check_schema(voice_schema)
    pack_schema = json.loads(pack_schema_path.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(pack_schema)
    scene_registry = (
        Registry()
        .with_resource(theme_schema["$id"], Resource.from_contents(theme_schema))
        .with_resource(scene_schema["$id"], Resource.from_contents(scene_schema))
    )
    validator = Draft202012Validator(
        request_schema, format_checker=FormatChecker(), registry=scene_registry
    )
    scene_validator = Draft202012Validator(scene_schema, registry=scene_registry)
    event_validator = Draft202012Validator(
        event_schema, format_checker=FormatChecker(), registry=scene_registry
    )
    usage_validator = Draft202012Validator(usage_schema, format_checker=FormatChecker())
    web_chat_validator = Draft202012Validator(web_chat_schema, format_checker=FormatChecker())
    voice_validator = Draft202012Validator(voice_schema, format_checker=FormatChecker())
    pack_validator = Draft202012Validator(pack_schema)
    requests = json.loads((ROOT / "protocol/examples/requests.json").read_text(encoding="utf-8"))
    for request in requests:
        validator.validate(request)
    theme_request = json.loads((ROOT / "protocol/examples/theme.request.json").read_text(encoding="utf-8"))
    validator.validate(theme_request)
    scene_validator.validate(json.loads((ROOT / "protocol/examples/focus.scene.json").read_text(encoding="utf-8")))
    scene_validator.validate(json.loads((ROOT / "protocol/examples/textarea.scene.json").read_text(encoding="utf-8")))
    theme_scene = json.loads((ROOT / "protocol/examples/theme.scene.json").read_text(encoding="utf-8"))
    scene_validator.validate(theme_scene)
    native_window_scene = json.loads(
        (ROOT / "protocol/examples/native-window-actions.scene.json").read_text(encoding="utf-8")
    )
    scene_validator.validate(native_window_scene)
    window_events = json.loads((ROOT / "protocol/examples/window-events.json").read_text(encoding="utf-8"))
    for event in window_events:
        event_validator.validate(event)
    for observation in json.loads((ROOT / "protocol/examples/usage-observation.json").read_text(encoding="utf-8")):
        usage_validator.validate(observation)
    for observation in json.loads((ROOT / "protocol/examples/web-chat-observation.json").read_text(encoding="utf-8")):
        web_chat_validator.validate(observation)
    for session in json.loads((ROOT / "protocol/examples/voice-session.json").read_text(encoding="utf-8")):
        voice_validator.validate(session)
    pack_validator.validate(json.loads((pack_examples / "packs/workday.pack.json").read_text(encoding="utf-8")))
    for invalid_name in ("pack-with-token.json", "pack-with-provider.json"):
        assert not pack_validator.is_valid(json.loads((pack_examples / "invalid" / invalid_name).read_text(encoding="utf-8")))
    theme_only = Draft202012Validator(theme_schema)
    theme_only.validate(theme_scene["theme"])
    checks.append("schemas_and_positive_fixtures")
    for bad in [
        {"id":"x","method":"world.create","params":{"window":{"width":-1}}},
        {"id":"x","method":"scene.execute_javascript","params":{}},
        {"id":"x","method":"hello","params":{"protocol":"0.2","provider_name":"x"}},
    ]:
        assert not validator.is_valid(bad), bad
    assert not scene_validator.is_valid({"root":{"id":"button","kind":"button"}})
    textarea_scene = json.loads((ROOT / "protocol/examples/textarea.scene.json").read_text(encoding="utf-8"))
    unknown_shortcut = json.loads(json.dumps(textarea_scene))
    unknown_shortcut["root"]["children"][1]["props"]["shortcut"] = "ctrl+q"
    assert not scene_validator.is_valid(unknown_shortcut)
    invalid_theme = json.loads(json.dumps(theme_scene))
    invalid_theme["theme"]["accent"] = "url(javascript:alert(1))"
    assert not scene_validator.is_valid(invalid_theme)
    unknown_theme_token = json.loads(json.dumps(theme_scene))
    unknown_theme_token["theme"]["css"] = "body{display:none}"
    assert not scene_validator.is_valid(unknown_theme_token)
    invalid_native_app = json.loads(json.dumps(native_window_scene))
    invalid_native_app["root"]["children"][0]["props"]["native_window_action"]["application"] = "powershell"
    assert not scene_validator.is_valid(invalid_native_app)
    invalid_native_operation = json.loads(json.dumps(native_window_scene))
    invalid_native_operation["root"]["children"][0]["props"]["native_window_action"]["operation"] = "launch"
    assert not scene_validator.is_valid(invalid_native_operation)
    invalid_anchor = json.loads(json.dumps(requests[-1]))
    invalid_anchor["params"]["patch"]["anchor"]["corner"] = "center"
    assert not validator.is_valid(invalid_anchor)
    invalid_anchor_margin = json.loads(json.dumps(requests[-1]))
    invalid_anchor_margin["params"]["patch"]["anchor"]["margin_x"] = 10001
    assert not validator.is_valid(invalid_anchor_margin)
    invalid_usage = {
        "provider_id": "synthetic.teamsense",
        "account_scope": "account-a",
        "window": "window-a",
        "metric": "requests",
        "used": 1,
        "limit": 2,
        "unit": "requests",
        "reset_at": None,
        "observed_at": "2026-10-27T12:00:00Z",
        "freshness": "fresh",
        "authority": "provider",
        "extra": "must reject",
    }
    assert not usage_validator.is_valid(invalid_usage)
    invalid_web_chat = json.loads(json.dumps({
        "source_id": "synthetic.web-chat", "tab_instance_id": "tab-a", "conversation_id": "c",
        "page_lifecycle": "active", "mode": "send_result", "summary": None,
        "outbound_preview": "send", "send_state": "sent", "observed_at": "2026-10-27T12:00:00Z",
        "freshness": "fresh", "user_confirmation": False, "page_html": "must reject",
    }))
    assert not web_chat_validator.is_valid(invalid_web_chat)
    invalid_event = json.loads(json.dumps(window_events[0]))
    invalid_event["data"]["type"] = "window.arbitrary"
    assert not event_validator.is_valid(invalid_event)
    invalid_theme_request = json.loads(json.dumps(theme_request))
    invalid_theme_request["params"]["scene"]["theme"]["accent"] = "url(javascript:alert(1))"
    assert not validator.is_valid(invalid_theme_request)
    checks.append("negative_schema_fixtures")
    methods = json.loads((ROOT / "protocol/methods.json").read_text(encoding="utf-8"))["methods"]
    source = (ROOT / "crates/wincraft-server/src/hub.rs").read_text(encoding="utf-8")
    transport = (ROOT / "crates/wincraft-server/src/transport.rs").read_text(encoding="utf-8")
    for name in methods:
        assert f'"{name}"' in source + transport, name
    checks.append("declared_methods_present_in_rust_source_not_execution")
    for pattern in ("eval(", "new Function(", "innerHTML", "document.write("):
        assert not any(pattern in f.read_text(encoding="utf-8") for f in (ROOT / "apps/desktop/src").glob("*.ts")), pattern
    checks.append("no_dynamic_code_or_html_rendering")
    for manifest in ["crates/wincraft-core/Cargo.toml","crates/wincraft-server/Cargo.toml","apps/desktop/src-tauri/Cargo.toml"]:
        file = ROOT / manifest
        data = tomllib.loads(file.read_text(encoding="utf-8"))
        for dep in data.get("dependencies", {}).values():
            if isinstance(dep, dict) and "path" in dep:
                assert (file.parent / dep["path"] / "Cargo.toml").resolve().exists()
    checks.append("workspace_path_dependencies")
    planner_path = ROOT / "docs/strategy/2026-10-26/examples/adapter/adaptive_plan.py"
    planner_spec = importlib.util.spec_from_file_location("wincraft_adaptive_plan", planner_path)
    assert planner_spec and planner_spec.loader
    planner_module = importlib.util.module_from_spec(planner_spec)
    planner_spec.loader.exec_module(planner_module)
    pack = json.loads((ROOT / "docs/strategy/2026-10-26/examples/packs/workday.pack.json").read_text(encoding="utf-8"))
    full_inventory = json.loads((ROOT / "docs/strategy/2026-10-26/examples/inventory/full.json").read_text(encoding="utf-8"))
    optional_inventory = json.loads((ROOT / "docs/strategy/2026-10-26/examples/inventory/optional-missing.json").read_text(encoding="utf-8"))
    required_inventory = json.loads((ROOT / "docs/strategy/2026-10-26/examples/inventory/required-missing.json").read_text(encoding="utf-8"))
    ambiguous_inventory = json.loads((ROOT / "docs/strategy/2026-10-26/examples/inventory/ambiguous.json").read_text(encoding="utf-8"))
    fixed_now = "2026-10-26T12:00:10Z"
    full_plan = planner_module.plan(pack, full_inventory, fixed_now)
    optional_plan = planner_module.plan(pack, optional_inventory, fixed_now)
    required_plan = planner_module.plan(pack, required_inventory, fixed_now)
    ambiguous_plan = planner_module.plan(pack, ambiguous_inventory, fixed_now)
    no_grant_inventory = json.loads((ROOT / "docs/strategy/2026-10-26/examples/inventory/no-grant.json").read_text(encoding="utf-8"))
    no_grant_plan = planner_module.plan(pack, no_grant_inventory, fixed_now)
    assert full_plan["status"] == "ready" and full_plan["mutates_host"] is False
    assert optional_plan["status"] == "degraded"
    assert required_plan["status"] == "blocked"
    assert ambiguous_plan["status"] == "blocked" and any("ambiguous" in item for item in ambiguous_plan["blockers"])
    assert no_grant_plan["status"] == "blocked"
    for plan_result in (full_plan, optional_plan, required_plan, ambiguous_plan, no_grant_plan):
        serialized = json.dumps(plan_result, ensure_ascii=False)
        assert "runtime.json" not in serialized and "token" not in serialized.lower()
    assert planner_module.plan(pack, full_inventory, fixed_now)["input_digest"] == full_plan["input_digest"]
    eligible, reasons = planner_module.check_submission_eligibility(
        full_plan, pack_id=pack["id"], inventory_generation=full_inventory["generation"],
        now=fixed_now, confirmed=True,
    )
    assert eligible and reasons == []
    for kwargs, expected in [
        ({"inventory_generation": 99, "confirmed": True}, "inventory_generation_changed"),
        ({"inventory_generation": full_inventory["generation"], "confirmed": False}, "user_confirmation_required"),
        ({"inventory_generation": full_inventory["generation"], "confirmed": True, "now": "2026-10-26T12:02:00Z"}, "plan_expired"),
    ]:
        values = {"pack_id": pack["id"], "inventory_generation": full_inventory["generation"], "now": fixed_now, "confirmed": True}
        values.update(kwargs)
        ok, reasons = planner_module.check_submission_eligibility(full_plan, **values)
        assert not ok and expected in reasons
    checks.append("adaptive_planner_determinism_and_fail_closed_statuses")
    handoff_tests = subprocess.run(
        [sys.executable, "-m", "unittest", "discover", "-s", "tests", "-v"],
        cwd=ROOT / "docs/strategy/2026-10-26",
        capture_output=True,
        text=True,
        check=False,
    )
    assert handoff_tests.returncode == 0, handoff_tests.stderr or handoff_tests.stdout
    checks.append("handoff_package_unit_tests")
    print(json.dumps({"status":"PASS","scope":"offline artifact consistency only","checks":checks},ensure_ascii=False,indent=2))

if __name__ == "__main__":
    main()
