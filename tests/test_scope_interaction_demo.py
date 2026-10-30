from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker
from referencing import Registry, Resource

ROOT = Path(__file__).resolve().parents[1]
EXAMPLES = ROOT / "examples" / "python"
if str(EXAMPLES) not in sys.path:
    sys.path.insert(0, str(EXAMPLES))

import scope_interaction_demo as demo  # noqa: E402


class ScopeInteractionDemoTests(unittest.TestCase):
    def test_scene_uses_static_action_and_separates_scoped_data(self):
        value = demo.scene()
        schema = json.loads((ROOT / "protocol" / "scene.schema.json").read_text(encoding="utf-8"))
        theme_schema = json.loads((ROOT / "protocol" / "theme.schema.json").read_text(encoding="utf-8"))
        registry = (
            Registry()
            .with_resource(theme_schema["$id"], Resource.from_contents(theme_schema))
            .with_resource(schema["$id"], Resource.from_contents(schema))
        )
        Draft202012Validator(schema, format_checker=FormatChecker(), registry=registry).validate(value)
        focus = value["root"]["children"][0]
        button = focus["children"][-1]
        self.assertEqual(button["id"], demo.ACTION_COMPONENT_ID)
        self.assertEqual(button["props"]["action"], demo.ACTION_ID)
        self.assertNotIn("native_window_action", button["props"])
        self.assertIn("counter", value["data"])
        self.assertIn("notes", value["data"])
        self.assertNotIn("<script", json.dumps(value))

    def test_interaction_scope_and_world_identity_are_both_required(self):
        message = {
            "event": "scope.interaction",
            "data": {
                "id": "synthetic-event",
                "world_id": "world-a",
                "scope_id": "scope-a",
                "scope_generation": 2,
                "component_id": demo.ACTION_COMPONENT_ID,
                "action": demo.ACTION_ID,
            },
        }
        self.assertTrue(demo.owns_scope_interaction(message, "world-a", "scope-a", 2))
        self.assertFalse(demo.owns_scope_interaction(message, "world-b", "scope-a", 2))
        self.assertFalse(demo.owns_scope_interaction(message, "world-a", "scope-b", 2))
        self.assertFalse(demo.owns_scope_interaction(message, "world-a", "scope-a", 3))


if __name__ == "__main__":
    unittest.main()
