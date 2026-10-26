"""Offline artifact checks, NOT a Rust compilation or native-window test."""
from __future__ import annotations
import ast
import json
import re
import sys
import tomllib
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
    try:
        from jsonschema import Draft202012Validator, FormatChecker
    except ImportError as exc:
        raise SystemExit("Install validation extra: python -m pip install jsonschema") from exc
    request_schema = json.loads((ROOT / "protocol/request.schema.json").read_text(encoding="utf-8"))
    scene_schema = json.loads((ROOT / "protocol/scene.schema.json").read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(request_schema)
    Draft202012Validator.check_schema(scene_schema)
    validator = Draft202012Validator(request_schema, format_checker=FormatChecker())
    for request in json.loads((ROOT / "protocol/examples/requests.json").read_text(encoding="utf-8")):
        validator.validate(request)
    Draft202012Validator(scene_schema).validate(json.loads((ROOT / "protocol/examples/focus.scene.json").read_text(encoding="utf-8")))
    checks.append("schemas_and_positive_fixtures")
    for bad in [
        {"id":"x","method":"world.create","params":{"window":{"width":-1}}},
        {"id":"x","method":"scene.execute_javascript","params":{}},
        {"id":"x","method":"hello","params":{"protocol":"0.2","provider_name":"x"}},
    ]:
        assert not validator.is_valid(bad), bad
    assert not Draft202012Validator(scene_schema).is_valid({"root":{"id":"button","kind":"button"}})
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
    print(json.dumps({"status":"PASS","scope":"offline artifact consistency only","checks":checks},ensure_ascii=False,indent=2))

if __name__ == "__main__":
    main()
