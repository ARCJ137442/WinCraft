#!/usr/bin/env python3
"""Validate handoff consistency only, NOT WinCraft implementation correctness."""
from __future__ import annotations
import argparse
import hashlib
import json
import re
from pathlib import Path, PurePosixPath
from datetime import date
from typing import Any
import jsonschema

ROOT = Path(__file__).resolve().parents[1]


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def metadata(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---\n"):
        raise ValueError(f"missing JSON/YAML front matter: {path.name}")
    return json.loads(text[4:].split("\n---\n", 1)[0])


def semantic_errors(name: str, value: dict[str, Any]) -> list[str]:
    errors = []
    if name == "pack":
        path = PurePosixPath(value["blueprint"])
        if path.is_absolute() or ".." in path.parts or "\\" in value["blueprint"]:
            errors.append("unsafe blueprint reference")
        ids = [x["id"] for x in value["bindings"]]
        if len(ids) != len(set(ids)):
            errors.append("duplicate binding id")
        if any(not x["provider_types"] for x in value["bindings"]):
            errors.append("binding must constrain provider type")
    if name == "inventory":
        ids = [x["instance_id"] for x in value["providers"]]
        if len(ids) != len(set(ids)):
            errors.append("duplicate provider instance")
    if name == "ephemeral-request":
        qs = value["payload"]["questions"]
        ids = [x["id"] for x in qs]
        if len(ids) != len(set(ids)):
            errors.append("duplicate question id")
        for q in qs:
            labels = [x["label"].strip().casefold() for x in q["options"]]
            if len(labels) != len(set(labels)):
                errors.append("duplicate option label")
            if any(x in ("other", "其他", "其它") for x in labels):
                errors.append("Other must be injected by the compatible transport")
            if any(o.get("recommended") for o in q["options"][1:]):
                errors.append("recommended option must be first")
    return errors


def check(root: Path = ROOT) -> dict[str, Any]:
    errors: list[str] = []
    sources = read_json(root / "sources/registry.json")["sources"]
    source_ids = {s["id"] for s in sources}
    if len(source_ids) != len(sources):
        errors.append("duplicate source id")
    docs = list(root.rglob("*.md"))
    doc_ids = set()
    doc_schema = read_json(root / "governance/doc-meta.schema.json")
    links = 0
    for path in docs:
        try:
            meta = metadata(path)
            jsonschema.Draft202012Validator(doc_schema, format_checker=jsonschema.FormatChecker()).validate(meta)
            if meta["doc_id"] in doc_ids:
                errors.append("duplicate doc_id: " + meta["doc_id"])
            doc_ids.add(meta["doc_id"])
            if set(meta["source_ids"]) - source_ids:
                errors.append("unknown source in " + str(path.relative_to(root)))
            if date.fromisoformat(meta["last_verified_at"]) > date.fromisoformat(meta["updated_at"]):
                errors.append("verification date exceeds update date: " + str(path.relative_to(root)))
            for link in re.findall(r"\[[^\]]*\]\(([^)]+)\)", path.read_text(encoding="utf-8")):
                if re.match(r"[a-zA-Z][a-zA-Z0-9+.-]*:", link) or link.startswith("#"):
                    continue
                target = (path.parent / link.split("#", 1)[0]).resolve()
                if not target.is_relative_to(root.resolve()) or not target.exists():
                    errors.append("broken/outside link: " + str(path.relative_to(root)) + " -> " + link)
                links += 1
        except (ValueError, KeyError, jsonschema.ValidationError) as exc:
            errors.append("document validation: " + str(path.relative_to(root)) + ": " + str(exc).splitlines()[0])
    reqs = read_json(root / "plan/requirements.json")["requirements"]
    tasks = read_json(root / "plan/tasks.json")["tasks"]
    accepts = read_json(root / "plan/acceptance.json")["cases"]
    reqmap = {r["id"]: r for r in reqs}
    taskmap = {t["id"]: t for t in tasks}
    acmap = {a["id"]: a for a in accepts}
    if len(reqmap) != len(reqs) or len(taskmap) != len(tasks) or len(acmap) != len(accepts):
        errors.append("duplicate planning id")
    for r in reqs:
        if not (root / r["owner_doc"]).exists() or not r["task_ids"] or not r["acceptance_ids"]:
            errors.append("requirement not fully mapped: " + r["id"])
        for tid in r["task_ids"]:
            if tid not in taskmap or r["id"] not in taskmap[tid]["requirement_ids"]:
                errors.append("asymmetric requirement mapping: " + r["id"])
        if any(a not in acmap for a in r["acceptance_ids"]):
            errors.append("unknown acceptance for " + r["id"])
    for t in tasks:
        for dep in t["depends_on"]:
            if dep not in taskmap:
                errors.append("unknown dependency: " + dep)
        if not t["implementation_steps"] or not t["acceptance"] or not t["rollback"] or not t["evidence_required"]:
            errors.append("incomplete task: " + t["id"])
        for a in t["acceptance"]:
            if a["id"] not in acmap or acmap[a["id"]]["criterion"] != a["criterion"]:
                errors.append("acceptance mismatch: " + a["id"])
    visiting, done = set(), set()
    def walk(tid: str) -> None:
        if tid in visiting:
            raise ValueError("dependency cycle: " + tid)
        if tid in done or tid not in taskmap:
            return
        visiting.add(tid)
        for dep in taskmap[tid]["depends_on"]:
            walk(dep)
        visiting.remove(tid)
        done.add(tid)
    try:
        for tid in taskmap:
            walk(tid)
    except ValueError as exc:
        errors.append(str(exc))
    examples = read_json(root / "contracts/examples-index.json")["cases"]
    for case in examples:
        try:
            spec = read_json(root / "contracts" / (case["schema"] + ".schema.json"))
            jsonschema.Draft202012Validator.check_schema(spec)
            value = read_json(root / case["path"])
            shape_errors = list(jsonschema.Draft202012Validator(spec, format_checker=jsonschema.FormatChecker()).iter_errors(value))
            semantic = [] if shape_errors else semantic_errors(case["schema"], value)
            actual_valid = not shape_errors and not semantic
            if actual_valid != case["expected_valid"]:
                reason = str(shape_errors[0]).splitlines()[0] if shape_errors else "; ".join(semantic)
                errors.append("example expectation mismatch: " + case["path"] + ": " + reason)
        except (ValueError, OSError) as exc:
            errors.append("example failure: " + str(exc))
    zh, en = read_json(root / "locales/zh-CN.json"), read_json(root / "locales/en-US.json")
    if set(zh) != set(en):
        errors.append("locale key mismatch")
    for k in set(zh) & set(en):
        if set(re.findall(r"\{([^}]+)\}", zh[k])) != set(re.findall(r"\{([^}]+)\}", en[k])):
            errors.append("locale placeholder mismatch: " + k)
    for t in read_json(root / "locales/index.json")["translations"]:
        source_hash = hashlib.sha256((root / t["source"]).read_bytes()).hexdigest()
        if source_hash != t["source_sha256"] and t["status"] != "stale":
            errors.append("unmarked stale translation: " + t["document"])
    forbidden = {".runtime.json", ".env", "id_rsa", "id_ed25519"}
    for p in root.rglob("*"):
        if p.is_symlink():
            errors.append("package contains symlink: " + str(p.relative_to(root)))
        if p.name in forbidden or p.name.endswith(".runtime.json"):
            errors.append("forbidden runtime/credential filename: " + str(p.relative_to(root)))
    return {"scope": "handoff consistency, draft fixtures and metadata; not runtime integration",
            "status": "PASS" if not errors else "FAIL", "documents": len(docs), "relative_links": links,
            "sources": len(sources), "requirements": len(reqs), "tasks": len(tasks), "acceptance_cases": len(accepts),
            "schema_examples": len(examples), "locale_keys": len(zh), "errors": errors}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, help="optional validation report path")
    args = parser.parse_args()
    report = check()
    text = json.dumps(report, ensure_ascii=False, indent=2)
    print(text)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text + "\n", encoding="utf-8")
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
