'''本机 Harness 文件来源的只读 count-only smoke
- 🎯验证 Codex App/Claude Code 进程状态与本地数据目录可读性
- 📌只输出来源状态、会话数量、输出片段数量和读取年龄
- 🚩不启动目标 Harness、不连接 WinCraft Host、不打印会话内容
'''
from __future__ import annotations

import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT: Path = Path(__file__).resolve().parents[1]
'''📜WinCraft repository root'''
AGENT_BOARD: Path = ROOT / 'examples' / 'integrations' / 'agent-board'
'''📜Local read-only Harness source adapter'''


def main() -> int:
    '''Read only selected local sources and print bounded aggregate evidence'''
    sys.path.insert(0, str(AGENT_BOARD))
    from live_sources import load_live_snapshot

    started_at = time.perf_counter()
    snapshot = load_live_snapshot(
        sequence=1,
        now=datetime.now(timezone.utc),
        enabled_sources=('codex-app', 'claude-code'),
    )
    records_by_source = snapshot.records_by_source
    source_ids = ('codex-app', 'claude-code')
    result: dict[str, Any] = {
        'observed_at': datetime.now(timezone.utc).isoformat(),
        'source_health': {
            source_id: snapshot.projection['source_health'].get(source_id, 'unknown')
            for source_id in source_ids
        },
        'data_health': {
            source_id: snapshot.projection['source_data_health'].get(source_id, 'unknown')
            for source_id in source_ids
        },
        'last_read_age_seconds': {
            source_id: snapshot.projection['source_age_seconds'].get(source_id)
            for source_id in source_ids
        },
        'session_count': {
            source_id: len(records_by_source.get(source_id, []))
            for source_id in source_ids
        },
        'bounded_agent_output_count': {
            source_id: sum(
                bool(record.get('summary'))
                for record in records_by_source.get(source_id, [])
            )
            for source_id in source_ids
        },
        'elapsed_seconds': round(time.perf_counter() - started_at, 4),
        'target_harnesses_started': False,
        'session_values_persisted_or_printed': False,
    }
    print(json.dumps(result, ensure_ascii=False, separators=(',', ':')))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
