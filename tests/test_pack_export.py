from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "wincraft_pack_export",
    ROOT / "tools" / "pack" / "export_pack.py",
)
assert SPEC and SPEC.loader
PACK_EXPORT = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(PACK_EXPORT)


class PackExportTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        source = ROOT / "docs" / "strategy" / "2026-10-26" / "examples" / "packs"
        self.pack = json.loads((source / "workday.pack.json").read_text(encoding="utf-8"))
        self.blueprint = json.loads(
            (source / "blueprints" / "workday.json").read_text(encoding="utf-8")
        )
        (self.root / "blueprints").mkdir()
        self.pack_path = self.root / "workday.pack.json"
        self.blueprint_path = self.root / "blueprints" / "workday.json"
        self.write_pack()
        self.write_blueprint()

    def tearDown(self) -> None:
        self.temp.cleanup()

    def write_pack(self) -> None:
        self.pack_path.write_text(json.dumps(self.pack, ensure_ascii=False), encoding="utf-8")

    def write_blueprint(self) -> None:
        self.blueprint_path.write_text(json.dumps(self.blueprint, ensure_ascii=False), encoding="utf-8")

    def test_export_contains_only_pack_and_referenced_blueprint(self) -> None:
        output = self.root / "workday.wcp"
        result = PACK_EXPORT.export_pack(self.pack_path, output)
        with zipfile.ZipFile(output) as archive:
            self.assertEqual(set(archive.namelist()), {"pack.json", "blueprints/workday.json"})
            self.assertEqual(json.loads(archive.read("pack.json")), self.pack)
            self.assertEqual(json.loads(archive.read("blueprints/workday.json")), self.blueprint)
        self.assertEqual(result["status"], "exported")
        self.assertEqual(result["entries"], ["blueprints/workday.json", "pack.json"])

    def test_archive_bytes_are_deterministic(self) -> None:
        first = self.root / "first.wcp"
        second = self.root / "second.wcp"
        PACK_EXPORT.export_pack(self.pack_path, first)
        PACK_EXPORT.export_pack(self.pack_path, second)
        self.assertEqual(first.read_bytes(), second.read_bytes())

    def test_cli_exports_the_explicit_pack(self) -> None:
        output = self.root / "cli-export.wcp"
        script = ROOT / "tools" / "pack" / "export_pack.py"
        result = subprocess.run(
            [
                sys.executable,
                str(script),
                "--pack",
                str(self.pack_path),
                "--output",
                str(output),
            ],
            cwd=ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=15,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["status"], "exported")
        with zipfile.ZipFile(output) as archive:
            self.assertEqual(set(archive.namelist()), {"pack.json", "blueprints/workday.json"})

    def test_rejects_provider_binary_descriptor_lease_and_install_fields(self) -> None:
        for key, value in (
            ("provider_binary", "provider.exe"),
            ("descriptor", {"token": "synthetic"}),
            ("lease", {"id": "synthetic"}),
            ("install_hook", "run me"),
        ):
            with self.subTest(key=key):
                self.pack[key] = value
                self.write_pack()
                with self.assertRaises(PACK_EXPORT.PackExportError):
                    PACK_EXPORT.export_pack(self.pack_path, self.root / f"{key}.wcp")
                self.pack.pop(key)

    def test_rejects_nested_adapter_binary_payload(self) -> None:
        self.pack["adapter"] = {
            "kind": "external-program-reference",
            "id": "fixture.adapter",
            "reference": "fixture-only",
            "sha256": "0" * 64,
            "execution": "separate-user-approval",
            "binary": "provider.exe",
        }
        self.write_pack()
        with self.assertRaises(PACK_EXPORT.PackExportError):
            PACK_EXPORT.export_pack(self.pack_path, self.root / "nested.wcp")

    def test_rejects_unsafe_blueprint_references(self) -> None:
        for reference in (
            "../outside.json",
            "/absolute.json",
            "blueprints\\outside.json",
            "pack.json",
        ):
            with self.subTest(reference=reference):
                self.pack["blueprint"] = reference
                self.write_pack()
                with self.assertRaises(PACK_EXPORT.PackExportError):
                    PACK_EXPORT.export_pack(self.pack_path, self.root / "unsafe.wcp")
        self.pack["blueprint"] = "blueprints/workday.json"
        self.write_pack()

    def test_rejects_symlinked_blueprint(self) -> None:
        outside = self.root.parent / f"{self.root.name}-outside.json"
        link = self.root / "blueprints" / "linked.json"
        outside.write_text("{}", encoding="utf-8")
        try:
            try:
                link.symlink_to(outside)
            except OSError as error:
                self.skipTest(f"symlink creation unavailable: {type(error).__name__}")
            self.pack["blueprint"] = "blueprints/linked.json"
            self.write_pack()
            with self.assertRaises(PACK_EXPORT.PackExportError):
                PACK_EXPORT.export_pack(self.pack_path, self.root / "symlink.wcp")
        finally:
            outside.unlink(missing_ok=True)

    def test_rejects_invalid_blueprint_schema(self) -> None:
        self.blueprint["provider_binary"] = "provider.exe"
        self.write_blueprint()
        with self.assertRaises(PACK_EXPORT.PackExportError):
            PACK_EXPORT.export_pack(self.pack_path, self.root / "invalid-blueprint.wcp")

    def test_rejects_oversized_pack_and_blueprint(self) -> None:
        self.pack_path.write_bytes(b" " * (PACK_EXPORT.MAX_INPUT_BYTES + 1))
        with self.assertRaises(PACK_EXPORT.PackExportError):
            PACK_EXPORT.export_pack(self.pack_path, self.root / "large-pack.wcp")

        self.write_pack()
        self.blueprint_path.write_bytes(b" " * (PACK_EXPORT.MAX_INPUT_BYTES + 1))
        with self.assertRaises(PACK_EXPORT.PackExportError):
            PACK_EXPORT.export_pack(self.pack_path, self.root / "large-blueprint.wcp")

    def test_existing_output_is_never_overwritten(self) -> None:
        output = self.root / "existing.wcp"
        output.write_bytes(b"preserve existing file")
        with self.assertRaises(PACK_EXPORT.PackExportError):
            PACK_EXPORT.export_pack(self.pack_path, output)
        self.assertEqual(output.read_bytes(), b"preserve existing file")

    def test_exporter_does_not_touch_host_or_run_adapter(self) -> None:
        self.pack["adapter"] = {
            "kind": "external-program-reference",
            "id": "fixture.adapter",
            "reference": "fixture-only",
            "sha256": "0" * 64,
            "execution": "separate-user-approval",
        }
        self.write_pack()
        result = PACK_EXPORT.export_pack(self.pack_path, self.root / "reference-only.wcp")
        self.assertEqual(result["status"], "exported")
        with zipfile.ZipFile(self.root / "reference-only.wcp") as archive:
            packed = json.loads(archive.read("pack.json"))
        self.assertEqual(packed["adapter"]["execution"], "separate-user-approval")


if __name__ == "__main__":
    unittest.main()
