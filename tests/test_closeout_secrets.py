"""Regression checks for private restore input and secret-free child argv."""
import contextlib
import importlib.util
import io
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("closeout_backup", ROOT / "lib/vincula-backup.py")
backup = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = backup
spec.loader.exec_module(backup)


class SecretInputs(unittest.TestCase):
    @unittest.skipIf(os.name == "nt", "Bash authentication seam runs on Linux")
    def test_authentication_requires_positive_and_both_negatives(self):
        script = '''source "$1/lib/vincula-common.sh"
clash_api_reachable_with_secret() { [[ "$2" == synthetic-good ]]; }
clash_api_authenticated 9090 synthetic-good || exit 1
clash_api_reachable_with_secret() { return 0; }
if clash_api_authenticated 9090 synthetic-good; then exit 2; fi
if clash_api_authenticated 9090 ""; then exit 3; fi
'''
        result = subprocess.run(["bash", "-c", script, "test", str(ROOT)], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_plaintext_cli_is_rejected_without_echo(self):
        for flag in ("--new-reality-private", "--new-clash-secret"):
            error = io.StringIO()
            with contextlib.redirect_stderr(error), self.assertRaises(SystemExit):
                backup.parse_args(["restore", "synthetic.tar.gz", flag, "synthetic-secret-never-echo"])
            self.assertNotIn("synthetic-secret-never-echo", error.getvalue())
            self.assertIn("plaintext secret options are disabled", error.getvalue())

    def test_owned_secret_file_is_read_and_permissions_enforced(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "secret"
            path.write_text("synthetic-secret\n", encoding="utf-8")
            path.chmod(0o600)
            args = backup.parse_args(["restore", "synthetic.tar.gz", "--new-clash-secret-file", str(path)])
            self.assertEqual(args.new_clash_secret, "synthetic-secret")
            if os.name != "nt":
                path.chmod(0o644)
                with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
                    backup.parse_args(["restore", "synthetic.tar.gz", "--new-clash-secret-file", str(path)])

    @unittest.skipIf(os.name == "nt", "Bash inherited descriptors checked by Linux jobs")
    def test_render_children_never_receive_private_key_or_clash_secret(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            wrapper = path / "python3"
            wrapper.write_text('#!/bin/bash\nprintf "%s\\n" "$@" >> "$ARGV_LOG"\nexec "$REAL_PYTHON" "$@"\n')
            wrapper.chmod(0o700)
            users = path / "users.json"
            users.write_text('{"users":[{"enabled":true,"tag":"test","credentials":[{"status":"active","uuid":"11111111-1111-4111-8111-111111111111"}]}]}')
            env = dict(os.environ, PATH=str(path)+os.pathsep+os.environ["PATH"],
                       ARGV_LOG=str(path/"argv"), REAL_PYTHON=sys.executable)
            # We inspect the Python child's argv, not this test driver's shell text.
            cmd = 'source "$1/lib/vincula-common.sh"; render_sing_box_config_accounting "$2/out.json" "$2/users.json" synthetic-private "" 443 example.test 127.0.0.1 9090 synthetic-clash true'
            proc = subprocess.run(["bash", "-c", cmd, "test", str(ROOT), str(path)], env=env, capture_output=True, text=True)
            self.assertEqual(proc.returncode, 0, proc.stderr)
            args = (path / "argv").read_text()
            self.assertNotIn("synthetic-private", args)
            self.assertNotIn("synthetic-clash", args)
            config = (path / "out.json").read_text()
            self.assertIn("synthetic-private", config)
            self.assertIn("synthetic-clash", config)
