"""Export a draft WinCraft configuration pack without providers or runtime credentials.

This is an offline proposal tool. It validates the pack and its referenced blueprint,
then writes a deterministic ZIP containing those two JSON documents only. It never
imports, installs, downloads, or executes an adapter and never calls a WinCraft Host.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import re
import sys
import zipfile
from pathlib import Path, PurePosixPath
from typing import Any

import jsonschema


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
CONTRACT_ROOT = REPOSITORY_ROOT / "docs" / "strategy" / "2026-10-26" / "contracts"
MAX_INPUT_BYTES = 1_048_576
MAX_ARCHIVE_BYTES = 2 * MAX_INPUT_BYTES + 65_536
PACK_SCHEMA = "pack.schema.json"
BLUEPRINT_SCHEMA = "blueprint.schema.json"


class PackExportError(ValueError):
    """Raised when an input pack cannot be safely exported."""


def _load_json_bytes(raw: bytes, label: str) -> Any:
    try:
        return json.loads(raw.decode("utf-8-sig"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise PackExportError(f"{label} is not valid UTF-8 JSON") from error


def _read_bounded_json(path: Path, label: str) -> dict[str, Any]:
    if path.is_symlink():
        raise PackExportError(f"{label} must not be a symlink")
    if not path.is_file():
        raise PackExportError(f"{label} must be a regular file")
    try:
        if path.stat().st_size > MAX_INPUT_BYTES:
            raise PackExportError(f"{label} exceeds the 1 MiB input limit")
        raw = path.read_bytes()
    except OSError as error:
        raise PackExportError(f"{label} could not be read") from error
    if len(raw) > MAX_INPUT_BYTES:
        raise PackExportError(f"{label} exceeds the 1 MiB input limit")
    value = _load_json_bytes(raw, label)
    if not isinstance(value, dict):
        raise PackExportError(f"{label} must be a JSON object")
    return value


def _validate_schema(value: dict[str, Any], schema_name: str, label: str) -> None:
    schema_path = CONTRACT_ROOT / schema_name
    try:
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
        jsonschema.Draft202012Validator(
            schema,
            format_checker=jsonschema.FormatChecker(),
        ).validate(value)
    except jsonschema.ValidationError as error:
        location = "/".join(str(part) for part in error.absolute_path)
        suffix = f" at {location}" if location else ""
        raise PackExportError(f"{label} does not match its draft schema{suffix}") from error
    except (OSError, json.JSONDecodeError) as error:
        raise PackExportError(f"{label} schema is unavailable or invalid") from error


def _safe_blueprint_reference(value: Any) -> PurePosixPath:
    if not isinstance(value, str) or not value or "\\" in value or "\x00" in value:
        raise PackExportError("blueprint must be a safe relative POSIX path")
    parts = value.split("/")
    if value.startswith("/") or any(part in ("", ".", "..") for part in parts):
        raise PackExportError("blueprint must not escape the pack directory")
    relative = PurePosixPath(value)
    if relative.is_absolute() or relative.suffix.casefold() != ".json":
        raise PackExportError("blueprint must be a relative JSON file")
    if relative.as_posix() == "pack.json":
        raise PackExportError("blueprint must not replace the packed manifest")
    if re.match(r"^[A-Za-z]:", value):
        raise PackExportError("drive-qualified blueprint paths are forbidden")
    return relative


def _resolve_blueprint(pack_root: Path, reference: PurePosixPath) -> Path:
    root = pack_root.resolve(strict=True)
    candidate = root
    for part in reference.parts:
        candidate = candidate / part
        if candidate.is_symlink():
            raise PackExportError("blueprint path must not contain symlinks")
    try:
        resolved = candidate.resolve(strict=True)
    except OSError as error:
        raise PackExportError("referenced blueprint does not exist") from error
    if not resolved.is_relative_to(root) or not resolved.is_file():
        raise PackExportError("blueprint must resolve to a regular file inside the pack directory")
    return resolved


def _canonical_json(value: dict[str, Any]) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def _archive_bytes(entries: dict[str, bytes]) -> bytes:
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for name, content in sorted(entries.items()):
            info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.create_system = 3
            info.external_attr = 0o100644 << 16
            archive.writestr(info, content, compress_type=zipfile.ZIP_DEFLATED, compresslevel=9)
    return output.getvalue()


def export_pack(pack_file: Path, output_file: Path) -> dict[str, Any]:
    """Validate and write a new .wcp archive; existing outputs are never overwritten."""
    if pack_file.is_symlink():
        raise PackExportError("pack file must not be a symlink")
    try:
        pack_path = pack_file.resolve(strict=True)
        pack_root = pack_path.parent.resolve(strict=True)
    except OSError as error:
        raise PackExportError("pack file does not exist") from error
    pack = _read_bounded_json(pack_path, "pack")
    _validate_schema(pack, PACK_SCHEMA, "pack")

    reference = _safe_blueprint_reference(pack.get("blueprint"))
    blueprint_path = _resolve_blueprint(pack_root, reference)
    blueprint = _read_bounded_json(blueprint_path, "blueprint")
    _validate_schema(blueprint, BLUEPRINT_SCHEMA, "blueprint")

    entries = {
        "pack.json": _canonical_json(pack),
        reference.as_posix(): _canonical_json(blueprint),
    }
    archive = _archive_bytes(entries)
    if len(archive) > MAX_ARCHIVE_BYTES:
        raise PackExportError("export archive exceeds the size limit")

    try:
        output_parent = output_file.parent.resolve(strict=True)
    except OSError as error:
        raise PackExportError("output directory must already exist") from error
    if not output_parent.is_dir():
        raise PackExportError("output parent is not a directory")
    output_path = output_parent / output_file.name
    if output_path in (pack_path, blueprint_path):
        raise PackExportError("output must not replace a source JSON file")
    if output_path.suffix.casefold() != ".wcp":
        raise PackExportError("output file must use the .wcp extension")

    created = False
    try:
        descriptor = os.open(
            output_path,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0),
            0o600,
        )
        created = True
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(archive)
            stream.flush()
            os.fsync(stream.fileno())
    except FileExistsError as error:
        raise PackExportError("output already exists; refusing to overwrite") from error
    except OSError as error:
        if created:
            try:
                output_path.unlink(missing_ok=True)
            except OSError:
                pass
        raise PackExportError("archive could not be written") from error

    return {
        "status": "exported",
        "output_name": output_path.name,
        "bytes": len(archive),
        "sha256": hashlib.sha256(archive).hexdigest(),
        "entries": sorted(entries),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pack", required=True, type=Path, help="explicit draft pack JSON")
    parser.add_argument("--output", required=True, type=Path, help="new .wcp path; must not exist")
    args = parser.parse_args()
    try:
        result = export_pack(args.pack, args.output)
    except (OSError, PackExportError) as error:
        print(f"Pack export rejected: {error}", file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
