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

    def test_scope_props_patch_is_valid_and_move_is_rejected(self):
        schema = load_json(PREVIEW / "scope-request.schema.json")
        validator = jsonschema.Draft202012Validator(schema, format_checker=jsonschema.FormatChecker())
        valid = load_json(PREVIEW / "examples/scope-patch-valid.json")
        invalid_move = load_json(PREVIEW / "examples/scope-patch-cross-scope-move-invalid.json")

        self.assertEqual(list(validator.iter_errors(valid)), [])
        self.assertTrue(list(validator.iter_errors(invalid_move)))


if __name__ == "__main__":
    unittest.main()
