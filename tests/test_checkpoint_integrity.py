"""Checkpoint integrity must be verified before rollback mutates live state."""
import hashlib
import importlib.util
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ".vincula-upgrade-checkpoint.manifest.json"
MARKER = ".vincula-upgrade-checkpoint"


def load_backup():
    spec = importlib.util.spec_from_file_location("checkpoint_backup", ROOT / "lib/vincula-backup.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@unittest.skipUnless(os.name == "posix", "requires POSIX/Bash")
class CheckpointIntegrityTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="vcl-checkpoint-integrity-")
        self.root = Path(self.tmp.name)
        self.app = self.root / "app"
        self.bin = self.app / "bin"
        self.state = self.root / "state"
        self.backups = self.root / "backups"
        self.bin.mkdir(parents=True)
        self.state.mkdir()
        self.backups.mkdir()
        # A staged helper uses its sibling lib/ exactly like a release payload.
        (self.app / "lib").symlink_to(ROOT / "lib")
        helper = self.bin / "vincula"
        helper.write_text((ROOT / "bin/vincula").read_text(encoding="utf-8").replace('main "$@"', 'cmd_upgrade "$@"'))
        helper.chmod(0o755)
        self.env = dict(os.environ)
        self.env.update({
            "VCL_STATE_DIR": str(self.state),
            "VCL_BACKUP_ROOT": str(self.backups),
            "VCL_ACCOUNTING_DB_FILE": str(self.state / "accounting.db"),
            "VCL_LOCK_FILE": str(self.root / "vincula.lock"),
            "VCL_UPGRADE_SKIP_SERVICE": "1",
            "VCL_CONFIG_FILE": str(self.root / "sing-box-config.json"),
        })
        (self.state / "VERSION").write_text("0.5.5\n")
        (self.state / "state.json").write_text(json.dumps({
            "node": {"node_id": "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
                     "instance_id": "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"}}))
        (self.state / "users.json").write_text('{"users": []}\n')
        (self.state / "config.toml").write_text('port = 443\n')
        self.db = self.state / "accounting.db"
        con = sqlite3.connect(self.db)
        con.execute("PRAGMA journal_mode=WAL")
        con.execute("CREATE TABLE sample(value TEXT)")
        con.execute("INSERT INTO sample VALUES('before')")
        con.commit()
        con.close()
        self.run_cli = [str(helper)]

    def tearDown(self):
        self.tmp.cleanup()

    def checkpoint(self):
        proc = subprocess.run(self.run_cli + ["checkpoint", "--json"],
                              env=self.env, capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        return Path(json.loads(proc.stdout)["path"])

    def rollback(self, ck):
        return subprocess.run(self.run_cli + ["rollback", str(ck), "--json"],
                              env=self.env, capture_output=True, text=True)

    def digest(self, path):
        return hashlib.sha256(Path(path).read_bytes()).hexdigest()

    def test_checkpoint_manifest_covers_marker_and_all_members(self):
        ck = self.checkpoint()
        manifest = json.loads((ck / MANIFEST).read_text())
        self.assertEqual(manifest["schema_version"], 1)
        self.assertEqual(manifest["source_version"], "0.5.5")
        self.assertIn(MARKER, manifest["files"])
        actual = {p.name for p in ck.iterdir()} - {MANIFEST}
        self.assertEqual(actual, set(manifest["files"]))
        self.assertIn("accounting.db", manifest["files"])

    def test_tampered_checkpoint_is_rejected_before_target_mutation(self):
        ck = self.checkpoint()
        before = self.digest(self.db)
        with (ck / "accounting.db").open("ab") as out:
            out.write(b"TAMPER")
        proc = self.rollback(ck)
        self.assertNotEqual(proc.returncode, 0)
        doc = json.loads(proc.stdout)
        self.assertFalse(doc["ok"])
        self.assertEqual(doc["error"], "checkpoint_integrity_failed")
        self.assertEqual(self.digest(self.db), before)
        self.assertEqual((self.state / "VERSION").read_text().strip(), "0.5.5")

    def test_missing_manifest_is_rejected_before_target_mutation(self):
        ck = self.checkpoint()
        before = self.digest(self.db)
        (ck / MANIFEST).unlink()
        proc = self.rollback(ck)
        self.assertNotEqual(proc.returncode, 0)
        doc = json.loads(proc.stdout)
        self.assertEqual(doc["error"], "checkpoint_integrity_failed")
        self.assertEqual(self.digest(self.db), before)

    def test_verify_only_checks_manifest_without_mutation(self):
        ck = self.checkpoint()
        (self.state / "VERSION").write_text("0.5.6\n")
        before = self.digest(self.db)
        proc = subprocess.run(self.run_cli + ["rollback", str(ck),
                                              "--verify-only", "--json"],
                              env=self.env, capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        doc = json.loads(proc.stdout)
        self.assertTrue(doc["ok"])
        self.assertTrue(doc["verified"])
        self.assertEqual(self.digest(self.db), before)
        self.assertEqual((self.state / "VERSION").read_text().strip(), "0.5.6")

    def test_valid_checkpoint_rolls_back(self):
        ck = self.checkpoint()
        (self.state / "VERSION").write_text("0.5.6\n")
        proc = self.rollback(ck)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        doc = json.loads(proc.stdout)
        self.assertTrue(doc["ok"])
        self.assertEqual((self.state / "VERSION").read_text().strip(), "0.5.5")


if __name__ == "__main__":
    unittest.main()
