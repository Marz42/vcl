"""Validate public monitoring views against the shipped schema, without pip.

This test evaluator intentionally implements only the keywords used in this
schema and rejects unsupported keywords, so additions cannot silently pass.
"""
import copy
import importlib.util
import json
import math
import re
import tempfile
import unittest
import uuid
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = json.loads((ROOT / "schemas/monitor/v1.schema.json").read_text())
SUPPORTED = {"$schema", "$id", "$defs", "$ref", "title", "description", "type", "additionalProperties", "required",
             "properties", "const", "enum", "maxItems", "items", "minimum", "maximum", "pattern", "format", "propertyNames"}


def validate(value, schema=SCHEMA):
    assert not set(schema) - SUPPORTED, "test evaluator needs new schema keyword support"
    if "$ref" in schema:
        target = SCHEMA
        for key in schema["$ref"].split("/")[1:]:
            target = target[key]
        return validate(value, target)
    if "const" in schema:
        assert value == schema["const"]
    if "enum" in schema:
        assert value in schema["enum"]
    if "type" in schema:
        types = schema["type"] if isinstance(schema["type"], list) else [schema["type"]]
        kind = "null" if value is None else "boolean" if type(value) is bool else "integer" if type(value) is int else (
            "number" if type(value) is float else "string" if isinstance(value, str) else "array" if isinstance(value, list) else "object" if isinstance(value, dict) else "invalid")
        assert kind in types or (kind == "integer" and "number" in types)
    if isinstance(value, dict):
        assert set(schema.get("required", ())) <= set(value)
        properties = schema.get("properties", {})
        additional = schema.get("additionalProperties", True)
        for key, item in value.items():
            if "propertyNames" in schema:
                validate(key, schema["propertyNames"])
            if key in properties:
                validate(item, properties[key])
            elif additional is False:
                raise AssertionError("unknown field")
            elif isinstance(additional, dict):
                validate(item, additional)
    elif isinstance(value, list):
        assert len(value) <= schema.get("maxItems", len(value))
        for item in value:
            validate(item, schema.get("items", {}))
    elif isinstance(value, str):
        if "pattern" in schema:
            assert re.search(schema["pattern"], value)
        if schema.get("format") == "uuid":
            uuid.UUID(value)
        if schema.get("format") == "date-time":
            assert datetime.fromisoformat(value.replace("Z", "+00:00")).tzinfo is not None
    elif type(value) in (int, float):
        assert math.isfinite(value)
        assert value >= schema.get("minimum", value) and value <= schema.get("maximum", value)


class MonitorSchemaTests(unittest.TestCase):
    def test_valid_fixture_and_implementation_output(self):
        fixture = json.loads((ROOT / "tests/fixtures/schemas/monitor/v1-valid.json").read_text())
        validate(fixture)
        spec = importlib.util.spec_from_file_location("schema_monitor", ROOT / "lib/observation/monitor.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        node = {"name": "example", "node_id": "11111111-1111-4111-8111-111111111111"}
        with tempfile.TemporaryDirectory() as temp:
            store = module.Store(Path(temp) / "observation.db")
            validate(store.read([node], 1790438400))
            for i, state in enumerate(("TIMEOUT", "AUTH_FAILED", "UNSUPPORTED")):
                store.record(node, {"state": state}, 1790438400 + i)
                validate(store.read([node], 1790438410 + i))
            snapshot = json.loads((ROOT / "tests/fixtures/schemas/telemetry/v1-valid.json").read_text())
            snapshot["observed_at"] = "2026-09-26T16:00:03Z"
            # Use the schema fixture's real UTC epoch instead of depending on the test runner's clock.
            now = module.store_module.health.timestamp(snapshot["observed_at"])
            store.record(node, {"state": "OK", "snapshot": snapshot}, now + 86400)
            snapshot["observed_at"] = module.store_module.health.utc(now + 86401)
            store.record(node, {"state": "OK", "snapshot": snapshot}, now + 86401)
            healthy = store.read([node], now + 86402)
            validate(healthy)
            leaked = copy.deepcopy(healthy)
            leaked["nodes"][0]["metrics"]["credential"] = "MUST_NOT_APPEAR"
            with self.assertRaises(AssertionError):
                validate(leaked)
            validate(store.read([node], 1790438600))

    def test_negative_fixtures_and_future_contract(self):
        fixture = json.loads((ROOT / "tests/fixtures/schemas/monitor/v1-valid.json").read_text())
        examples = []
        missing = copy.deepcopy(fixture)
        missing.pop("cache_state")
        examples.append(missing)
        examples.append({**fixture, "schema": "monitor/v2"})
        examples.append({**fixture, "credential": "MUST_NOT_APPEAR"})
        for item in examples:
            with self.assertRaises(AssertionError):
                validate(item)
        bad = json.loads((ROOT / "tests/fixtures/schemas/monitor/v1-missing-cache-state.json").read_text())
        with self.assertRaises(AssertionError):
            validate(bad)


if __name__ == "__main__":
    unittest.main()
