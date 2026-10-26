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
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

PROTOCOL_VERSION = "0.3"

class RpcError(RuntimeError):
    def __init__(self, error: dict[str, Any]):
        self.code = str(error.get("code", "UNKNOWN"))
        super().__init__(f"{self.code}: {error.get('message', '')}")

class Client:
    def __init__(self, runtime: str | Path, name: str, ws_url: str | None = None):
        self.descriptor = json.loads(Path(runtime).read_text(encoding="utf-8"))
        if self.descriptor.get("protocol") != PROTOCOL_VERSION:
            raise ValueError("Unsupported runtime descriptor protocol")
        self.url = ws_url or self.descriptor["ws_url"]
        parsed = urlparse(self.url)
        if parsed.scheme not in ("ws", "wss"):
            raise ValueError("WebSocket URL required")
        if parsed.scheme == "ws" and parsed.hostname not in ("localhost", "127.0.0.1", "::1"):
            raise ValueError("Use a loopback SSH tunnel or authenticated TLS; no plaintext remote bearer credentials")
        self.name = name
        self.pending: dict[str, asyncio.Future[Any]] = {}
        self.events: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=128)
        self.snapshots: dict[str, dict[str, Any]] = {}
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
            self.ready = await self.call("hello", {"protocol": PROTOCOL_VERSION, "provider_name": self.name})
            if self.ready["host_id"] != self.descriptor["host_id"]:
                raise RuntimeError("Descriptor host_id does not match the server; refuse stale/wrong endpoint")
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
