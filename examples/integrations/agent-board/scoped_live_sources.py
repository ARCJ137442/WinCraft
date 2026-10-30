"""Verify independent, local-only Codex CLI and Claude Code scope writers.

The host process owns one temporary world and its layout. Two child Provider
processes independently read one selected local source and write only their
granted component subtree. Output is aggregate-only; session text stays in the
Provider/Host memory used to render the local test window.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import subprocess
import sys
import time
from collections.abc import Mapping
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import UUID

SCRIPT_DIR = Path(__file__).resolve().parent
PYTHON_EXAMPLES = Path(__file__).resolve().parents[2] / "python"
for import_path in (PYTHON_EXAMPLES, SCRIPT_DIR):
    if str(import_path) not in sys.path:
        sys.path.insert(0, str(import_path))

from client import (  # noqa: E402
    COMPONENT_LEASES_PREVIEW_PROTOCOL,
    Client,
    RpcError,
    add_runtime_args,
    destroy_world_safely,
    event_world_id,
    require_runtime,
)
from live_sources import (  # noqa: E402
    LIVE_SOURCE_LABELS,
    LiveSnapshot,
    load_live_snapshot,
    summarize_live_snapshot,
)

SOURCE_IDS = ("codex", "claude-code")
LIFECYCLE_SCOPE = {"root_node_id": "scope-lifecycle", "data_namespace": "host"}
SOURCE_SCOPES = {
    "codex": {"root_node_id": "scope-codex", "data_namespace": "codex"},
    "claude-code": {
        "root_node_id": "scope-claude-code",
        "data_namespace": "claude_code",
    },
}
PREVIEW_LIMIT = 3
MAX_BOOTSTRAP_BYTES = 16_384
MAX_CHILD_OUTPUT_BYTES = 65_536
MAX_SOURCE_READ_SECONDS = 120
SCOPE_STATUS_POLL_SECONDS = 0.2
WORKER_NAME_PREFIX = "python.agent-board.scoped-source"

PROCESS_HEALTH_LABELS = {
    "online": "进程在线",
    "offline": "进程离线",
    "unknown": "进程状态未知",
    "partial": "部分可用",
    "disconnected": "来源断开",
    "unavailable": "来源不可用",
    "not_requested": "本轮未查询",
}
DATA_HEALTH_LABELS = {
    "local_state": "本机历史可读",
    "partial": "本机历史部分可读",
    "unavailable": "本机历史不可读",
    "disconnected": "本机历史读取中断",
    "not_applicable": "状态由来源提供",
    "not_requested": "本轮未查询",
    "online": "数据可读",
    "offline": "数据离线",
}
STATUS_LABELS = {
    "running": "进行中",
    "waiting_input": "等待输入",
    "waiting_approval": "等待批准",
    "blocked": "阻塞",
    "stale": "已过期",
    "unknown": "未知",
    "not_loaded": "未载入",
    "completed": "已完成",
    "failed": "失败",
    "idle": "空闲",
}
SCOPE_STATUS_PRESENTATION = {
    "online": ("Writer 在线", "success"),
    "stale": ("Writer 离线 · 数据保留", "warning"),
    "vacant": ("尚未接入", "muted"),
    "revoked": ("Scope 已撤销", "danger"),
    "unknown": ("Scope 状态未知", "muted"),
}
LIFECYCLE_DATA_KEYS = {"codex": "codex", "claude-code": "claude_code"}


def _node(
    node_id: str,
    kind: str,
    props: dict[str, Any],
    children: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    return {"id": node_id, "kind": kind, "props": props, "children": children or []}


def _empty_scope_data() -> dict[str, Any]:
    return {
        "health_label": "等待 Provider",
        "data_health_label": "等待本机读取",
        "freshness_label": "更新时间未知",
        "record_count": 0,
        "status_summary": "等待快照",
        "previews": [
            {"identity": "", "context": ""} for _ in range(PREVIEW_LIMIT)
        ],
    }


def _empty_lifecycle_data() -> dict[str, str]:
    return {
        key: value
        for source_id in SOURCE_IDS
        for key, value in (
            (f"{LIFECYCLE_DATA_KEYS[source_id]}_status", "等待 Host 状态"),
            (f"{LIFECYCLE_DATA_KEYS[source_id]}_tone", "muted"),
        )
    }


def _lifecycle_data(statuses: Mapping[str, str]) -> dict[str, str]:
    if set(statuses) != set(SOURCE_IDS):
        raise ValueError("scope lifecycle status must cover both source providers")
    data: dict[str, str] = {}
    for source_id in SOURCE_IDS:
        label, tone = SCOPE_STATUS_PRESENTATION.get(
            statuses[source_id], SCOPE_STATUS_PRESENTATION["unknown"]
        )
        namespace = LIFECYCLE_DATA_KEYS[source_id]
        data[f"{namespace}_status"] = label
        data[f"{namespace}_tone"] = tone
    return data


def _preview_nodes(root_id: str, namespace: str) -> list[dict[str, Any]]:
    return [
        _node(
            f"{root_id}-preview-{index}",
            "stack",
            {"gap": 2},
            [
                _node(
                    f"{root_id}-preview-{index}-identity",
                    "text",
                    {"text": {"$path": f"/{namespace}/previews/{index}/identity"}, "size": "small"},
                ),
                _node(
                    f"{root_id}-preview-{index}-context",
                    "text",
                    {"text": {"$path": f"/{namespace}/previews/{index}/context"}, "size": "small"},
                ),
            ],
        )
        for index in range(PREVIEW_LIMIT)
    ]


def _source_panel(source_id: str) -> dict[str, Any]:
    scope = SOURCE_SCOPES[source_id]
    root_id = scope["root_node_id"]
    namespace = scope["data_namespace"]
    return _node(
        root_id,
        "stack",
        {"gap": 6},
        [
            _node(
                f"{root_id}-title",
                "text",
                {"text": LIVE_SOURCE_LABELS[source_id], "size": "heading"},
            ),
            _node(
                f"{root_id}-health",
                "badge",
                {"text": {"$path": f"/{namespace}/health_label"}, "tone": "accent"},
            ),
            _node(
                f"{root_id}-data-health",
                "text",
                {"text": {"$path": f"/{namespace}/data_health_label"}, "size": "small"},
            ),
            _node(
                f"{root_id}-count",
                "metric",
                {
                    "label": "可列会话",
                    "value": {"$path": f"/{namespace}/record_count"},
                    "caption": {"$path": f"/{namespace}/freshness_label"},
                },
            ),
            _node(
                f"{root_id}-status-counts",
                "text",
                {"text": {"$path": f"/{namespace}/status_summary"}, "size": "small"},
            ),
            *_preview_nodes(root_id, namespace),
        ],
    )


def _lifecycle_panel() -> dict[str, Any]:
    children = [
        _node(
            "scope-lifecycle-title",
            "text",
            {"text": "Host 观察到的 scope 生命周期", "size": "small"},
        )
    ]
    for source_id in SOURCE_IDS:
        label = LIVE_SOURCE_LABELS[source_id]
        key = LIFECYCLE_DATA_KEYS[source_id]
        children.append(
            _node(
                f"scope-lifecycle-{key}",
                "row",
                {"gap": 4},
                [
                    _node(
                        f"scope-lifecycle-{key}-label",
                        "text",
                        {"text": label, "size": "small"},
                    ),
                    _node(
                        f"scope-lifecycle-{key}-status",
                        "badge",
                        {
                            "text": {"$path": f"/host/{key}_status"},
                            "tone": {"$path": f"/host/{key}_tone"},
                        },
                    ),
                ],
            )
        )
    return _node(LIFECYCLE_SCOPE["root_node_id"], "stack", {"gap": 3}, children)


def scene() -> dict[str, Any]:
    """Build one fixed layout; each source child owns a separate panel subtree."""
    return {
        "root": _node(
            "scoped-live-root",
            "stack",
            {"gap": 10},
            [
                _node(
                    "scoped-live-title",
                    "text",
                    {"text": "Agent Activity · 独立来源写入", "size": "title"},
                ),
                _node(
                    "scoped-live-note",
                    "text",
                    {"text": "本机只读快照；每个来源 Provider 仅更新自己的组件区。", "size": "small"},
                ),
                _lifecycle_panel(),
                _source_panel("codex"),
                _source_panel("claude-code"),
            ],
        ),
        "data": {
            LIFECYCLE_SCOPE["data_namespace"]: _empty_lifecycle_data(),
            **{
                SOURCE_SCOPES[source_id]["data_namespace"]: _empty_scope_data()
                for source_id in SOURCE_IDS
            },
        },
    }


def _bounded_text(value: object, limit: int) -> str:
    if not isinstance(value, str):
        return ""
    return " ".join(value.split())[:limit]


def _source_health_label(source_id: str, health: str) -> str:
    if source_id == "codex":
        return {
            "online": "CLI 可查询",
            "partial": "CLI 部分可查询",
            "disconnected": "CLI 连接中断",
            "unavailable": "CLI 不可用",
        }.get(health, "CLI 状态未知")
    return PROCESS_HEALTH_LABELS.get(health, "进程状态未知")


def _freshness_label(age: object, freshness: str) -> str:
    if isinstance(age, int) and not isinstance(age, bool):
        return f"最近成功读取 {age} 秒前 · {freshness}"
    return f"最近成功读取时间未知 · {freshness}"


def _status_summary(status_counts: Mapping[str, Any]) -> str:
    return " · ".join(
        f"{STATUS_LABELS.get(status, '未知')} {count}"
        for status, count in sorted(status_counts.items())
        if isinstance(count, int) and count > 0
    ) or "当前无可列会话状态"


def _preview_data(records: list[dict[str, Any]]) -> list[dict[str, str]]:
    previews = []
    for record in records[:PREVIEW_LIMIT]:
        if not isinstance(record, Mapping):
            continue
        name = _bounded_text(record.get("display_name"), 96) or "未命名会话"
        status = STATUS_LABELS.get(record.get("normalized_status"), "未知")
        project = _bounded_text(record.get("project_label"), 64) or "项目未知"
        output = _bounded_text(record.get("summary"), 112) or "暂无最近 Agent 输出"
        previews.append({"identity": f"{name} · {status}", "context": f"{project} · {output}"})
    if not previews:
        previews.append({"identity": "该来源暂无可列会话", "context": ""})
    previews.extend(
        {"identity": "", "context": ""}
        for _ in range(PREVIEW_LIMIT - len(previews))
    )
    return previews


def source_scope_data(snapshot: LiveSnapshot, source_id: str) -> dict[str, Any]:
    """Project only the selected source's sanitized display fields into its scope."""
    if source_id not in SOURCE_IDS:
        raise ValueError("unsupported scoped source")
    projection = snapshot.projection
    status_counts = summarize_live_snapshot(snapshot)["status_counts"].get(source_id, {})
    records = snapshot.records_by_source.get(source_id, [])
    return {
        "health_label": _source_health_label(
            source_id, projection.get("source_health", {}).get(source_id, "unknown")
        ),
        "data_health_label": DATA_HEALTH_LABELS.get(
            projection.get("source_data_health", {}).get(source_id, "unknown"),
            "数据状态未知",
        ),
        "freshness_label": _freshness_label(
            projection.get("source_age_seconds", {}).get(source_id),
            projection.get("source_freshness", {}).get(source_id, "unknown"),
        ),
        "record_count": len(records),
        "status_summary": _status_summary(status_counts),
        "previews": _preview_data(records),
    }


def worker_command(source_id: str, duration_seconds: float, ws_url: str | None) -> list[str]:
    if source_id not in SOURCE_IDS:
        raise ValueError("unsupported scoped source")
    command = [
        sys.executable,
        str(Path(__file__).resolve()),
        "--source-worker",
        "--source",
        source_id,
        "--duration-seconds",
        str(duration_seconds),
    ]
    if ws_url:
        command.extend(("--ws-url", ws_url))
    return command


def _read_worker_bootstrap() -> bytes:
    raw = sys.stdin.buffer.readline(MAX_BOOTSTRAP_BYTES + 1)
    if not raw or not raw.endswith(b"\n"):
        raise ValueError("one bounded JSON bootstrap line is required on stdin")
    return raw[:-1]


async def _reap_workers(processes: Mapping[str, asyncio.subprocess.Process]) -> None:
    for process in processes.values():
        if process.returncode is not None:
            continue
        try:
            await asyncio.wait_for(process.wait(), timeout=15)
        except TimeoutError:
            process.terminate()
            try:
                await asyncio.wait_for(process.wait(), timeout=3)
            except TimeoutError:
                process.kill()
                await process.wait()


async def _destroy_owned_world(
    client: Client,
    world_id: str,
    lease: Mapping[str, Any],
) -> None:
    try:
        await destroy_world_safely(
            client,
            world_id,
            lease,
            provider_name="Scoped live sources",
        )
    except RuntimeError as cleanup_error:
        if getattr(cleanup_error.__cause__, "code", None) != "NOT_FOUND":
            raise
        try:
            await client.call("world.snapshot", {"world_id": world_id})
        except Exception as verification_error:
            if getattr(verification_error, "code", None) == "NOT_FOUND":
                print("Scoped live sources cleanup confirmed after local window close.", flush=True)
                return
            raise cleanup_error from verification_error
        raise cleanup_error


def _validate_worker_payload(raw: bytes, source_id: str) -> tuple[str, dict[str, Any]]:
    if len(raw) > MAX_BOOTSTRAP_BYTES:
        raise ValueError("scope grant bootstrap exceeds the local size cap")
    value = json.loads(raw.decode("utf-8"))
    if not isinstance(value, Mapping):
        raise ValueError("scope grant bootstrap must be an object")
    world_id = value.get("world_id")
    grant = value.get("grant")
    if not isinstance(world_id, str) or not isinstance(grant, Mapping):
        raise ValueError("scope grant bootstrap is incomplete")
    UUID(world_id)
    expected = SOURCE_SCOPES[source_id]["root_node_id"]
    if grant.get("root_node_id") != expected:
        raise ValueError("scope grant does not match the selected source")
    scope_id = grant.get("scope_id")
    generation = grant.get("generation")
    join_key = grant.get("join_key")
    if not isinstance(scope_id, str):
        raise ValueError("scope grant id is missing")
    UUID(scope_id)
    if isinstance(generation, bool) or not isinstance(generation, int) or generation < 1:
        raise ValueError("scope generation is invalid")
    if not isinstance(join_key, str) or not 1 <= len(join_key) <= 512:
        raise ValueError("scope join key is invalid")
    return world_id, dict(grant)


async def _read_worker_output(
    source_id: str,
    process: asyncio.subprocess.Process,
    timeout_seconds: float,
) -> dict[str, Any]:
    stdout, _ = await asyncio.wait_for(process.communicate(), timeout=timeout_seconds)
    if process.returncode != 0:
        raise RuntimeError(f"{source_id} source Provider exited with code {process.returncode}")
    if len(stdout) > MAX_CHILD_OUTPUT_BYTES:
        raise ValueError("source Provider aggregate output exceeded its size cap")
    reports = []
    for line in stdout.splitlines():
        try:
            report = json.loads(line.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            continue
        if isinstance(report, Mapping) and report.get("event") == "scope-source-writer":
            reports.append(report)
    matches = [report for report in reports if report.get("source") == source_id]
    if len(matches) != 1 or matches[0].get("write_completed") is not True:
        raise RuntimeError(f"{source_id} source Provider did not confirm its scope update")
    return dict(matches[0])


async def _create_parent_world(client: Client, args: argparse.Namespace) -> tuple[str, dict[str, Any], int]:
    created = await client.call(
        "world.create",
        {
            "window": {
                "title": args.title,
                "width": 520,
                "height": 520,
                "always_on_top": True,
                "geometry_control": "human",
                "resizable": True,
            },
            "join_policy": "invite",
            "claim": True,
        },
    )
    world_id = str(created["world"]["id"])
    lease = created.get("lease")
    if not isinstance(lease, dict):
        raise RuntimeError("host did not issue the parent world lease")
    return world_id, lease, int(created["world"]["revision"])


async def _partition_source_scopes(
    client: Client,
    world_id: str,
    world_lease: dict[str, Any],
    expected_revision: int,
) -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
    replaced = await client.mutate(
        "scene.replace",
        world_id,
        world_lease,
        expected_revision=expected_revision,
        scene=scene(),
    )
    partition = await client.partition_scopes(
        world_id,
        world_lease,
        int(replaced["revision"]),
        [LIFECYCLE_SCOPE, *(SOURCE_SCOPES[source_id] for source_id in SOURCE_IDS)],
    )
    authority_lease = partition.get("authority_lease")
    if not isinstance(authority_lease, dict):
        raise RuntimeError("host did not issue parent authority after partition")
    grants = {
        grant["root_node_id"]: grant
        for grant in partition.get("scopes", [])
        if isinstance(grant, Mapping)
    }
    expected_roots = {
        LIFECYCLE_SCOPE["root_node_id"],
        *(SOURCE_SCOPES[source_id]["root_node_id"] for source_id in SOURCE_IDS),
    }
    if set(grants) != expected_roots:
        raise RuntimeError("host did not issue both independent source scopes")
    return authority_lease, grants


async def _start_source_workers(
    args: argparse.Namespace,
    world_id: str,
    grants: Mapping[str, Mapping[str, Any]],
    processes: dict[str, asyncio.subprocess.Process],
) -> None:
    for source_id in SOURCE_IDS:
        root_id = SOURCE_SCOPES[source_id]["root_node_id"]
        grant = grants[root_id]
        child_environment = os.environ.copy()
        child_environment["WINCRAFT_RUNTIME"] = args.runtime
        process = await asyncio.create_subprocess_exec(
            *worker_command(source_id, args.duration_seconds, args.ws_url),
            env=child_environment,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
            limit=MAX_CHILD_OUTPUT_BYTES,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        processes[source_id] = process
        if process.stdin is None:
            raise RuntimeError("source Provider bootstrap pipe was not created")
        bootstrap = json.dumps(
            {"world_id": world_id, "grant": dict(grant)},
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode("utf-8")
        if len(bootstrap) + 1 > MAX_BOOTSTRAP_BYTES:
            raise ValueError("scope bootstrap exceeds its local size cap")
        process.stdin.write(bootstrap + b"\n")
        await process.stdin.drain()
        process.stdin.close()
        await process.stdin.wait_closed()


async def _collect_source_reports(
    args: argparse.Namespace,
    processes: Mapping[str, asyncio.subprocess.Process],
) -> dict[str, dict[str, Any]]:
    timeout_seconds = args.duration_seconds + MAX_SOURCE_READ_SECONDS
    reports = await asyncio.gather(
        *(
            _read_worker_output(source_id, process, timeout_seconds)
            for source_id, process in processes.items()
        )
    )
    return dict(zip(processes, reports, strict=True))


def _verified_source_summary(
    processes: Mapping[str, asyncio.subprocess.Process],
    reports: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    if set(processes) != set(SOURCE_IDS) or set(reports) != set(SOURCE_IDS):
        raise RuntimeError("both source Providers must report a scoped write")
    if len({process.pid for process in processes.values()}) != len(SOURCE_IDS):
        raise RuntimeError("source writers were not separate operating-system processes")
    starts = [float(report["write_completed_at"]) for report in reports.values()]
    finishes = [float(report["writer_finished_at"]) for report in reports.values()]
    overlap = min(finishes) - max(starts)
    if overlap <= 0:
        raise RuntimeError("source write leases did not overlap")
    return {
        "event": "scoped-live-source-writers-verified",
        "independent_processes": True,
        "concurrent_write_lease_overlap_seconds": round(overlap, 2),
        "sources": {
            source_id: {
                key: report[key]
                for key in (
                    "source_health",
                    "source_data_health",
                    "source_freshness",
                    "source_age_seconds",
                    "record_count",
                    "status_counts",
                    "scope_revision",
                )
            }
            for source_id, report in reports.items()
        },
    }


def _validated_scope_status(
    value: object,
    *,
    world_id: str,
    scope_id: str,
    generation: int,
) -> str:
    if not isinstance(value, Mapping):
        raise RuntimeError("Host returned an invalid scope lifecycle response")
    if (
        value.get("world_id") != world_id
        or value.get("scope_id") != scope_id
        or value.get("requested_generation") != generation
    ):
        raise RuntimeError("Host scope lifecycle response does not match the requested scope")
    if any(field in value for field in ("data", "root", "writer", "writer_session_id")):
        raise RuntimeError("Host scope lifecycle response contains business data or writer identity")
    expected_fields = {
        "world_id",
        "scope_id",
        "requested_generation",
        "current_generation",
        "revision",
        "sequence",
        "status",
    }
    if set(value) != expected_fields:
        raise RuntimeError("Host scope lifecycle response contains unsupported fields")
    current_generation = value["current_generation"]
    revision = value["revision"]
    if (
        type(value["requested_generation"]) is not int
        or (current_generation is not None and (type(current_generation) is not int or current_generation < 1))
        or (revision is not None and (type(revision) is not int or revision < 0))
        or type(value["sequence"]) is not int
        or value["sequence"] < 0
    ):
        raise RuntimeError("Host returned invalid scope lifecycle metadata")
    status = value.get("status")
    if status not in {"online", "stale", "vacant", "revoked", "unknown"}:
        raise RuntimeError("Host returned an unknown scope lifecycle state")
    return str(status)


async def _wait_for_scope_statuses(
    client: Client,
    world_id: str,
    grants: Mapping[str, Mapping[str, Any]],
    expected_status: str,
    timeout_seconds: float,
) -> dict[str, str]:
    if expected_status not in {"online", "stale"}:
        raise ValueError("scope lifecycle probe only waits for online or stale")
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout_seconds
    pending = set(SOURCE_IDS)
    statuses: dict[str, str] = {}
    while pending:
        async def read_status(source_id: str) -> tuple[str, str]:
            root_id = SOURCE_SCOPES[source_id]["root_node_id"]
            grant = grants[root_id]
            status = await _read_scope_status(client, world_id, grant)
            return source_id, status

        observed = await asyncio.gather(*(read_status(source_id) for source_id in pending))
        for source_id, status in observed:
            if status == expected_status:
                statuses[source_id] = status
                pending.remove(source_id)
            elif status in {"revoked", "unknown"}:
                raise RuntimeError(f"{source_id} scope became {status} before {expected_status}")
            elif expected_status == "online" and status == "stale":
                raise RuntimeError(f"{source_id} scope disconnected before becoming online")
            elif expected_status == "stale" and status == "vacant":
                raise RuntimeError(f"{source_id} scope became vacant instead of stale")
        if pending:
            remaining = deadline - loop.time()
            if remaining <= 0:
                raise TimeoutError("source scope lifecycle state did not reach the expected value")
            await asyncio.sleep(min(SCOPE_STATUS_POLL_SECONDS, remaining))
    return statuses


async def _read_scope_status(
    client: Client,
    world_id: str,
    grant: Mapping[str, Any],
) -> str:
    scope_id = str(grant["scope_id"])
    generation = int(grant["generation"])
    value = await client.read_scope_status(world_id, scope_id, generation)
    return _validated_scope_status(
        value,
        world_id=world_id,
        scope_id=scope_id,
        generation=generation,
    )


async def _publish_lifecycle_status(
    client: Client,
    world_id: str,
    lease: Mapping[str, Any],
    expected_scope_revision: int,
    statuses: Mapping[str, str],
) -> int:
    updated = await client.replace_scope_data(
        world_id,
        dict(lease),
        expected_scope_revision,
        _lifecycle_data(statuses),
    )
    return int(updated["revision"])


async def run_host(args: argparse.Namespace) -> None:
    processes: dict[str, asyncio.subprocess.Process] = {}
    async with Client(
        args.runtime,
        "python.agent-board.scoped-live-host",
        args.ws_url,
        protocol_version=COMPONENT_LEASES_PREVIEW_PROTOCOL,
    ) as client:
        client.require_component_leases()
        client.require_scope_status()
        client.require_capabilities(components=("stack", "text", "badge", "metric"))
        world_id, world_lease, expected_revision = await _create_parent_world(client, args)
        cleanup_lease = world_lease
        try:
            cleanup_lease, grants = await _partition_source_scopes(
                client, world_id, world_lease, expected_revision
            )
            lifecycle_join = await client.join_scope(
                world_id,
                grants[LIFECYCLE_SCOPE["root_node_id"]],
                "write",
            )
            lifecycle_lease = lifecycle_join.get("lease")
            if not isinstance(lifecycle_lease, dict):
                raise RuntimeError("parent Provider did not receive its lifecycle scope writer lease")
            lifecycle_revision = int(lifecycle_join["snapshot"]["revision"])
            await _start_source_workers(args, world_id, grants, processes)
            writer_statuses = await _wait_for_scope_statuses(
                client,
                world_id,
                grants,
                "online",
                MAX_SOURCE_READ_SECONDS,
            )
            lifecycle_revision = await _publish_lifecycle_status(
                client,
                world_id,
                lifecycle_lease,
                lifecycle_revision,
                writer_statuses,
            )
            reports = await _collect_source_reports(args, processes)
            disconnected_statuses = await _wait_for_scope_statuses(
                client,
                world_id,
                grants,
                "stale",
                10,
            )
            lifecycle_revision = await _publish_lifecycle_status(
                client,
                world_id,
                lifecycle_lease,
                lifecycle_revision,
                disconnected_statuses,
            )
            current_parent = await client.call("world.snapshot", {"world_id": world_id})
            await client.patch_structure(
                world_id,
                dict(cleanup_lease),
                int(current_parent["revision"]),
                [{"op": "remove", "node_id": SOURCE_SCOPES["codex"]["root_node_id"]}],
            )
            revoked_statuses = {
                "codex": await _read_scope_status(
                    client,
                    world_id,
                    grants[SOURCE_SCOPES["codex"]["root_node_id"]],
                ),
                "claude-code": await _read_scope_status(
                    client,
                    world_id,
                    grants[SOURCE_SCOPES["claude-code"]["root_node_id"]],
                ),
            }
            if revoked_statuses != {"codex": "revoked", "claude-code": "stale"}:
                raise RuntimeError("source scope removal did not preserve revoked and sibling stale states")
            await _publish_lifecycle_status(
                client,
                world_id,
                lifecycle_lease,
                lifecycle_revision,
                revoked_statuses,
            )
            summary = _verified_source_summary(processes, reports)
            summary["scope_lifecycle"] = {
                source_id: {
                    "during_write": writer_statuses[source_id],
                    "after_disconnect": disconnected_statuses[source_id],
                    "after_revocation": revoked_statuses[source_id],
                }
                for source_id in SOURCE_IDS
            }
            print(json.dumps(summary, ensure_ascii=False, separators=(",", ":")), flush=True)
        finally:
            try:
                await _destroy_owned_world(client, world_id, cleanup_lease)
            finally:
                await _reap_workers(processes)


async def _wait_for_scope_end(client: Client, world_id: str, duration_seconds: float) -> bool:
    deadline = asyncio.get_running_loop().time() + duration_seconds
    while True:
        remaining = deadline - asyncio.get_running_loop().time()
        if remaining <= 0:
            return False
        try:
            event = await asyncio.wait_for(client.events.get(), timeout=remaining)
        except TimeoutError:
            return False
        if event.get("event") == "world.deleted" and event_world_id(event) == world_id:
            return True
        if event.get("event") in {"connection.error", "connection.closed", "provider.error"}:
            raise ConnectionError("scope Provider transport ended")


def _source_writer_report(
    snapshot: LiveSnapshot,
    source_id: str,
    scope_revision: int,
    writer_started_at: float,
    write_completed_at: float,
    writer_finished_at: float,
    world_deleted: bool,
) -> dict[str, Any]:
    summary = summarize_live_snapshot(snapshot)
    return {
        "event": "scope-source-writer",
        "source": source_id,
        "write_completed": True,
        "scope_revision": scope_revision,
        "writer_started_at": writer_started_at,
        "write_completed_at": write_completed_at,
        "writer_finished_at": writer_finished_at,
        "world_deleted": world_deleted,
        "source_health": snapshot.projection["source_health"].get(source_id, "unknown"),
        "source_data_health": snapshot.projection["source_data_health"].get(source_id, "unknown"),
        "source_freshness": snapshot.projection["source_freshness"].get(source_id, "unknown"),
        "source_age_seconds": snapshot.projection["source_age_seconds"].get(source_id),
        "record_count": len(snapshot.records_by_source.get(source_id, [])),
        "status_counts": summary["status_counts"].get(source_id, {}),
    }


async def run_worker(args: argparse.Namespace, raw_bootstrap: bytes) -> None:
    world_id, grant = _validate_worker_payload(raw_bootstrap, args.source)
    provider_name = f"{WORKER_NAME_PREFIX}.{args.source}"
    async with Client(
        args.runtime,
        provider_name,
        args.ws_url,
        protocol_version=COMPONENT_LEASES_PREVIEW_PROTOCOL,
    ) as client:
        client.require_component_leases()
        joined = await client.join_scope(world_id, grant, "write")
        lease = joined.get("lease")
        if not isinstance(lease, dict):
            raise RuntimeError("host did not grant this Provider a scope writer lease")
        writer_started_at = time.monotonic()
        snapshot = await asyncio.to_thread(
            load_live_snapshot,
            None,
            sequence=1,
            enabled_sources=(args.source,),
        )
        updated = await client.replace_scope_data(
            world_id,
            lease,
            int(joined["snapshot"]["revision"]),
            source_scope_data(snapshot, args.source),
        )
        write_completed_at = time.monotonic()
        world_deleted = await _wait_for_scope_end(client, world_id, args.duration_seconds)
        report = _source_writer_report(
            snapshot,
            args.source,
            int(updated["revision"]),
            writer_started_at,
            write_completed_at,
            time.monotonic(),
            world_deleted,
        )
        print(json.dumps(report, ensure_ascii=False, separators=(",", ":")), flush=True)


def _run_child(args: argparse.Namespace) -> None:
    try:
        raw = _read_worker_bootstrap()
        asyncio.run(run_worker(args, raw))
    except Exception as error:
        print(
            json.dumps(
                {
                    "event": "scope-source-worker-error",
                    "source": args.source,
                    "error_type": type(error).__name__,
                },
                ensure_ascii=False,
                separators=(",", ":"),
            ),
            flush=True,
        )
        raise SystemExit(1) from error


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    add_runtime_args(parser)
    parser.add_argument("--source-worker", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--source", choices=SOURCE_IDS, help=argparse.SUPPRESS)
    parser.add_argument("--duration-seconds", type=float, default=12)
    parser.add_argument("--title", default="Agent Activity · 双来源独立写入验收")
    args = parser.parse_args()
    require_runtime(parser, args)
    if not 2 <= args.duration_seconds <= 600:
        parser.error("--duration-seconds must be between 2 and 600")
    if args.source_worker and args.source is None:
        parser.error("internal source worker requires --source")
    if not args.source_worker and args.source is not None:
        parser.error("--source is reserved for the internal worker mode")
    return args


def main() -> None:
    args = _parse_args()
    if args.source_worker:
        _run_child(args)
        return
    try:
        asyncio.run(run_host(args))
    except RpcError as error:
        print(f"Scoped live source host request failed ({error.code}).", file=sys.stderr)
        raise SystemExit(1) from error
    except Exception as error:
        print(f"Scoped live source host failed ({type(error).__name__}).", file=sys.stderr)
        raise SystemExit(1) from error


if __name__ == "__main__":
    main()
