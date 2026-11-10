"""Backup self-verification and uncertain remote preparation regression tests."""
import importlib.util
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
def load(name, file):
    spec = importlib.util.spec_from_file_location(name, ROOT / file)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module
backup = load('prepare_backup', 'lib/vincula-backup.py')
upgrade = load('prepare_upgrade', 'lib/node_upgrade.py')

class BackupTests(unittest.TestCase):
    def test_create_streams_without_extracting_and_detects_tamper(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as tmp:
            root = Path(tmp)
            state = root / 'state'; state.mkdir()
            (state / 'state.json').write_text(json.dumps({'node': {
                'node_id': 'n', 'instance_id': 'i', 'reality_private_key': 'secret'}}))
            (state / 'users.json').write_text('{"users": []}')
            (state / 'config.toml').write_text('clash_api_secret="secret"\n')
            (state / 'VERSION').write_text('0.5.0')
            db = root / 'db'
            with sqlite3.connect(db) as con:
                con.execute('create table sample (value blob)')
                con.execute('insert into sample values (zeroblob(2097152))')
            con.close()
            archive = root / 'out.tar'
            with patch.object(backup, '_read_tar_members', side_effect=AssertionError('must not extract')):
                result = backup.create_backup(state, db, False, archive)
            self.assertTrue(result['ok'])
            self.assertTrue(backup.verify_manifest(archive)['ok'])
            self.assertEqual(list(root.glob('.vincula-backup-*')), [])
            # Damage the DB bytes in the completed tar, retain valid tar framing.
            import tarfile
            with tarfile.open(archive) as tar:
                offset = tar.getmember('accounting.db').offset_data
            with archive.open('r+b') as f:
                f.seek(offset + 100); f.write(b'BROKEN')
            self.assertFalse(backup.verify_manifest(archive)['ok'])

    def test_snapshot_preserves_database(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as tmp:
            src, dest = Path(tmp)/'src', Path(tmp)/'dest'
            with sqlite3.connect(src) as con:
                con.execute('create table t(x)'); con.execute('insert into t values (42)')
            con.close()
            backup.snapshot_sqlite(src, dest)
            with sqlite3.connect(dest) as con:
                self.assertEqual(con.execute('pragma integrity_check').fetchone()[0], 'ok')
                self.assertEqual(con.execute('select x from t').fetchone()[0], 42)
            con.close()

class PrepareTests(unittest.TestCase):
    def test_lost_start_reply_queries_same_operation(self):
        binding = {'node_id': 'n'}
        reply = {'state': 'SUCCEEDED', 'operation_id': 'op', 'binding': binding,
                 'backup': {'path': '/b'}, 'checkpoint': {'path': '/c'}}
        ssh = Mock(side_effect=[('ERROR', None, 'timeout'), ('OK', reply, '')])
        with patch.object(upgrade, '_ssh_json', ssh), patch.object(upgrade.time, 'sleep'):
            self.assertEqual(upgrade._prepare_remote({}, '/runner', 'op', binding, '/helper', 900), reply)
        self.assertEqual(ssh.call_args_list[1].args[1], ['python3', '/runner', 'status', 'op'])
        self.assertEqual(sum('start' in call.args[1] for call in ssh.call_args_list), 1)

    def test_unknown_status_does_not_mean_cancelled(self):
        with patch.object(upgrade, '_ssh_json', return_value=('ERROR', None, 'timeout')), \
             patch.object(upgrade.time, 'monotonic', side_effect=[0, 1000]):
            result = upgrade._prepare_remote({}, '/r', 'op', {}, '/h', 30)
        self.assertEqual(result['state'], 'UNKNOWN')

    def test_wrong_binding_refused(self):
        doc = {'state': 'SUCCEEDED', 'operation_id': 'op', 'binding': {'node_id': 'other'}}
        with patch.object(upgrade, '_ssh_json', return_value=('OK', doc, '')):
            result = upgrade._prepare_remote({}, '/r', 'op', {'node_id': 'n'}, '/h', 30)
        self.assertEqual(result['code'], 'PREPARATION_BINDING_MISMATCH')

    def test_apply_unknown_preserves_stage_and_never_installs(self):
        prov = Mock(); prov.NODE_PAYLOAD_VERSION = '0.5.5'
        prov.verify_local_payload.return_value = {'sha256': 'a'*64}
        prov._create_remote_stage.return_value = '/stage'
        prov._remote_stage_paths.return_value = {'unpack': '/stage/pkg', 'tar': '/stage/payload.tar'}
        host = Mock(); host.load_provision_module.return_value = prov
        host.ssh_run.return_value.returncode = 0
        upgrade.bind(host)
        plan = {'state': 'PLANNED', 'allowlist_ok': True, 'identity': {'node_id': 'n', 'instance_id': 'i'}, 'current_version': '0.5.0'}
        with patch.object(upgrade, 'run_upgrade_plan', return_value=plan), \
             patch.object(upgrade, '_prepare_remote', return_value={'state': 'UNKNOWN'}):
            result = upgrade.run_upgrade_apply({'name': 'n', 'node_id': 'n', 'ssh_host': 'h', 'ssh_user': 'root'}, confirmed=True)
        self.assertFalse(result['migrate_started'])
        self.assertFalse(result['retry_allowed'])
        prov.installer_remote_argv.assert_not_called()
        prov._cleanup_remote_stage.assert_not_called()


@unittest.skipUnless(__import__('os').name == 'posix', 'requires Linux flock and process groups')
class LinuxWorkerTests(unittest.TestCase):
    def test_worker_success_and_deadline(self):
        import os
        import uuid
        worker = load('prepare_worker', 'lib/upgrade_prepare.py')
        for seconds, script, expected in [
            (10, 'if [ "$1" = backup ]; then echo \'{"ok":true,"path":"/b","source_node_id":"n","source_instance_id":"i"}\'; else echo \'{"ok":true,"path":"/c","source_version":"0.5.0"}\'; fi', 'SUCCEEDED'),
            (0.1, 'sleep 30', 'CANCELLED'),
        ]:
            with tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp); root.chmod(0o700)
                helper = root / 'helper'; helper.write_text(script)
                state = root / 'state'; state.mkdir()
                (state/'state.json').write_text('{"node":{"node_id":"n","instance_id":"i"}}')
                (state/'VERSION').write_text('0.5.0')
                op = str(uuid.uuid4()); dest = root/op; dest.mkdir()
                worker.save(dest/'status.json', {'state':'RUNNING', 'operation_id':op,
                    'binding':{'node_id':'n','instance_id':'i','source_version':'0.5.0'},
                    'helper':str(helper), 'seconds':seconds})
                fd = worker.lock(root)
                with patch.object(worker.os, 'nice'), patch.object(worker.subprocess, 'run'):
                    worker.worker(root,op,fd,state)
                doc = json.loads((dest/'status.json').read_text())
                self.assertEqual(doc['state'],expected,doc)
                fd = worker.lock(root); self.assertIsNotNone(fd); os.close(fd)

    def test_live_lock_and_abandoned_operation_block_restart(self):
        import os
        import uuid
        worker = load('prepare_worker_lock', 'lib/upgrade_prepare.py')
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); root.chmod(0o700)
            old = str(uuid.uuid4()); dest=root/old; dest.mkdir()
            worker.save(dest/'status.json',{'state':'RUNNING','operation_id':old,'binding':{}})
            fd=worker.lock(root)
            self.assertEqual(worker.read_status(dest/'status.json')['state'],'RUNNING')
            os.close(fd)
            self.assertEqual(worker.read_status(dest/'status.json')['state'],'UNKNOWN')
            doc=worker.start(root,str(uuid.uuid4()),{},root/'helper',30)
            self.assertEqual(doc['code'],'UNRESOLVED_PREPARATION')

if __name__ == '__main__':
    unittest.main()
