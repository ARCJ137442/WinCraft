"""A REAL Python provider with SIMULATED focus/job business data.

It is NOT an ExoMind integration. The separate exomind_readonly.py is for that.
"""
from __future__ import annotations
import argparse
import asyncio
import json
import time
from pathlib import Path
from client import Client, add_runtime_args, event_world_id, require_runtime

async def run(args: argparse.Namespace) -> None:
    async with Client(args.runtime, "python.focus-demo", args.ws_url) as c:
        if args.join:
            joined = await c.call("world.join", {"world_id": args.join, "mode": "write", "join_key": args.join_key})
            world_id, lease = joined["world"]["id"], joined["lease"]
        else:
            created = await c.call("world.create", {"window": {"title": args.title, "width": 460, "height": 600}, "join_policy": "invite"})
            world_id, lease = created["world"]["id"], created["lease"]
        assert lease is not None
        print(f"World: {world_id}. Ctrl+C disconnects; the host should mark it stale.")
        source = Path(__file__).resolve().parents[2] / "protocol/examples/focus.scene.json"
        scene = json.loads(source.read_text(encoding="utf-8"))
        await c.mutate("scene.replace", world_id, lease, scene=scene)
        state = {"paused": False, "elapsed": 0.0, "note": "", "ticks": 0, "rebuilt": False}
        gate = asyncio.Lock()
        previous = time.monotonic()
        async def publish() -> None:
            seconds = max(0, 1500 - int(state["elapsed"]))
            await c.mutate("data.replace", world_id, lease, data={
                "clock": f"{seconds//60:02}:{seconds%60:02}", "progress": min(100, state["ticks"] * 3),
                "button": "继续" if state["paused"] else "暂停", "note": state["note"],
                "source": "Python 模拟业务；并非真实外心状态"})
        async def tick() -> None:
            nonlocal previous
            while True:
                await asyncio.sleep(args.tick_interval)
                async with gate:
                    now = time.monotonic()
                    if not state["paused"]:
                        state["elapsed"] += now - previous
                        state["ticks"] += 1
                    previous = now
                    await publish()
        ticker = asyncio.create_task(tick())
        def tick_finished(task: asyncio.Task) -> None:
            if not task.cancelled() and task.exception() is not None:
                try:
                    c.events.put_nowait({"event": "provider.error", "error": str(task.exception())})
                except asyncio.QueueFull:
                    pass
        ticker.add_done_callback(tick_finished)
        try:
            while True:
                message = await c.events.get()
                if message.get("event") in ("connection.error", "connection.closed", "provider.error"):
                    raise ConnectionError(message.get("error", "Disconnected"))
                if message.get("event") == "world.deleted" and event_world_id(message) == world_id:
                    print("World was closed by the local operator.")
                    return
                if message.get("event") != "interaction":
                    continue
                event = message["data"]
                if event["world_id"] != world_id:
                    continue
                async with gate:
                    ok, error = True, None
                    try:
                        if event["action"] == "toggle_pause":
                            now = time.monotonic()
                            if not state["paused"]:
                                state["elapsed"] += now - previous
                            previous = now
                            state["paused"] = not state["paused"]
                        elif event["action"] == "note":
                            state["note"] = str(event["value"])
                        elif event["action"] == "rebuild" and not state["rebuilt"]:
                            await c.mutate("scene.patch", world_id, lease, ops=[{"op": "replace", "node_id": "progress", "node": {
                                "id": "result", "kind": "badge", "props": {"text": "组件结构已动态替换", "tone": "success"}, "children": []}}])
                            state["rebuilt"] = True
                        await publish()
                    except Exception as exc:
                        ok, error = False, str(exc)
                    await c.call("action.result", {"world_id": world_id, "lease": lease, "event_id": event["id"], "ok": ok, "message": error})
        finally:
            ticker.cancel()
            try:
                await ticker
            except asyncio.CancelledError:
                pass

def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    add_runtime_args(parser)
    parser.add_argument("--join", help="Join a blank open_authenticated world instead of creating one")
    parser.add_argument("--join-key", help="Optional invitation secret; prefer not to expose real keys in shell history")
    parser.add_argument("--title", default="Python 提供者 · 专注与任务", help="Window title for distinguishing parallel local demo worlds")
    parser.add_argument("--tick-interval", type=float, default=1.0, help="Simulated data refresh interval in seconds (0.1–30)")
    args = parser.parse_args()
    require_runtime(parser, args)
    if not 0.1 <= args.tick_interval <= 30:
        parser.error("--tick-interval must be between 0.1 and 30 seconds")
    try:
        asyncio.run(run(args))
    except KeyboardInterrupt:
        pass

if __name__ == "__main__":
    main()
