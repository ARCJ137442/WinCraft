"""Read-only ExoMind active-timeblock projection for a WinCraft floating world.

The ExoMind RT remains authoritative. This provider calls only
GET /timeblocks/active. Its buttons change only the local WinCraft display or
hide the WinCraft world; they never mutate ExoMind tasks or time blocks.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import math
import os
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlparse
from urllib.request import Request, urlopen

from client import Client, add_runtime_args, require_runtime

MAX_RESPONSE_BYTES = 128 * 1024
DEFAULT_POLL_INTERVAL = 1.0
MAX_TEXT_LENGTH = 180
# 🤖ExoMind source fallback sizes; the source normally measures its visible surface.
RUNNING_FULL_SIZE: dict[str, int] = {'width': 390, 'height': 192}
'''外心运行态完整卡片的来源回退尺寸'''
RUNNING_COMPACT_SIZE: dict[str, int] = {'width': 328, 'height': 160}
'''外心运行态 mini-peek 的来源 CSS 宽度与本地布局高度估值'''
RUNNING_MINI_SIZE: dict[str, int] = {'width': 248, 'height': 120}
'''外心 mini 窗口的来源 fallback；不代表测量后的 pill 尺寸'''
DisplayMode = Literal['full', 'compact', 'mini']
'''WinCraft 本地投影窗口的三档显示模式'''
DISPLAY_MODE_ORDER: tuple[DisplayMode, ...] = ('full', 'compact', 'mini')
'''显示模式循环顺序；此状态只保存在 provider 内存中'''
DISPLAY_MODE_ACTION_LABELS: dict[DisplayMode, str] = {
    'full': '收起',
    'compact': '迷你',
    'mini': '展开',
}
'''各模式中本地显示切换按钮的动作名称'''
DISPLAY_NEXT_ACTION: str = 'wincraft.display.next'
'''在 full、compact 与 mini 之间本地切换'''
DISPLAY_HIDE_ACTION: str = 'wincraft.display.hide'
'''仅隐藏 WinCraft 投影窗口，保留世界与租约'''
LOCAL_DISPLAY_ACTIONS: tuple[str, str] = (
    DISPLAY_NEXT_ACTION,
    DISPLAY_HIDE_ACTION,
)
'''工作台接受的两个 WinCraft 本地显示动作'''
REQUIRED_COMPONENTS = ("stack", "row", "text", "badge", "metric", "button")
REQUIRED_WINDOW_PROPERTIES = (
    "title_bar_visible",
    "background_drag_enabled",
    "text_selectable",
    "surface_opacity",
    "visible",
    "always_on_top",
    "resizable",
    "skip_taskbar",
    "decorations",
    "geometry_control",
    "position_control",
)
REQUIRED_SCENE_FEATURES = ("theme_tokens",)
TRANSITION_PHASES = {
    "start": "running",
    "resume": "running",
    "pause": "paused",
    "feedback_start": "feedback",
    "feedback_submit": "completed",
    "end": "completed",
}


@dataclass(frozen=True)
class ActiveBlockRead:
    """Bounded result of the one allowed ExoMind read endpoint."""

    state: Literal["active", "empty", "not_found_ambiguous"]
    block: dict[str, Any] | None = None


@dataclass(frozen=True)
class WorkbenchProjection:
    """Display-only values derived from fields returned by ExoMind RT."""

    source_state: str
    title: str
    status: str
    clock_label: str
    clock: str
    detail: str
    tone: str


def _finite_number(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    number = float(value)
    return number if math.isfinite(number) else None


def _bounded_text(value: Any, fallback: str = "") -> str:
    if not isinstance(value, str):
        return fallback
    return value.strip()[:MAX_TEXT_LENGTH] or fallback


def _transitions(block: dict[str, Any]) -> list[dict[str, Any]]:
    value = block.get("transitions")
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def derive_phase(block: dict[str, Any]) -> str:
    transitions = _transitions(block)
    if transitions:
        return TRANSITION_PHASES.get(transitions[-1].get("type"), "idle")

    phase = block.get("phase")
    if block.get("feedbackSubmittedAt") is not None or phase == "feedback_submitted":
        return "completed"
    if (
        block.get("actionEndedAt") is not None
        or block.get("feedbackStartedAt") is not None
        or phase in ("feedback_in_progress", "action_ended")
    ):
        return "feedback"
    if phase == "paused" or block.get("paused") is True:
        return "paused"
    if phase == "running":
        return "running"
    return "idle"


def _last_transition_time(block: dict[str, Any]) -> float | None:
    transitions = _transitions(block)
    if transitions:
        return _finite_number(transitions[-1].get("at"))
    return _finite_number(block.get("lastTransitionAt"))


def _effective_now(block: dict[str, Any], phase: str, now_ms: float) -> float:
    last_transition = _last_transition_time(block)
    if phase in ("feedback", "completed"):
        for key in ("actionEndedAt", "feedbackStartedAt", "feedbackSubmittedAt"):
            timestamp = _finite_number(block.get(key))
            if timestamp is not None:
                return timestamp
        return last_transition if last_transition is not None else now_ms
    if phase == "paused":
        paused_at = _finite_number(block.get("pausedAt"))
        if paused_at is not None:
            return paused_at
        return last_transition if last_transition is not None else now_ms
    return now_ms


def _accumulated_pause_ms(block: dict[str, Any], now_ms: float) -> float:
    transitions = _transitions(block)
    if transitions:
        total = 0.0
        pause_start: float | None = None
        for transition in transitions:
            at = _finite_number(transition.get("at"))
            if at is None:
                continue
            if transition.get("type") == "pause":
                pause_start = at
            elif transition.get("type") == "resume" and pause_start is not None:
                total += at - pause_start
                pause_start = None
        if pause_start is not None:
            total += now_ms - pause_start
        return max(0.0, total)
    return max(0.0, _finite_number(block.get("pauseAccumulatedMs")) or 0.0)


def _work_duration_ms(block: dict[str, Any], phase: str, effective_now: float) -> float:
    transitions = _transitions(block)
    if transitions:
        total = 0.0
        run_start: float | None = None
        for transition in transitions:
            at = _finite_number(transition.get("at"))
            if at is None:
                continue
            transition_type = transition.get("type")
            if transition_type in ("start", "resume"):
                run_start = at
            elif transition_type in ("pause", "feedback_start", "end") and run_start is not None:
                total += at - run_start
                run_start = None
        if run_start is not None:
            total += effective_now - run_start
        return max(0.0, total)

    accumulated = _finite_number(block.get("accumulatedRunMs"))
    if accumulated is not None:
        resumed_at = _finite_number(block.get("lastResumedAt"))
        running_slice = max(0.0, effective_now - (resumed_at if resumed_at is not None else effective_now)) \
            if phase == "running" else 0.0
        return max(0.0, accumulated + running_slice)

    start_time = _finite_number(block.get("startTime"))
    if start_time is None:
        return max(0.0, _finite_number(block.get("elapsed")) or 0.0)
    pause_total = _accumulated_pause_ms(block, effective_now)
    paused_slice = 0.0
    if phase == "paused":
        paused_at = _finite_number(block.get("pausedAt"))
        if paused_at is not None:
            paused_slice = max(0.0, effective_now - paused_at)
    return max(0.0, effective_now - start_time - pause_total - paused_slice)


def format_clock(milliseconds: float) -> str:
    total_seconds = max(0, math.floor(milliseconds / 1000))
    hours, remainder = divmod(total_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    if hours > 0:
        return f"{hours}:{minutes:02d}:{seconds:02d}"
    return f"{minutes:02d}:{seconds:02d}"


def _clock_time(timestamp_ms: float) -> str:
    return datetime.fromtimestamp(timestamp_ms / 1000).strftime("%H:%M")


def project_active_block(block: dict[str, Any], now_ms: float) -> WorkbenchProjection:
    """Mirror ExoMind's display-only clock math from the active-block response."""
    phase = derive_phase(block)
    title = _bounded_text(block.get("name"), "未命名时间块")
    status = {
        "running": "进行中",
        "paused": "已暂停",
        "feedback": "待反馈",
        "completed": "已完成",
    }.get(phase, "状态待确认")
    tone = "warning" if phase == "paused" else "success" if phase == "running" else "muted"
    effective_now = _effective_now(block, phase, now_ms)
    work_ms = _work_duration_ms(block, phase, effective_now)

    if block.get("mode") == "countdown":
        target_minutes = _finite_number(block.get("targetMinutes"))
        if target_minutes is None or target_minutes <= 0:
            target_minutes = 25.0
        expected_ms = target_minutes * 60_000
        remaining_ms = max(0.0, expected_ms - work_ms)
        overrun_ms = max(0.0, work_ms - expected_ms)
        clock = f"+{format_clock(overrun_ms)}" if overrun_ms > 0 else format_clock(remaining_ms)
        if phase in ("feedback", "completed"):
            detail = "等待反馈"
        else:
            expected_end = _clock_time(now_ms + remaining_ms)
            detail = (
                f"暂停中，若恢复预计 {expected_end} 结束"
                if phase == "paused"
                else f"预计 {expected_end} 结束"
            )
        return WorkbenchProjection("ok", title, status, "专注倒计时", clock, detail, tone)

    return WorkbenchProjection("ok", title, status, "累计专注时长", format_clock(work_ms), "", tone)


def project_read_result(read: ActiveBlockRead, now_ms: float) -> WorkbenchProjection:
    if read.state == "active" and isinstance(read.block, dict):
        return project_active_block(read.block, now_ms)
    if read.state == "not_found_ambiguous":
        return WorkbenchProjection(
            "not_found_ambiguous",
            "",
            "状态待核对",
            "专注计时",
            "--:--",
            "HTTP 404：无活动时间块，或端点需要核对",
            "warning",
        )
    return WorkbenchProjection("empty", "", "暂无活动时间块", "专注计时", "--:--", "", "muted")


def _node(
    node_id: str,
    kind: str,
    props: dict[str, Any],
    children: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    return {"id": node_id, "kind": kind, "props": props, "children": children or []}


def build_scene(data: dict[str, Any], display_mode: DisplayMode) -> dict[str, Any]:
    '''为本地显示档位组装 WinCraft 通用组件场景
    - 🤖仅使用已声明的组件与本地交互，不传执行代码或外心写动作
    - 📌内容状态由投影数据表达，窗口展示模式由本地循环表达
    '''
    status = _node('status', 'badge', {'text': {'$path': '/status'}, 'tone': 'accent'})
    title = _node('title', 'text', {'text': {'$path': '/title'}, 'size': 'heading'})
    clock = _node(
        'clock',
        'metric',
        {
            'label': {'$path': '/clock_label'},
            'value': {'$path': '/clock'},
            'caption': {'$path': '/detail'},
        },
    )
    controls = _node(
        'local-controls',
        'row',
        {'gap': 8},
        [
            _node(
                'display-next',
                'button',
                {
                    'label': {'$path': '/display_action_label'},
                    'action': DISPLAY_NEXT_ACTION,
                    'tone': 'accent',
                },
            ),
            _node(
                'display-hide',
                'button',
                {'label': '隐藏', 'action': DISPLAY_HIDE_ACTION},
            ),
        ],
    )
    source_status = _node(
        'source-status',
        'text',
        {'text': {'$path': '/source_status'}, 'size': 'small', 'tone': 'warning'},
    )
    read_only_note = _node(
        'read-only-note',
        'text',
        {'text': {'$path': '/read_only_note'}, 'size': 'small', 'tone': 'muted'},
    )

    children: list[dict[str, Any]]
    if data['content_state'] == 'idle':
        # 🤖空闲内容不伪造时间值或开始按钮；ExoMind 仍由用户在原程序操作。
        idle_guidance = _node(
            'idle-guidance',
            'text',
            {'text': {'$path': '/idle_guidance'}, 'size': 'small', 'tone': 'muted'},
        )
        if display_mode == 'mini':
            children = [
                _node(
                    'mini-idle',
                    'row',
                    {'gap': 8, 'align': 'center'},
                    [
                        _node('mini-idle-copy', 'stack', {'gap': 4}, [status, idle_guidance]),
                        _node('mini-controls', 'stack', {'gap': 4}, controls['children']),
                    ],
                ),
            ]
        else:
            children = [
                _node(
                    'idle-heading',
                    'row',
                    {'gap': 8, 'align': 'center'},
                    [status, controls],
                ),
                idle_guidance,
                read_only_note,
            ]
    elif display_mode == 'mini':
        # 🤖迷你 HUD 保留时钟、身份和本地展开/隐藏入口。
        mini_identity = _node(
            'mini-identity',
            'stack',
            {'gap': 2},
            [
                _node(
                    'mini-clock',
                    'text',
                    {'text': {'$path': '/clock'}, 'size': 'title', 'tone': 'accent'},
                ),
                _node(
                    'mini-status',
                    'text',
                    {'text': {'$path': '/mini_status'}, 'size': 'small'},
                ),
                _node(
                    'mini-title',
                    'text',
                    {'text': {'$path': '/title'}, 'size': 'small'},
                ),
            ],
        )
        mini_hud = _node(
            'mini-hud',
            'row',
            {'gap': 8, 'align': 'center'},
            [
                mini_identity,
                _node('mini-controls', 'stack', {'gap': 4}, controls['children']),
            ],
        )
        children = [mini_hud]
        if data['source_status']:
            children.insert(0, source_status)
    elif display_mode == 'compact':
        # 🤖compact 对应来源 mini-peek 的较宽信息层；外心操作用只读说明取代。
        children = [
            _node(
                'compact-heading',
                'row',
                {'gap': 8, 'align': 'center'},
                [status, controls],
            ),
            title,
            clock,
            read_only_note,
        ]
        if data['source_status']:
            children.insert(-1, source_status)
    else:
        # 🤖完整卡片突出时间块身份与计时，窗口动作固定在标题行。
        children = [
            _node(
                'full-heading',
                'row',
                {'gap': 8, 'align': 'center'},
                [status, controls],
            ),
            title,
            clock,
            read_only_note,
        ]
        if data['source_status']:
            children.insert(-1, source_status)

    return {
        "theme": {
            'background': '#1C1917',
            'foreground': '#FAFAF9',
            'accent': '#F7A98B',
            'font_scale': 1,
            'radius_px': 24,
            'spacing_px': 12,
        },
        'root': _node('root', 'stack', {'gap': 10}, children),
        'data': data,
    }


def build_display_data(
    projection: WorkbenchProjection,
    display_mode: DisplayMode,
) -> dict[str, Any]:
    '''生成不暴露来源标识的有界显示数据
    - 🤖内容状态与窗口显示模式分开表达，空闲不冒充活动时间块
    - 📌正常读取不常驻来源状态文字，异常状态仍需明显披露
    '''
    source_status = {
        "ok": "外心 RT 实时只读",
        "empty": "当前无活动时间块",
        "not_found_ambiguous": "HTTP 404：无活动块或端点需核对",
        "stale": "来源暂时不可达 · 显示最后一次读取",
        "error": "外心读取失败",
        "connecting": "正在读取外心",
    }.get(projection.source_state, "来源状态未知")
    return {
        "content_state": "idle" if projection.source_state == "empty" else "projection",
        "source_status": source_status if projection.source_state not in ("ok", "empty") else "",
        "status": projection.status,
        "title": projection.title,
        "mini_status": f"{projection.status} · 只读",
        "clock_label": projection.clock_label,
        "clock": projection.clock,
        "detail": projection.detail,
        "read_only_note": "只读投影；暂停/继续/结束请在外心原程序中操作",
        "idle_guidance": "在外心原程序开始计时后，这里会显示只读投影。",
        "display_mode": display_mode,
        "display_action_label": DISPLAY_MODE_ACTION_LABELS[display_mode],
    }


def build_window_spec() -> dict[str, Any]:
    """Match ExoMind's running-full fallback size without owning position."""
    return {
        "title": "外心 · 只读专注工作台",
        **window_size_patch("full"),
        "always_on_top": True,
        "visible": True,
        "resizable": False,
        "title_bar_visible": False,
        "background_drag_enabled": True,
        "text_selectable": False,
        "decorations": False,
        "skip_taskbar": True,
        "surface_opacity": 0.8,
        "geometry_control": "provider",
        "position_control": "human",
    }


def window_size_patch(display_mode: DisplayMode) -> dict[str, int]:
    '''返回指定 WinCraft 展示档位的回退尺寸
    - 🤖full/mini 使用外心来源 fallback；mini 不是测量后的稳态尺寸
    - 📌compact 高度是本地布局估值，三个尺寸都不代表 DOM 测量结果
    '''
    size = {
        'full': RUNNING_FULL_SIZE,
        'compact': RUNNING_COMPACT_SIZE,
        'mini': RUNNING_MINI_SIZE,
    }[display_mode]
    return {'width': size['width'], 'height': size['height']}


def next_display_mode(display_mode: DisplayMode) -> DisplayMode:
    '''返回模式循环中的下一档
    - 🤖窗口动作仅改变本地投影，不触及 ExoMind 状态
    '''
    current_index = DISPLAY_MODE_ORDER.index(display_mode)  # 🤖模式来自本模块的封闭状态表
    next_index = (current_index + 1) % len(DISPLAY_MODE_ORDER)  # 🤖迷你态继续切换回完整态
    return DISPLAY_MODE_ORDER[next_index]


def read_headers() -> dict[str, str]:
    try:
        headers = json.loads(os.environ.get("EXOMIND_HEADERS_JSON", "{}"))
    except json.JSONDecodeError as error:
        raise ValueError("EXOMIND_HEADERS_JSON must be valid JSON") from error
    if not isinstance(headers, dict) or not all(isinstance(key, str) and isinstance(value, str) for key, value in headers.items()):
        raise ValueError("EXOMIND_HEADERS_JSON must be a string-to-string map")
    return headers


def validate_rt_base(base: str) -> str:
    parsed = urlparse(base)
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        raise ValueError("Explicit ExoMind HTTP(S) base URL required")
    if parsed.path not in ("", "/") or parsed.query or parsed.fragment:
        raise ValueError("ExoMind RT base must be a root URL without path, query, or fragment")
    if parsed.scheme == "http" and parsed.hostname not in ("127.0.0.1", "localhost", "::1"):
        raise ValueError("Use HTTPS or an SSH tunnel for remote ExoMind RT")
    return base.rstrip("/")


def fetch_active_timeblock(
    base: str,
    profile: str,
    headers: dict[str, str],
    timeout: float = 4.0,
) -> ActiveBlockRead:
    if not profile.strip():
        raise ValueError("Explicit ExoMind profile required; anonymous scope is forbidden")
    url = f"{base.rstrip('/')}/timeblocks/active?{urlencode({'user_id': profile})}"
    request = Request(url, headers={"Accept": "application/json", **headers}, method="GET")
    try:
        with urlopen(request, timeout=timeout) as response:
            body = response.read(MAX_RESPONSE_BYTES + 1)
            if len(body) > MAX_RESPONSE_BYTES:
                raise ValueError("ExoMind active-timeblock response exceeds 128 KiB")
            payload = json.loads(body)
    except HTTPError as error:
        if error.code == 404:
            return ActiveBlockRead("not_found_ambiguous")
        raise RuntimeError(f"ExoMind active-timeblock GET returned HTTP {error.code}") from error
    except URLError as error:
        raise RuntimeError("ExoMind active-timeblock GET failed") from error

    if payload is None:
        return ActiveBlockRead("empty")
    if not isinstance(payload, dict):
        raise ValueError("Unexpected ExoMind active-timeblock shape; no schema guessing")
    return ActiveBlockRead("active", payload)


def error_projection(previous: WorkbenchProjection | None, error: Exception) -> WorkbenchProjection:
    error_type = type(error).__name__
    if previous and previous.source_state == "ok":
        return WorkbenchProjection(
            "stale",
            previous.title,
            previous.status,
            previous.clock_label,
            previous.clock,
            f"来源读取失败（{error_type}）；显示最后一次读取",
            "warning",
        )
    return WorkbenchProjection(
        "error",
        "",
        "来源读取失败",
        "专注计时",
        "--:--",
        f"ExoMind GET 失败（{error_type}）",
        "danger",
    )


async def _acknowledge(
    client: Client,
    world_id: str,
    lease: dict[str, Any],
    event: dict[str, Any],
    ok: bool,
    message: str | None = None,
) -> None:
    await client.call("action.result", {
        "world_id": world_id,
        "lease": lease,
        "event_id": event["id"],
        "ok": ok,
        "message": message,
    })


async def _cleanup_local_world(
    client: Client,
    world_id: str,
    lease: dict[str, Any],
) -> bool:
    try:
        await client.call("world.destroy", {"world_id": world_id, "lease": lease})
        return True
    except Exception:
        # A timeout leaves the WinCraft local cleanup outcome unknown; do not retry blindly.
        return False


async def run(args: argparse.Namespace) -> None:
    headers = read_headers()
    base = validate_rt_base(args.exomind)
    if not 0.5 <= args.interval <= 30:
        raise ValueError("--interval must be between 0.5 and 30 seconds")

    async with Client(args.runtime, "exomind.now-workbench-readonly", args.ws_url) as client:
        client.require_capabilities(
            components=REQUIRED_COMPONENTS,
            window_properties=REQUIRED_WINDOW_PROPERTIES,
            scene_features=REQUIRED_SCENE_FEATURES,
        )
        created = await client.call("world.create", {
            "window": build_window_spec(),
            "join_policy": "invite",
        })
        world_id = created["world"]["id"]
        lease = created["lease"]
        if not isinstance(lease, dict):
            raise RuntimeError("WinCraft host did not grant a write lease for the local projection world")

        display_mode: DisplayMode = 'full'  # 🤖窗口展示档位只在此 provider 会话的内存中保存
        latest_projection: WorkbenchProjection | None = None
        initial = WorkbenchProjection(
            "connecting",
            "",
            "连接中",
            "专注计时",
            "--:--",
            "只读读取当前活动时间块",
            "muted",
        )
        display_data = build_display_data(initial, display_mode)
        scene = build_scene(display_data, display_mode)
        deleted = False
        destroy_attempted = False
        try:
            await client.mutate("scene.replace", world_id, lease, scene=scene)
            while True:
                try:
                    read = await asyncio.to_thread(fetch_active_timeblock, base, args.profile, headers)
                    projection = project_read_result(read, time.time() * 1000)
                    latest_projection = projection
                except Exception as error:
                    projection = error_projection(latest_projection, error)

                next_data = build_display_data(projection, display_mode)
                if next_data != display_data:
                    display_data = next_data
                    await client.mutate("data.replace", world_id, lease, data=display_data)

                try:
                    message = await asyncio.wait_for(client.events.get(), timeout=args.interval)
                except asyncio.TimeoutError:
                    continue
                if message.get("event") in ("connection.error", "connection.closed", "provider.error"):
                    raise ConnectionError("WinCraft provider session disconnected")
                if message.get("event") == "world.deleted":
                    deleted = True
                    return
                if message.get("event") != "interaction":
                    continue
                event = message.get("data")
                if not isinstance(event, dict) or event.get("world_id") != world_id:
                    continue

                ok = True
                error_message = None
                scene_updated = False
                try:
                    action = event.get("action")
                    if action == DISPLAY_NEXT_ACTION:
                        next_mode = next_display_mode(display_mode)
                        next_data = build_display_data(latest_projection or initial, next_mode)
                        await client.mutate(
                            'scene.replace',
                            world_id,
                            lease,
                            scene=build_scene(next_data, next_mode),
                        )
                        scene_updated = True
                        display_mode = next_mode
                        display_data = next_data
                        await client.mutate(
                            'window.configure',
                            world_id,
                            lease,
                            patch=window_size_patch(display_mode),
                        )
                    elif action == DISPLAY_HIDE_ACTION:
                        await client.mutate(
                            'window.configure',
                            world_id,
                            lease,
                            patch={'visible': False},
                        )
                    else:
                        ok = False
                        error_message = "This prototype accepts only local WinCraft display actions."
                except Exception as error:
                    ok = False
                    if scene_updated:
                        error_message = (
                            "Partial local display update: scene changed but window size was not confirmed "
                            f"({type(error).__name__}); inspect the WinCraft manager."
                        )
                    else:
                        error_message = f"Local display action failed ({type(error).__name__})."
                await _acknowledge(client, world_id, lease, event, ok, error_message)
        finally:
            if not deleted and not destroy_attempted:
                destroy_attempted = True
                await _cleanup_local_world(client, world_id, lease)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    add_runtime_args(parser)
    parser.add_argument(
        "--exomind",
        default=os.environ.get("EXOMIND_RT_BASE"),
        help="Verified ExoMind RT base URL",
    )
    parser.add_argument(
        "--profile",
        default=os.environ.get("EXOMIND_PROFILE_ID"),
        help="Explicit ExoMind user_id/profile scope",
    )
    parser.add_argument(
        "--interval",
        type=float,
        default=DEFAULT_POLL_INTERVAL,
        help="Read-only active-block polling interval",
    )
    args = parser.parse_args()
    require_runtime(parser, args)
    if not args.exomind:
        parser.error("--exomind or EXOMIND_RT_BASE is required; RT port is never guessed")
    if not args.profile:
        parser.error("--profile or EXOMIND_PROFILE_ID is required; anonymous scope is forbidden")
    try:
        asyncio.run(run(args))
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
