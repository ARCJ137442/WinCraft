"""Create the synthetic .wcp code package for World Manager onboarding checks."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo


ROOT = Path(__file__).resolve().parents[1]
SAMPLE = ROOT / "examples" / "provider-bundle-sample"
CLIENT = ROOT / "examples" / "python" / "client.py"


def build(output: Path) -> Path:
    output.parent.mkdir(parents=True, exist_ok=True)
    manifest = {
        "kind": "wincraft.provider-bundle",
        "schema_version": "1",
        "id": "sample-click-counter",
        "version": "0.1.0",
        "title": {"zh-CN": "合成点击计数器", "en-US": "Synthetic click counter"},
        "entrypoint": {"runtime": "python", "path": "main.py"},
    }
    with ZipFile(output, "w", compression=ZIP_DEFLATED, compresslevel=9) as archive:
        manifest_entry = ZipInfo("wincraft-provider.json", date_time=(2026, 10, 31, 0, 0, 0))
        manifest_entry.compress_type = ZIP_DEFLATED
        manifest_entry.external_attr = 0o100644 << 16
        archive.writestr(
            manifest_entry,
            json.dumps(manifest, ensure_ascii=False, separators=(",", ":")),
        )
        archive.write(SAMPLE / "main.py", "main.py")
        archive.write(SAMPLE / "README.md", "README.md")
        archive.write(CLIENT, "client.py")
    return output


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "target" / "provider-bundles" / "wincraft-sample-provider.wcp",
    )
    args = parser.parse_args()
    output = args.output.resolve()
    build(output)
    print(f"Created synthetic Provider package: {output}")


if __name__ == "__main__":
    main()
