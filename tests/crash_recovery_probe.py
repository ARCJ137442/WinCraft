'''Exercise stale-world recovery after an abrupt synthetic Provider exit.
- 🎯Verify a crashed writer is fenced and a new writer can clean up its world.
- 🧪Use only a disposable world on an already-running local WinCraft Host.
- 🤖Agent-generated probe, not yet human-reviewed【2026-10-31】
'''

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
import uuid
from pathlib import Path
from typing import TypedDict


REPO_ROOT: Path = Path(__file__).resolve().parents[1]
'''Repository root used to import the shared Python Provider SDK.'''

EXAMPLES_PYTHON_DIR: Path = REPO_ROOT / 'examples' / 'python'
'''Directory containing the shared Provider SDK.'''

TESTS_DIR: Path = Path(__file__).resolve().parent
'''Directory containing the synthetic performance helpers.'''

OWNER_READY_TIMEOUT_SECONDS: float = 15.0
'''Maximum time to wait for the crash-owner Provider to publish its private record.'''

STALE_WAIT_TIMEOUT_SECONDS: float = 8.0
'''Maximum time to wait for the Host to observe the abrupt WebSocket disconnect.'''

HOST_DISCONNECT_TIMEOUT_SECONDS: float = 15.0
'''Maximum time to wait for a forced Host shutdown to close the Provider socket.'''

POLL_INTERVAL_SECONDS: float = 0.1
'''Interval for idempotent status snapshots while waiting for disconnect propagation.'''

HOST_DISCONNECT_EVENTS: frozenset[str] = frozenset(
    {'connection.error', 'connection.closed'}
)
'''Provider SDK events emitted after the Host WebSocket becomes unavailable.'''

if str(EXAMPLES_PYTHON_DIR) not in sys.path:
    sys.path.insert(0, str(EXAMPLES_PYTHON_DIR))

if str(TESTS_DIR) not in sys.path:
    sys.path.insert(0, str(TESTS_DIR))

from client import Client, RpcError
from performance_probe import create_synthetic_world, quiet_destroy


class CrashOwnerRecord(TypedDict):
    '''Temporary fields required to inspect and clean the synthetic world.'''

    world_id: str
    join_key: str
    owner_epoch: int


def parse_crash_owner_record(content: str) -> CrashOwnerRecord:
    '''Validate the private handoff from the crash-owner child process.'''
    value = json.loads(content)
    if not isinstance(value, dict):
        raise ValueError('Crash-owner record must be an object')

    world_id = value.get('world_id')
    join_key = value.get('join_key')
    owner_epoch = value.get('owner_epoch')
    if not isinstance(world_id, str) or not isinstance(join_key, str):
        raise ValueError('Crash-owner record is missing its world join fields')
    if not isinstance(owner_epoch, int) or isinstance(owner_epoch, bool):
        raise ValueError('Crash-owner record has an invalid lease epoch')

    return {
        'world_id': world_id,
        'join_key': join_key,
        'owner_epoch': owner_epoch,
    }


def is_host_disconnect_event(event: dict[str, object]) -> bool:
    '''Identify only terminal transport events for the active Host connection.'''
    return event.get('event') in HOST_DISCONNECT_EVENTS


async def hold_crash_owner(runtime_path: str, record_path: Path) -> None:
    '''Create one synthetic world and keep its writer connection open.
    - 🎯The parent process terminates this Provider without running cleanup.
    - 📌The private record is temporary and must be removed by the parent.
    '''
    client = Client(runtime_path, f'wincraft.b11-01.crash-owner.{uuid.uuid4().hex}')
    await client.__aenter__()

    world_id, lease, join_key = await create_synthetic_world(
        client,
        0,
        title_prefix='WinCraft B11-01 abrupt Provider exit',
    )
    record_path.write_text(
        json.dumps(
            {
                'world_id': world_id,
                'join_key': join_key,
                'owner_epoch': lease['epoch'],
            }
        ),
        encoding='utf-8',
    )

    # 📌Keep the socket and heartbeat alive until the parent kills this process.
    await asyncio.Event().wait()


async def terminate_crash_owner(runtime_path: str, record_path: Path) -> CrashOwnerRecord:
    '''Abruptly terminate the disposable Provider after it creates its world.
    - 📌The parent kills only the exact child process it launched.
    - 🚩Return the temporary identifiers only to the in-process recovery path.
    '''
    child = await asyncio.create_subprocess_exec(
        sys.executable,
        str(Path(__file__).resolve()),
        '--runtime',
        runtime_path,
        '--record-file',
        str(record_path),
        '--owner-child',
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.DEVNULL,
    )
    deadline = time.monotonic() + OWNER_READY_TIMEOUT_SECONDS

    try:
        while not record_path.exists():
            if child.returncode is not None:
                raise RuntimeError(
                    f'Crash-owner Provider exited before ready (exit={child.returncode})'
                )
            if time.monotonic() >= deadline:
                raise TimeoutError('Crash-owner Provider did not become ready in time')
            await asyncio.sleep(POLL_INTERVAL_SECONDS)

        record = parse_crash_owner_record(record_path.read_text(encoding='utf-8'))
        child.kill()
        await child.wait()
        return record
    finally:
        if child.returncode is None:
            child.kill()
            await child.wait()


async def recover_crashed_world(
    runtime_path: str,
    record: CrashOwnerRecord,
) -> dict[str, bool | str]:
    '''Observe stale state, acquire a fenced writer lease, and destroy the test world.
    - 🎯Fail unless the crashed lease epoch advances before the new writer acts.
    - 📌Only the synthetic world created by the child Provider is changed.
    '''
    world_id = record['world_id']
    join_key = record['join_key']
    owner_epoch = record['owner_epoch']
    async with Client(runtime_path, f'wincraft.b11-01.crash-recovery.{uuid.uuid4().hex}') as client:
        read_join = await client.call(
            'world.join',
            {'world_id': world_id, 'join_key': join_key, 'mode': 'read'},
        )
        world = read_join.get('world')
        if not isinstance(world, dict):
            raise RuntimeError('Host did not return a snapshot for the recovery reader')

        deadline = time.monotonic() + STALE_WAIT_TIMEOUT_SECONDS
        while world.get('status') != 'stale' and time.monotonic() < deadline:
            await asyncio.sleep(POLL_INTERVAL_SECONDS)
            world = await client.call('world.snapshot', {'world_id': world_id})
        if world.get('status') != 'stale':
            raise RuntimeError('Host did not mark the crashed writer stale')

        writer_join = await client.call(
            'world.join',
            {'world_id': world_id, 'join_key': join_key, 'mode': 'write'},
        )
        lease = writer_join.get('lease')
        world = writer_join.get('world')
        if not isinstance(lease, dict):
            raise RuntimeError('Host did not issue a replacement writer lease')
        if not isinstance(world, dict) or world.get('status') != 'online':
            raise RuntimeError('Replacement writer did not restore online status')

        replacement_epoch = lease.get('epoch')
        if not isinstance(replacement_epoch, int) or replacement_epoch <= owner_epoch:
            raise RuntimeError('Replacement lease did not advance the fencing epoch')

        destroy_attempted = False
        world_destroyed = False
        try:
            destroy_attempted = True
            await quiet_destroy(client, world_id, lease)
            world_destroyed = True
            try:
                await client.call('world.snapshot', {'world_id': world_id})
            except RpcError as exc:
                if exc.code != 'NOT_FOUND':
                    raise
            else:
                raise RuntimeError('Synthetic world remains after destroy confirmation')
        finally:
            if not destroy_attempted and not world_destroyed:
                await quiet_destroy(client, world_id, lease)

    return {
        'status': 'PASS',
        'owner_process_terminated': True,
        'stale_status_observed': True,
        'writer_reacquired': True,
        'lease_epoch_advanced': True,
        'synthetic_world_destroyed': True,
        'identifiers_or_leases_recorded': False,
    }


async def run_probe(runtime_path: str, record_path: Path) -> dict[str, bool | str]:
    '''Run the abrupt-exit and recovery flow, then remove its private record.
    - 📌The caller is responsible for stopping its disposable Host after failure.
    '''
    if record_path.exists():
        raise FileExistsError(f'Refusing to overwrite an existing test record: {record_path.name}')

    record_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        record = await terminate_crash_owner(runtime_path, record_path)
        return await recover_crashed_world(runtime_path, record)
    finally:
        if record_path.exists():
            record_path.unlink()


async def wait_for_host_disconnect(
    runtime_path: str,
    ready_path: Path,
    *,
    visible: bool,
) -> dict[str, bool | str]:
    '''Create a visible synthetic world and wait for its Host socket to close.
    - 🎯The parent terminates the disposable Tauri Host after the ready marker.
    - 📌The report includes only the terminal event name, never its error text.
    '''
    async with Client(runtime_path, f'wincraft.b11-01.host-crash.{uuid.uuid4().hex}') as client:
        world_id, lease, _join_key = await create_synthetic_world(
            client,
            0,
            visible=visible,
            title_prefix='WinCraft B11-01 synthetic Host crash',
        )
        scene = {
            'root': {
                'id': 'root',
                'kind': 'stack',
                'props': {'gap': 8},
                'children': [
                    {'id': 'title', 'kind': 'text', 'props': {
                        'text': 'Synthetic Host crash probe', 'size': 'heading',
                    }},
                    {'id': 'counter', 'kind': 'metric', 'props': {
                        'label': 'Synthetic counter',
                        'value': {'$path': '/counter'},
                    }},
                ],
            },
            'data': {'counter': 0},
        }
        await client.mutate('scene.replace', world_id, lease, scene=scene)
        ready_path.write_text('ready', encoding='utf-8')

        deadline = time.monotonic() + HOST_DISCONNECT_TIMEOUT_SECONDS
        while time.monotonic() < deadline:
            remaining = deadline - time.monotonic()
            event = await asyncio.wait_for(client.events.get(), timeout=remaining)
            if is_host_disconnect_event(event):
                return {
                    'status': 'PASS',
                    'host_connection_lost': True,
                    'synthetic_world_created': True,
                    'window_visible': visible,
                    'terminal_event': str(event['event']),
                    'identifiers_or_leases_recorded': False,
                }

    raise TimeoutError('Provider did not observe the forced Host shutdown')


async def run_host_disconnect_probe(
    runtime_path: str,
    ready_path: Path,
    *,
    visible: bool = False,
) -> dict[str, bool | str]:
    '''Run the disconnect observer and remove only its ready marker.'''
    if ready_path.exists():
        raise FileExistsError(f'Refusing to overwrite an existing marker: {ready_path.name}')

    ready_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        return await wait_for_host_disconnect(
            runtime_path,
            ready_path,
            visible=visible,
        )
    finally:
        if ready_path.exists():
            ready_path.unlink()


def main() -> None:
    '''Parse the probe mode and print aggregate results only.'''
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime', type=Path, required=True)
    parser.add_argument('--record-file', type=Path, required=True)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--owner-child', action='store_true')
    mode.add_argument('--expect-host-disconnect', action='store_true')
    parser.add_argument('--visible-window', action='store_true')
    args = parser.parse_args()

    if args.visible_window and not args.expect_host_disconnect:
        parser.error('--visible-window requires --expect-host-disconnect')

    runtime_path = str(args.runtime.resolve())
    record_path = args.record_file.resolve()
    if args.owner_child:
        asyncio.run(hold_crash_owner(runtime_path, record_path))
        return

    if args.expect_host_disconnect:
        result = asyncio.run(
            run_host_disconnect_probe(
                runtime_path,
                record_path,
                visible=args.visible_window,
            )
        )
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return

    result = asyncio.run(run_probe(runtime_path, record_path))
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
