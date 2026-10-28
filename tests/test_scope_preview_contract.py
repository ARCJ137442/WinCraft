import json
import unittest
from pathlib import Path

import jsonschema


ROOT = Path(__file__).resolve().parents[1]
PREVIEW = ROOT / "protocol/preview-0.4"


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


class ComponentScopePreviewContractTests(unittest.TestCase):
    def test_preview_handshake_is_explicit_and_versioned(self):
        schema = load_json(PREVIEW / "hello.schema.json")
        request = load_json(PREVIEW / "examples/hello-preview.json")
        jsonschema.Draft202012Validator(schema, format_checker=jsonschema.FormatChecker()).validate(request)

        request["params"]["protocol"] = "0.3"
        errors = list(jsonschema.Draft202012Validator(schema).iter_errors(request))
        self.assertTrue(errors)

    def test_scope_patch_schema_accepts_structural_ops_but_engine_enforces_ownership(self):
        schema = load_json(PREVIEW / "scope-request.schema.json")
        validator = jsonschema.Draft202012Validator(schema, format_checker=jsonschema.FormatChecker())
        valid_props = load_json(PREVIEW / "examples/scope-patch-valid.json")
        valid_structure = load_json(PREVIEW / "examples/scope-patch-structure-valid.json")
        cross_scope_move = load_json(PREVIEW / "examples/scope-patch-cross-scope-move-invalid.json")
        malformed_move = load_json(PREVIEW / "examples/scope-patch-missing-parent-invalid.json")

        self.assertEqual(list(validator.iter_errors(valid_props)), [])
        self.assertEqual(list(validator.iter_errors(valid_structure)), [])
        # A structurally valid move is rejected by the live engine when its source is outside the caller's scope.
        self.assertEqual(list(validator.iter_errors(cross_scope_move)), [])
        self.assertTrue(list(validator.iter_errors(malformed_move)))

    def test_root_structure_patch_schema_uses_world_authority(self):
        schema = load_json(PREVIEW / "scope-request.schema.json")
        request = load_json(PREVIEW / "examples/scope-structure-remove-parent-valid.json")
        jsonschema.Draft202012Validator(schema, format_checker=jsonschema.FormatChecker()).validate(request)
        self.assertEqual(request["method"], "scope.structure.patch")


if __name__ == "__main__":
    unittest.main()
