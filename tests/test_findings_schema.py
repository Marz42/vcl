"""Public Findings/Timeline contracts, real output and corrupt-cache boundaries."""
import copy
import importlib.util
import json
import re
import shutil
import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from types import SimpleNamespace

import test_findings as support
import test_monitor_schema as evaluator
import test_user_traffic as user_support

ROOT = Path(__file__).resolve().parents[1]
findings = support.findings


def validate(doc, kind):
    schema = json.loads((ROOT / "schemas" / kind / "v1.schema.json").read_text())
    previous = evaluator.SCHEMA
    try:
        evaluator.SCHEMA = schema
        evaluator.validate(doc, schema)
    finally:
        evaluator.SCHEMA = previous


class FindingsSchemaTests(unittest.TestCase):
    def test_standalone_controller_payload_pin_has_no_installer_dependency(self):
        # Reproduce the distributed layout: lib siblings exist, Node installer
        # does not. Reading the source checkout would hide this packaging fault.
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            shutil.copytree(ROOT / "lib", root / "lib", ignore=shutil.ignore_patterns("__pycache__"))
            spec = importlib.util.spec_from_file_location("standalone_pin", root / "lib/vincula-fleet.py")
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            provision = module.load_provision_module()
            canonical = re.search(r'^readonly VINCULA_VERSION="([^"]+)"', (ROOT / "vincula.sh").read_text(encoding="utf-8"), re.M)[1]
            self.assertEqual(provision.NODE_PAYLOAD_VERSION, canonical)
            self.assertFalse((root / "vincula.sh").exists())

    def test_shipped_positive_and_negative_fixtures(self):
        for kind in ("findings", "timeline"):
            fixtures = sorted((ROOT / "tests/fixtures/schemas" / kind).glob("*.json"))
            self.assertGreaterEqual(len(fixtures), 7)
            for fixture in fixtures:
                with self.subTest(fixture=fixture.name):
                    doc = json.loads(fixture.read_text())
                    if "invalid" in fixture.name:
                        with self.assertRaises(AssertionError):
                            validate(doc, kind)
                    else:
                        validate(doc, kind)

    def test_real_node_user_lifecycle_and_timeline_are_cache_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            store = findings.Store(root / "findings.db")
            validate(store.read(), "findings")
            self.assertFalse(store.path.exists())
            total = 0
            for n in range(21):
                total += 3000
                at = support.NOW + n * 30
                store.evaluate(support.NODE, user_support.record(at, total), {}, at)
            for n in range(21, 32):
                total += 10 * 1024 * 1024 * 30
                at = support.NOW + n * 30
                doc = user_support.record(at, total, 100)
                doc["metrics"]["last_poll_age_seconds"] = 100
                store.evaluate(support.NODE, doc, {}, at)
            output = store.read(nodes=[support.NODE])
            validate(output, "findings")
            types = {row["type"] for row in output["findings"]}
            self.assertTrue(set(findings.user_traffic.TYPES) <= types)
            self.assertIn("AUDIT_STALLED", types)
            self.assertEqual({row["subject"]["kind"] for row in output["evaluations"]}, {"node", "user"})
            at += 30
            store.evaluate(support.NODE, user_support.record(at, total + 3000), {}, at)
            validate(store.read(), "findings")
            self.assertTrue(all(row["state"] == "RESOLVED" for row in store.read()["findings"]))
            journal = root / "operations.jsonl"
            journal.write_text(json.dumps({"time": findings.utc(at), "operation": "verify", "state": "SUCCESS",
                "target": support.NODE["name"], "exit_code": 0, "credential": "vless://private"}) + "\n{bad}\n")
            host = SimpleNamespace(fleet_db_path=lambda: root / "fleet.db", operation_journal_path=lambda **kw: journal)
            before = {path.name: (path.read_bytes(), path.stat().st_mtime_ns) for path in root.iterdir()}
            timeline = findings.timeline(host, [support.NODE])
            validate(timeline, "timeline")
            self.assertEqual(timeline["cache_state"], "PARTIAL")
            self.assertEqual(len([row for row in timeline["events"] if row["kind"] == "OPERATION"]), 1)
            self.assertNotIn("vless://", json.dumps(timeline))
            self.assertEqual(before, {path.name: (path.read_bytes(), path.stat().st_mtime_ns) for path in root.iterdir()})

    def test_corrupt_rows_are_isolated_and_never_break_public_contract(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = findings.Store(Path(tmp) / "findings.db")
            store.evaluate(support.NODE, user_support.record(support.NOW), {}, support.NOW)
            with closing(store.writer()) as conn:
                conn.execute("INSERT INTO findings VALUES(?,?,?)", ("broken", support.NOW, "{bad}"))
                payload = json.loads(conn.execute("SELECT payload FROM evaluations").fetchone()[0])
                payload["user_coverage"]["observed_at"] = 2**63 - 1
                payload["secret"] = "MUST_NOT_APPEAR"
                conn.execute("UPDATE evaluations SET payload=?", (json.dumps(payload),))
                conn.commit()
            output = store.read()
            self.assertEqual(output["cache_state"], "PARTIAL")
            self.assertNotIn("observed_at", output["evaluations"][0]["user_coverage"])
            self.assertNotIn("MUST_NOT_APPEAR", json.dumps(output))
            validate(output, "findings")
            with closing(store.writer()) as conn:
                conn.execute("PRAGMA user_version=99")
            validate(store.read(), "findings")
            self.assertEqual(store.read()["cache_state"], "CACHE_CORRUPT")

    def test_event_subject_type_confusion_is_rejected_by_store_and_schema(self):
        parent = findings.target(support.NODE)
        user = findings.user_target(support.NODE, {"user_key": user_support.KEY, "tag": "alice"})
        examples = [("SERVICE_RESTART", {"restart_delta": 1}, user),
                    ("HEALTH_CHANGE", {"node": "HEALTHY"}, user),
                    ("FINDING_OPEN", {"type": "USER_TRAFFIC_SPIKE"}, parent),
                    ("FINDING_RESOLVED", {"type": "DISK_PRESSURE"}, user)]
        for kind, detail, subject in examples:
            event = {"id": findings.digest(kind), "at": support.NOW, "kind": kind, "subject": subject, "detail": detail}
            with self.subTest(kind=kind):
                with self.assertRaises(ValueError):
                    findings.decode(json.dumps(event), "event")
                with self.assertRaises(AssertionError):
                    validate({"schema": "timeline/v1", "cache_state": "OK", "events": [event], "truncated": []}, "timeline")

    def test_contract_rejects_oversized_duplicate_truncation_and_private_state(self):
        doc = json.loads((ROOT / "tests/fixtures/schemas/findings/v1-valid.json").read_text())
        for mutation in (lambda item: item.update(truncated=["timeline", "timeline"]),
                         lambda item: item["evaluations"][0].update(detector_state={"points": [[1, 2]]}),
                         lambda item: item.update(findings=item["findings"] * 1001),
                         lambda item: item["findings"][0].update(severity="ERROR")):
            bad = copy.deepcopy(doc)
            mutation(bad)
            with self.assertRaises(AssertionError):
                validate(bad, "findings")


if __name__ == "__main__":
    unittest.main()
