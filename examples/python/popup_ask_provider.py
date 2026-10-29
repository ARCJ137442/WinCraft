"""WinCraft transport for the installed Popup-Ask structured skill.

The local skill remains the authority for validation and result serialization.
This provider only renders its validated questions and returns its existing result
shape. It does not send HTML, JavaScript, or executable content to the host.
"""
from __future__ import annotations

import argparse
import asyncio
import contextlib
import ctypes
import importlib.util
import json
import os
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

from client import Client, add_runtime_args, event_world_id, require_runtime

DEFAULT_TIMEOUT_SECONDS = 1800
MAX_TIMEOUT_SECONDS = 86400
POPUP_MUTEX_NAME = r"Local\WinCraft.PopupAsk.v1"


class PopupInstanceBusyError(RuntimeError):
    def __init__(self) -> None:
        super().__init__(
            "A Popup-Ask window is already active. Open it from the WinCraft World "
            "Manager; no second window was created. / 已有 Popup-Ask 窗口在运行，"
            "请从 WinCraft 世界管理器找到它；本次没有创建第二个窗口。"
        )


class PopupInstanceGate:
    """Enforce one active Popup-Ask world per interactive user session."""

    def __init__(self, *, mutex_name: str | None = None, lock_path: Path | None = None):
        self.mutex_name = mutex_name or POPUP_MUTEX_NAME
        self.lock_path = lock_path or default_position_store().with_name("active.lock")
        self._handle: int | None = None
        self._kernel32: Any = None
        self._stream: Any = None

    def __enter__(self) -> "PopupInstanceGate":
        if os.name == "nt":
            from ctypes import wintypes

            kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
            create_mutex = kernel32.CreateMutexW
            create_mutex.argtypes = [wintypes.LPVOID, wintypes.BOOL, wintypes.LPCWSTR]
            create_mutex.restype = wintypes.HANDLE
            close_handle = kernel32.CloseHandle
            close_handle.argtypes = [wintypes.HANDLE]
            close_handle.restype = wintypes.BOOL
            release_mutex = kernel32.ReleaseMutex
            release_mutex.argtypes = [wintypes.HANDLE]
            release_mutex.restype = wintypes.BOOL

            ctypes.set_last_error(0)
            handle = create_mutex(None, True, self.mutex_name)
            error = ctypes.get_last_error()
            if not handle:
                raise OSError(error, "Could not claim the Popup-Ask instance slot")
            if error == 183:  # ERROR_ALREADY_EXISTS
                close_handle(handle)
                raise PopupInstanceBusyError()
            self._handle = handle
            self._kernel32 = kernel32
            return self

        import fcntl

        self.lock_path.parent.mkdir(parents=True, exist_ok=True)
        stream = self.lock_path.open("a+b")
        try:
            fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            stream.close()
            raise PopupInstanceBusyError() from error
        self._stream = stream
        return self

    def __exit__(self, *_: Any) -> None:
        if self._handle is not None:
            self._kernel32.ReleaseMutex(self._handle)
            self._kernel32.CloseHandle(self._handle)
            self._handle = None
            return
        if self._stream is not None:
            import fcntl

            fcntl.flock(self._stream.fileno(), fcntl.LOCK_UN)
            self._stream.close()
            self._stream = None

TEXT = {
    "zh-CN": {
        "title": "结构化提问",
        "status": "选择选项并提交。选择 Other 时，请补充备注。",
        "notes": "备注",
        "notes_hint": "说明原因、约束或补充信息；每题最多 8192 个字符。",
        "save_notes": "保存备注",
        "submit": "提交回答",
        "confirm_submit": "再次确认提交",
        "cancel": "取消",
        "selected": "已选",
        "choose": "选择",
        "recommended": "推荐",
        "unanswered": "尚有未回答问题：{names}。检查后再次确认提交。",
        "other_notes": "选择 Other 时需要填写备注。",
        "timeout": "等待回答超时；未收到可确认的最终答案。",
        "unknown": "连接在最终结果确认前中断；结果未知，请勿自动重放。",
    },
    "en-US": {
        "title": "Structured question",
        "status": "Choose options and submit. Add notes when selecting Other.",
        "notes": "Notes",
        "notes_hint": "Add reasons, constraints, or context; up to 8,192 characters per question.",
        "save_notes": "Save notes",
        "submit": "Submit answers",
        "confirm_submit": "Confirm submit",
        "cancel": "Cancel",
        "selected": "Selected",
        "choose": "Choose",
        "recommended": "Recommended",
        "unanswered": "Unanswered questions: {names}. Review them and confirm again.",
        "other_notes": "Add notes when selecting Other.",
        "timeout": "The response wait timed out; no final answer was confirmed.",
        "unknown": "Connection ended before the final result was confirmed; outcome is unknown. Do not replay automatically.",
    },
}


def load_skill(script_path: Path) -> Any:
    if not script_path.is_file():
        raise FileNotFoundError("Popup-Ask script was not found at the explicitly supplied path")
    spec = importlib.util.spec_from_file_location("wincraft_popup_ask_skill", script_path)
    if spec is None or spec.loader is None:
        raise RuntimeError("Popup-Ask script could not be loaded")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def validate_with_skill(module: Any, request_path: Path) -> tuple[Any, dict[str, Any]]:
    """Run the installed skill's validate-only path without opening its Tk window."""
    argv = ["structured", "--file", str(request_path), "--validate-only", "--json"]
    args = module.build_parser().parse_args(argv)
    request = module.load_structured_payload(args)
    validated = module.build_validated_payload(request)
    if validated.get("status") != "validated":
        raise ValueError("Popup-Ask validate-only did not return a validated request")
    return request, validated


def default_position_store() -> Path:
    local_app_data = os.environ.get("LOCALAPPDATA")
    base = Path(local_app_data) if local_app_data else Path.home() / ".local" / "share"
    return base / "dev.wincraft.prototype" / "PopupAsk" / "window.json"


def load_window_memory(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    if not isinstance(value, dict):
        return {}
    result: dict[str, Any] = {}
    position = value.get("position")
    if isinstance(position, dict) and type(position.get("x")) is int and type(position.get("y")) is int:
        if abs(position["x"]) <= 100_000 and abs(position["y"]) <= 100_000:
            result["position"] = {"x": position["x"], "y": position["y"]}
    width, height = value.get("width"), value.get("height")
    if isinstance(width, (int, float)) and 160 <= width <= 2400:
        result["width"] = float(width)
    if isinstance(height, (int, float)) and 80 <= height <= 1800:
        result["height"] = float(height)
    return result


def save_window_memory(path: Path, window: dict[str, Any]) -> bool:
    position = window.get("position")
    if not isinstance(position, dict) or type(position.get("x")) is not int or type(position.get("y")) is not int:
        return False
    if abs(position["x"]) > 100_000 or abs(position["y"]) > 100_000:
        return False
    width, height = window.get("width"), window.get("height")
    if not isinstance(width, (int, float)) or not 160 <= width <= 2400:
        return False
    if not isinstance(height, (int, float)) or not 80 <= height <= 1800:
        return False
    payload = {
        "position": {"x": position["x"], "y": position["y"]},
        "width": float(width),
        "height": float(height),
        "updated_at": int(time.time()),
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_name: str | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=path.parent,
            prefix=f"{path.name}.", suffix=".tmp", delete=False,
        ) as temp:
            temp_name = temp.name
            json.dump(payload, temp, ensure_ascii=False, separators=(",", ":"))
            temp.flush()
            os.fsync(temp.fileno())
        Path(temp_name).replace(path)
    except OSError:
        if temp_name:
            with contextlib.suppress(OSError):
                Path(temp_name).unlink()
        return False
    return True


def build_window_spec(title: str, remembered: dict[str, Any]) -> dict[str, Any]:
    """Create a new human-controlled window using geometry only, never an old world id."""
    window: dict[str, Any] = {
        "title": title[:100],
        "width": remembered.get("width", 620.0),
        "height": remembered.get("height", 520.0),
    }
    position = remembered.get("position")
    if isinstance(position, dict) and type(position.get("x")) is int and type(position.get("y")) is int:
        window["position"] = {"x": position["x"], "y": position["y"]}
    return window


def choose_locale(validated: dict[str, Any], requested: str) -> str:
    if requested != "auto":
        return requested
    visible = [validated.get("title", "")]
    for question in validated.get("questions", []):
        visible.extend((question.get("header", ""), question.get("question", "")))
        for option in question.get("options", []):
            visible.extend((option.get("label", ""), option.get("description", ""), option.get("preview", "")))
    if any("\u4e00" <= char <= "\u9fff" for value in visible for char in str(value)):
        return "zh-CN"
    return "en-US"


def component(component_id: str, kind: str, props: dict[str, Any] | None = None,
              children: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    return {"id": component_id, "kind": kind, "props": props or {}, "children": children or []}


def build_scene(module: Any, request: Any, states: dict[str, Any], locale: str,
                status: str, confirm_submit: bool) -> dict[str, Any]:
    strings = TEXT[locale]
    questions = []
    total = len(request.questions)
    for question_index, question in enumerate(request.questions):
        state = states[question.id]
        selected = set(state.selected_labels)
        option_nodes = []
        for option_index, option in enumerate(question.options):
            is_selected = option.label in selected
            marker = ("☑" if is_selected else "☐") if question.multi_select else ("●" if is_selected else "○")
            action = f"option:{question_index}:{option_index}"
            label = f"{strings['selected'] if is_selected else strings['choose']} · {marker} {option.label}"
            if option.is_recommended:
                label += f" · {strings['recommended']}"
            option_nodes.append(component(
                f"option-{question_index}-{option_index}", "stack", {"gap": 4}, [
                    component(f"choice-{question_index}-{option_index}", "button", {
                        "label": label,
                        "action": action,
                        "tone": "accent" if is_selected else "normal",
                        "selection_group": f"question-{question_index}",
                        "selection_mode": "multiple" if question.multi_select else "single",
                        "pressed": is_selected,
                    }),
                    component(f"description-{question_index}-{option_index}", "text", {
                        "text": option.description,
                        "size": "small",
                    }),
                ]
            ))
        preview = module.resolve_preview_content(question, state.selected_labels)
        question_children = [
            component(f"header-{question_index}", "text", {
                "text": f"{question_index + 1}/{total} · {question.header}",
                "size": "heading",
            }),
            component(f"question-{question_index}", "text", {"text": question.question}),
            component(f"options-{question_index}", "stack", {"gap": 8}, option_nodes),
            component(f"preview-{question_index}", "text", {"text": preview, "tone": "muted"}),
            component(f"notes-{question_index}", "textarea", {
                "label": f"{strings['notes']} · {question.header}",
                "value": state.notes,
                "action": f"notes:{question_index}",
                "placeholder": strings["notes_hint"],
                "submit_label": strings["save_notes"],
                "shortcut": "ctrl_enter",
                "shortcut_action": f"submit:{question_index}",
            }),
            component(f"divider-{question_index}", "divider"),
        ]
        questions.append(component(f"question-group-{question_index}", "stack", {"gap": 8}, question_children))
    submit_label = strings["confirm_submit"] if confirm_submit else strings["submit"]
    root_children = [
        component("popup-title", "text", {"text": request.title, "size": "title"}),
        component("popup-status", "text", {"text": status or strings["status"], "tone": "warning" if status else "muted"}),
        *questions,
        component("popup-actions", "row", {"gap": 8}, [
            component("popup-submit", "button", {"label": submit_label, "action": "submit", "tone": "accent"}),
            component("popup-cancel", "button", {
                "label": strings["cancel"],
                "action": "cancel.button",
                "shortcut": "escape",
                "shortcut_action": "cancel.escape",
            }),
        ]),
    ]
    return {"root": component("root", "stack", {"gap": 12}, root_children), "data": {}}


def request_result(module: Any, request: Any, states: dict[str, Any]) -> dict[str, Any]:
    return module.build_structured_success_payload(request, states)


def _cancelled_payload_for_action(module: Any, action: str) -> dict[str, Any] | None:
    '''将宿主取消动作映射到上游技能的原始取消原因
    - 🎯区分取消按钮、Escape和普通操作失败
    '''
    if action == 'cancel.button':
        return module.cancelled_payload(module.CANCEL_REASON_CANCEL_BUTTON)
    if action == 'cancel.escape':
        return module.cancelled_payload(module.CANCEL_REASON_ESCAPE_KEY)
    return None


def _terminal_for_host_message(
    module: Any,
    message: dict[str, Any],
    world_id: str,
    strings: dict[str, str],
) -> tuple[dict[str, Any], bool] | None:
    '''只将当前世界的关闭或连接故障映射为请求终态
    - 🎯关闭是取消；连接中断保留为未知结果
    '''
    name = message.get('event')
    if name == 'world.deleted':
        if event_world_id(message) != world_id:
            return None
        return module.cancelled_payload(module.CANCEL_REASON_WINDOW_CLOSED), True
    if name in ('connection.error', 'connection.closed', 'provider.error'):
        return module.error_payload(strings['unknown']), False
    return None


def _unanswered(request: Any, states: dict[str, Any]) -> list[Any]:
    return [question for question in request.questions if not states[question.id].answered()]


def _missing_other_notes(request: Any, states: dict[str, Any]) -> list[Any]:
    missing = []
    for question in request.questions:
        selected = set(states[question.id].selected_labels)
        other_selected = any(option.is_other and option.label in selected for option in question.options)
        if other_selected and not states[question.id].notes.strip():
            missing.append(question)
    return missing


async def _run_with_slot(args: argparse.Namespace) -> dict[str, Any]:
    module = load_skill(Path(args.popup_ask_script))
    request, validated = validate_with_skill(module, Path(args.request_file))
    locale = choose_locale(validated, args.locale)
    strings = TEXT[locale]
    states = {question.id: module.QuestionState() for question in request.questions}
    pending_unanswered: list[str] = []
    status = ""
    world_id: str | None = None
    lease: dict[str, Any] | None = None
    deleted = False
    terminal: dict[str, Any] | None = None
    position_store = Path(args.position_store) if args.position_store else default_position_store()
    remembered_window = load_window_memory(position_store) if args.remember_position else {}
    async with Client(args.runtime, "python.popup-ask", args.ws_url) as client:
        client.require_capabilities(
            components=("textarea",),
            keyboard_shortcuts=("escape", "ctrl_enter"),
            button_features=("selection_groups",),
        )
        created = await client.call("world.create", {
            "window": build_window_spec(request.title, remembered_window),
            "join_policy": "invite",
            "claim": True,
        })
        world_id, lease = created["world"]["id"], created.get("lease")
        if not isinstance(lease, dict):
            raise RuntimeError("Host did not issue a writer lease for the temporary question world")
        if getattr(args, "verbose", False):
            print("Popup-Ask temporary world created.", file=sys.stderr)
        try:
            await client.mutate("scene.replace", world_id, lease, scene=build_scene(
                module, request, states, locale, status, False))
            loop = asyncio.get_running_loop()
            deadline = loop.time() + args.timeout_seconds
            while terminal is None:
                remaining = deadline - loop.time()
                if remaining <= 0:
                    terminal = module.error_payload(strings["timeout"])
                    break
                try:
                    message = await asyncio.wait_for(client.events.get(), timeout=remaining)
                except asyncio.TimeoutError:
                    terminal = module.error_payload(strings["timeout"])
                    break
                name = message.get("event")
                host_terminal = _terminal_for_host_message(module, message, world_id, strings)
                if host_terminal is not None:
                    terminal, deleted = host_terminal
                    break
                if name != "interaction":
                    continue
                event = message.get("data", {})
                if event.get("world_id") != world_id:
                    continue
                ok, error = True, None
                action = event.get("action")
                try:
                    if action.startswith("option:"):
                        _, q_raw, o_raw = action.split(":", 2)
                        q_index, o_index = int(q_raw), int(o_raw)
                        question = request.questions[q_index]
                        option = question.options[o_index]
                        state = states[question.id]
                        if question.multi_select:
                            if option.label in state.selected_labels:
                                state.selected_labels.remove(option.label)
                            else:
                                selected = set(state.selected_labels)
                                selected.add(option.label)
                                state.selected_labels = [candidate.label for candidate in question.options if candidate.label in selected]
                        else:
                            state.selected_labels = [] if state.selected_labels == [option.label] else [option.label]
                        pending_unanswered = []
                        status = ""
                    elif action.startswith("notes:"):
                        q_index = int(action.split(":", 1)[1])
                        question = request.questions[q_index]
                        value = event.get("value")
                        if not isinstance(value, str):
                            raise ValueError("Notes action did not contain text")
                        states[question.id].notes = value
                        pending_unanswered = []
                        status = ""
                    elif action in ("cancel.button", "cancel.escape"):
                        terminal = _cancelled_payload_for_action(module, action)
                    elif action == "submit" or action.startswith("submit:"):
                        if action.startswith("submit:"):
                            q_index = int(action.split(":", 1)[1])
                            question = request.questions[q_index]
                            value = event.get("value")
                            if not isinstance(value, str):
                                raise ValueError("Ctrl+Enter submit did not contain the focused notes text")
                            states[question.id].notes = value
                        missing_notes = _missing_other_notes(request, states)
                        if missing_notes:
                            status = strings["other_notes"]
                            pending_unanswered = []
                            ok, error = False, status
                        else:
                            unanswered = _unanswered(request, states)
                            unanswered_ids = [question.id for question in unanswered]
                            if unanswered_ids and unanswered_ids != pending_unanswered:
                                pending_unanswered = unanswered_ids
                                names = " / ".join(question.header for question in unanswered)
                                status = strings["unanswered"].format(names=names)
                                ok, error = False, status
                            else:
                                terminal = request_result(module, request, states)
                    else:
                        raise ValueError("Unknown Popup-Ask action")
                    if terminal is None:
                        await client.mutate("scene.replace", world_id, lease, scene=build_scene(
                            module, request, states, locale, status, bool(pending_unanswered)))
                except Exception as exc:
                    ok, error = False, str(exc)
                    status = error
                    with contextlib.suppress(Exception):
                        await client.mutate("scene.replace", world_id, lease, scene=build_scene(
                            module, request, states, locale, status, bool(pending_unanswered)))
                try:
                    await client.call("action.result", {
                        "world_id": world_id,
                        "lease": lease,
                        "event_id": event["id"],
                        "ok": ok,
                        "message": error,
                    })
                except Exception:
                    if terminal and terminal.get("status") == "success":
                        terminal = module.error_payload(strings["unknown"])
                    elif terminal is None:
                        terminal = module.error_payload(strings["unknown"])
                if terminal and terminal.get("status") == "success":
                    # The click is acknowledged before the temporary world is removed.
                    if args.remember_position:
                        try:
                            final_snapshot = await client.call("world.snapshot", {"world_id": world_id})
                            if not save_window_memory(position_store, final_snapshot["window"]):
                                print("Popup-Ask answer completed; current native position was unavailable, so no position preference was saved.", file=sys.stderr)
                        except Exception:
                            print("Popup-Ask answer completed; the position preference could not be read.", file=sys.stderr)
                    try:
                        await client.call("world.destroy", {"world_id": world_id, "lease": lease})
                        deleted = True
                        if getattr(args, "verbose", False):
                            print("Popup-Ask temporary world cleanup confirmed.", file=sys.stderr)
                    except Exception:
                        terminal = module.error_payload(strings["unknown"])
                    break
        finally:
            if world_id and lease and not deleted:
                cleanup = asyncio.create_task(client.call(
                    "world.destroy", {"world_id": world_id, "lease": lease}
                ))
                try:
                    await asyncio.shield(cleanup)
                    if getattr(args, "verbose", False):
                        print("Popup-Ask temporary world cleanup confirmed.", file=sys.stderr)
                except asyncio.CancelledError:
                    # A normal Ctrl+C cancels the request task; keep the cleanup RPC
                    # alive until the host confirms deletion, then propagate cancel.
                    with contextlib.suppress(Exception):
                        await asyncio.shield(cleanup)
                    raise
                except Exception:
                    print("Popup-Ask temporary world cleanup could not be confirmed.", file=sys.stderr)
    return terminal or module.error_payload(strings["unknown"])


async def run(args: argparse.Namespace) -> dict[str, Any]:
    """Run one request while holding the per-session popup quota."""
    mutex_name = getattr(args, "instance_mutex_name", None)
    lock_path = getattr(args, "instance_lock_path", None)
    with PopupInstanceGate(
        mutex_name=mutex_name,
        lock_path=Path(lock_path) if lock_path else None,
    ):
        return await _run_with_slot(args)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    add_runtime_args(parser)
    parser.add_argument("--popup-ask-script", required=True,
                        help="Explicit path to the installed popup_ask.py; no profile scan is performed")
    parser.add_argument("--request-file", required=True, help="UTF-8 JSON file using the Popup-Ask structured request shape")
    parser.add_argument("--locale", choices=("auto", "zh-CN", "en-US"), default="auto")
    parser.add_argument("--timeout-seconds", type=int, default=DEFAULT_TIMEOUT_SECONDS)
    parser.add_argument("--remember-position", action=argparse.BooleanOptionalAction, default=True,
                        help="Reuse the last native position and size in a local preference file")
    parser.add_argument("--position-store", help="Optional preference-file path; contains only window position and size")
    parser.add_argument("--json", action="store_true", help="Return the existing Popup-Ask structured JSON result")
    parser.add_argument("--verbose", action="store_true", help="Log sanitized world creation and cleanup confirmation")
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    require_runtime(parser, args)
    if not 1 <= args.timeout_seconds <= MAX_TIMEOUT_SECONDS:
        parser.error(f"--timeout-seconds must be in 1..{MAX_TIMEOUT_SECONDS}")
    try:
        result = asyncio.run(run(args))
        if args.json:
            print(module_json(result), flush=True)
        else:
            script = load_skill(Path(args.popup_ask_script))
            print(script.render_payload_for_stdout(result), flush=True)
        if result.get("status") == "error":
            raise SystemExit(1)
        if result.get("status") == "error":
            raise SystemExit(1)
    except KeyboardInterrupt:
        # The caller may have been cancelled; do not fabricate an answer or replay it.
        raise
    except Exception as exc:
        if isinstance(exc, (FileNotFoundError, PermissionError)):
            message = "The selected Popup-Ask script or request file could not be opened."
        else:
            message = str(exc) or type(exc).__name__
        try:
            script = load_skill(Path(args.popup_ask_script))
            result = script.error_payload(message)
        except Exception:
            result = {"status": "error", "error": message, "timestamp": int(time.time())}
        if args.json:
            print(module_json(result), flush=True)
        else:
            try:
                print(script.render_payload_for_stdout(result), flush=True)
            except Exception:
                print(f"Popup-Ask error: {message}", flush=True)
        raise SystemExit(1)


def module_json(value: Any) -> str:
    import json
    return json.dumps(value, ensure_ascii=False)


if __name__ == "__main__":
    main()
