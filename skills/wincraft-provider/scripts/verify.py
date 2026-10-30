#!/usr/bin/env python3
"""Check that the bundled WinCraft provider tutorial matches this repository."""
from __future__ import annotations

import sys
from pathlib import Path


REQUIRED_PATHS = (
    "docs/protocol.md",
    "protocol/theme.schema.json",
    "protocol/examples/theme.scene.json",
    "protocol/examples/theme.request.json",
    "examples/python/client.py",
    "examples/python/focus_demo.py",
    "examples/python/provider_tutorial.py",
    "examples/python/lease_probe.py",
    "examples/python/theme_demo.py",
    "examples/python/scope_interaction_demo.py",
    "examples/python/trafficmonitor_provider.py",
    "examples/python/obsidian-workspace.py",
    "examples/trafficmonitor/wincraft_bridge.cpp",
    "examples/trafficmonitor/build_bridge.ps1",
    "examples/trafficmonitor/stage_demo.ps1",
    "examples/trafficmonitor/configure_staged_copy.py",
    "apps/desktop/src-tauri/src/main.rs",
    "skills/wincraft-provider/references/trafficmonitor.md",
    "skills/wincraft-provider/references/theme.md",
    "apps/desktop/src/accessibility.ts",
    "protocol/activity.schema.json",
    "examples/integrations/agent-board/README.md",
    "examples/integrations/agent-board/activity_board.py",
    "examples/integrations/agent-board/provider.py",
    "examples/integrations/agent-board/scoped_live_sources.py",
    "tests/test_agent_scoped_sources.py",
    "protocol/device-message.schema.json",
    "examples/integrations/device-inbox/README.md",
    "examples/integrations/device-inbox/device_inbox.py",
    "examples/integrations/device-inbox/provider.py",
    "examples/integrations/model_quota/README.md",
    "examples/integrations/model_quota/provider.py",
    "examples/integrations/model_quota/team_sense_quota.py",
)


def main() -> int:
    if len(REQUIRED_PATHS) != len(set(REQUIRED_PATHS)):
        print("FAIL: repository reference list contains duplicates")
        return 1
    skill_dir = Path(__file__).resolve().parents[1]
    repo_root = skill_dir.parents[1]
    skill_file = skill_dir / "SKILL.md"
    content = skill_file.read_text(encoding="utf-8")
    if not content.startswith("---\n") or "\nname: wincraft-provider\n" not in content:
        print("FAIL: SKILL.md frontmatter is missing or has the wrong name")
        return 1
    if "Use when" not in content:
        print("FAIL: skill description has no trigger phrase")
        return 1

    missing = [path for path in REQUIRED_PATHS if not (repo_root / path).is_file()]
    if missing:
        for path in missing:
            print(f"FAIL: missing tutorial dependency: {path}")
        return 1
    traffic_reference = (
        repo_root / "skills/wincraft-provider/references/trafficmonitor.md"
    ).read_text(encoding="utf-8")
    bridge_source = (repo_root / "examples/trafficmonitor/wincraft_bridge.cpp").read_text(encoding="utf-8")
    desktop_source = (repo_root / "apps/desktop/src-tauri/src/main.rs").read_text(encoding="utf-8")
    if "OnMonitorInfo" not in traffic_reference or "OnMonitorInfo" not in bridge_source:
        print("FAIL: TrafficMonitor guidance and bridge must share the real OnMonitorInfo source")
        return 1
    if "--open-manager" not in content or "--open-manager" not in desktop_source:
        print("FAIL: manager startup guidance does not match the desktop CLI flag")
        return 1

    live_start = content.find("`examples/integrations/agent-board/live_provider.py`")
    live_end = content.find("- `examples/integrations/device-inbox/README.md`", live_start)
    if live_start < 0 or live_end < 0:
        print("FAIL: provider skill is missing the local Harness adapter guidance")
        return 1
    live_guidance = content[live_start:live_end]
    required_claims: tuple[str, ...] = (
        "useStateDbOnly=true",
        "state_*.sqlite",
        "session_meta` UUID",
        "OS process metadata",
        "Neither App nor CLI is started for collection.",
    )
    missing_claims = [claim for claim in required_claims if claim not in live_guidance]
    if missing_claims:
        print("FAIL: provider skill omits the process-and-local-files source contract")
        return 1
    obsolete_claims: tuple[str, ...] = (
        "agents --json",
        "codex-app-bridge",
        "Codex App connector",
        "MCP snapshot",
    )
    if any(claim in live_guidance for claim in obsolete_claims):
        print("FAIL: provider skill still describes a superseded Harness collection path")
        return 1

    lesson_titles = (
        "看见第一个世界",
        "搭一块会变的方块",
        "与程序对话",
        "换一个自己的外观",
        "发现与加入是两件事",
    )
    tutorial = (repo_root / "examples/python/provider_tutorial.py").read_text(encoding="utf-8")
    missing_lessons = [title for title in lesson_titles if title not in tutorial]
    if missing_lessons:
        print(f"FAIL: provider tutorial is missing lessons: {', '.join(missing_lessons)}")
        return 1
    if "examples/python/provider_tutorial.py" not in content:
        print("FAIL: skill does not link the guided provider tutorial")
        return 1
    if "examples/python/scope_interaction_demo.py" not in content:
        print("FAIL: skill does not link the scope interaction example")
        return 1
    if "examples/integrations/model_quota/provider.py" not in content:
        print("FAIL: provider skill is missing the TeamSense read-only quota example")
        return 1
    if "examples/integrations/agent-board/scoped_live_sources.py" not in content:
        print("FAIL: provider skill is missing the independent scope writer example")
        return 1
    print(f"PASS: {len(REQUIRED_PATHS)} repository references exist")
    return 0


if __name__ == "__main__":
    sys.exit(main())
