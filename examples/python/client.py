"""Small WinCraft provider client. No browser/HTML/JS required by the caller.

No automatic replay of timed-out writes: a timeout has an unknown outcome.
Reconnect explicitly, discover/rejoin, acquire a NEW lease and rebuild state.
"""
from __future__ import annotations
import asyncio
import contextlib
import json
import os
import uuid
from collections.abc import Mapping
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

PROTOCOL_VERSION = "0.3"
COMPONENT_LEASES_PREVIEW_PROTOCOL = "0.4-preview.1"
SUPPORTED_PROTOCOLS = (PROTOCOL_VERSION, COMPONENT_LEASES_PREVIEW_PROTOCOL)

class RpcError(RuntimeError):
    def __init__(self, error: dict[str, Any]):
        self.code = str(error.get("code", "UNKNOWN"))
        super().__init__(f"{self.code}: {error.get('message', '')}")


def event_world_id(message: Any) -> str | None:
    """Read a world ID from top-level lifecycle events or nested event data."""
    if not isinstance(message, Mapping):
        return None
    value = message.get("world_id")
    if isinstance(value, str) and value:
        return value
    data = message.get("data")
    value = data.get("world_id") if isinstance(data, Mapping) else None
    return value if isinstance(value, str) and value else None


class EventQueue(asyncio.Queue[dict[str, Any]]):
    """Bounded event queue that retains only the newest queued state per subscription/type."""

    @staticmethod
    def _state_key(message: Any) -> tuple[str, str] | None:
        if not isinstance(message, Mapping) or message.get("event") != "window.event":
            return None
        data = message.get("data")
        if not isinstance(data, Mapping) or data.get("delivery") != "state":
            return None
        subscription_id = data.get("subscription_id")
        event_type = data.get("type")
        if isinstance(subscription_id, str) and isinstance(event_type, str):
            return subscription_id, event_type
        return None

    def put_nowait(self, item: dict[str, Any]) -> None:
        key = self._state_key(item)
        if key is not None and self._queue and self._state_key(self._queue[-1]) == key:
            self._queue[-1] = item
            return
        super().put_nowait(item)

class Client:
    def __init__(
        self,
        runtime: str | Path,
        name: str,
        ws_url: str | None = None,
        protocol_version: str | None = None,
    ):
        self.descriptor = json.loads(Path(runtime).read_text(encoding="utf-8"))
        if self.descriptor.get("protocol") != PROTOCOL_VERSION:
            raise ValueError("Unsupported runtime descriptor protocol")
        advertised_protocols = self.descriptor.get("supported_protocols", [PROTOCOL_VERSION])
        if not isinstance(advertised_protocols, list) or not all(
            isinstance(value, str) for value in advertised_protocols
        ):
            raise ValueError("Runtime descriptor has an invalid supported_protocols list")
        self.protocol_version = protocol_version or PROTOCOL_VERSION
        if self.protocol_version not in SUPPORTED_PROTOCOLS:
            raise ValueError("Unsupported protocol selection")
        if self.protocol_version not in advertised_protocols:
            raise ValueError(
                f"Host does not advertise requested protocol {self.protocol_version}"
            )
        self.url = ws_url or self.descriptor["ws_url"]
        parsed = urlparse(self.url)
        if parsed.scheme not in ("ws", "wss"):
            raise ValueError("WebSocket URL required")
        if parsed.scheme == "ws" and parsed.hostname not in ("localhost", "127.0.0.1", "::1"):
            raise ValueError("Use a loopback SSH tunnel or authenticated TLS; no plaintext remote bearer credentials")
        self.name = name
        self.pending: dict[str, asyncio.Future[Any]] = {}
        self.events: asyncio.Queue[dict[str, Any]] = EventQueue(maxsize=128)
        self.snapshots: dict[str, dict[str, Any]] = {}
        self.scope_snapshots: dict[tuple[str, str], dict[str, Any]] = {}
        self.socket: Any = None
        self.reader: asyncio.Task[Any] | None = None
        self.heartbeat: asyncio.Task[Any] | None = None
        self.ready: dict[str, Any] = {}

    async def __aenter__(self) -> Client:
        try:
            from websockets.asyncio.client import connect
        except ImportError as exc:
            raise RuntimeError("Run: python -m pip install -r examples/python/requirements.txt") from exc
        self.socket = await connect(self.url,
            additional_headers={"Authorization": f"Bearer {self.descriptor['token']}"},
            max_size=1_048_576, open_timeout=5, ping_interval=10)
        self.reader = asyncio.create_task(self._receive())
        try:
            self.ready = await self.call(
                "hello",
                {"protocol": self.protocol_version, "provider_name": self.name},
            )
            if self.ready["host_id"] != self.descriptor["host_id"]:
                raise RuntimeError("Descriptor host_id does not match the server; refuse stale/wrong endpoint")
            if self.ready.get("protocol", self.protocol_version) != self.protocol_version:
                raise RuntimeError("Server negotiated a different protocol than requested")
            self.heartbeat = asyncio.create_task(self._heartbeat())
        except BaseException:
            await self.close()
            raise
        return self

    async def __aexit__(self, *_: Any) -> None:
        await self.close()

    async def close(self) -> None:
        for task in (self.heartbeat, self.reader):
            if task:
                task.cancel()
        if self.socket:
            await self.socket.close()
        for task in (self.heartbeat, self.reader):
            if task:
                with contextlib.suppress(asyncio.CancelledError, Exception):
                    await task
        for future in self.pending.values():
            if not future.done():
                future.set_exception(ConnectionError("Provider session closed"))
        self.pending.clear()

    async def _receive(self) -> None:
        try:
            async for raw in self.socket:
                message = json.loads(raw)
                if "id" in message:
                    future = self.pending.pop(str(message["id"]), None)
                    if future and not future.done():
                        if message.get("ok"):
                            future.set_result(message.get("result"))
                        else:
                            future.set_exception(RpcError(message.get("error", {})))
                elif message.get("event") == "world.snapshot":
                    snapshot = message["data"]
                    previous = self.snapshots.get(snapshot["id"])
                    if previous is None or snapshot["sequence"] > previous["sequence"]:
                        self.snapshots[snapshot["id"]] = snapshot
                elif message.get("event") == "scope.snapshot":
                    snapshot = message["data"]
                    self._remember_scope_snapshot(snapshot)
                elif message.get("event") == "scope.revoked":
                    data = message.get("data", {})
                    key = (str(data.get("world_id", "")), str(data.get("scope_id", "")))
                    self.scope_snapshots.pop(key, None)
                    self.events.put_nowait(message)
                else:
                    if message.get("event") == "resync_required":
                        raise ConnectionError("Slow consumer: reconnect and reconstruct explicitly")
                    self.events.put_nowait(message)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            for future in list(self.pending.values()):
                if not future.done():
                    future.set_exception(exc)
            self.pending.clear()
            await self.socket.close()
            # Wake the foreground demo instead of leaving it waiting silently.
            with contextlib.suppress(asyncio.QueueFull):
                self.events.put_nowait({"event": "connection.error", "error": str(exc)})
        finally:
            with contextlib.suppress(asyncio.QueueFull):
                self.events.put_nowait({"event": "connection.closed"})
            for future in list(self.pending.values()):
                if not future.done():
                    future.set_exception(ConnectionError("WebSocket closed"))
            self.pending.clear()

    def _remember_scope_snapshot(self, snapshot: Mapping[str, Any]) -> None:
        key = (str(snapshot.get("world_id", "")), str(snapshot.get("scope_id", "")))
        previous = self.scope_snapshots.get(key)
        if previous is None or (
            snapshot.get("generation", -1), snapshot.get("revision", -1)
        ) > (previous.get("generation", -1), previous.get("revision", -1)):
            self.scope_snapshots[key] = dict(snapshot)

    async def _heartbeat(self) -> None:
        try:
            while True:
                await asyncio.sleep(3)
                await self.call("session.ping", {})
        except asyncio.CancelledError:
            raise
        except Exception:
            await self.socket.close()

    async def call(self, method: str, params: dict[str, Any]) -> Any:
        request_id = uuid.uuid4().hex
        future = asyncio.get_running_loop().create_future()
        self.pending[request_id] = future
        try:
            await self.socket.send(json.dumps({"id": request_id, "method": method, "params": params}, ensure_ascii=False))
            return await asyncio.wait_for(future, 8)
        finally:
            self.pending.pop(request_id, None)

    def require_capabilities(self, *, components: tuple[str, ...] = (),
                             keyboard_shortcuts: tuple[str, ...] = (),
                             button_features: tuple[str, ...] = (),
                             scene_features: tuple[str, ...] = (),
                             window_properties: tuple[str, ...] = (),
                             event_types: tuple[str, ...] = (),
                             component_leases_version: int | None = None,
                             component_scope_operations: tuple[str, ...] = (),
                             root_structure_patch: bool = False,
                             state_slots_version: int | None = None,
                             state_slot_schema_types: tuple[str, ...] = ()) -> None:
        """Fail closed when a provider needs an optional renderer feature."""
        capabilities = self.ready.get("capabilities")
        if not isinstance(capabilities, dict):
            raise RuntimeError("Host did not return a capability table; optional features are unavailable")
        advertised_components = capabilities.get("components")
        advertised_shortcuts = capabilities.get("keyboard_shortcuts")
        advertised_button_features = capabilities.get("button_features")
        advertised_scene_features = capabilities.get("scene_features")
        advertised_window_properties = capabilities.get("window_properties")
        event_subscriptions = capabilities.get("event_subscriptions")
        advertised_events = event_subscriptions.get("events") if isinstance(event_subscriptions, dict) else None
        component_leases = capabilities.get("component_leases")
        state_slots = component_leases.get("state_slots") \
            if isinstance(component_leases, dict) else None
        component_set = {value for value in advertised_components if isinstance(value, str)} \
            if isinstance(advertised_components, list) else set()
        shortcut_set = {value for value in advertised_shortcuts if isinstance(value, str)} \
            if isinstance(advertised_shortcuts, list) else set()
        button_feature_set = {value for value in advertised_button_features if isinstance(value, str)} \
            if isinstance(advertised_button_features, list) else set()
        scene_feature_set = {value for value in advertised_scene_features if isinstance(value, str)} \
            if isinstance(advertised_scene_features, list) else set()
        window_property_set = {value for value in advertised_window_properties if isinstance(value, str)} \
            if isinstance(advertised_window_properties, list) else set()
        event_type_set = {
            event.get("type") for event in advertised_events
            if isinstance(event, dict) and isinstance(event.get("type"), str)
        } if isinstance(advertised_events, list) else set()
        missing = [f"component:{value}" for value in components if value not in component_set]
        missing.extend(f"keyboard_shortcut:{value}" for value in keyboard_shortcuts if value not in shortcut_set)
        missing.extend(f"button_feature:{value}" for value in button_features if value not in button_feature_set)
        missing.extend(f"scene_feature:{value}" for value in scene_features if value not in scene_feature_set)
        missing.extend(f"window_property:{value}" for value in window_properties if value not in window_property_set)
        missing.extend(f"event:{value}" for value in event_types if value not in event_type_set)
        if component_leases_version is not None:
            if (
                self.protocol_version != COMPONENT_LEASES_PREVIEW_PROTOCOL
                or not isinstance(component_leases, dict)
                or component_leases.get("status") != "preview"
                or component_leases.get("version") != component_leases_version
            ):
                missing.append(f"component_leases:preview-v{component_leases_version}")
        advertised_scope_operations = component_leases.get("scope_patch_operations") \
            if isinstance(component_leases, dict) else None
        scope_operation_set = {
            value for value in advertised_scope_operations if isinstance(value, str)
        } if isinstance(advertised_scope_operations, list) else set()
        missing.extend(
            f"component_scope_operation:{value}"
            for value in component_scope_operations
            if value not in scope_operation_set
        )
        if root_structure_patch and (
            not isinstance(component_leases, dict)
            or component_leases.get("root_structure_patch") != "scope.structure.patch"
        ):
            missing.append("root_structure_patch:scope.structure.patch")
        if state_slots_version is not None and (
            not isinstance(state_slots, dict)
            or state_slots.get("status") != "preview"
            or state_slots.get("version") != state_slots_version
        ):
            missing.append(f"state_slots:preview-v{state_slots_version}")
        advertised_slot_types = state_slots.get("schema_types") \
            if isinstance(state_slots, dict) else None
        slot_type_set = {
            value for value in advertised_slot_types if isinstance(value, str)
        } if isinstance(advertised_slot_types, list) else set()
        missing.extend(
            f"state_slot_schema:{value}"
            for value in state_slot_schema_types
            if value not in slot_type_set
        )
        if state_slots_version is not None and isinstance(state_slots, dict):
            if state_slots.get("reads") != "explicit_scope_grants":
                missing.append("state_slot_reads:explicit_scope_grants")
            if state_slots.get("writes") != "owner_scope_cas":
                missing.append("state_slot_writes:owner_scope_cas")
        if missing:
            raise RuntimeError("Host does not advertise required optional capabilities: " + ", ".join(missing))

    def require_component_leases(self, version: int = 1) -> None:
        """Fail closed unless this connection negotiated the matching scope-lease preview."""
        self.require_capabilities(component_leases_version=version)

    def require_state_slots(self, version: int = 1) -> None:
        """Fail closed unless typed state slots and their access rules are advertised."""
        self.require_capabilities(
            component_leases_version=1,
            state_slots_version=version,
            state_slot_schema_types=("boolean", "integer", "number", "string", "enum"),
        )

    async def subscribe_events(self, world_id: str, types: tuple[str, ...]) -> dict[str, Any]:
        """Subscribe to connection-scoped window state events for an already joined world."""
        self.require_capabilities(event_types=types)
        return await self.call("event.subscribe", {"world_id": world_id, "types": list(types)})

    async def unsubscribe_events(self, subscription_id: str) -> dict[str, Any]:
        """Cancel a subscription; it also disappears automatically when this session ends."""
        return await self.call("event.unsubscribe", {"subscription_id": subscription_id})

    async def partition_scopes(
        self,
        world_id: str,
        lease: dict[str, Any],
        expected_revision: int,
        scopes: list[dict[str, str]],
    ) -> dict[str, Any]:
        self.require_component_leases()
        return await self.call("scope.partition", {
            "world_id": world_id,
            "lease": lease,
            "expected_revision": expected_revision,
            "scopes": scopes,
        })

    async def join_scope(
        self,
        world_id: str,
        grant: Mapping[str, Any],
        mode: str = "read",
    ) -> dict[str, Any]:
        self.require_component_leases()
        if mode not in ("read", "write"):
            raise ValueError("scope mode must be 'read' or 'write'")
        result = await self.call("scope.join", {
            "world_id": world_id,
            "scope_id": grant["scope_id"],
            "generation": grant["generation"],
            "join_key": grant["join_key"],
            "mode": mode,
        })
        self._remember_scope_snapshot(result["snapshot"])
        return result

    async def read_scope(self, world_id: str, scope_id: str, generation: int) -> dict[str, Any]:
        self.require_component_leases()
        snapshot = await self.call("scope.snapshot", {
            "world_id": world_id,
            "scope_id": scope_id,
            "generation": generation,
        })
        self._remember_scope_snapshot(snapshot)
        return snapshot

    async def patch_scope(
        self,
        world_id: str,
        lease: dict[str, Any],
        expected_scope_revision: int,
        ops: list[dict[str, Any]],
    ) -> dict[str, Any]:
        self.require_component_leases()
        operations = tuple(sorted({
            operation.get("op")
            for operation in ops
            if isinstance(operation, Mapping) and isinstance(operation.get("op"), str)
        } - {"props"}))
        if operations:
            self.require_capabilities(component_scope_operations=operations)
        result = await self.call("scope.patch", {
            "world_id": world_id,
            "lease": lease,
            "expected_scope_revision": expected_scope_revision,
            "ops": ops,
        })
        self._remember_scope_snapshot(result)
        return result

    async def patch_structure(
        self,
        world_id: str,
        authority_lease: dict[str, Any],
        expected_revision: int,
        ops: list[dict[str, Any]],
    ) -> dict[str, Any]:
        self.require_capabilities(component_leases_version=1, root_structure_patch=True)
        return await self.call("scope.structure.patch", {
            "world_id": world_id,
            "authority_lease": authority_lease,
            "expected_revision": expected_revision,
            "ops": ops,
        })

    async def replace_scope_data(
        self,
        world_id: str,
        lease: dict[str, Any],
        expected_scope_revision: int,
        data: Any,
    ) -> dict[str, Any]:
        self.require_component_leases()
        result = await self.call("scope.data.replace", {
            "world_id": world_id,
            "lease": lease,
            "expected_scope_revision": expected_scope_revision,
            "data": data,
        })
        self._remember_scope_snapshot(result)
        return result

    async def leave_scope(self, world_id: str, scope_id: str) -> dict[str, Any]:
        self.require_component_leases()
        return await self.call("scope.leave", {"world_id": world_id, "scope_id": scope_id})

    @staticmethod
    def _state_slot_scope_refs(scopes: list[Mapping[str, Any]]) -> list[dict[str, Any]]:
        return [
            {"scope_id": scope["scope_id"], "generation": scope["generation"]}
            for scope in scopes
        ]

    async def create_state_slot(
        self,
        world_id: str,
        lease: Mapping[str, Any],
        name: str,
        schema: Mapping[str, Any],
        initial_value: Any,
        reader_scopes: list[Mapping[str, Any]] | None = None,
    ) -> dict[str, Any]:
        self.require_state_slots()
        return await self.call("state.slot.create", {
            "world_id": world_id,
            "lease": dict(lease),
            "name": name,
            "schema": dict(schema),
            "initial_value": initial_value,
            "reader_scopes": self._state_slot_scope_refs(reader_scopes or []),
        })

    async def set_state_slot_readers(
        self,
        world_id: str,
        lease: Mapping[str, Any],
        slot_id: str,
        generation: int,
        expected_revision: int,
        reader_scopes: list[Mapping[str, Any]],
    ) -> dict[str, Any]:
        self.require_state_slots()
        return await self.call("state.slot.set_readers", {
            "world_id": world_id,
            "lease": dict(lease),
            "slot_id": slot_id,
            "generation": generation,
            "expected_revision": expected_revision,
            "reader_scopes": self._state_slot_scope_refs(reader_scopes),
        })

    async def read_state_slot(
        self,
        world_id: str,
        slot_id: str,
        generation: int,
        reader_scope_id: str,
        reader_scope_generation: int,
    ) -> dict[str, Any]:
        self.require_state_slots()
        return await self.call("state.slot.read", {
            "world_id": world_id,
            "slot_id": slot_id,
            "generation": generation,
            "reader_scope_id": reader_scope_id,
            "reader_scope_generation": reader_scope_generation,
        })

    async def compare_and_set_state_slot(
        self,
        world_id: str,
        lease: Mapping[str, Any],
        slot_id: str,
        generation: int,
        expected_revision: int,
        value: Any,
    ) -> dict[str, Any]:
        self.require_state_slots()
        return await self.call("state.slot.compare_and_set", {
            "world_id": world_id,
            "lease": dict(lease),
            "slot_id": slot_id,
            "generation": generation,
            "expected_revision": expected_revision,
            "value": value,
        })

    async def delete_state_slot(
        self,
        world_id: str,
        lease: Mapping[str, Any],
        slot_id: str,
        generation: int,
        expected_revision: int,
    ) -> None:
        self.require_state_slots()
        await self.call("state.slot.delete", {
            "world_id": world_id,
            "lease": dict(lease),
            "slot_id": slot_id,
            "generation": generation,
            "expected_revision": expected_revision,
        })

    async def mutate(self, method: str, world_id: str, lease: dict[str, Any], **payload: Any) -> dict[str, Any]:
        """Only retry explicit revision rejection, never a timeout or native failure."""
        for attempt in range(3):
            current = await self.call("world.snapshot", {"world_id": world_id})
            try:
                result = await self.call(method, {"world_id": world_id, "lease": lease,
                    "expected_revision": current["revision"], **payload})
                self.snapshots[world_id] = result
                return result
            except RpcError as exc:
                if exc.code != "REVISION_CONFLICT" or attempt == 2:
                    raise
        raise AssertionError("Unreachable")


def add_runtime_args(parser: Any) -> None:
    parser.add_argument("--runtime", default=os.environ.get("WINCRAFT_RUNTIME"),
        help="Path printed by the host or shown in its manager; contains a secret")
    parser.add_argument("--ws-url", help="Optional loopback URL override for an SSH tunnel")


def require_runtime(parser: Any, args: Any) -> None:
    if not args.runtime:
        parser.error("--runtime PATH or WINCRAFT_RUNTIME is required; no default port is guessed")


async def destroy_world_safely(
    client: Client,
    world_id: str,
    lease: Mapping[str, Any],
    *,
    provider_name: str = "Provider",
) -> None:
    """Destroy only this provider's world and finish cleanup before propagating Ctrl+C."""
    cleanup = asyncio.create_task(
        client.call("world.destroy", {"world_id": world_id, "lease": dict(lease)})
    )
    was_cancelled = False
    while not cleanup.done():
        try:
            await asyncio.shield(cleanup)
        except asyncio.CancelledError:
            was_cancelled = True
        except Exception as exc:
            raise RuntimeError(
                f"{provider_name} world cleanup outcome is unknown; inspect the manager before retrying"
            ) from exc
    if cleanup.cancelled():
        raise RuntimeError(
            f"{provider_name} world cleanup was cancelled; inspect the manager before retrying"
        )
    error = cleanup.exception()
    if error is not None:
        raise RuntimeError(
            f"{provider_name} world cleanup outcome is unknown; inspect the manager before retrying"
        ) from error
    print(f"{provider_name} world cleanup confirmed.", flush=True)
    if was_cancelled:
        raise asyncio.CancelledError
