'''Run the quota Provider against an isolated release headless Rust Host.
- 🎯验证真实 WebSocket/Host 接受本机 quota scene；数据只来自合成 rollout fixture。
- 📌Host descriptor、fixture 与进程输出留在系统临时目录并随运行删除。
- 🤖由 Agent 编写，未经人工逐行审阅。
'''
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
'''📌WinCraft checkout 根目录'''

DEFAULT_HOST_EXE = ROOT / 'target' / 'release' / 'wincraft-headless.exe'
'''📜Windows release headless Host 默认路径'''

PROVIDER_SCRIPT = ROOT / 'examples' / 'integrations' / 'model_quota' / 'provider.py'
'''📌要连接到隔离 Host 的只读 quota Provider'''

DEFAULT_DURATION_SECONDS: int = 5
'''📜smoke 默认运行时长'''

MAX_DURATION_SECONDS: int = 30
'''📜防止 smoke 意外成为常驻进程的上限'''

HOST_READY_TIMEOUT_SECONDS: int = 10
'''📜等待 loopback runtime descriptor 的上限'''

PROVIDER_TIMEOUT_GRACE_SECONDS: int = 15
'''📜Provider 窗口时长外允许握手/清理的宽限'''

PRIVATE_ENV_KEYS: tuple[str, ...] = (
    'CODEX_HOME',
    'DEEPSEEK_API_KEY',
    'MINIMAX_API_KEY',
    'TEAM_SENSE_API_TOKEN',
    'TEAM_SENSE_BASE_URL',
)
'''📌合成 smoke 不向子进程传递真实额度来源身份或 key'''


class SmokeError(RuntimeError):
    '''不含路径、descriptor 或子进程输出的稳定 smoke 错误码。'''

    def __init__(self, code: str) -> None:
        self.code: str = code
        super().__init__(code)


def __synthetic_event(now: datetime) -> dict[str, Any]:
    '''构造仅包含合成额度字段的 rollout 事件。'''
    return {
        'timestamp': now.isoformat(timespec='seconds').replace('+00:00', 'Z'),
        'type': 'event_msg',
        'thread_id': 'synthetic-headless-smoke',
        'ordinal': 1,
        'payload': {
            'type': 'token_count',
            'rate_limits': {
                'primary': {
                    'used_percent': 25,
                    'window_minutes': 300,
                    'resets_at': int(now.timestamp()) + 3600,
                },
            },
        },
    }


def __isolated_environment(runtime_dir: Path) -> dict[str, str]:
    '''为子进程准备 loopback 测试环境并剔除真实额度来源变量。'''
    environment = os.environ.copy()
    for key in PRIVATE_ENV_KEYS:
        environment.pop(key, None)
    environment['WINCRAFT_RUNTIME_DIR'] = str(runtime_dir)
    environment['WINCRAFT_BIND'] = '127.0.0.1:0'
    return environment


def __stop_host(process: subprocess.Popen[Any]) -> str:
    '''停止本次 smoke 创建的 Host；此处是强制终止而非 graceful shutdown 测试。'''
    if process.poll() is not None:
        return 'already_exited'
    try:
        process.terminate()
    except OSError:
        process.wait(timeout=3)
        return 'already_exited'
    try:
        process.wait(timeout=3)
        return 'forced_after_provider_cleanup'
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=3)
        return 'killed_after_provider_cleanup'


def __wait_for_descriptor(runtime_dir: Path, host: subprocess.Popen[Any]) -> Path:
    '''等待本次临时 Host 创建的 runtime descriptor，不读取或显示其内容。'''
    deadline = time.monotonic() + HOST_READY_TIMEOUT_SECONDS
    while time.monotonic() < deadline:
        if host.poll() is not None:
            raise SmokeError('HOST_EXITED_BEFORE_READY')
        descriptors = list(runtime_dir.glob('*.runtime.json'))
        if descriptors:
            return descriptors[0]
        time.sleep(0.1)
    raise SmokeError('HOST_READY_TIMEOUT')


def run_smoke(host_exe: Path, duration_seconds: int) -> dict[str, Any]:
    '''创建隔离 loopback Host，运行合成 Codex rollout Provider 并清理临时状态。'''
    if not 1 <= duration_seconds <= MAX_DURATION_SECONDS:
        raise SmokeError('INVALID_DURATION')
    if not host_exe.is_file():
        raise SmokeError('HOST_BINARY_MISSING')
    if not PROVIDER_SCRIPT.is_file():
        raise SmokeError('PROVIDER_SCRIPT_MISSING')

    result: dict[str, Any] = {
        'status': 'FAIL',
        'host_binary': host_exe.name,
        'descriptor_created': False,
        'provider_exit_code': None,
        'provider_cleanup': 'unconfirmed',
        'host_stop': 'not_started',
        'synthetic_fixture_only': True,
        'credentials_read': False,
        'external_network': False,
        'temporary_files_removed': False,
        'error_code': None,
    }
    with tempfile.TemporaryDirectory(prefix='wincraft-quota-smoke-') as temporary:
        temporary_root = Path(temporary)
        runtime_dir = temporary_root / 'runtime'
        quota_home = temporary_root / 'synthetic-codex'
        rollout_dir = quota_home / 'sessions' / '2026' / '10' / '31'
        runtime_dir.mkdir()
        rollout_dir.mkdir(parents=True)
        now = datetime.now(timezone.utc).replace(microsecond=0)
        event_path = rollout_dir / 'rollout-synthetic.jsonl'
        event_path.write_text(
            json.dumps(__synthetic_event(now), ensure_ascii=False, separators=(',', ':')) + '\n',
            encoding='utf-8',
        )
        environment = __isolated_environment(runtime_dir)
        creation_flags = getattr(subprocess, 'CREATE_NO_WINDOW', 0)
        host = subprocess.Popen(
            [str(host_exe)],
            cwd=ROOT,
            env=environment,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=creation_flags,
        )
        try:
            descriptor = __wait_for_descriptor(runtime_dir, host)
            result['descriptor_created'] = True
            provider = subprocess.run(
                [
                    sys.executable,
                    str(PROVIDER_SCRIPT),
                    '--runtime',
                    str(descriptor),
                    '--codex-rollout-quota',
                    '--codex-home',
                    str(quota_home),
                    '--duration-seconds',
                    str(duration_seconds),
                ],
                cwd=ROOT,
                env=environment,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=duration_seconds + PROVIDER_TIMEOUT_GRACE_SECONDS,
                check=False,
            )
            result['provider_exit_code'] = provider.returncode
            result['provider_cleanup'] = (
                'confirmed_by_zero_exit'
                if provider.returncode == 0
                else 'unconfirmed'
            )
            result['status'] = 'PASS' if provider.returncode == 0 else 'FAIL'
        except subprocess.TimeoutExpired:
            result['error_code'] = 'PROVIDER_TIMEOUT'
        except SmokeError as error:
            result['error_code'] = error.code
        except (OSError, ValueError):
            result['error_code'] = 'SMOKE_IO_ERROR'
        finally:
            result['host_stop'] = __stop_host(host)
    result['temporary_files_removed'] = not temporary_root.exists()
    return result


def main() -> int:
    '''执行本地合成 release-host smoke 并打印不含敏感内容的 JSON 摘要。'''
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--host-exe', type=Path, default=DEFAULT_HOST_EXE)
    parser.add_argument('--duration-seconds', type=int, default=DEFAULT_DURATION_SECONDS)
    args = parser.parse_args()
    try:
        summary = run_smoke(args.host_exe, args.duration_seconds)
    except SmokeError as error:
        summary = {
            'status': 'FAIL',
            'error_code': error.code,
            'credentials_read': False,
            'external_network': False,
        }
    except (OSError, ValueError):
        summary = {
            'status': 'FAIL',
            'error_code': 'SMOKE_IO_ERROR',
            'credentials_read': False,
            'external_network': False,
        }
    print(json.dumps(summary, ensure_ascii=False, sort_keys=True))
    return 0 if summary['status'] == 'PASS' else 1


if __name__ == '__main__':
    raise SystemExit(main())
