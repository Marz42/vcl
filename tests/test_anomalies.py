"""M3 cold starts, realistic counter resets and explainable bounded baselines."""
import copy
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("node_anomalies_test", ROOT / "tests/test_findings.py")
support = importlib.util.module_from_spec(spec)
spec.loader.exec_module(support)
findings, anomalies = support.findings, support.findings.anomalies
NOW, NODE = support.NOW, support.NODE


def sample(at, rate=2 * 1024 * 1024, count=0, **kw):
    return support.record(at, rx_bytes_per_second=rate, tx_bytes_per_second=0,
                          uptime_seconds=1000 + at - NOW, restart_count=count, **kw)


class StatisticalTests(unittest.TestCase):
    def baseline(self, floor=10):
        state = None
        for n in range(20):
            signal, state, summary = anomalies.series(100, NOW + n * 30, state, floor=floor)
            self.assertIsNone(signal)
            self.assertEqual(summary["reason"], "COLD")
        return state

    def test_normal_fluctuation_threshold_evidence_and_hysteresis(self):
        state = self.baseline()
        signal, state, summary = anomalies.series(401, NOW + 600, state, floor=10)
        self.assertTrue(signal)
        self.assertEqual(summary["baseline_median"], 100)
        self.assertEqual(summary["baseline_mad"], 0)
        self.assertEqual(summary["threshold"], 400)
        self.assertEqual(len(state["points"]), 20)
        signal, state, _ = anomalies.series(350, NOW + 630, state, floor=10, active=True)
        self.assertTrue(signal)
        signal, state, _ = anomalies.series(339, NOW + 660, state, floor=10, active=True)
        self.assertFalse(signal)
        for n in range(100):
            signal, state, _ = anomalies.series(90 + n % 21, NOW + 690 + n * 30, state, floor=10)
            self.assertFalse(signal)
            self.assertLessEqual(len(state["points"]), 60)

    def test_sustained_spike_cannot_train_baseline_or_skip_duration(self):
        state = self.baseline()
        for n in range(11):
            signal, state, summary = anomalies.series(500, NOW + 600 + n * 30, state, floor=10, sustained_seconds=300)
            self.assertEqual(signal, n >= 10)
            self.assertEqual(summary["baseline_median"], 100)
            self.assertEqual(summary["above_seconds"], n * 30)
            self.assertEqual(len(state["points"]), 20)

    def test_missing_gap_replay_and_time_span_are_unknown(self):
        state = self.baseline()
        signal, after, _ = anomalies.series(None, NOW + 600, state, floor=10)
        self.assertIsNone(signal)
        self.assertEqual(after, state)
        for at in (NOW + 570, NOW + 540):
            signal, after, summary = anomalies.series(1, at, state, floor=10)
            self.assertIsNone(signal)
            self.assertEqual(summary["reason"], "NO_NEW_SAMPLE")
        signal, after, summary = anomalies.series(500, NOW + 700, state, floor=10)
        self.assertIsNone(signal)
        self.assertEqual(len(after["points"]), 1)
        self.assertEqual(summary["reason"], "COLD")
        state = None
        for n in range(25):
            signal, state, _ = anomalies.series(100, NOW + n, state, floor=10)
            self.assertIsNone(signal)  # Twenty values in twenty seconds are not a baseline.

    def test_expired_anomalous_baseline_cannot_train_itself_away(self):
        state = self.baseline()
        for n in range(140):
            signal, state, summary = anomalies.series(500, NOW + 600 + n * 30, state,
                                                       floor=10, active=True, sustained_seconds=300)
            self.assertIn(signal, (True, None))
            self.assertEqual(summary["baseline_median"], 100)
        self.assertEqual(summary["reason"], "STALE")
        self.assertEqual(len(state["points"]), 20)

    def test_idle_floor_invalid_values_and_injected_state_are_bounded(self):
        state = {"points": [[NOW + n * 30, 0] for n in range(20)], "last_at": NOW + 570}
        for value, expected in ((9, False), (10, True)):
            signal, _, _ = anomalies.series(value, NOW + 600, state, floor=10)
            self.assertEqual(signal, expected)
        for value in (True, float("inf"), -1, 2**100):
            self.assertIsNone(anomalies.series(value, NOW + 600, state, floor=10)[0])
        self.assertEqual(anomalies.clean_series({"points": [[NOW, 1]] * 61, "secret": "vless://x"})["points"], [])
        self.assertNotIn("vless", json.dumps(anomalies.clean_state({"secret": "vless://x"})))


class NodeTests(unittest.TestCase):
    def test_restart_loop_recovery_timeline_and_counter_reset(self):
        state = None
        for n in range(4):
            checks, state, summary, event = anomalies.evaluate(sample(NOW + n * 30, count=n), state, NOW + n * 30)
            self.assertEqual(checks["SERVICE_RESTART_LOOP"][0], None if n == 0 else n == 3)
            if n:
                self.assertEqual(event, {"restart_delta": 1})
        for n in range(4, 15):
            checks, state, _, _ = anomalies.evaluate(sample(NOW + n * 30, count=3), state, NOW + n * 30)
        self.assertFalse(checks["SERVICE_RESTART_LOOP"][0])
        checks, state, summary, event = anomalies.evaluate(sample(NOW + 450, count=0), state, NOW + 450)
        self.assertIsNone(checks["SERVICE_RESTART_LOOP"][0])
        self.assertEqual(summary["SERVICE_RESTART_LOOP"]["reason"], "RESET")
        self.assertIsNone(event)

    def test_reboot_instance_change_stale_and_missing_are_unknown(self):
        state = None
        for n in range(21):
            _, state, _, _ = anomalies.evaluate(sample(NOW + n * 30), state, NOW + n * 30)
        original = copy.deepcopy(state)
        doc = sample(NOW + 630)
        for change in ("reboot", "instance", "stale", "missing"):
            modified = copy.deepcopy(doc)
            if change == "reboot":
                modified["metrics"]["uptime_seconds"] = 1
                modified["metrics"]["rx_bytes_per_second"] = None
            elif change == "instance":
                modified["instance_id"] = "33333333-3333-4333-8333-333333333333"
            elif change == "stale":
                modified["health"]["observation"]["reason"] = "TELEMETRY_STALE"
            else:
                modified["metrics"]["rx_bytes_per_second"] = None
            checks, _, _, _ = anomalies.evaluate(modified, state, NOW + 630)
            self.assertIsNone(checks["NETWORK_RATE_ANOMALY"][0], change)
        self.assertEqual(state, original)

    def test_store_persistence_unknown_dedupe_recovery_and_private_state(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "findings.db"
            for n in range(20):
                findings.Store(path).evaluate(NODE, sample(NOW + n * 30), {}, NOW + n * 30)
            for n in range(20, 24):
                findings.Store(path).evaluate(NODE, sample(NOW + n * 30, rate=10 * 1024 * 1024, count=n - 20), {}, NOW + n * 30)
            store = findings.Store(path)
            doc = store.read()
            alerts = {item["type"]: item for item in doc["findings"]}
            self.assertEqual(alerts["NETWORK_RATE_ANOMALY"]["state"], "ACTIVE")
            self.assertEqual(alerts["SERVICE_RESTART_LOOP"]["state"], "ACTIVE")
            self.assertEqual(len([e for e in doc["events"] if e["kind"] == "SERVICE_RESTART"]), 3)
            self.assertNotIn("detector_state", doc["evaluations"][0])
            self.assertEqual(doc["evaluations"][0]["baselines"]["NETWORK_RATE_ANOMALY"]["baseline_median"], 2 * 1024 * 1024)
            for n in range(24, 26):
                store.evaluate(NODE, {}, {}, NOW + n * 30)
            self.assertEqual(next(f for f in store.read()["findings"] if f["type"] == "NETWORK_RATE_ANOMALY")["state"], "ACTIVE")
            # Recover before the last sample gap exceeds 90 seconds.
            store.evaluate(NODE, sample(NOW + 780, count=3), {}, NOW + 780)
            self.assertEqual(next(f for f in store.read()["findings"] if f["type"] == "NETWORK_RATE_ANOMALY")["state"], "RESOLVED")

    def test_detectors_have_no_io_hooks_and_do_not_echo_arbitrary_text(self):
        doc = sample(NOW)
        doc["argv"] = "ssh sudo reboot vless://credential"
        before = copy.deepcopy(doc)
        with mock.patch("subprocess.run", side_effect=AssertionError("mutation forbidden")):
            output = anomalies.evaluate(doc, {}, NOW)
        self.assertEqual(doc, before)
        self.assertNotIn("vless", json.dumps(output))


if __name__ == "__main__":
    unittest.main()
