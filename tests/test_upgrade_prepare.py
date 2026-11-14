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
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state = root / 'state'; state.mkdir()
            (state / 'state.json').write_text(json.dumps({'node': {
                'node_id': 'n', 'instance_id': 'i', 'reality_private_key': 'secret'}}))
            (state / 'users.json').write_text('{"users": []}')
            (state / 'config.toml').write_text('clash_api_secret="secret"\n')
            (state / 'VERSION').write_text('0.5.0')
            db = root / 'db'
            with sqlite3.connect(db) as con:
                con.execute('pragma journal_mode=wal')
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
        with tempfile.TemporaryDirectory() as tmp:
            src, dest = Path(tmp)/'src', Path(tmp)/'dest'
            with sqlite3.connect(src) as con:
                con.execute('pragma journal_mode=wal')
                con.execute('create table t(x)'); con.execute('insert into t values (42)')
            con.close()
            backup.snapshot_sqlite(src, dest)
            with sqlite3.connect(dest) as con:
                self.assertEqual(con.execute('pragma integrity_check').fetchone()[0], 'ok')
                self.assertEqual(con.execute('select x from t').fetchone()[0], 42)
            con.close()

    def test_snapshot_rejects_non_wal(self):
        with tempfile.TemporaryDirectory() as tmp:
            src, dest = Path(tmp)/'src', Path(tmp)/'dest'
            with sqlite3.connect(src) as con:
                con.execute('create table t(x)')
                con.execute('insert into t values (42)')
            con.close()
            with self.assertRaises(sqlite3.OperationalError) as ctx:
                backup.snapshot_sqlite(src, dest)
            self.assertIn('requires WAL', str(ctx.exception))
            self.assertFalse(dest.exists())

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


class AutoRollbackCompatibilityTests(unittest.TestCase):
    def test_old_or_unknown_installed_helper_is_not_used_for_mutation(self):
        host = Mock()
        upgrade.bind(host)
        with patch.object(upgrade, '_ssh_json',
                          side_effect=[('ERROR', None, 'unknown option')]) as ssh:
            result = upgrade._attempt_post_upgrade_rollback(
                {'name': 'n', 'node_id': 'n'},
                checkpoint_path='/backups/ck', backup_path='/backups/b.tar',
                post_check_detail='verify failed', pre_version='0.5.0',
                target='0.5.5')
        self.assertIsNone(result)
        self.assertEqual(ssh.call_count, 1)
        argv = ssh.call_args.args[1]
        self.assertIn('--verify-only', argv)

    def test_new_helper_preflight_then_real_rollback(self):
        host = Mock()
        upgrade.bind(host)
        with patch.object(upgrade, '_ssh_json', side_effect=[('OK', {'ok': True, 'verified': True}, ''), ('OK', {'ok': True, 'restored_version': '0.5.5'}, '')]) as ssh:
            result = upgrade._attempt_post_upgrade_rollback({'name': 'n', 'node_id': 'n'}, checkpoint_path='/backups/ck', backup_path='/backups/b.tar', post_check_detail='verify failed', pre_version='0.5.0', target='0.5.5')
        self.assertIsNotNone(result)
        self.assertEqual(result['state'], 'ROLLED_BACK')
        self.assertEqual(ssh.call_count, 2)
        self.assertIn('--verify-only', ssh.call_args_list[0].args[1])
        self.assertNotIn('--verify-only', ssh.call_args_list[1].args[1])
        self.assertGreaterEqual(ssh.call_args_list[1].kwargs['timeout'], 900)

    def test_apply_uses_extended_install_timeout_not_60s(self):
        prov = Mock(); prov.NODE_PAYLOAD_VERSION = '0.5.5'
        prov.verify_local_payload.return_value = {'sha256': 'a' * 64}
        prov._create_remote_stage.return_value = '/stage'
        prov._remote_stage_paths.return_value = {'unpack': '/stage/pkg', 'tar': '/stage/payload.tar'}
        prov.installer_remote_argv.return_value = ['bash', '/stage/pkg/vincula.sh']
        host = Mock()
        host.SSH_MUTATION_TIMEOUT_SECONDS = 60
        host.SSH_UPGRADE_APPLY_TIMEOUT_SECONDS = 900
        host.SSH_UPGRADE_VERIFY_TIMEOUT_SECONDS = 300
        host.load_provision_module.return_value = prov
        host.ssh_run.return_value.returncode = 0
        upgrade.bind(host)
        plan = {'state': 'PLANNED', 'allowlist_ok': True,
                'identity': {'node_id': 'n', 'instance_id': 'i'}, 'current_version': '0.5.0'}
        prepared = {'state': 'SUCCEEDED', 'operation_id': 'op',
                    'backup': {'path': '/b.tar'}, 'checkpoint': {'path': '/ck'}}
        with patch.object(upgrade, 'run_upgrade_plan', return_value=plan), \
             patch.object(upgrade, '_prepare_remote', return_value=prepared), \
             patch.object(upgrade, '_ssh_json', side_effect=[
                 ('OK', {'ok': True}, ''),
                 ('OK', {'schema': 'capabilities/v1', 'node_version': '0.5.5', 'capabilities': []}, ''),
                 ('OK', {'node_id': 'n', 'instance_id': 'i', 'vincula_version': '0.5.5'}, ''),
             ]) as post_ssh:
            host.load_observation_capabilities_module = Mock(
                return_value=Mock(CAPABILITIES_MAX_BYTES=4096, validate_capabilities_v1=lambda _: [])
            )
            result = upgrade.run_upgrade_apply(
                {'name': 'n', 'node_id': 'n', 'ssh_host': 'h', 'ssh_user': 'root'}, confirmed=True
            )
        self.assertEqual(result['state'], 'SUCCESS', result)
        install_call = host.ssh_run.call_args_list[-1]
        self.assertEqual(install_call.kwargs['timeout'], 900)
        verify_call = post_ssh.call_args_list[0]
        self.assertEqual(verify_call.args[1], ['vcl', 'verify', '--json'])
        self.assertEqual(verify_call.kwargs['timeout'], 300)
        self.assertEqual(post_ssh.call_args_list[1].kwargs['timeout'], 60)
        self.assertEqual(post_ssh.call_args_list[2].kwargs['timeout'], 60)

class BackupVerificationTests(unittest.TestCase):
    def make_archive(self, root):
        state = root / 'state'; state.mkdir()
        (state / 'state.json').write_text(json.dumps({'node': {
            'node_id': 'n', 'instance_id': 'i'}}))
        (state / 'users.json').write_text('{"users": []}')
        (state / 'config.toml').write_text('port = 443\n')
        (state / 'VERSION').write_text('0.5.0')
        db = root / 'db'
        with sqlite3.connect(db) as con:
            con.execute('pragma journal_mode=wal')
            con.execute('create table sample (value blob)')
            con.execute('insert into sample values (zeroblob(2097152))')
        archive = root / 'backup.tar'
        result = backup.create_backup(state, db, False, archive)
        self.assertTrue(result['ok'])
        return archive

    @unittest.skipUnless(__import__("os").name == "posix", "requires POSIX open flags")
    def test_fd_verify_accepts_intact_and_detects_truncation_and_tamper(self):
        import os
        with tempfile.TemporaryDirectory() as tmp:
            archive = self.make_archive(Path(tmp))
            fd = os.open(archive, os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW)
            try:
                result = backup.verify_archive_fd(fd)
                self.assertTrue(result['ok'], result)
                self.assertEqual(result['archive_sha256'], backup.sha256_file(archive))
                os.truncate(archive, archive.stat().st_size * 3 // 5)
                self.assertEqual(backup.verify_archive_fd(fd).get('error'), 'invalid_archive')
            finally:
                os.close(fd)
        with tempfile.TemporaryDirectory() as tmp:
            archive = self.make_archive(Path(tmp))
            import tarfile
            with tarfile.open(archive) as tar:
                offset = tar.getmember('accounting.db').offset_data
            with archive.open('r+b') as fh:
                fh.seek(offset + 100); fh.write(b'BROKEN')
            fd = os.open(archive, os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW)
            try:
                self.assertEqual(backup.verify_archive_fd(fd).get('error'), 'checksum_mismatch')
            finally:
                os.close(fd)

    def test_snapshot_deadline_is_explicit(self):
        import os
        with tempfile.TemporaryDirectory() as tmp:
            src, dest = Path(tmp)/'src', Path(tmp)/'dest'
            with sqlite3.connect(src) as con:
                con.execute('pragma journal_mode=wal')
                con.execute('create table t(x)'); con.execute('insert into t values (42)')
            con.close()
            with patch.dict(os.environ, {'VCL_PREPARE_DEADLINE_MONO': '0'}):
                with self.assertRaises(sqlite3.OperationalError):
                    backup.snapshot_sqlite(src, dest)


@unittest.skipUnless(__import__('os').name == 'posix', 'requires Linux flock and process groups')
class LinuxWorkerTests(unittest.TestCase):
    def _fixture(self, tmp):
        import os
        import uuid
        worker = load('prepare_worker', 'lib/upgrade_prepare.py')
        root = Path(tmp); root.chmod(0o700)
        root.joinpath('backups').mkdir()
        helper = root / 'helper'
        state = root / 'state'; state.mkdir()
        (state/'state.json').write_text('{"node":{"node_id":"n","instance_id":"i"}}')
        (state/'VERSION').write_text('0.5.0')
        (state/'users.json').write_text('{"users": []}')
        (state/'config.toml').write_text('port = 443\n')
        db = root/'db'
        with sqlite3.connect(db) as con:
            con.execute('pragma journal_mode=wal')
            con.execute('create table t(x)'); con.execute('insert into t values (42)')
        con.close()
        archive = root/'backups'/'backup.tar'
        made = backup.create_backup(state, db, False, archive)
        backup_json = root/'backup.json'
        backup_json.write_text(json.dumps(made))
        checkpoint_json = json.dumps({'ok': True, 'path': str(root/'checkpoint'), 'source_version': '0.5.0'})
        helper.write_text(
            '#!/bin/bash\n'
            'if [ "$1" = backup ]; then cat "$VCL_TEST_BACKUP_JSON"; else printf %s "' + checkpoint_json.replace('"','\\"') + '"; fi\n')
        helper.chmod(0o755)
        import os
        os.environ['VCL_TEST_BACKUP_JSON'] = str(backup_json)
        op = str(uuid.uuid4()); dest = root/op; dest.mkdir()
        worker.save(dest/'status.json', {'state':'RUNNING', 'operation_id':op,
            'binding':{'node_id':'n','instance_id':'i','source_version':'0.5.0'},
            'helper':str(helper), 'seconds':30})
        fd = worker.lock(root)
        return worker, root, op, fd, dest, archive

    def test_worker_success_verifies_archive_and_runs_checkpoint(self):
        import os
        with tempfile.TemporaryDirectory() as tmp:
            worker, root, op, fd, dest, archive = self._fixture(tmp)
            with patch.object(worker, 'BACKUP_ROOT', root/'backups'), \
                 patch.object(worker.os, 'nice'), \
                 patch.object(worker.subprocess, 'run'):
                worker.worker(root, op, fd, root/'state')
            doc = json.loads((dest/'status.json').read_text())
            self.assertEqual(doc['state'], 'SUCCEEDED', doc)
            self.assertTrue(doc['backup_verification']['ok'])
            self.assertEqual(doc['backup_verification']['archive_sha256'],
                             backup.sha256_file(archive))
            fd2 = worker.lock(root); self.assertIsNotNone(fd2); os.close(fd2)

    def test_archive_stability_rejects_in_place_growth(self):
        import os
        worker = load('prepare_archive_metadata', 'lib/upgrade_prepare.py')
        with tempfile.TemporaryDirectory() as tmp:
            archive = Path(tmp) / 'backup.tar'
            archive.write_bytes(b'12345678')
            before = archive.stat()
            fd = os.open(archive, os.O_RDONLY)
            try:
                evidence = {'path': str(archive),
                            'archive_dev': before.st_dev,
                            'archive_ino': before.st_ino,
                            'archive_size': before.st_size,
                            'archive_mtime_ns': before.st_mtime_ns}
                worker._check_archive_unchanged(fd, evidence)
                # Same inode, grown in place.  fd and path agree with each
                # other, so only the verification-time size/mtime catch this.
                archive.write_bytes(b'1234567890123456789')
                after = archive.stat()
                self.assertEqual((after.st_dev, after.st_ino),
                                 (before.st_dev, before.st_ino))
                with self.assertRaisesRegex(ValueError, 'backup archive changed'):
                    worker._check_archive_unchanged(fd, evidence)
            finally:
                os.close(fd)

    def test_start_refuses_without_pid_namespace(self):
        import uuid
        worker = load('prepare_start_refusal', 'lib/upgrade_prepare.py')
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); root.chmod(0o700)
            helper = root / 'helper'; helper.write_text('#!/bin/bash\nexit 0\n')
            with patch.object(worker, 'lifecycle_available', return_value=False), \
                 patch.object(worker.subprocess, 'Popen') as popen:
                doc = worker.start(root, str(uuid.uuid4()),
                                   {'node_id': 'n', 'instance_id': 'i', 'source_version': '0.5.0'},
                                   helper, 30)
            self.assertEqual((doc['state'], doc['code']), ('FAILED', 'LIFECYCLE_UNAVAILABLE'))
            popen.assert_not_called()
            self.assertFalse((root / doc['operation_id'] / 'worker.log').exists())
    def test_worker_deadline_guard_covers_blocked_verification(self):
        import os
        import time
        with tempfile.TemporaryDirectory() as tmp:
            worker, root, op, fd, dest, archive = self._fixture(tmp)
            deadline = time.monotonic() + 1.0
            pid = os.fork()
            if pid == 0:
                try:
                    with patch.object(worker, '_verify_backup',
                                      side_effect=lambda *a, **k: time.sleep(10)), \
                         patch.object(worker, 'BACKUP_ROOT', root/'backups'), \
                         patch.object(worker.os, 'nice'), \
                         patch.object(worker.subprocess, 'run'):
                        os.environ['VCL_PREPARE_DEADLINE_MONO'] = repr(deadline)
                        worker.worker(root, op, fd, root/'state')
                finally:
                    os._exit(0)
            os.close(fd)
            began = time.monotonic()
            os.waitpid(pid, 0)
            elapsed = time.monotonic() - began
            doc = json.loads((dest/'status.json').read_text())
            self.assertEqual((doc['state'], doc['code']),
                             ('CANCELLED', 'PREPARATION_DEADLINE'), doc)
            self.assertEqual(doc.get('deadline_owner'), 'worker_guard')
            self.assertNotIn(doc['state'], ('SUCCEEDED', 'RUNNING'))
            self.assertLess(elapsed, 8)
            fd2 = worker.lock(root)
            self.assertIsNotNone(fd2)
            os.close(fd2)

    def test_worker_deadline_guard_survives_status_write_failure(self):
        import errno
        import os
        import signal
        import time
        with tempfile.TemporaryDirectory() as tmp:
            worker, root, op, fd, dest, archive = self._fixture(tmp)
            pid_file = root / 'helper.pid'
            helper = root / 'helper'
            helper.write_text(
                '#!/bin/bash\n'
                'echo $$ > "$VCL_TEST_HELPER_PID"\n'
                'sleep 30\n')
            helper.chmod(0o755)
            os.environ['VCL_TEST_HELPER_PID'] = str(pid_file)
            deadline = time.monotonic() + 4.0
            events = root / 'guard-events'
            real_save = worker.save
            guard_failed = {'value': False}

            def save_or_fail(target, document):
                # Fail the guard's diagnostic write once.  Later writes (the
                # main thread's final CANCELLED record) succeed, proving the
                # event was published before the failed save.
                if document.get('deadline_owner') == 'worker_guard' and not guard_failed['value']:
                    guard_failed['value'] = True
                    with events.open('a') as out:
                        out.write('save-enospc\n')
                    raise OSError(errno.ENOSPC, 'No space left on device')
                return real_save(target, document)

            real_killpg = worker.os.killpg

            def record_killpg(pgid, sig):
                with events.open('a') as out:
                    out.write(f'killpg {sig}\n')
                return real_killpg(pgid, sig)

            pid = os.fork()
            if pid == 0:
                try:
                    with patch.object(worker, 'save', side_effect=save_or_fail), \
                         patch.object(worker.os, 'killpg', side_effect=record_killpg), \
                         patch.object(worker, 'BACKUP_ROOT', root/'backups'), \
                         patch.object(worker.os, 'nice'), \
                         patch.object(worker.subprocess, 'run'):
                        os.environ['VCL_PREPARE_DEADLINE_MONO'] = repr(deadline)
                        worker.worker(root, op, fd, root/'state')
                finally:
                    os._exit(0)
            os.close(fd)
            began = time.monotonic()
            child_status = None
            while time.monotonic() - began < 8:
                got, status = os.waitpid(pid, os.WNOHANG)
                if got == pid:
                    child_status = status
                    break
                time.sleep(0.05)
            elapsed = time.monotonic() - began
            if child_status is None:
                os.kill(pid, signal.SIGKILL)
                os.waitpid(pid, 0)
            try:
                helper_pid = int(pid_file.read_text())
                try:
                    os.killpg(helper_pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
            except (OSError, ValueError):
                pass
            self.assertIsNotNone(child_status, 'deadline guard did not exit after status write failure')
            self.assertLess(elapsed, 8)
            doc = json.loads((dest/'status.json').read_text())
            self.assertEqual((doc.get('state'), doc.get('code')),
                             ('CANCELLED', 'PREPARATION_DEADLINE'), doc)
            recorded = events.read_text()
            self.assertEqual(recorded.count('save-enospc'), 1)
            self.assertIn('killpg 15', recorded)

    def test_worker_with_bad_helper_does_not_succeed(self):
        import os
        with tempfile.TemporaryDirectory() as tmp:
            worker, root, op, fd, dest, archive = self._fixture(tmp)
            (root/'helper').write_text('#!/bin/bash\nexit 3\n')
            with patch.object(worker, 'BACKUP_ROOT', root/'backups'), \
                 patch.object(worker.os, 'nice'), \
                 patch.object(worker.subprocess, 'run'):
                worker.worker(root, op, fd, root/'state')
            doc = json.loads((dest/'status.json').read_text())
            self.assertEqual(doc['state'], 'FAILED')
            self.assertFalse(doc.get('checkpoint'))

    def test_read_status_converges_after_lock_release(self):
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
            doc=worker.read_status(dest/'status.json')
            self.assertEqual((doc['state'],doc['code']),('FAILED','WORKER_LOST'))

    def test_read_status_keeps_terminal_state_published_before_lock(self):
        import os
        import uuid
        worker = load('prepare_worker_terminal_race', 'lib/upgrade_prepare.py')
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); root.chmod(0o700)
            op = str(uuid.uuid4()); dest = root/op; dest.mkdir()
            status = dest/'status.json'
            worker.save(status, {'state':'RUNNING','operation_id':op,'binding':{}})
            real_lock = worker.lock

            def publish_success_then_lock(root_path):
                # Simulate a worker that publishes SUCCEEDED and releases the
                # lock after the query's first read but before it locks.
                worker.save(status, {'state':'SUCCEEDED','operation_id':op,
                                     'binding':{},'checkpoint':{'ok':True}})
                return real_lock(root_path)

            with patch.object(worker, 'lock', side_effect=publish_success_then_lock):
                doc = worker.read_status(status)
            self.assertEqual(doc['state'], 'SUCCEEDED', doc)
            self.assertEqual(json.loads(status.read_text())['state'], 'SUCCEEDED')

if __name__ == '__main__':
    unittest.main()
