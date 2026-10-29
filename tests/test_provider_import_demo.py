from __future__ import annotations

import asyncio
import importlib.util
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
EXAMPLE = ROOT / "examples" / "python" / "pack_provider_demo.py"
SPEC = importlib.util.spec_from_file_location("wincraft_pack_provider_demo", EXAMPLE)
assert SPEC and SPEC.loader
DEMO = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(DEMO)


class ProviderImportDemoTests(unittest.IsolatedAsyncioTestCase):
    def event(self, approved_permissions: list[str]) -> dict:
        return {
            "event": "world.import.joined",
            "data": {
                "kind": "wincraft.provider-import.event",
                "schema_version": "draft-2026-10-26",
                "host_id": "00000000-0000-4000-8000-000000000001",
                "pack_id": "fixture.pack",
                "pack_version": "1.0.0",
                "blueprint_id": "fixture.blueprint",
                "blueprint_world_id": "agents-board",
                "binding_ids": ["agents"],
                "approved_permissions": approved_permissions,
                "world": {"id": "00000000-0000-4000-8000-000000000010"},
                "lease": {"id": "00000000-0000-4000-8000-000000000020", "epoch": 1},
            },
        }

    async def test_inventory_claim_is_opt_in_and_never_contains_grants(self):
        registration = DEMO.inventory_registration("fixture-instance", 4)
        source = registration["providers"][0]
        self.assertIn("world.import.accept", source["capabilities"])
        self.assertNotIn("grants", source)
        self.assertEqual(registration["generation"], 4)

    async def test_import_event_updates_only_the_selected_world_and_leaves_it_alive(self):
        class FakeClient:
            def __init__(self):
                self.mutations = []
                self.calls = []

            def validate_provider_import_event(self, message):
                return message["data"]

            async def mutate(self, method, world_id, lease, **payload):
                self.mutations.append((method, world_id, lease, payload))
                return {"revision": len(self.mutations) + 1}

            async def call(self, method, payload):
                self.calls.append((method, payload))
                return {}

        client = FakeClient()
        world_id = await DEMO.handle_import_event(client, self.event(["activity.read"]), 0.01)
        self.assertEqual(world_id, "00000000-0000-4000-8000-000000000010")
        self.assertEqual([method for method, *_ in client.mutations], ["scene.replace", "scene.patch"])
        self.assertEqual(client.calls, [("world.leave", {"world_id": world_id})])
        self.assertNotIn("world.destroy", [method for method, _ in client.calls])

    async def test_unapproved_data_permission_fails_before_scene_mutation(self):
        class FakeClient:
            def __init__(self):
                self.mutations = []

            def validate_provider_import_event(self, message):
                return message["data"]

            async def mutate(self, *_args, **_kwargs):
                self.mutations.append("mutated")

        client = FakeClient()
        with self.assertRaisesRegex(RuntimeError, "did not approve"):
            await DEMO.handle_import_event(client, self.event([]), 0.01)
        self.assertEqual(client.mutations, [])


if __name__ == "__main__":
    unittest.main()
