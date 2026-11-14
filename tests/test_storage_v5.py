"""Synthetic durability regressions; never opens production databases."""
import hashlib
import importlib.util
from pathlib import Path
import sqlite3
import sys
import tempfile
import time
from datetime import datetime, timedelta, timezone
from unittest import mock
import unittest
from contextlib import closing

ROOT = Path(__file__).resolve().parents[1]


def load(name, relative):
    spec = importlib.util.spec_from_file_location(name, ROOT / relative)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


accountd = load('storage_test_accountd', 'lib/vincula-accountd.py')
audit = load('storage_test_audit', 'lib/vincula-audit.py')
store = accountd._STORE
USER = '11111111-1111-4111-8111-111111111111'


def database(path=':memory:', version='5'):
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    conn.executescript(accountd.SCHEMA_SQL)
    accountd.meta_set(conn, 'schema_version', version)
    conn.commit()
    return conn


def insert(conn, when, *, closed=None):
    conn.execute('INSERT INTO connections(connection_id,generation,user_id,node_id,user_tag,started_at,last_seen_at,closed_at,destination_host,upload_bytes,download_bytes,export_seq) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)',
                 ('synthetic',0,USER,'node','alice',when,when,closed,'example.test',100,200,1 if closed else None))
    conn.commit()


class DurableStorage(unittest.TestCase):
    def test_sqlite_failure_classification_without_python311_attributes(self):
        for message in ('file is not a database','database disk image is malformed','database schema is corrupt'):
            error=sqlite3.DatabaseError(message)
            self.assertFalse(hasattr(error,'sqlite_errorcode'))
            self.assertEqual(store.sqlite_failure_state(error),'CORRUPT')
        self.assertEqual(store.sqlite_failure_state(sqlite3.OperationalError('no such table: synthetic')),'SCHEMA_MISMATCH')
        self.assertEqual(store.sqlite_failure_state(sqlite3.OperationalError('database is locked')),'UNKNOWN')

    def test_nanoseconds_are_normalized_before_minimum_runtime_parser(self):
        import re
        class MinimumDatetime(datetime):
            @classmethod
            def fromisoformat(cls,value):
                fraction=re.search(r"\.(\d+)(?=[+-])",value)
                if fraction and len(fraction[1]) not in (3,6):
                    raise ValueError('minimum-runtime ISO parser')
                return super().fromisoformat(value)
        value='2026-10-26T23:30:00.123456789-07:00'
        expected='2026-10-27T06:30:00.123456Z'
        with mock.patch.object(store,'datetime',MinimumDatetime):
            self.assertEqual(store.utc(value),expected)
        with mock.patch.object(audit,'datetime',MinimumDatetime):
            self.assertEqual(audit.parse_rfc3339(value),expected)

    def test_utc_is_fixed_precision_and_rejects_naive(self):
        self.assertEqual(store.utc('2026-10-26T23:30:00.123456789-07:00'), '2026-10-27T06:30:00.123456Z')
        self.assertEqual(store.utc('2026-10-27T08:00:00+08:00'), '2026-10-27T00:00:00.000000Z')
        for value in ('2026-10-27T00:00:00', 'invalid', True):
            with self.assertRaises(ValueError):
                store.utc(value)

    def test_daily_survives_raw_and_is_independently_expired(self):
        conn = database()
        old = store.utc(datetime.now(timezone.utc)-timedelta(days=3))
        insert(conn, old, closed=old)
        accountd.rollup_daily_usage(conn)
        accountd.rollup_daily_usage(conn)
        self.assertEqual(tuple(conn.execute('SELECT upload_bytes,download_bytes,connection_count FROM daily_usage').fetchone()), (100,200,1))
        accountd.apply_retention(conn, 1, 365)
        self.assertEqual(conn.execute('SELECT COUNT(*) FROM connections').fetchone()[0], 0)
        self.assertEqual(conn.execute('SELECT COUNT(*) FROM daily_contributions').fetchone()[0], 0)
        accountd.rollup_daily_usage(conn)
        self.assertEqual(conn.execute('SELECT upload_bytes FROM daily_usage').fetchone()[0], 100)
        accountd.apply_retention(conn, 1, 1)
        accountd.rollup_daily_usage(conn)
        self.assertEqual(conn.execute('SELECT COUNT(*) FROM daily_usage').fetchone()[0], 0)
        conn.close()

    def test_audit_exact_microsecond_boundary(self):
        conn = database()
        started = store.utc('2026-10-26T23:30:00.123456-07:00')
        insert(conn, started)
        common = dict(query_from='2026-10-27T06:30:00Z')
        self.assertEqual(len(audit.query_audit(conn, query_to='2026-10-27T06:30:00.123456Z', **common)), 0)
        self.assertEqual(len(audit.query_audit(conn, query_to='2026-10-27T06:30:00.123457Z', **common)), 1)
        conn.close()

    def test_changed_contribution_and_failure_are_atomic(self):
        conn = database()
        insert(conn, '2026-10-26T23:30:00-07:00')
        accountd.rollup_daily_usage(conn)
        conn.commit()
        conn.execute('UPDATE connections SET upload_bytes=150')
        conn.commit()
        with mock.patch.object(store, '_adjust', side_effect=sqlite3.OperationalError('injected')):
            with self.assertRaises(sqlite3.Error):
                accountd.rollup_daily_usage(conn)
        self.assertEqual(conn.execute('SELECT upload_bytes FROM daily_usage').fetchone()[0], 100)
        accountd.rollup_daily_usage(conn)
        self.assertEqual(tuple(conn.execute('SELECT date,upload_bytes,connection_count FROM daily_usage').fetchone()), ('2026-10-27',150,1))
        conn.close()

    def test_unknown_tag_keeps_existing_live_generation(self):
        conn = database()
        accountd.TAG_TO_USER_ID = {'alice':USER}
        item = {'id':'synthetic','chains':['acct/alice'],'start':'2026-10-27T00:00:00Z','upload':100,'download':0}
        known = accountd.apply_poll_delta(conn, accountd.decode_clash_connections_payload({'connections':[item]}), {})
        conn.commit()
        accountd.TAG_TO_USER_ID = {}
        snapshot = accountd.decode_clash_connections_payload({'connections':[item]})
        known = accountd.apply_poll_delta(conn, snapshot, known)
        self.assertEqual(accountd.close_stale_open_connections(conn, list(snapshot.live_ids)), 0)
        accountd.TAG_TO_USER_ID = {'alice':USER}
        item['upload'] = 300
        accountd.apply_poll_delta(conn, accountd.decode_clash_connections_payload({'connections':[item]}), known)
        self.assertEqual(conn.execute('SELECT COUNT(*) FROM connections').fetchone()[0], 1)
        self.assertEqual(conn.execute('SELECT upload_bytes FROM connections').fetchone()[0], 200)
        conn.close()

    def test_staged_migration_preserves_ids_legacy_and_verified_backup(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'accounting.db'
            conn = database(path, '4')
            insert(conn, '2026-10-26T23:30:00-07:00', closed='2026-10-27T07:00:00Z')
            conn.execute("INSERT INTO daily_usage VALUES('2026-10-26',?,'alice','example.test',100,200,1)", (USER,))
            conn.commit();conn.close()
            backup = store.staged_migrate(path, accountd.migrate_schema)
            with closing(sqlite3.connect(backup)) as old:
                self.assertEqual(old.execute('PRAGMA integrity_check').fetchone()[0], 'ok')
                self.assertEqual(old.execute("SELECT value FROM meta WHERE key='schema_version'").fetchone()[0], '4')
            with closing(sqlite3.connect(path)) as new:
                self.assertEqual(new.execute("SELECT value FROM meta WHERE key='schema_version'").fetchone()[0], '5')
                self.assertEqual(tuple(new.execute('SELECT event_id,export_seq,started_at FROM connections').fetchone()), (1,1,'2026-10-27T06:30:00.000000Z'))
                self.assertEqual(new.execute('SELECT COUNT(*) FROM legacy_daily_usage').fetchone()[0], 1)

    def test_failed_migration_never_activates_candidate(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'accounting.db'
            conn = database(path, '4');insert(conn, 'invalid-no-timezone');conn.close()
            before = hashlib.sha256(path.read_bytes()).digest()
            with self.assertRaises(ValueError):
                store.staged_migrate(path, accountd.migrate_schema)
            self.assertEqual(hashlib.sha256(path.read_bytes()).digest(), before)
            with mock.patch.object(store.shutil, 'disk_usage') as disk:
                disk.return_value.free = 0
                with self.assertRaisesRegex(sqlite3.OperationalError, 'DISK_SPACE_LOW'):
                    store.staged_migrate(path, accountd.migrate_schema)

    def test_fleet_legacy_only_totals_are_snapshot_not_verified_usage(self):
        fleet = load('storage_coverage_fleet', 'lib/vincula-fleet.py')
        conn = sqlite3.connect(':memory:')
        self.addCleanup(conn.close)
        conn.row_factory = sqlite3.Row
        conn.executescript(fleet.FLEET_DB_DDL)
        fleet.fleet_db_meta_set(conn, 'schema_version', '4')
        conn.execute("INSERT INTO daily_usage(date,node_id,user_id,user_tag,destination_host,upload_bytes,download_bytes,connection_count) VALUES('2026-01-01','old-node',?,'alice','example.test',100,200,1)", (USER,))
        conn.commit()
        fleet._migrate_fleet_db_to_5(conn)
        self.assertEqual(conn.execute('SELECT COUNT(*) FROM daily_usage').fetchone()[0], 0)
        self.assertEqual(conn.execute('SELECT SUM(upload_bytes) FROM legacy_daily_usage').fetchone()[0], 100)
        coverage = fleet._STORAGE.history_coverage(conn)
        self.assertEqual(coverage['legacy_at_snapshot'], {'rows':1, 'from_date':'2026-01-01','through_date':'2026-01-01'})
        self.assertEqual(coverage['raw_at_snapshot']['rows'], 0)
        self.assertEqual(coverage['gaps'][0]['kind'], 'LEGACY_DAILY_UNVERIFIED')
        self.assertFalse(coverage['missing_history_recovered'])

    def test_coverage_contract_and_pruned_history_are_explicit(self):
        import json
        import test_monitor_schema as evaluator
        schema = json.loads((ROOT/'schemas/history-coverage/v1.schema.json').read_text())
        conn = database()
        self.addCleanup(conn.close)
        insert(conn,'2026-01-01T00:00:00Z',closed='2026-01-01T01:00:00Z')
        accountd.meta_set(conn,'history_coverage',json.dumps(store.coverage_snapshot(conn,'connections',status='NEW_DATABASE')))
        accountd.rollup_daily_usage(conn)
        accountd.apply_retention(conn,1,365)
        coverage=store.history_coverage(conn)
        evaluator.validate(coverage,schema)
        self.assertEqual(coverage['raw_pruned_max_export_seq'],1)
        self.assertEqual(coverage['gaps'][-1],{'kind':'RAW_EVENTS_PRUNED','through_export_seq':1})
        self.assertEqual(coverage['completeness'],'NOT_PROVEN')
        for path in (ROOT/'tests/fixtures/schemas/history-coverage').glob('*.json'):
            value=json.loads(path.read_text())
            if 'invalid' in path.name:
                with self.assertRaises(AssertionError):
                    evaluator.validate(value,schema)
            else:
                evaluator.validate(value,schema)

    def test_legacy_coverage_does_not_require_optional_closed_column(self):
        conn=sqlite3.connect(':memory:')
        self.addCleanup(conn.close)
        conn.execute('CREATE TABLE audit_events(started_at TEXT,last_seen_at TEXT)')
        conn.execute("INSERT INTO audit_events VALUES('2026-01-01T00:00:00.000000Z','2026-01-01T01:00:00.000000Z')")
        coverage=store.coverage_snapshot(conn,'audit_events')
        self.assertEqual(coverage['raw_at_snapshot'],{'rows':1,'from':'2026-01-01T00:00:00.000000Z','through':'2026-01-01T01:00:00.000000Z'})

    def test_concurrent_migrations_activate_once_and_preserve_history(self):
        from concurrent.futures import ThreadPoolExecutor
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'accounting.db'
            conn=database(path,'4');insert(conn,'2026-10-27T00:00:00Z');conn.close()
            with ThreadPoolExecutor(max_workers=2) as pool:
                results=list(pool.map(lambda _:store.staged_migrate(path,accountd.migrate_schema),range(2)))
            self.assertEqual(sum(value is not None for value in results),1)
            with closing(sqlite3.connect(path)) as conn:
                self.assertEqual(conn.execute('SELECT COUNT(*) FROM connections').fetchone()[0],1)
                self.assertEqual(conn.execute("SELECT value FROM meta WHERE key='schema_version'").fetchone()[0],'5')

    def test_source_write_during_conversion_aborts_activation(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'accounting.db'
            conn=database(path,'4');insert(conn,'2026-10-27T00:00:00Z');conn.close()
            def convert(candidate):
                accountd.migrate_schema(candidate)
                with closing(sqlite3.connect(path)) as writer:
                    writer.execute('UPDATE connections SET upload_bytes=101');writer.commit()
            with self.assertRaisesRegex(sqlite3.OperationalError,'source changed'):
                store.staged_migrate(path,convert)
            with closing(sqlite3.connect(path)) as conn:
                self.assertEqual(conn.execute('SELECT upload_bytes FROM connections').fetchone()[0],101)
                self.assertEqual(conn.execute("SELECT value FROM meta WHERE key='schema_version'").fetchone()[0],'4')

    def test_migration_preflight_failure_never_leaves_an_unverified_backup(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'accounting.db'
            conn=database(path,'4');conn.close()
            original=path.read_bytes()
            with self.assertRaisesRegex(sqlite3.OperationalError,'BUDGET_EXHAUSTED'):
                store.staged_migrate(path,accountd.migrate_schema,deadline=time.monotonic()-1)
            self.assertEqual(path.read_bytes(),original)
            self.assertEqual(list(path.parent.glob('*.pre-v5-*.db')),[])
            path.write_bytes(b'not a database')
            with self.assertRaises(sqlite3.DatabaseError):
                store.staged_migrate(path,accountd.migrate_schema)
            self.assertEqual(path.read_bytes(),b'not a database')
            self.assertEqual(list(path.parent.glob('*.pre-v5-*.db')),[])

    def test_staged_migration_cleans_orphaned_zero_byte_stubs_and_stage_temps(self):
        with tempfile.TemporaryDirectory() as directory:
            d = Path(directory)
            path = d / 'accounting.db'
            conn = database(path, '4'); insert(conn, '2026-10-27T00:00:00Z'); conn.close()
            stage_zero = d / '.accounting.db.v5-orphan0.db'
            stage_partial = d / '.accounting.db.v5-orphan1.db'
            backup_zero = d / 'accounting.db.pre-v5-orphan0.db'
            backup_valid = d / 'accounting.db.pre-v5-valid.db'
            stage_zero.write_bytes(b'')
            stage_partial.write_bytes(b'partial')
            backup_zero.write_bytes(b'')
            backup_valid.write_bytes(b'prior-backup')
            created_backup = store.staged_migrate(path, accountd.migrate_schema)
            self.assertIsNotNone(created_backup)
            self.assertFalse(stage_zero.exists())
            self.assertFalse(stage_partial.exists())
            self.assertFalse(backup_zero.exists())
            self.assertTrue(backup_valid.exists())
            self.assertTrue(Path(created_backup).is_file())

    def test_accountd_migrate_only_upgrades_schema_and_handles_missing_db(self):
        import subprocess
        with tempfile.TemporaryDirectory() as directory:
            d = Path(directory)
            missing = d / 'missing.db'
            proc_missing = subprocess.run(
                [sys.executable, '-I', str(ROOT / 'lib/vincula-accountd.py'), '--migrate-only', '--db', str(missing)],
                capture_output=True, text=True,
            )
            self.assertEqual(proc_missing.returncode, 0, proc_missing.stderr)
            self.assertFalse(missing.exists())
            path = d / 'accounting.db'
            conn = database(path, '4'); insert(conn, '2026-10-27T00:00:00Z'); conn.close()
            proc = subprocess.run(
                [sys.executable, '-I', str(ROOT / 'lib/vincula-accountd.py'), '--migrate-only', '--db', str(path)],
                capture_output=True, text=True,
            )
            self.assertEqual(proc.returncode, 0, proc.stderr)
            with closing(sqlite3.connect(path)) as upgraded:
                self.assertEqual(upgraded.execute("SELECT value FROM meta WHERE key='schema_version'").fetchone()[0], '5')
