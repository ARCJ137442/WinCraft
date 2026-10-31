"""Create a clean Obsidian plugin folder ZIP for manual installation."""
from __future__ import annotations

import argparse
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile


ROOT = Path(__file__).resolve().parents[1]
PLUGIN = ROOT / "examples" / "obsidian-plugin"


def package(output: Path) -> Path:
    output.parent.mkdir(parents=True, exist_ok=True)
    with ZipFile(output, "w", compression=ZIP_DEFLATED, compresslevel=9) as archive:
        for name in ("manifest.json", "main.js", "README.md"):
            archive.write(PLUGIN / name, f"wincraft-workspace-dashboard/{name}")
    return output


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "target" / "obsidian-plugin" / "wincraft-workspace-dashboard.zip",
    )
    args = parser.parse_args()
    output = package(args.output.resolve())
    print(f"Created Obsidian plugin ZIP: {output}")


if __name__ == "__main__":
    main()
