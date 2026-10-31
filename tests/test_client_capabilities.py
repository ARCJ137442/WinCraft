import asyncio
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "examples" / "python"))
from client import (  # noqa: E402
    COMPONENT_LEASES_PREVIEW_PROTOCOL,
    PROTOCOL_VERSION,
    Client,
)


class CapabilityTests(unittest.TestCase):
    def client_with(self, capabilities):
        client = Client.__new__(Client)
        client.ready = {"capabilities": capabilities}
        client.protocol_version = PROTOCOL_VERSION
        return client

    def test_advertised_optional_component_and_shortcut_are_accepted(self):
        client = self.client_with({
            "components": ["input", "textarea", "icon", "bar_chart"],
            "keyboard_shortcuts": ["escape", "ctrl_enter"],
            "button_features": ["selection_groups", "appearance_variants", "key_value_actions"],
            "scene_features": ["theme_tokens", "rich_key_value"],
            "window_properties": ["background_drag_enabled", "anchor", "position_control"],
        })
        client.require_capabilities(components=("textarea", "icon", "bar_chart"), keyboard_shortcuts=("escape", "ctrl_enter"),
                                    button_features=("selection_groups", "appearance_variants", "key_value_actions"), scene_features=("theme_tokens", "rich_key_value"),
                                    window_properties=("background_drag_enabled", "anchor", "position_control"))

    def test_missing_capability_fails_before_provider_uses_feature(self):
        client = self.client_with({"components": ["input"], "keyboard_shortcuts": [], "button_features": []})
        with self.assertRaisesRegex(RuntimeError, "component:textarea.*keyboard_shortcut:escape.*button_feature:selection_groups"):
            client.require_capabilities(components=("textarea",), keyboard_shortcuts=("escape",),
                                        button_features=("selection_groups",))

    def test_theme_tokens_fail_closed_when_host_does_not_advertise_them(self):
        client = self.client_with({
            "components": ["text"], "keyboard_shortcuts": [], "button_features": [],
        })
        with self.assertRaisesRegex(RuntimeError, "scene_feature:theme_tokens"):
            client.require_capabilities(scene_features=("theme_tokens",))

    def test_old_host_without_capability_table_fails_closed(self):
        client = self.client_with(None)
        with self.assertRaisesRegex(RuntimeError, "did not return a capability table"):
            client.require_capabilities(components=("textarea",))

    def presentation_client(self, groups):
        client = self.client_with({
            "components": [], "keyboard_shortcuts": [], "button_features": [], "scene_features": [],
            "component_leases": {"status": "preview", "version": 1},
            "presentation_groups": groups,
        })
        client.protocol_version = COMPONENT_LEASES_PREVIEW_PROTOCOL
        return client

    def test_presentation_groups_require_the_preview_capability(self):
        client = self.presentation_client({
            "status": "preview", "version": 1, "atomic": False,
            "apply_semantics": "per_member_independent",
            "lease_required_per_member": True,
            "discovery_grants_operation_right": False,
        })
        client.require_presentation_groups()

    def test_presentation_groups_fail_closed_without_the_capability(self):
        client = self.presentation_client(None)
        with self.assertRaisesRegex(RuntimeError, "presentation_groups:preview-v1"):
            client.require_presentation_groups()

    def test_presentation_groups_reject_an_atomic_host(self):
        client = self.presentation_client({
            "status": "preview", "version": 1, "atomic": True,
            "apply_semantics": "per_member_independent",
            "lease_required_per_member": True,
            "discovery_grants_operation_right": False,
        })
        with self.assertRaisesRegex(RuntimeError, "presentation_groups_atomic:false"):
            client.require_presentation_groups()

    def test_presentation_groups_reject_a_host_that_grants_rights_through_discovery(self):
        client = self.presentation_client({
            "status": "preview", "version": 1, "atomic": False,
            "apply_semantics": "per_member_independent",
            "lease_required_per_member": True,
            "discovery_grants_operation_right": True,
        })
        with self.assertRaisesRegex(RuntimeError, "presentation_groups_discovery:no_operation_right"):
            client.require_presentation_groups()

    def test_background_drag_property_fails_closed_when_host_does_not_advertise_it(self):
        client = self.client_with({"components": [], "keyboard_shortcuts": [], "button_features": [], "scene_features": []})
        with self.assertRaisesRegex(RuntimeError, "window_property:background_drag_enabled"):
            client.require_capabilities(window_properties=("background_drag_enabled",))

    def test_anchor_fails_closed_when_host_does_not_advertise_it(self):
        client = self.client_with({"components": [], "window_properties": ["background_drag_enabled"]})
        with self.assertRaisesRegex(RuntimeError, "window_property:anchor"):
            client.require_capabilities(window_properties=("anchor",))

    def test_position_control_fails_closed_when_host_does_not_advertise_it(self):
        client = self.client_with({"components": [], "window_properties": ["background_drag_enabled"]})
        with self.assertRaisesRegex(RuntimeError, "window_property:position_control"):
            client.require_capabilities(window_properties=("position_control",))

    def test_advertised_window_state_events_are_accepted(self):
        client = self.client_with({"event_subscriptions": {"events": [
            {"type": "window.geometry_changed", "delivery": "state"},
            {"type": "window.visibility_changed", "delivery": "state"},
        ]}})
        client.require_capabilities(event_types=("window.geometry_changed", "window.visibility_changed"))

    def test_unadvertised_window_event_fails_closed(self):
        client = self.client_with({"event_subscriptions": {"events": []}})
        with self.assertRaisesRegex(RuntimeError, "event:window.geometry_changed"):
            client.require_capabilities(event_types=("window.geometry_changed",))

    def test_component_leases_require_explicit_preview_protocol_and_capability(self):
        client = self.client_with({
            "component_leases": {"status": "preview", "version": 1}
        })
        with self.assertRaisesRegex(RuntimeError, "component_leases:preview-v1"):
            client.require_component_leases()

        client.protocol_version = COMPONENT_LEASES_PREVIEW_PROTOCOL
        client.ready["capabilities"]["component_leases"] = False
        with self.assertRaisesRegex(RuntimeError, "component_leases:preview-v1"):
            client.require_component_leases()

        client.ready["capabilities"]["component_leases"] = {
            "status": "preview",
            "version": 1,
        }
        client.require_component_leases()

    def test_scope_structure_operations_and_parent_patch_are_capability_gated(self):
        client = self.client_with({
            "component_leases": {
                "status": "preview",
                "version": 1,
                "scope_patch_operations": ["props"],
            }
        })
        client.protocol_version = COMPONENT_LEASES_PREVIEW_PROTOCOL
        client.require_component_leases()
        with self.assertRaisesRegex(RuntimeError, "component_scope_operation:insert"):
            client.require_capabilities(component_scope_operations=("insert",))
        with self.assertRaisesRegex(RuntimeError, "root_structure_patch:scope.structure.patch"):
            client.require_capabilities(root_structure_patch=True)

    def test_scoped_interactions_require_an_explicit_preview_capability(self):
        client = self.client_with({
            "component_leases": {"status": "preview", "version": 1}
        })
        client.protocol_version = COMPONENT_LEASES_PREVIEW_PROTOCOL
        with self.assertRaisesRegex(RuntimeError, "scope_interactions:preview-v1"):
            client.require_scope_interactions()

        client.ready["capabilities"]["component_leases"]["scope_interactions"] = {
            "status": "preview",
            "version": 1,
            "event": "scope.interaction",
            "acknowledge_method": "scope.action.result",
            "routing": "component_scope_owner",
            "native_window_actions": False,
        }
        client.require_scope_interactions()

    def test_scope_status_is_fail_closed_and_sends_only_scope_metadata_request(self):
        client = self.client_with({
            "component_leases": {"status": "preview", "version": 1}
        })
        client.protocol_version = COMPONENT_LEASES_PREVIEW_PROTOCOL
        with self.assertRaisesRegex(RuntimeError, "scope_status:preview-v1"):
            client.require_scope_status()

        client.ready["capabilities"]["component_leases"]["scope_status"] = {
            "status": "preview",
            "version": 1,
            "method": "scope.status",
            "data": "lifecycle_metadata_only",
            "authorization": "active_world_authority_or_scope_member",
            "states": ["online", "stale", "vacant", "revoked", "unknown"],
        }
        with self.assertRaisesRegex(RuntimeError, "scope_status:preview-v1"):
            client.require_scope_status()

        client.ready["capabilities"]["component_leases"]["scope_status"] = {
            "status": "preview",
            "version": 1,
            "method": "scope.status",
            "data": "lifecycle_metadata_only",
            "authorization": "local_operator_or_active_world_authority_or_scope_member",
            "states": ["online", "stale", "vacant", "revoked", "unknown"],
        }
        client.require_scope_status()
        calls = []

        async def capture(method, params):
            calls.append((method, params))
            return {"status": "stale"}

        client.call = capture
        result = asyncio.run(client.read_scope_status("world", "scope", 1))
        self.assertEqual(result, {"status": "stale"})
        self.assertEqual(calls, [(
            "scope.status",
            {"world_id": "world", "scope_id": "scope", "generation": 1},
        )])

    def test_scope_action_result_uses_the_current_scoped_lease(self):
        client = self.client_with({
            "component_leases": {
                "status": "preview",
                "version": 1,
                "scope_interactions": {
                    "status": "preview",
                    "version": 1,
                    "event": "scope.interaction",
                    "acknowledge_method": "scope.action.result",
                    "routing": "component_scope_owner",
                    "native_window_actions": False,
                },
            }
        })
        client.protocol_version = COMPONENT_LEASES_PREVIEW_PROTOCOL
        calls = []

        async def capture(method, params):
            calls.append((method, params))
            return {"acknowledged": True}

        client.call = capture
        result = asyncio.run(client.scope_action_result(
            "world-a",
            {"scope_id": "scope-a", "lease_id": "lease-a", "epoch": 3, "generation": 2},
            "event-a",
            ok=True,
            message="accepted",
        ))

        self.assertEqual(result, {"acknowledged": True})
        self.assertEqual(calls, [(
            "scope.action.result",
            {
                "world_id": "world-a",
                "lease": {"scope_id": "scope-a", "lease_id": "lease-a", "epoch": 3, "generation": 2},
                "event_id": "event-a",
                "ok": True,
                "message": "accepted",
            },
        )])

    def test_scoped_interactions_require_an_explicit_preview_capability(self):
        client = self.client_with({
            "component_leases": {"status": "preview", "version": 1}
        })
        client.protocol_version = COMPONENT_LEASES_PREVIEW_PROTOCOL
        with self.assertRaisesRegex(RuntimeError, "scope_interactions:preview-v1"):
            client.require_scope_interactions()

        client.ready["capabilities"]["component_leases"]["scope_interactions"] = {
            "status": "preview",
            "version": 1,
            "event": "scope.interaction",
            "acknowledge_method": "scope.action.result",
            "routing": "component_scope_owner",
            "native_window_actions": False,
        }
        client.require_scope_interactions()

    def test_scope_action_result_uses_the_current_scoped_lease(self):
        client = self.client_with({
            "component_leases": {
                "status": "preview",
                "version": 1,
                "scope_interactions": {
                    "status": "preview",
                    "version": 1,
                    "event": "scope.interaction",
                    "acknowledge_method": "scope.action.result",
                    "routing": "component_scope_owner",
                    "native_window_actions": False,
                },
            }
        })
        client.protocol_version = COMPONENT_LEASES_PREVIEW_PROTOCOL
        calls = []

        async def capture(method, params):
            calls.append((method, params))
            return {"acknowledged": True}

        client.call = capture
        result = asyncio.run(client.scope_action_result(
            "world-a",
            {"scope_id": "scope-a", "lease_id": "lease-a", "epoch": 3, "generation": 2},
            "event-a",
            ok=True,
            message="accepted",
        ))

        self.assertEqual(result, {"acknowledged": True})
        self.assertEqual(calls, [(
            "scope.action.result",
            {
                "world_id": "world-a",
                "lease": {"scope_id": "scope-a", "lease_id": "lease-a", "epoch": 3, "generation": 2},
                "event_id": "event-a",
                "ok": True,
                "message": "accepted",
            },
        )])

    def test_scope_patch_does_not_send_unadvertised_structure_operation(self):
        client = self.client_with({
            "component_leases": {
                "status": "preview",
                "version": 1,
                "scope_patch_operations": ["props"],
            }
        })
        client.protocol_version = COMPONENT_LEASES_PREVIEW_PROTOCOL
        async def unexpected_send(*_args, **_kwargs):
            raise AssertionError("unadvertised operation reached the transport")
        client.call = unexpected_send

        with self.assertRaisesRegex(RuntimeError, "component_scope_operation:move"):
            asyncio.run(client.patch_scope(
                "world",
                {"scope_id": "scope", "lease_id": "lease", "epoch": 1, "generation": 1},
                3,
                [{"op": "move", "node_id": "source", "parent": "target", "index": 0}],
            ))

    def test_scope_snapshot_cache_is_monotonic_and_parent_revocation_clears_it(self):
        client = Client.__new__(Client)
        client.scope_snapshots = {}
        client.events = asyncio.Queue()
        client.pending = {}

        client._remember_scope_snapshot({
            "world_id": "world",
            "scope_id": "scope",
            "generation": 1,
            "revision": 4,
            "data": {"value": "current"},
        })
        client._remember_scope_snapshot({
            "world_id": "world",
            "scope_id": "scope",
            "generation": 1,
            "revision": 3,
            "data": {"value": "stale"},
        })
        self.assertEqual(client.scope_snapshots[("world", "scope")]["revision"], 4)

        class FakeSocket:
            def __init__(self, messages):
                self.messages = iter(messages)

            def __aiter__(self):
                return self

            async def __anext__(self):
                try:
                    return next(self.messages)
                except StopIteration:
                    raise StopAsyncIteration

            async def close(self):
                return None

        client.socket = FakeSocket([json.dumps({
            "event": "scope.revoked",
            "data": {"world_id": "world", "scope_id": "scope", "generation": 2},
        })])
        asyncio.run(client._receive())
        self.assertNotIn(("world", "scope"), client.scope_snapshots)
        self.assertEqual(client.events.get_nowait()["event"], "scope.revoked")

    def test_preview_protocol_must_be_advertised_by_the_runtime_descriptor(self):
        descriptor = {
            "protocol": PROTOCOL_VERSION,
            "supported_protocols": [PROTOCOL_VERSION],
            "host_id": "host.fixture",
            "token": "fixture-only",
            "ws_url": "ws://127.0.0.1:12345/v1/ws",
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "runtime.json"
            path.write_text(json.dumps(descriptor), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "does not advertise requested protocol"):
                Client(path, "fixture", protocol_version=COMPONENT_LEASES_PREVIEW_PROTOCOL)

            descriptor["supported_protocols"].append(COMPONENT_LEASES_PREVIEW_PROTOCOL)
            path.write_text(json.dumps(descriptor), encoding="utf-8")
            client = Client(path, "fixture", protocol_version=COMPONENT_LEASES_PREVIEW_PROTOCOL)
            self.assertEqual(client.protocol_version, COMPONENT_LEASES_PREVIEW_PROTOCOL)

    def test_state_slots_require_preview_capability_schema_and_access_rules(self):
        client = self.client_with({
            "component_leases": {"status": "preview", "version": 1}
        })
        with self.assertRaisesRegex(RuntimeError, "component_leases:preview-v1"):
            client.require_state_slots()

        client.protocol_version = COMPONENT_LEASES_PREVIEW_PROTOCOL
        with self.assertRaisesRegex(RuntimeError, "state_slots:preview-v1"):
            client.require_state_slots()

        client.ready["capabilities"]["component_leases"]["state_slots"] = {
            "status": "preview",
            "version": 1,
            "schema_types": ["boolean", "integer", "number", "string", "enum"],
            "reads": "explicit_scope_grants",
            "writes": "owner_scope_cas",
        }
        client.require_state_slots()

        client.ready["capabilities"]["component_leases"]["state_slots"]["schema_types"].remove("enum")
        with self.assertRaisesRegex(RuntimeError, "state_slot_schema:enum"):
            client.require_state_slots()

    def test_state_slot_helpers_fail_closed_and_use_named_preview_methods(self):
        client = self.client_with({
            "component_leases": {"status": "preview", "version": 1}
        })
        client.protocol_version = COMPONENT_LEASES_PREVIEW_PROTOCOL

        async def unexpected_send(*_args, **_kwargs):
            raise AssertionError("unadvertised state slot operation reached the transport")

        client.call = unexpected_send
        with self.assertRaisesRegex(RuntimeError, "state_slots:preview-v1"):
            asyncio.run(client.read_state_slot("world", "slot", 1, "scope", 1))

        client.ready["capabilities"]["component_leases"]["state_slots"] = {
            "status": "preview",
            "version": 1,
            "schema_types": ["boolean", "integer", "number", "string", "enum"],
            "reads": "explicit_scope_grants",
            "writes": "owner_scope_cas",
        }
        calls = []

        async def capture(method, params):
            calls.append((method, params))
            return {"method": method, "params": params}

        client.call = capture
        lease = {"scope_id": "owner", "lease_id": "lease", "epoch": 2, "generation": 1}
        reader_scope = {
            "scope_id": "reader",
            "generation": 3,
            "join_key": "secret-not-sent",
        }

        async def invoke_all():
            await client.create_state_slot(
                "world", lease, "shared.value", {"type": "integer", "min": 0, "max": 10},
                2, [reader_scope],
            )
            await client.set_state_slot_readers("world", lease, "slot", 1, 1, [reader_scope])
            await client.read_state_slot("world", "slot", 1, "reader", 3)
            await client.compare_and_set_state_slot("world", lease, "slot", 1, 2, 4)
            await client.delete_state_slot("world", lease, "slot", 1, 3)

        asyncio.run(invoke_all())
        self.assertEqual(
            [method for method, _params in calls],
            [
                "state.slot.create",
                "state.slot.set_readers",
                "state.slot.read",
                "state.slot.compare_and_set",
                "state.slot.delete",
            ],
        )
        self.assertEqual(
            calls[0][1]["reader_scopes"],
            [{"scope_id": "reader", "generation": 3}],
        )
        self.assertEqual(calls[2][1]["reader_scope_generation"], 3)

    def test_provider_inventory_requires_the_advertised_preview_capability(self):
        client = self.client_with({
            "provider_inventory": {"status": "preview", "version": 1}
        })
        with self.assertRaisesRegex(RuntimeError, "provider_inventory:preview-v1"):
            client.require_provider_inventory()

        client.protocol_version = COMPONENT_LEASES_PREVIEW_PROTOCOL
        client.require_provider_inventory()

        client.ready["capabilities"]["provider_inventory"]["version"] = 2
        with self.assertRaisesRegex(RuntimeError, "provider_inventory:preview-v1"):
            client.require_provider_inventory()

    def test_provider_import_requires_preview_contract_and_is_absent_from_stable_protocol(self):
        client = self.client_with({
            "provider_inventory": {"status": "preview", "version": 1},
            "provider_import": {
                "status": "preview",
                "version": 1,
                "schema_version": "draft-2026-10-26",
                "event": "world.import.joined",
                "required_claim": "world.import.accept",
                "writer_scope": "exclusive_world_lease",
                "requires_local_confirmation": True,
            },
        })
        with self.assertRaisesRegex(RuntimeError, "provider_import:preview-v1"):
            client.require_provider_import()

        client.protocol_version = COMPONENT_LEASES_PREVIEW_PROTOCOL
        client.require_provider_import()

        client.ready["capabilities"]["provider_import"]["event"] = "world.create"
        with self.assertRaisesRegex(RuntimeError, "provider_import_event:world.import.joined"):
            client.require_provider_import()

    def test_provider_import_event_is_bound_to_host_and_matching_world_lease_epoch(self):
        client = self.client_with({
            "provider_inventory": {"status": "preview", "version": 1},
            "provider_import": {
                "status": "preview",
                "version": 1,
                "schema_version": "draft-2026-10-26",
                "event": "world.import.joined",
                "required_claim": "world.import.accept",
                "writer_scope": "exclusive_world_lease",
                "requires_local_confirmation": True,
            },
        })
        client.protocol_version = COMPONENT_LEASES_PREVIEW_PROTOCOL
        client.ready["host_id"] = "00000000-0000-4000-8000-000000000001"
        event = {
            "event": "world.import.joined",
            "data": {
                "kind": "wincraft.provider-import.event",
                "schema_version": "draft-2026-10-26",
                "host_id": client.ready["host_id"],
                "pack_id": "fixture.pack",
                "pack_version": "1.0",
                "blueprint_id": "fixture.blueprint",
                "blueprint_world_id": "agents",
                "binding_ids": ["agents"],
                "approved_permissions": ["activity.read"],
                "world": {
                    "id": "00000000-0000-4000-8000-000000000010",
                    "epoch": 2,
                    "writer": "00000000-0000-4000-8000-000000000020",
                    "system": False,
                    "scene": {},
                    "window": {},
                },
                "lease": {"id": "00000000-0000-4000-8000-000000000030", "epoch": 2},
            },
        }
        self.assertEqual(client.validate_provider_import_event(event)["pack_id"], "fixture.pack")

        foreign = json.loads(json.dumps(event))
        foreign["data"]["host_id"] = "00000000-0000-4000-8000-000000000099"
        with self.assertRaisesRegex(RuntimeError, "different Host"):
            client.validate_provider_import_event(foreign)

        stale_epoch = json.loads(json.dumps(event))
        stale_epoch["data"]["lease"]["epoch"] = 1
        with self.assertRaisesRegex(RuntimeError, "inconsistent"):
            client.validate_provider_import_event(stale_epoch)

    def test_provider_import_requires_preview_contract_and_is_absent_from_stable_protocol(self):
        client = self.client_with({
            "provider_inventory": {"status": "preview", "version": 1},
            "provider_import": {
                "status": "preview",
                "version": 1,
                "schema_version": "draft-2026-10-26",
                "event": "world.import.joined",
                "required_claim": "world.import.accept",
                "writer_scope": "exclusive_world_lease",
                "requires_local_confirmation": True,
            },
        })
        with self.assertRaisesRegex(RuntimeError, "provider_import:preview-v1"):
            client.require_provider_import()

        client.protocol_version = COMPONENT_LEASES_PREVIEW_PROTOCOL
        client.require_provider_import()

        client.ready["capabilities"]["provider_import"]["event"] = "world.create"
        with self.assertRaisesRegex(RuntimeError, "provider_import_event:world.import.joined"):
            client.require_provider_import()

    def test_inventory_rpc_helpers_fail_before_sending_when_capability_is_missing(self):
        client = self.client_with({})
        client.protocol_version = COMPONENT_LEASES_PREVIEW_PROTOCOL
        calls = []

        async def unexpected_call(method, params):
            calls.append((method, params))
            return {}

        client.call = unexpected_call
        with self.assertRaisesRegex(RuntimeError, "provider_inventory:preview-v1"):
            asyncio.run(client.register_provider_inventory({"kind": "synthetic"}))
        with self.assertRaisesRegex(RuntimeError, "provider_inventory:preview-v1"):
            asyncio.run(client.list_provider_inventory())
        self.assertEqual(calls, [])

    def test_provider_import_claim_is_not_registered_without_import_capability(self):
        client = self.client_with({
            "provider_inventory": {"status": "preview", "version": 1},
        })
        client.protocol_version = COMPONENT_LEASES_PREVIEW_PROTOCOL
        calls = []

        async def unexpected_call(method, params):
            calls.append((method, params))
            return {}

        client.call = unexpected_call
        registration = {
            "kind": "wincraft.inventory.registration",
            "providers": [{"capabilities": ["world.import.accept"]}],
        }
        with self.assertRaisesRegex(RuntimeError, "provider_import:preview-v1"):
            asyncio.run(client.register_provider_inventory(registration))
        self.assertEqual(calls, [])

    def test_inventory_rpc_helpers_use_explicit_methods_after_preview_gate(self):
        client = self.client_with({
            "provider_inventory": {"status": "preview", "version": 1}
        })
        client.protocol_version = COMPONENT_LEASES_PREVIEW_PROTOCOL
        client.ready["host_id"] = "synthetic-endpoint"
        calls = []

        async def capture(method, params):
            calls.append((method, params))
            return {"endpoint_id": "synthetic-endpoint", "providers": []}

        client.call = capture
        registration = {"kind": "wincraft.inventory.registration", "providers": []}
        result = asyncio.run(client.register_provider_inventory(registration))
        listing = asyncio.run(client.list_provider_inventory())

        self.assertEqual(result, {"endpoint_id": "synthetic-endpoint", "providers": []})
        self.assertEqual(listing, {"endpoint_id": "synthetic-endpoint", "providers": []})
        self.assertEqual(calls, [
            ("provider.inventory.register", registration),
            ("provider.inventory.list", {}),
        ])

    def test_provider_inventory_snapshot_must_match_hello_endpoint(self):
        client = self.client_with({
            "provider_inventory": {"status": "preview", "version": 1}
        })
        client.protocol_version = COMPONENT_LEASES_PREVIEW_PROTOCOL
        client.ready["host_id"] = "selected-endpoint"

        async def wrong_endpoint(*_args, **_kwargs):
            return {"endpoint_id": "another-endpoint", "providers": []}

        client.call = wrong_endpoint
        with self.assertRaisesRegex(RuntimeError, "different endpoint"):
            asyncio.run(client.list_provider_inventory())


if __name__ == "__main__":
    unittest.main()
