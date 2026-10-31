'''Exercise presentation groups against an isolated release headless Rust Host.
- 🎯验证真实 WebSocket/Host 上窗口组逐成员执行、部分失败可观察、跨会话不可见。
- 📌Host descriptor 与进程输出留在系统临时目录并随运行删除；不读取或显示凭据。
- 🤖由 Agent 编写，未经人工逐行审阅。
'''
from __future__ import annotations

import argparse
import asyncio
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
'''📌WinCraft checkout 根目录'''

DEFAULT_HOST_EXE = ROOT / 'target' / 'release' / 'wincraft-headless.exe'
'''📜Windows release headless Host 默认路径'''

sys.path.insert(0, str(ROOT / 'examples' / 'python'))

from client import Client  # noqa: E402  (path is prepared above)
'''📌WinCraft Provider SDK'''

from client import COMPONENT_LEASES_PREVIEW_PROTOCOL  # noqa: E402
'''📌窗口组是 0.4-preview.1 的可选能力，Provider 必须显式协商该协议'''

HOST_READY_TIMEOUT_SECONDS: int = 10
'''📜等待 loopback runtime descriptor 的上限'''

SMOKE_TIMEOUT_SECONDS: int = 30
'''📜整轮 smoke 的上限'''

PRIVATE_ENV_KEYS: tuple[str, ...] = (
    'CODEX_HOME',
    'DEEPSEEK_API_KEY',
    'MINIMAX_API_KEY',
    'TEAM_SENSE_API_TOKEN',
    'TEAM_SENSE_BASE_URL',
)
'''📌合成 smoke 不向子进程传递真实来源身份或 key'''


class SmokeError(RuntimeError):
    '''不含路径、descriptor 或子进程输出的稳定 smoke 错误码。'''

    def __init__(self, code: str) -> None:
        self.code: str = code
        super().__init__(code)


def __isolated_environment(runtime_dir: Path) -> dict[str, str]:
    '''构造只带本次临时 runtime 目录的子进程环境。'''
    environment = {
        key: value
        for key, value in os.environ.items()
        if key not in PRIVATE_ENV_KEYS
    }
    environment['WINCRAFT_RUNTIME_DIR'] = str(runtime_dir)
    return environment


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


def __stop_host(host: subprocess.Popen[Any]) -> str:
    '''停止本次启动的 Host，并如实记录它是否自行退出。'''
    if host.poll() is not None:
        return 'already_exited'
    host.terminate()
    try:
        host.wait(timeout=5)
        return 'terminated_after_provider_cleanup'
    except subprocess.TimeoutExpired:
        host.kill()
        host.wait(timeout=3)
        return 'killed_after_timeout'


async def __run_group_checks(descriptor: Path) -> dict[str, Any]:
    '''在真实 Host 上跑完窗口组正反用例。'''
    checks: dict[str, Any] = {}
    async with Client(
        str(descriptor),
        'python.integration.presentation-group',
        protocol_version=COMPONENT_LEASES_PREVIEW_PROTOCOL,
    ) as owner:
        owner.require_presentation_groups()
        capabilities = owner.ready.get('capabilities', {})
        groups = capabilities.get('presentation_groups', {})
        checks['capability_atomic'] = groups.get('atomic') is False
        checks['capability_apply_semantics'] = (
            groups.get('apply_semantics') == 'per_member_independent'
        )

        created: list[dict[str, Any]] = []
        for title in ('first', 'second'):
            result = await owner.call('world.create', {
                'window': {'title': title, 'width': 320.0, 'height': 220.0},
                'claim': True,
            })
            created.append(result)
        first, second = created
        first_id = first['world']['id']
        second_id = second['world']['id']
        first_lease = first['lease']
        second_lease = second['lease']

        group = await owner.create_presentation_group(
            'smoke-hud',
            members=[
                {'world_id': first_id, 'order': 0},
                {'world_id': second_id, 'order': 1},
            ],
            roles=[{'name': 'primary', 'member': None}],
        )
        group_id = group['id']
        checks['group_created'] = bool(group_id)

        listed = await owner.list_presentation_groups()
        checks['group_listed'] = any(
            entry.get('id') == group_id for entry in listed['groups']
        )
        checks['group_roles_present'] = bool(group.get('roles'))

        # One member receives a wrong lease, so only the other member applies.
        applied = await owner.apply_presentation_group(
            group_id,
            leases={
                first_id: first_lease,
                second_id: {'id': second_lease['id'], 'epoch': second_lease['epoch'] + 99},
            },
            expected_revisions={
                first_id: first['world']['revision'],
                second_id: second['world']['revision'],
            },
            visible=False,
        )
        results = applied['result']['results']
        checks['atomic_is_false'] = applied.get('atomic') is False
        checks['applied_count'] = applied['result']['applied'] == 1
        checks['refused_count'] = applied['result']['refused'] == 1
        checks['per_member_results'] = len(results) == 2
        statuses = {
            entry['world_id']: entry['outcome']['status'] for entry in results
        }
        checks['first_member_applied'] = statuses.get(first_id) == 'applied'
        checks['second_member_refused'] = statuses.get(second_id) == 'refused'
        checks['refusal_keeps_code'] = any(
            entry['outcome'].get('code') for entry in results
            if entry['outcome']['status'] == 'refused'
        )
        checks['only_applied_member_changed'] = applied['changed'] == [first_id]

        # A second session must not see or operate on the owner's group.
        async with Client(
            str(descriptor),
            'python.integration.presentation-group-other',
            protocol_version=COMPONENT_LEASES_PREVIEW_PROTOCOL,
        ) as other:
            other_groups = await other.list_presentation_groups()
            checks['other_session_sees_no_groups'] = other_groups['groups'] == []
            try:
                await other.apply_presentation_group(
                    group_id,
                    leases={first_id: first_lease},
                    expected_revisions={first_id: first['world']['revision']},
                    visible=True,
                )
                checks['other_session_blocked'] = False
            except Exception:
                checks['other_session_blocked'] = True

        # The applied member really changed; the refused one did not.
        first_after = await owner.call('world.snapshot', {'world_id': first_id})
        second_after = await owner.call('world.snapshot', {'world_id': second_id})
        checks['applied_member_visible_changed'] = (
            first_after['window']['visible'] is False
        )
        checks['refused_member_unchanged'] = (
            second_after['window']['visible'] is True
        )

        for world in created:
            await owner.call('world.destroy', {
                'world_id': world['world']['id'],
                'lease': world['lease'],
            })
        checks['worlds_destroyed'] = True
    return checks


def run_smoke(host_exe: Path) -> dict[str, Any]:
    '''创建隔离 loopback Host，运行窗口组 smoke 并清理临时状态。'''
    if not host_exe.is_file():
        raise SmokeError('HOST_BINARY_MISSING')

    result: dict[str, Any] = {
        'status': 'FAIL',
        'host_binary': host_exe.name,
        'descriptor_created': False,
        'host_stop': 'not_started',
        'checks': {},
        'error_code': None,
    }
    with tempfile.TemporaryDirectory(prefix='wincraft-group-smoke-') as temporary:
        temporary_root = Path(temporary)
        runtime_dir = temporary_root / 'runtime'
        runtime_dir.mkdir()
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
            checks = asyncio.run(__run_group_checks(descriptor))
            result['checks'] = checks
            failed = [name for name, value in checks.items() if value is not True]
            result['failed_checks'] = failed
            result['status'] = 'PASS' if not failed else 'FAIL'
        except SmokeError as error:
            result['error_code'] = error.code
        except asyncio.TimeoutError:
            result['error_code'] = 'SMOKE_TIMEOUT'
        except Exception as error:
            result['error_code'] = 'SMOKE_ERROR'
            result['error_detail'] = f'{type(error).__name__}: {error}'[:300]
        finally:
            result['host_stop'] = __stop_host(host)
    result['temporary_files_removed'] = not temporary_root.exists()
    return result


def main() -> int:
    '''执行本地合成 release-host 窗口组 smoke 并打印不含敏感内容的 JSON 摘要。'''
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--host-exe', type=Path, default=DEFAULT_HOST_EXE)
    arguments = parser.parse_args()
    try:
        result = run_smoke(arguments.host_exe)
    except SmokeError as error:
        print(json.dumps({'status': 'FAIL', 'error_code': error.code}, indent=2))
        return 1
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0 if result['status'] == 'PASS' else 1


if __name__ == '__main__':
    raise SystemExit(main())
