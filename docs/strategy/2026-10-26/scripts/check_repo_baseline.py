#!/usr/bin/env python3
"""Read-only baseline inspection. Does not fetch, checkout, reset or read secrets."""
from __future__ import annotations
import argparse
import json
import subprocess
from pathlib import Path

BASELINE = "6929056700b1ba6702288534579debc8a502c139"
REQUIRED = ["AGENTS.md", "Cargo.toml", "package.json", "docs/protocol.md",
            "crates/wincraft-core/src/model.rs", "crates/wincraft-server/src/transport.rs",
            "skills/wincraft-provider/SKILL.md"]


def run_git(repo: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["git", "-C", str(repo), *args], capture_output=True,
                          text=True, encoding="utf-8", errors="replace", timeout=20, check=False)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, required=True)
    args = parser.parse_args()
    try:
        head = run_git(args.repo, "rev-parse", "HEAD")
        if head.returncode:
            raise ValueError("not a readable Git repository")
        dirty = run_git(args.repo, "status", "--porcelain=v1")
        known = run_git(args.repo, "cat-file", "-e", BASELINE + "^{commit}").returncode == 0
        sha = head.stdout.strip()
        ancestry = run_git(args.repo, "merge-base", "--is-ancestor", BASELINE, sha).returncode if known else 128
        relation = "exact" if sha == BASELINE else "descendant" if ancestry == 0 else "diverged" if known else "baseline-unavailable"
        missing = [p for p in REQUIRED if not (args.repo / p).is_file()]
        result = {"baseline": BASELINE, "current_head": sha, "relation": relation,
                  "dirty": bool(dirty.stdout.strip()), "missing_required_paths": missing,
                  "mutated_repository": False, "network_access": False,
                  "next_action": "Review local changes and run current tests; never reset to this baseline automatically."}
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if relation in ("exact", "descendant") and not missing else 3
    except (OSError, ValueError, subprocess.TimeoutExpired) as exc:
        print(json.dumps({"status": "unavailable", "error": str(exc), "mutated_repository": False}, ensure_ascii=False))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
