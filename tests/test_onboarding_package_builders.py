from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parents[1]
sys.path.extend([str(ROOT / "scripts")])

from build_provider_bundle import build as build_provider_bundle  # noqa: E402
from package_obsidian_plugin import package as package_obsidian_plugin  # noqa: E402


class OnboardingPackageBuilderTests(unittest.TestCase):
    def test_provider_archive_has_strict_manifest_entrypoint_and_no_runtime_descriptor(self):
        with tempfile.TemporaryDirectory() as folder:
            output = build_provider_bundle(Path(folder) / "sample.wcp")
            with ZipFile(output) as archive:
                entries = set(archive.namelist())
                manifest = json.loads(archive.read("wincraft-provider.json"))
            self.assertEqual(
                entries,
                {"wincraft-provider.json", "main.py", "README.md", "client.py"},
            )
            self.assertEqual(manifest["kind"], "wincraft.provider-bundle")
            self.assertEqual(manifest["entrypoint"], {"runtime": "python", "path": "main.py"})
            self.assertNotIn("runtime", entries)

    def test_obsidian_plugin_zip_contains_only_reviewed_source_files(self):
        with tempfile.TemporaryDirectory() as folder:
            output = package_obsidian_plugin(Path(folder) / "obsidian.zip")
            with ZipFile(output) as archive:
                entries = set(archive.namelist())
            self.assertEqual(
                entries,
                {
                    "wincraft-workspace-dashboard/manifest.json",
                    "wincraft-workspace-dashboard/main.js",
                    "wincraft-workspace-dashboard/README.md",
                },
            )


if __name__ == "__main__":
    unittest.main()
