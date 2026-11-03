"""Local cache limits reject writes without deleting history or advancing cursors."""
import argparse
from contextlib import closing
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import time
from unittest import mock
import unittest

ROOT = Path(__file__).resolve().parents[1]


def load(name, path):
    spec=importlib.util.spec_from_file_location(name,ROOT/path)
    module=importlib.util.module_from_spec(spec);sys.modules[name]=module;spec.loader.exec_module(module)
    return module


storage=load('capacity_storage','lib/storage_v5.py')
backup=load('capacity_backup','lib/vincula-backup.py')


class CacheCapacity(unittest.TestCase):
    def test_public_cache_schema_positive_and_negative_fixtures(self):
        import test_monitor_schema as evaluator
        schema=json.loads((ROOT/'schemas/cache-status/v1.schema.json').read_text())
        previous=evaluator.SCHEMA
        try:
            evaluator.SCHEMA=schema
            for path in (ROOT/'tests/fixtures/schemas/cache-status').glob('*.json'):
                doc=json.loads(path.read_text())
                if 'invalid' in path.name:
                    with self.assertRaises(AssertionError):
                        evaluator.validate(doc,schema)
                else:
                    evaluator.validate(doc,schema)
        finally:
            evaluator.SCHEMA=previous

    def test_status_absent_does_not_create_anything(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'absent'/'fleet.db'
            status=storage.cache_status(path,dict(storage.DEFAULT_POLICY))
            self.assertEqual(status['state'],'ABSENT')
            self.assertFalse(path.parent.exists())

    def test_limit_rolls_back_page_and_keeps_previous_cursor(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'fleet.db'
            with closing(sqlite3.connect(path, factory=storage.CacheConnection)) as conn:
                conn.execute('CREATE TABLE meta(key TEXT PRIMARY KEY,value TEXT)')
                conn.execute("INSERT INTO meta VALUES('cursor','1')")
                conn.execute('CREATE TABLE audit(payload BLOB)');conn.commit()
                used=conn.execute('PRAGMA page_count').fetchone()[0]*conn.execute('PRAGMA page_size').fetchone()[0]
                policy=dict(storage.DEFAULT_POLICY,max_bytes=used+16384,min_free_bytes=0)
                storage.guard_cache(conn,path,policy)
                conn.execute('BEGIN IMMEDIATE')
                try:
                    conn.execute('INSERT INTO audit VALUES(?)',(b'x'*100000,))
                    conn.execute("UPDATE meta SET value='2' WHERE key='cursor'")
                    conn.commit()
                except storage.CapacityError as exc:
                    self.assertEqual(exc.code,'CACHE_LIMIT_REACHED');conn.rollback()
                else:
                    self.fail('oversize page was accepted')
                self.assertEqual(conn.execute("SELECT value FROM meta WHERE key='cursor'").fetchone()[0],'1')
                self.assertEqual(conn.execute('SELECT COUNT(*) FROM audit').fetchone()[0],0)

    def test_low_disk_and_oversize_existing_db_are_readable(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'fleet.db'
            with closing(sqlite3.connect(path)) as conn:
                conn.execute('CREATE TABLE meta(key TEXT,value TEXT)')
                conn.execute("INSERT INTO meta VALUES('schema_version','5')");conn.commit()
            before=hashlib.sha256(path.read_bytes()).digest()
            policy=dict(storage.DEFAULT_POLICY,max_bytes=16384)
            with mock.patch.object(storage.shutil,'disk_usage') as disk:
                disk.return_value.free=0
                self.assertEqual(storage.cache_status(path,policy)['error_code'],'DISK_SPACE_LOW')
            self.assertEqual(hashlib.sha256(path.read_bytes()).digest(),before)
            with closing(sqlite3.connect(path.resolve().as_uri()+'?mode=ro',uri=True)) as conn:
                self.assertEqual(conn.execute('SELECT value FROM meta').fetchone()[0],'5')

    def test_transaction_reserve_is_reported_without_double_reserving_at_commit(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'fleet.db'
            with closing(sqlite3.connect(path,factory=storage.CacheConnection)) as conn:
                conn.execute('CREATE TABLE meta(key TEXT,value TEXT)');conn.commit()
                size=path.stat().st_size
                policy=dict(storage.DEFAULT_POLICY,min_free_bytes=1024)
                with mock.patch.object(storage.shutil,'disk_usage') as disk:
                    disk.return_value.free=size//2+1024
                    report=storage.cache_status(path,policy)
                    self.assertEqual(report['error_code'],'DISK_SPACE_LOW')
                    self.assertEqual(report['required_free_bytes'],size+1024)
                    disk.return_value.free=size+2048
                    storage.guard_cache(conn,path,policy)
                    conn.execute('BEGIN IMMEDIATE')
                    conn.execute("INSERT INTO meta VALUES('synthetic','value')")
                    disk.return_value.free=1025
                    conn.commit()  # journal has already been allocated; floor still holds
                self.assertEqual(conn.execute('SELECT COUNT(*) FROM meta').fetchone()[0],1)

    def test_initial_lock_failure_has_node_rows_and_is_bounded(self):
        fleet=load('capacity_fleet','lib/vincula-fleet.py')
        targets=[{'name':'synthetic','node_id':'11111111-1111-4111-8111-111111111111'}]
        with mock.patch.object(fleet,'open_fleet_db',side_effect=sqlite3.OperationalError('database is locked')):
            before=time.monotonic()
            conn,failure=fleet._open_sync_cache({'budget':.05},targets,'sync_full')
        self.assertIsNone(conn);self.assertLess(time.monotonic()-before,.5)
        code,doc=failure
        self.assertEqual(code,2);self.assertEqual(doc['state'],'PARTIAL')
        self.assertEqual(doc['nodes'][0]['error_phase'],'cache_open')
        self.assertEqual(doc['nodes'][0]['error_code'],'DATABASE_ERROR')

    def test_real_exclusive_lock_is_bounded_before_any_ssh(self):
        fleet=load('locked_capacity_fleet','lib/vincula-fleet.py')
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'fleet.db'
            with closing(sqlite3.connect(path)) as conn:
                conn.executescript(fleet.FLEET_DB_DDL)
                conn.execute("INSERT INTO meta VALUES('schema_version','5')")
                conn.execute("INSERT INTO meta VALUES('fleet_id','')");conn.commit()
            with closing(sqlite3.connect(path, isolation_level=None)) as locker:
                locker.execute('BEGIN EXCLUSIVE')
                with mock.patch.object(fleet,'fleet_db_path',return_value=path), mock.patch.object(fleet,'_ensure_fleet_home'), mock.patch.object(fleet,'cache_policy_path',return_value=Path(directory)/'policy.json'):
                    before=time.monotonic()
                    conn,failure=fleet._open_sync_cache({'budget':.05},[{'name':'test','node_id':'synthetic'}],'sync')
                    elapsed=time.monotonic()-before
                locker.rollback()
            self.assertIsNone(conn);self.assertLess(elapsed,.25)
            self.assertEqual(failure[0],2)
            self.assertEqual(failure[1]['nodes'][0]['error_phase'],'cache_open')

    def test_backup_verify_rejects_missing_restore_components(self):
        content=b'{}'
        manifest={'schema_version':1,'secret_bearing':False,'encryption':'none','included_components':['state.json'],
                  'files':[{'path':'state.json','sha256':hashlib.sha256(content).hexdigest()}]}
        result=backup._verify_members({'manifest.json':json.dumps(manifest).encode(),'state.json':content},Path('synthetic.tar.gz'))
        self.assertFalse(result['ok'])

    def test_cache_cli_and_stats_wrong_path_leave_no_database(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            env=dict(os.environ,VCL_FLEET_HOME=str(root/'home'),VCL_FLEET_LOCAL_STATE=str(root/'state'),XDG_CONFIG_HOME=str(root/'config'))
            result=subprocess.run([sys.executable,'-B',str(ROOT/'bin/vcl-fleet'),'cache','status','--json'],env=env,capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stderr)
            self.assertEqual(json.loads(result.stdout)['state'],'ABSENT')
            self.assertFalse((root/'home').exists())
            missing=root/'typo.db'
            result=subprocess.run([sys.executable,'-B',str(ROOT/'lib/vincula-stats.py'),'--db',str(missing),'--users',str(root/'users.json'),'--mode','summary','--days','7'],env=env,capture_output=True,text=True)
            self.assertNotEqual(result.returncode,0)
            self.assertFalse(missing.exists())
