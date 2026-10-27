import asyncio
import contextlib
import io
import json
import subprocess
import sys
import tempfile
import time
import unittest
import uuid
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "examples" / "python"))
import popup_ask_provider as popup  # noqa: E402


class PopupProviderTests(unittest.TestCase):
    def setUp(self):
        self.options = [
            SimpleNamespace(label="保守", description="先兼容现有流程。", preview="保留原入口。",
                            recommended=True, is_recommended=True, is_other=False),
            SimpleNamespace(label="Other", description="补充真实意图。", preview="",
                            recommended=False, is_recommended=False, is_other=True),
        ]
        self.question = SimpleNamespace(
            id="approach", header="路径", question="先做哪条路径？",
            options=self.options, multi_select=False,
        )
        self.request = SimpleNamespace(title="Popup 测试", questions=[self.question])
        self.state = SimpleNamespace(selected_labels=["保守"], notes="第一行\n第二行", answered=lambda: True)
        self.module = SimpleNamespace(
            resolve_preview_content=lambda question, selected: "保留原入口。" if selected == ["保守"] else "",
        )

    def run_provider(self, messages, *, timeout_seconds=0.5, action_ack_error=False,
                     destroy_error=False, remember_position=False, position_store=None,
                     observed_window=None, verbose=False):
        calls = []
        state = SimpleNamespace(selected_labels=["保守"], notes="", answered=lambda: True)
        skill = SimpleNamespace(
            CANCEL_REASON_CANCEL_BUTTON='cancel_button',
            CANCEL_REASON_ESCAPE_KEY='escape_key',
            CANCEL_REASON_WINDOW_CLOSED='window_closed',
            QuestionState=lambda: state,
            resolve_preview_content=lambda question, selected: '保留原入口。',
            build_structured_success_payload=lambda request, states: {
                'status': 'success', 'answer': 'fixture-only result',
            },
            cancelled_payload=lambda reason: {'status': 'cancelled', 'reason': reason},
            error_payload=lambda message: {'status': 'error', 'message': message},
        )

        class FakeClient:
            def __init__(self, runtime, name, ws_url=None):
                self.events = asyncio.Queue()
                self.delayed_events = []
                self.observed_window = observed_window or {
                    'position': {'x': -120, 'y': 80}, 'width': 620.0, 'height': 540.0,
                }
                for message in messages:
                    if isinstance(message, tuple) and len(message) == 2:
                        delay, delayed_message = message
                        self.delayed_events.append(
                            asyncio.create_task(self.publish_after(delay, delayed_message))
                        )
                    else:
                        self.events.put_nowait(message)

            async def publish_after(self, delay, message):
                await asyncio.sleep(delay)
                await self.events.put(message)

            async def __aenter__(self):
                return self

            async def __aexit__(self, *_):
                for task in self.delayed_events:
                    if not task.done():
                        task.cancel()
                if self.delayed_events:
                    await asyncio.gather(*self.delayed_events, return_exceptions=True)
                return None

            def require_capabilities(self, **capabilities):
                calls.append(('require_capabilities', None))

            async def mutate(self, method, world_id, lease, **payload):
                calls.append((method, world_id))
                return {'revision': 1}

            async def call(self, method, params):
                calls.append((method, params.get('world_id')))
                if method == 'world.create':
                    return {'world': {'id': 'current-world'}, 'lease': {'epoch': 1}}
                if method == 'action.result' and action_ack_error:
                    raise ConnectionError('SYNTHETIC_PRIVATE_BODY_FOR_TEST')
                if method == 'world.destroy' and destroy_error:
                    raise ConnectionError('fixture host unavailable during cleanup')
                if method == 'world.snapshot':
                    return {'revision': 1, 'window': self.observed_window}
                return {'revision': 1}

        args = SimpleNamespace(
            runtime='fixture-runtime', ws_url=None, popup_ask_script='fixture-skill',
            request_file='fixture-request', locale='zh-CN', timeout_seconds=timeout_seconds,
            remember_position=remember_position, position_store=position_store,
            verbose=verbose,
            instance_mutex_name=f'Local\\WinCraft.PopupAsk.Test.{uuid.uuid4().hex}',
            instance_lock_path=Path(tempfile.gettempdir()) / f'wincraft-popup-test-{uuid.uuid4().hex}.lock',
        )
        with patch.object(popup, 'Client', FakeClient), \
                patch.object(popup, 'load_skill', return_value=skill), \
                patch.object(popup, 'validate_with_skill', return_value=(self.request, {})):
            result = asyncio.run(popup.run(args))
        return result, calls

    def test_popup_instance_gate_rejects_a_second_window_and_releases_after_exit(self):
        with tempfile.TemporaryDirectory(prefix="wincraft-popup-gate-") as temporary:
            name=f'Local\\WinCraft.PopupAsk.Test.{uuid.uuid4().hex}'
            lock_path=Path(temporary)/'active.lock'
            first=popup.PopupInstanceGate(mutex_name=name,lock_path=lock_path)
            second=popup.PopupInstanceGate(mutex_name=name,lock_path=lock_path)
            with first:
                with self.assertRaises(popup.PopupInstanceBusyError):
                    with second:
                        self.fail('a second Popup-Ask slot was granted')
            with second:
                pass

    def test_popup_instance_gate_is_shared_across_provider_processes(self):
        with tempfile.TemporaryDirectory(prefix="wincraft-popup-process-gate-") as temporary:
            name=f'Local\\WinCraft.PopupAsk.Test.{uuid.uuid4().hex}'
            lock_path=Path(temporary)/'active.lock'
            script = '''
import sys
from pathlib import Path
sys.path.insert(0, str(Path.cwd() / 'examples' / 'python'))
from popup_ask_provider import PopupInstanceGate, PopupInstanceBusyError
name, path = sys.argv[1], Path(sys.argv[2])
try:
    with PopupInstanceGate(mutex_name=name, lock_path=path):
        print('acquired')
except PopupInstanceBusyError:
    print('busy')
'''
            with popup.PopupInstanceGate(mutex_name=name,lock_path=lock_path):
                child=subprocess.run(
                    [sys.executable,'-c',script,name,str(lock_path)],
                    capture_output=True,text=True,timeout=10,check=False,
                )
                self.assertEqual(child.returncode,0,child.stderr)
                self.assertEqual(child.stdout.strip(),'busy')

    def test_busy_popup_returns_before_client_or_world_creation(self):
        with tempfile.TemporaryDirectory(prefix="wincraft-popup-busy-") as temporary:
            name=f'Local\\WinCraft.PopupAsk.Test.{uuid.uuid4().hex}'
            lock_path=Path(temporary)/'active.lock'
            args=SimpleNamespace(instance_mutex_name=name,instance_lock_path=lock_path)
            with popup.PopupInstanceGate(mutex_name=name,lock_path=lock_path):
                with patch.object(popup,'Client',side_effect=AssertionError('Client must not be opened')):
                    with self.assertRaises(popup.PopupInstanceBusyError):
                        asyncio.run(popup.run(args))

    def test_main_returns_a_clear_busy_error_without_success_payload(self):
        skill=SimpleNamespace(
            error_payload=lambda message: {'status':'error','message':message},
            render_payload_for_stdout=lambda value: json.dumps(value,ensure_ascii=False),
        )
        output=io.StringIO()
        argv=[
            'popup_ask_provider.py','--runtime','fixture-runtime',
            '--popup-ask-script','fixture-skill','--request-file','fixture-request','--json',
        ]
        with patch.object(sys,'argv',argv), \
                patch.object(popup,'require_runtime'), \
                patch.object(popup,'run',side_effect=popup.PopupInstanceBusyError()), \
                patch.object(popup,'load_skill',return_value=skill), \
                contextlib.redirect_stdout(output):
            with self.assertRaises(SystemExit) as exit_error:
                popup.main()
        self.assertEqual(exit_error.exception.code,1)
        result=json.loads(output.getvalue())
        self.assertEqual(result['status'],'error')
        self.assertIn('no second window was created',result['message'])

    def test_main_returns_nonzero_for_run_timeout_error(self):
        skill=SimpleNamespace(
            error_payload=lambda message: {'status':'error','message':message},
            render_payload_for_stdout=lambda value: json.dumps(value,ensure_ascii=False),
        )
        output=io.StringIO()
        async def timeout_result(_args):
            return {'status':'error','message':'timeout'}
        argv=[
            'popup_ask_provider.py','--runtime','fixture-runtime',
            '--popup-ask-script','fixture-skill','--request-file','fixture-request','--json',
        ]
        with patch.object(sys,'argv',argv), \
                patch.object(popup,'require_runtime'), \
                patch.object(popup,'run',side_effect=timeout_result), \
                patch.object(popup,'load_skill',return_value=skill), \
                contextlib.redirect_stdout(output):
            with self.assertRaises(SystemExit) as exit_error:
                popup.main()
        self.assertEqual(exit_error.exception.code,1)
        self.assertEqual(json.loads(output.getvalue())['status'],'error')

    def test_scene_uses_shared_components_and_preserves_multiline_notes(self):
        scene = popup.build_scene(self.module, self.request, {"approach": self.state}, "zh-CN", "", False)
        children = scene["root"]["children"]
        self.assertEqual(children[0]["kind"], "text")
        self.assertIn("保留原入口。", str(scene))
        notes = next(node for node in children[2]["children"] if node["kind"] == "textarea")
        self.assertEqual(notes["props"]["value"], "第一行\n第二行")
        escape = children[-1]["children"][1]["props"]
        self.assertEqual(escape["action"], "cancel.button")
        self.assertEqual(escape["shortcut_action"], "cancel.escape")
        notes_control = next(node for node in children[2]["children"] if node["kind"] == "textarea")["props"]
        self.assertEqual(notes_control["shortcut"], "ctrl_enter")
        self.assertEqual(notes_control["shortcut_action"], "submit:0")
        flattened = str(scene)
        self.assertNotIn("<script", flattened)
        self.assertNotIn("javascript:", flattened)

    def test_cancel_button_and_escape_preserve_distinct_skill_reasons(self):
        module = SimpleNamespace(
            CANCEL_REASON_CANCEL_BUTTON='cancel_button',
            CANCEL_REASON_ESCAPE_KEY='escape_key',
            cancelled_payload=lambda reason: {'status': 'cancelled', 'reason': reason},
        )
        self.assertEqual(
            popup._cancelled_payload_for_action(module, 'cancel.button'),
            {'status': 'cancelled', 'reason': 'cancel_button'},
        )
        self.assertEqual(
            popup._cancelled_payload_for_action(module, 'cancel.escape'),
            {'status': 'cancelled', 'reason': 'escape_key'},
        )
        self.assertIsNone(popup._cancelled_payload_for_action(module, 'submit'))

    def test_host_terminal_messages_are_scoped_to_this_world(self):
        module = SimpleNamespace(
            CANCEL_REASON_WINDOW_CLOSED='window_closed',
            cancelled_payload=lambda reason: {'status': 'cancelled', 'reason': reason},
            error_payload=lambda message: {'status': 'error', 'message': message},
        )
        self.assertEqual(
            popup._terminal_for_host_message(
                module,
                {'event': 'world.deleted', 'data': {'world_id': 'current'}},
                'current',
                {'unknown': 'outcome unknown'},
            ),
            ({'status': 'cancelled', 'reason': 'window_closed'}, True),
        )
        self.assertIsNone(
            popup._terminal_for_host_message(
                module,
                {'event': 'world.deleted', 'data': {'world_id': 'another'}},
                'current',
                {'unknown': 'outcome unknown'},
            )
        )
        for event_name in ('connection.error', 'connection.closed', 'provider.error'):
            self.assertEqual(
                popup._terminal_for_host_message(
                    module,
                    {'event': event_name},
                    'current',
                    {'unknown': 'outcome unknown'},
                ),
                ({'status': 'error', 'message': 'outcome unknown'}, False),
            )

    def test_run_acknowledges_cancel_before_destroying_only_its_world(self):
        event = {
            'event': 'interaction',
            'data': {'id': 'event-1', 'world_id': 'current-world', 'action': 'cancel.button'},
        }
        result, calls = self.run_provider([event])
        self.assertEqual(result, {'status': 'cancelled', 'reason': 'cancel_button'})
        self.assertLess(calls.index(('action.result', 'current-world')), calls.index(('world.destroy', 'current-world')))

    def test_success_acknowledges_once_then_destroys_and_saves_only_observed_geometry(self):
        submit={
            'event':'interaction',
            'data':{'id':'event-success','world_id':'current-world','action':'submit'},
        }
        with tempfile.TemporaryDirectory(prefix='wincraft-popup-success-') as temporary:
            preference=Path(temporary)/'window.json'
            stderr=io.StringIO()
            with contextlib.redirect_stderr(stderr):
                result,calls=self.run_provider(
                    [submit,dict(submit,data={**submit['data'],'id':'duplicate-event'})],
                    remember_position=True,
                    position_store=preference,
                    observed_window={'position':{'x':-480,'y':140},'width':710.0,'height':490.0},
                    verbose=True,
                )
            self.assertEqual(result['status'],'success')
            self.assertEqual(sum(call[0]=='action.result' for call in calls),1)
            self.assertEqual(sum(call[0]=='world.destroy' for call in calls),1)
            self.assertLess(calls.index(('action.result','current-world')),calls.index(('world.snapshot','current-world')))
            self.assertLess(calls.index(('world.snapshot','current-world')),calls.index(('world.destroy','current-world')))
            self.assertIn('Popup-Ask temporary world cleanup confirmed.',stderr.getvalue())
            stored=json.loads(preference.read_text(encoding='utf-8'))
            self.assertEqual(stored['position'],{'x':-480,'y':140})
            self.assertEqual((stored['width'],stored['height']),(710.0,490.0))
            self.assertLessEqual(set(stored),{'position','width','height','updated_at'})

    def test_option_action_ack_does_not_end_human_request(self):
        events = [
            {
                'event': 'interaction',
                'data': {
                    'id': 'event-option',
                    'world_id': 'current-world',
                    'action': 'option:0:0',
                },
            },
            {
                'event': 'interaction',
                'data': {
                    'id': 'event-cancel',
                    'world_id': 'current-world',
                    'action': 'cancel.button',
                },
            },
        ]

        result, calls = self.run_provider(events)

        self.assertEqual(result, {'status': 'cancelled', 'reason': 'cancel_button'})
        acknowledgements = [call for call in calls if call[0] == 'action.result']
        self.assertEqual(len(acknowledgements), 2)
        self.assertIn(('world.destroy', 'current-world'), calls)

    def test_human_wait_can_exceed_ten_second_action_ack_window(self):
        event={
            'event':'interaction',
            'data':{'id':'late-submit','world_id':'current-world','action':'submit'},
        }
        started=time.monotonic()
        result,calls=self.run_provider([(10.2,event)],timeout_seconds=20)
        elapsed=time.monotonic()-started
        self.assertGreaterEqual(elapsed,10.0)
        self.assertEqual(result['status'],'success')
        self.assertIn(('action.result','current-world'),calls)
        self.assertIn(('world.destroy','current-world'),calls)

    def test_run_window_close_does_not_destroy_already_deleted_world(self):
        event = {'event': 'world.deleted', 'data': {'world_id': 'current-world'}}
        result, calls = self.run_provider([event])
        self.assertEqual(result, {'status': 'cancelled', 'reason': 'window_closed'})
        self.assertNotIn(('world.destroy', 'current-world'), calls)

    def test_run_connection_loss_reports_unknown_even_if_cleanup_fails(self):
        event = {'event': 'connection.closed'}
        with contextlib.redirect_stderr(io.StringIO()):
            result, calls = self.run_provider([event], destroy_error=True)
        self.assertEqual(result, {'status': 'error', 'message': popup.TEXT['zh-CN']['unknown']})
        self.assertIn(('world.destroy', 'current-world'), calls)

    def test_run_timeout_is_not_reported_as_success_and_cleans_world(self):
        result, calls = self.run_provider([], timeout_seconds=0.001)
        self.assertEqual(result, {'status': 'error', 'message': popup.TEXT['zh-CN']['timeout']})
        self.assertIn(('world.destroy', 'current-world'), calls)

    def test_lost_action_ack_converts_success_to_unknown_and_cleans_world(self):
        event = {
            'event': 'interaction',
            'data': {'id': 'event-2', 'world_id': 'current-world', 'action': 'submit'},
        }
        result, calls = self.run_provider([event], action_ack_error=True)
        self.assertEqual(result, {'status': 'error', 'message': popup.TEXT['zh-CN']['unknown']})
        self.assertNotIn('SYNTHETIC_PRIVATE_BODY_FOR_TEST', repr(result))
        self.assertIn(('world.destroy', 'current-world'), calls)

    def test_single_select_renders_selected_and_unselected_states(self):
        scene = popup.build_scene(self.module, self.request, {"approach": self.state}, "zh-CN", "", False)
        options = scene["root"]["children"][2]["children"][2]["children"]
        labels = [group["children"][0]["props"]["label"] for group in options]
        self.assertTrue(labels[0].startswith("已选 · ●"))
        self.assertIn("推荐", labels[0])
        self.assertTrue(labels[1].startswith("选择 · ○"))
        for group in options:
            props = group["children"][0]["props"]
            self.assertEqual(props["selection_group"], "question-0")
            self.assertEqual(props["selection_mode"], "single")

    def test_locale_uses_question_language_without_rewriting_question_text(self):
        validated = {"title": "Question", "questions": [{"header": "Plan", "question": "Which?", "options": []}]}
        self.assertEqual(popup.choose_locale(validated, "auto"), "en-US")
        validated["questions"][0]["question"] = "选哪个？"
        self.assertEqual(popup.choose_locale(validated, "auto"), "zh-CN")
        self.assertEqual(popup.choose_locale(validated, "en-US"), "en-US")

    def test_unanswered_and_other_notes_are_separate_gates(self):
        state = SimpleNamespace(selected_labels=[], notes="", answered=lambda: False)
        self.assertEqual(popup._unanswered(self.request, {"approach": state}), [self.question])
        other_state = SimpleNamespace(selected_labels=["Other"], notes="", answered=lambda: True)
        self.assertEqual(popup._missing_other_notes(self.request, {"approach": other_state}), [self.question])
        other_state.notes = "补充"
        self.assertEqual(popup._missing_other_notes(self.request, {"approach": other_state}), [])

    def test_position_preference_contains_only_bounded_geometry(self):
        with tempfile.TemporaryDirectory(prefix="wincraft-popup-position-") as temporary:
            path = Path(temporary) / "window.json"
            window = {"position": {"x": -320, "y": 140}, "width": 620.0, "height": 540.0}
            self.assertTrue(popup.save_window_memory(path, window))
            self.assertEqual(popup.load_window_memory(path), window)
            self.assertTrue(set(json.loads(path.read_text(encoding="utf-8"))) <= {
                "position", "width", "height", "updated_at"
            })

    def test_position_preference_rejects_out_of_bounds_geometry(self):
        with tempfile.TemporaryDirectory(prefix="wincraft-popup-position-") as temporary:
            path = Path(temporary) / "window.json"
            self.assertFalse(popup.save_window_memory(path, {
                "position": {"x": 999_999, "y": 0}, "width": 620, "height": 540,
            }))
            self.assertFalse(path.exists())

    def test_reopen_uses_only_saved_geometry_and_creates_a_new_window_spec(self):
        window = popup.build_window_spec("Next question", {
            "position": {"x": -240, "y": 80}, "width": 640.0, "height": 520.0,
            "world_id": "previous-world-must-not-be-reused",
        })
        self.assertEqual(window, {
            "title": "Next question", "position": {"x": -240, "y": 80},
            "width": 640.0, "height": 520.0,
        })
        self.assertNotIn("world_id", window)
        self.assertEqual(popup.build_window_spec("Fresh", {}), {
            "title": "Fresh", "width": 620.0, "height": 520.0,
        })


if __name__ == "__main__":
    unittest.main()
