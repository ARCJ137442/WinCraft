import asyncio
import os
import time
import unittest
from argparse import Namespace
from unittest.mock import patch

from examples.integrations.model_quota.configure_model_quota import (  # noqa: E402
    build_provider_command,
    build_provider_environment,
)
from examples.integrations.model_quota.provider import (  # noqa: E402
    apply_source_configuration,
    wait_for_world_or_timeout,
)


class ModelQuotaLauncherTests(unittest.TestCase):
    def test_source_choices_become_flags_and_credentials_stay_out_of_arguments(self):
        sources = {
            "codex_rollout": True,
            "codex_live": False,
            "deepseek": True,
            "deepseek_key": "deepseek-test-key",
            "minimax": False,
            "minimax_key": "minimax-test-key",
        }
        command = build_provider_command("C:/runtime.json", sources)
        self.assertIn("--codex-rollout-quota", command)
        self.assertIn("--deepseek-quota", command)
        self.assertNotIn("--minimax-quota", command)
        self.assertNotIn("deepseek-test-key", command)
        environment = build_provider_environment({"MINIMAX_API_KEY": "old"}, sources)
        self.assertEqual(environment["DEEPSEEK_API_KEY"], "deepseek-test-key")
        self.assertNotIn("MINIMAX_API_KEY", environment)

    def test_runtime_descriptor_path_is_passed_without_reading_its_contents(self):
        command = build_provider_command("C:/private/runtime.json", {})
        runtime_index = command.index("--runtime")
        self.assertEqual(command[runtime_index + 1], "C:/private/runtime.json")
        self.assertNotIn("token", command)

    def test_source_configuration_updates_memory_only_and_removes_unchecked_keys(self):
        args = Namespace(
            codex_rollout_quota=False,
            codex_quota=False,
            deepseek_quota=False,
            minimax_quota=True,
        )
        with patch.dict(os.environ, {"MINIMAX_API_KEY": "old-key"}, clear=False):
            apply_source_configuration(
                args,
                {
                    "codex_rollout": True,
                    "codex_live": False,
                    "deepseek": True,
                    "deepseek_key": "new-key",
                    "minimax": False,
                    "minimax_key": "old-key",
                },
            )
            self.assertTrue(args.codex_rollout_quota)
            self.assertFalse(args.codex_quota)
            self.assertTrue(args.deepseek_quota)
            self.assertFalse(args.minimax_quota)
            self.assertEqual(os.environ["DEEPSEEK_API_KEY"], "new-key")
            self.assertNotIn("MINIMAX_API_KEY", os.environ)

    def test_source_settings_action_is_acknowledged_before_slow_dialog_finishes(self):
        async def exercise():
            class FakeClient:
                def __init__(self):
                    self.events = asyncio.Queue()
                    self.calls = []

                async def call(self, method, params):
                    self.calls.append((method, params, time.monotonic()))

            args = Namespace(
                codex_rollout_quota=False,
                codex_quota=False,
                deepseek_quota=False,
                minimax_quota=False,
                codex_home=None,
                source_config_changed=asyncio.Event(),
                source_config_open=False,
                source_config_error=None,
                source_config_task=None,
            )
            client = FakeClient()
            await client.events.put({
                "event": "interaction",
                "data": {
                    "id": "synthetic-action",
                    "world_id": "synthetic-world",
                    "action": "quota.sources.configure",
                },
            })

            def slow_dialog(current, *, focus=None):
                time.sleep(0.3)
                return {
                    "codex_rollout": True,
                    "codex_live": False,
                    "deepseek": False,
                    "minimax": False,
                    "deepseek_key": "",
                    "minimax_key": "",
                }

            with patch(
                "examples.integrations.model_quota.provider.show_source_configuration_dialog",
                side_effect=slow_dialog,
            ):
                started = time.monotonic()
                result = await wait_for_world_or_timeout(
                    client,
                    "synthetic-world",
                    0.1,
                    args,
                    {"synthetic": True},
                )
                self.assertEqual(result, "timeout")
                self.assertEqual(client.calls[0][0], "action.result")
                self.assertLess(client.calls[0][2] - started, 0.1)
                await args.source_config_task
                self.assertTrue(args.codex_rollout_quota)
                self.assertTrue(args.source_config_changed.is_set())

        asyncio.run(exercise())


if __name__ == "__main__":
    unittest.main()
