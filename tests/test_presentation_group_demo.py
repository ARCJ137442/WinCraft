from __future__ import annotations

import asyncio
import sys
import unittest
from pathlib import Path
from typing import Any
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'examples' / 'python'))
import presentation_group_demo  # noqa: E402


class FakeClient:
    '''Minimal stand-in for the SDK client used by the demo.'''

    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self.required: list[str] = []

    def require_presentation_groups(self) -> None:
        self.required.append('presentation_groups')

    async def call(self, method: str, params: dict[str, Any]) -> Any:
        self.calls.append((method, params))
        if method == 'world.create':
            index = len([c for c in self.calls if c[0] == 'world.create'])
            return {
                'world': {'id': f'world-{index}', 'revision': 1},
                'lease': {'id': f'lease-{index}', 'epoch': 1},
            }
        if method == 'world.snapshot':
            return {'revision': 7}
        if method == 'scene.replace':
            return {'revision': 7}
        return {}

    async def create_presentation_group(self, name, members=(), roles=()):
        self.calls.append(('presentation.group.create', {
            'name': name,
            'members': [dict(m) for m in members],
            'roles': [dict(r) for r in roles],
        }))
        return {
            'id': 'group-1',
            'name': name,
            'members': [dict(m) for m in members],
            'roles': [dict(r) for r in roles],
        }

    async def apply_presentation_group(self, group_id, leases, expected_revisions=None, **patch):
        self.calls.append(('presentation.group.apply', {
            'group_id': group_id,
            'leases': {str(k): dict(v) for k, v in leases.items()},
            'expected_revisions': {str(k): int(v) for k, v in (expected_revisions or {}).items()},
            'patch': dict(patch),
        }))
        results = []
        applied = 0
        refused = 0
        changed = []
        for world_id in leases:
            lease = leases[world_id]
            if world_id == 'world-2':
                results.append({
                    'world_id': world_id,
                    'outcome': {'status': 'refused', 'code': 'STALE_LEASE'},
                })
                refused += 1
            else:
                results.append({'world_id': world_id, 'outcome': {'status': 'applied'}})
                applied += 1
                changed.append(world_id)
        return {
            'atomic': False,
            'result': {'applied': applied, 'refused': refused, 'results': results},
            'changed': changed,
        }


class FakeClientContext:
    def __init__(self, client: FakeClient) -> None:
        self.client = client

    async def __aenter__(self) -> FakeClient:
        return self.client

    async def __aexit__(self, *_: Any) -> None:
        return None


class PresentationGroupDemoTests(unittest.TestCase):
    def run_demo(self) -> tuple[dict[str, Any], FakeClient]:
        client = FakeClient()
        with patch.object(presentation_group_demo, 'Client', lambda *a, **k: FakeClientContext(client)):
            summary = asyncio.run(presentation_group_demo.run_demo('runtime.json', 0))
        return summary, client

    def test_demo_requires_the_capability_before_creating_worlds(self):
        summary, client = self.run_demo()
        self.assertEqual(client.required, ['presentation_groups'])
        self.assertTrue(summary['group_created'])
        self.assertTrue(summary['synthetic_only'])

    def test_demo_reports_a_partial_outcome_without_claiming_group_success(self):
        summary, _ = self.run_demo()
        self.assertFalse(summary['atomic'])
        self.assertEqual(summary['applied'], 1)
        self.assertEqual(summary['refused'], 1)
        self.assertEqual(summary['changed'], ['world-1'])
        statuses = {entry['world_id']: entry['status'] for entry in summary['results']}
        self.assertEqual(statuses['world-1'], 'applied')
        self.assertEqual(statuses['world-2'], 'refused')

    def test_demo_supplies_the_current_revision_not_the_creation_revision(self):
        _, client = self.run_demo()
        apply_calls = [params for method, params in client.calls
                       if method == 'presentation.group.apply']
        self.assertTrue(apply_calls)
        self.assertEqual(apply_calls[0]['expected_revisions']['world-1'], 7)

    def test_demo_destroys_only_the_worlds_it_created(self):
        _, client = self.run_demo()
        destroyed = [params for method, params in client.calls if method == 'world.destroy']
        self.assertEqual(len(destroyed), 2)
        self.assertEqual({params['world_id'] for params in destroyed}, {'world-1', 'world-2'})


if __name__ == '__main__':
    unittest.main()
