"""Read-only bridge for ExoMind's GET /timeblocks/active?user_id=... .

Upstream inspection: exomind-team/exomind @ ddb1ba1a, timeblock-rt-adapter.ts
and runtime-profile-scope.ts. No default RT port/profile is guessed. An HTTP
404 is displayed as 'no active block / verify endpoint', NOT proof of health.
No pause/resume/end APIs are invoked by this prototype.
"""
from __future__ import annotations
import argparse
import asyncio
import json
import os
from urllib.error import HTTPError
from urllib.parse import urlencode, urlparse
from urllib.request import Request, urlopen
from client import Client, add_runtime_args, require_runtime

def poll(base: str, profile: str, headers: dict[str, str]) -> dict:
    url = base.rstrip("/") + "/timeblocks/active?" + urlencode({"user_id": profile})
    request = Request(url, headers={"Accept": "application/json", **headers}, method="GET")
    try:
        with urlopen(request, timeout=4) as response:
            body = response.read(131073)
            if len(body) > 131072:
                raise ValueError("ExoMind response exceeds 128 KiB prototype budget")
            data = json.loads(body)
    except HTTPError as exc:
        if exc.code == 404:
            return {"status": "HTTP 404：无活动时间块，或端点需核对", "items": []}
        raise
    if data is None:
        return {"status": "外心返回空活动时间块", "items": []}
    if not isinstance(data, dict):
        raise ValueError("Unexpected ExoMind response shape; do not guess a business schema")
    # Schema-agnostic projection: no independent countdown or inferred task state.
    items = [{"key": str(k), "value": v if isinstance(v, (str, int, float, bool)) or v is None else json.dumps(v, ensure_ascii=False)}
             for k, v in list(data.items())[:32]]
    return {"status": "外心 RT 读取成功 · 原始字段投影", "items": items}

async def run(args: argparse.Namespace) -> None:
    headers = json.loads(os.environ.get("EXOMIND_HEADERS_JSON", "{}"))
    if not isinstance(headers, dict) or not all(isinstance(k, str) and isinstance(v, str) for k, v in headers.items()):
        raise ValueError("EXOMIND_HEADERS_JSON must be a string-to-string map")
    parsed = urlparse(args.exomind)
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        raise ValueError("Explicit ExoMind HTTP(S) base URL required")
    if parsed.scheme == "http" and parsed.hostname not in ("127.0.0.1", "localhost", "::1"):
        raise ValueError("Use an SSH tunnel or HTTPS for remote ExoMind, especially with auth headers")
    async with Client(args.runtime, "exomind.readonly-bridge", args.ws_url) as c:
        created = await c.call("world.create", {"window": {"title": "外心 · 只读状态投影", "width": 480, "height": 560}})
        wid, lease = created["world"]["id"], created["lease"]
        def n(id: str, kind: str, props: dict, children: list | None = None) -> dict:
            return {"id": id, "kind": kind, "props": props, "children": children or []}
        scene = {"root": n("root", "stack", {"gap": 14}, [
            n("title", "text", {"text": "外心的状态，在窗口中延伸", "size": "title"}),
            n("status", "badge", {"text": {"$path": "/status"}}),
            n("note", "text", {"text": "只读桥接 · 不自行计算计时，不修改任务或时间块", "tone": "muted"}),
            n("raw", "key_value", {"items": {"$path": "/items"}})]), "data": {"status": "连接中", "items": []}}
        await c.mutate("scene.replace", wid, lease, scene=scene)
        print(f"Read-only world: {wid}; source profile must be the one you explicitly selected.")
        last_items = []
        while True:
            try:
                data = await asyncio.to_thread(poll, args.exomind, args.profile, headers)
                last_items = data["items"]
            except Exception as exc:
                # Host lease may be online while the source is stale. Report the source failure explicitly.
                data = {"status": f"来源读取失败（旧字段保留）：{type(exc).__name__}", "items": last_items}
            await c.mutate("data.replace", wid, lease, data=data)
            await asyncio.sleep(2)

if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    add_runtime_args(p)
    p.add_argument("--exomind", required=True, help="Verified RT URL, including its actual port")
    p.add_argument("--profile", required=True, help="Explicit user_id / active profile; never default to anonymous")
    args = p.parse_args()
    require_runtime(p, args)
    try:
        asyncio.run(run(args))
    except KeyboardInterrupt:
        pass
