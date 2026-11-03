"""Synthetic durability regressions; never opens production databases."""
import hashlib
import importlib.util
from pathlib import Path
import sqlite3
import sys
import tempfile
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
