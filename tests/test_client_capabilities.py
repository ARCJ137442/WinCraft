import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "examples" / "python"))
from client import Client  # noqa: E402


class CapabilityTests(unittest.TestCase):
    def client_with(self, capabilities):
        client = Client.__new__(Client)
        client.ready = {"capabilities": capabilities}
        return client

    def test_advertised_optional_component_and_shortcut_are_accepted(self):
        client = self.client_with({
            "components": ["input", "textarea", "icon", "bar_chart"],
            "keyboard_shortcuts": ["escape", "ctrl_enter"],
            "button_features": ["selection_groups", "appearance_variants", "key_value_actions"],
            "scene_features": ["theme_tokens", "rich_key_value"],
            "window_properties": ["background_drag_enabled", "anchor"],
        })
        client.require_capabilities(components=("textarea", "icon", "bar_chart"), keyboard_shortcuts=("escape", "ctrl_enter"),
                                    button_features=("selection_groups", "appearance_variants", "key_value_actions"), scene_features=("theme_tokens", "rich_key_value"),
                                    window_properties=("background_drag_enabled", "anchor"))

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

    def test_background_drag_property_fails_closed_when_host_does_not_advertise_it(self):
        client = self.client_with({"components": [], "keyboard_shortcuts": [], "button_features": [], "scene_features": []})
        with self.assertRaisesRegex(RuntimeError, "window_property:background_drag_enabled"):
            client.require_capabilities(window_properties=("background_drag_enabled",))

    def test_anchor_fails_closed_when_host_does_not_advertise_it(self):
        client = self.client_with({"components": [], "window_properties": ["background_drag_enabled"]})
        with self.assertRaisesRegex(RuntimeError, "window_property:anchor"):
            client.require_capabilities(window_properties=("anchor",))

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


if __name__ == "__main__":
    unittest.main()
