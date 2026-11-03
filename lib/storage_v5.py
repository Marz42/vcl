"""Shared 0.5.5 time, staged SQLite migration and durable rollup primitives.

Stdlib only. No service, network, environment credentials or implicit repair.
"""
from datetime import datetime, timezone
from contextlib import closing
import hashlib
import json
import os
from pathlib import Path
import shutil
import sqlite3
import tempfile
import time

MIN_FREE = 512 * 1024 * 1024
DEFAULT_POLICY = {"schema_version":1, "max_bytes":8*1024**3, "warning_fraction":.8, "min_free_bytes":MIN_FREE}
NODE_DDL = """
CREATE TABLE IF NOT EXISTS daily_contributions (
 event_id INTEGER PRIMARY KEY, date TEXT NOT NULL, user_id TEXT NOT NULL,
 user_tag TEXT, destination_host TEXT NOT NULL,
 upload_bytes INTEGER NOT NULL, download_bytes INTEGER NOT NULL
);
"""


def utc(value):
    """Canonical, lexically sortable RFC3339 UTC, preserving microseconds."""
    if isinstance(value, bool):
        raise ValueError("invalid timestamp")
    if isinstance(value, (int, float)):
        when = datetime.fromtimestamp(value, timezone.utc)
    elif isinstance(value, datetime):
        when = value
    elif isinstance(value, str):
        try:
            when = datetime.fromisoformat(value.replace("Z", "+00:00").replace("z", "+00:00"))
        except ValueError:
            raise ValueError("invalid RFC3339 timestamp") from None
    else:
        raise ValueError("invalid timestamp")
    if when.tzinfo is None:
        raise ValueError("timestamp requires an explicit timezone")
    return when.astimezone(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")


def normalize_table(conn, table, columns):
    available = {r[1] for r in conn.execute(f"PRAGMA table_info({table})")}
    columns = [c for c in columns if c in available]
    if not columns:
        return
    rows = conn.execute(f"SELECT rowid,{','.join(columns)} FROM {table}")
    while True:
        chunk = rows.fetchmany(1000)
        if not chunk:
            break
        values = []
        for row in chunk:
            values.append(tuple(None if v is None else utc(v) for v in tuple(row)[1:]) + (row[0],))
        conn.executemany(f"UPDATE {table} SET " + ','.join(c+'=?' for c in columns) + " WHERE rowid=?", values)


def staged_migrate(path, converter, *, minimum_free=MIN_FREE, deadline=None):
    """Offline/cooperatively locked migration; preserve a verified source backup.

    Caller holds its normal writer lock or has stopped its sole collector.
    A live writer detected during conversion aborts activation. Read-only callers
    never call this function. Backups deliberately survive success and failure.
    """
    path = Path(path)
    needed = path.stat().st_size * 3 + minimum_free
    if shutil.disk_usage(path.parent).free < needed:
        raise sqlite3.OperationalError("DISK_SPACE_LOW: insufficient migration reserve")
    backup_fd, backup_name = tempfile.mkstemp(prefix=path.name+'.pre-v5-', suffix='.db', dir=path.parent)
    os.close(backup_fd)
    stage_fd, stage_name = tempfile.mkstemp(prefix='.'+path.name+'.v5-', suffix='.db', dir=path.parent)
    os.close(stage_fd)
    def check_deadline(*_args):
        if deadline is not None and time.monotonic() >= deadline:
            raise sqlite3.OperationalError('BUDGET_EXHAUSTED: migration deadline reached')
    source = sqlite3.connect(str(path), timeout=max(.001, min(1, deadline-time.monotonic())) if deadline else 1)
    try:
        if source.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
            raise sqlite3.DatabaseError('migration source integrity check failed')
        # A WAL must not survive activation beside a different database file.
        result = source.execute('PRAGMA wal_checkpoint(TRUNCATE)').fetchone()
        if result and result[0]:
            raise sqlite3.OperationalError('migration source is busy')
        source.execute('PRAGMA journal_mode=DELETE')
        version = source.execute('PRAGMA data_version').fetchone()[0]
        with closing(sqlite3.connect(backup_name)) as backup:
            source.backup(backup, pages=1024, progress=check_deadline)
            if backup.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
                raise sqlite3.DatabaseError('migration backup integrity check failed')
        os.chmod(backup_name, 0o600)
        with closing(sqlite3.connect(stage_name)) as stage:
            stage.row_factory = sqlite3.Row
            source.backup(stage, pages=1024, progress=check_deadline)
            if deadline is not None:
                stage.set_progress_handler(lambda: int(time.monotonic() >= deadline), 1000)
            converter(stage)
            stage.execute("INSERT OR REPLACE INTO meta(key,value) VALUES('pre_v5_backup',?)", (backup_name,))
            stage.commit()
            if stage.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
                raise sqlite3.DatabaseError('migration candidate integrity check failed')
        if source.execute('PRAGMA data_version').fetchone()[0] != version:
            raise sqlite3.OperationalError('migration source changed; stop all writers before retrying')
        check_deadline()
        source.close()
        os.chmod(stage_name, 0o600)
        os.replace(stage_name, path)
        return backup_name
    finally:
        source.close()
        if os.path.exists(stage_name):
            os.unlink(stage_name)


def _adjust(conn, contribution, sign):
    date, user_id, user_tag, host, up, down = contribution
    conn.execute("""INSERT INTO daily_usage(date,user_id,user_tag,destination_host,
        upload_bytes,download_bytes,connection_count) VALUES(?,?,?,?,?,?,?)
        ON CONFLICT(date,user_id,destination_host) DO UPDATE SET
        user_tag=excluded.user_tag,
        upload_bytes=daily_usage.upload_bytes+excluded.upload_bytes,
        download_bytes=daily_usage.download_bytes+excluded.download_bytes,
        connection_count=daily_usage.connection_count+excluded.connection_count""",
        (date, user_id, user_tag, host, sign*up, sign*down, sign))


def rollup(conn):
    """Idempotently replace each raw event's contribution, never erase history."""
    conn.execute('SAVEPOINT durable_daily')
    try:
        conn.execute(NODE_DDL.strip().rstrip(';'))
        cursor = conn.execute("""SELECT event_id,started_at,user_id,user_tag,
            COALESCE(NULLIF(destination_host,''),NULLIF(destination_ip,''),'(unknown)'),
            upload_bytes,download_bytes FROM connections ORDER BY event_id""")
        while True:
            chunk = cursor.fetchmany(1000)
            if not chunk:
                break
            for row in chunk:
                current = (utc(row[1])[:10],) + tuple(row)[2:]
                old = conn.execute('SELECT date,user_id,user_tag,destination_host,upload_bytes,download_bytes FROM daily_contributions WHERE event_id=?', (row[0],)).fetchone()
                if old is not None and tuple(old) == current:
                    continue
                cutoff = conn.execute("SELECT value FROM meta WHERE key='daily_retention_cutoff'").fetchone()
                expired = cutoff is not None and current[0] < cutoff[0]
                if old is not None and conn.execute('SELECT 1 FROM daily_usage WHERE date=? AND user_id=? AND destination_host=?', (old[0],old[1],old[3])).fetchone():
                    _adjust(conn, tuple(old), -1)
                if not expired:
                    _adjust(conn, current, 1)
                conn.execute('INSERT OR REPLACE INTO daily_contributions VALUES(?,?,?,?,?,?,?)', (row[0],)+current)
        conn.execute('DELETE FROM daily_usage WHERE connection_count=0 AND upload_bytes=0 AND download_bytes=0')
        conn.execute('RELEASE durable_daily')
    except BaseException:
        conn.execute('ROLLBACK TO durable_daily')
        conn.execute('RELEASE durable_daily')
        raise


def convert_node(conn):
    conn.execute('CREATE TABLE IF NOT EXISTS legacy_daily_usage AS SELECT * FROM daily_usage')
    normalize_table(conn, 'connections', ('started_at','last_seen_at','closed_at'))
    normalize_table(conn, 'poll_baseline', ('last_seen_at',))
    conn.execute('DELETE FROM daily_usage')
    conn.execute(NODE_DDL.strip().rstrip(';'))
    conn.execute('DELETE FROM daily_contributions')
    rollup(conn)
    legacy = conn.execute('SELECT COUNT(*) FROM legacy_daily_usage').fetchone()[0]
    coverage = {'status':'RAW_RECONSTRUCTED', 'legacy_unverified':bool(legacy),
                'missing_history_recovered':False, 'day_basis':'UTC_CONNECTION_START'}
    conn.execute("INSERT OR REPLACE INTO meta VALUES('history_coverage',?)", (json.dumps(coverage,sort_keys=True),))
    conn.execute("INSERT OR REPLACE INTO meta VALUES('schema_version','5')")
    conn.commit()


class CapacityError(sqlite3.OperationalError):
    def __init__(self, code):
        self.code = code
        super().__init__(code + ': local cache import refused; inspect cache status')


def read_policy(path):
    policy = dict(DEFAULT_POLICY)
    path = Path(path)
    if path.is_file():
        try:
            supplied = json.loads(path.read_text(encoding='utf-8'))
            if not isinstance(supplied, dict) or set(supplied)-set(policy):
                raise ValueError()
            policy.update(supplied)
        except (ValueError, OSError):
            raise ValueError('invalid machine-local cache policy') from None
    if policy['schema_version'] != 1 or any(type(policy[k]) is not int for k in ('max_bytes','min_free_bytes')) or policy['max_bytes'] < 16384 or policy['min_free_bytes'] < 0 or isinstance(policy['warning_fraction'], bool) or not isinstance(policy['warning_fraction'], (int,float)) or not 0 < policy['warning_fraction'] < 1:
        raise ValueError('invalid machine-local cache policy')
    return policy


def cache_status(path, policy, conn=None, *, timeout=.1, deadline=None):
    """Read existing facts only; never create a database, policy or directory."""
    path = Path(path)
    def check_time():
        if deadline is not None and time.monotonic() >= deadline:
            raise CapacityError('BUDGET_EXHAUSTED')
    check_time()
    parent = path.parent
    while not parent.exists() and parent != parent.parent:
        parent = parent.parent
    free = shutil.disk_usage(parent).free
    check_time()
    allocated = path.stat().st_size if path.is_file() else 0
    aux = sum(Path(str(path)+suffix).stat().st_size for suffix in ('-wal','-shm','-journal') if Path(str(path)+suffix).is_file())
    check_time()
    report = {"schema_version":1, "state":"ABSENT" if not path.is_file() else "OK",
              "policy":policy, "database_bytes":allocated, "auxiliary_bytes":aux,
              "free_bytes":free, "error_code":None, "import_allowed":True,
              "history_coverage":{"status":"UNAVAILABLE"}}
    def read(connection):
        nonlocal allocated
        allocated = max(allocated, connection.execute('PRAGMA page_count').fetchone()[0]*connection.execute('PRAGMA page_size').fetchone()[0])
        if not connection.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='meta'").fetchone():
            return
        row = connection.execute("SELECT value FROM meta WHERE key='history_coverage'").fetchone()
        report['history_coverage'] = json.loads(row[0]) if row else {"status":"LEGACY_UNVERIFIED"}
    try:
        if conn is not None:
            read(conn)
        elif path.is_file():
            # Windows SQLite's native busy handler can exceed short budgets by
            # several hundred ms; fail fast rather than spend the run budget here.
            timeout = 0 if deadline is not None else timeout
            with closing(sqlite3.connect(path.resolve().as_uri()+'?mode=ro',uri=True,timeout=timeout)) as reader:
                read(reader)
    except (sqlite3.Error, ValueError):
        report.update(state='CACHE_CORRUPT',error_code='DATABASE_ERROR',import_allowed=False)
    report['database_bytes'] = allocated
    if free < policy['min_free_bytes']:
        report.update(state='STOPPED',error_code='DISK_SPACE_LOW',import_allowed=False)
    elif allocated+aux >= policy['max_bytes']:
        report.update(state='STOPPED',error_code='CACHE_LIMIT_REACHED',import_allowed=False)
    elif allocated+aux >= policy['max_bytes']*policy['warning_fraction'] and report['import_allowed']:
        report['state'] = 'WARNING'
    return report


class CacheConnection(sqlite3.Connection):
    capacity_path = None
    policy = None

    def check_capacity(self):
        if self.capacity_path is not None:
            report = cache_status(self.capacity_path, self.policy, self)
            if not report['import_allowed']:
                raise CapacityError(report['error_code'])

    def execute(self, sql, parameters=(), /):
        if sql.lstrip().split(' ',1)[0].upper() in ('BEGIN','SAVEPOINT'):
            self.check_capacity()
        try:
            return super().execute(sql, parameters)
        except sqlite3.Error as exc:
            if 'full' in str(exc).lower() and self.capacity_path is not None:
                free = shutil.disk_usage(Path(self.capacity_path).parent).free
                raise CapacityError('DISK_SPACE_LOW' if free < self.policy['min_free_bytes'] else 'CACHE_LIMIT_REACHED') from None
            raise

    def commit(self):
        self.check_capacity()
        return super().commit()


def guard_cache(conn, path, policy):
    conn.capacity_path, conn.policy = Path(path), policy
    conn.check_capacity()
    page_size = conn.execute('PRAGMA page_size').fetchone()[0]
    conn.execute('PRAGMA max_page_count='+str(max(1,policy['max_bytes']//page_size)))


def error_code(exc):
    code = getattr(exc,'code',None)
    if code:
        return code
    for known in ('CACHE_LIMIT_REACHED','DISK_SPACE_LOW','BUDGET_EXHAUSTED'):
        if known in str(exc):
            return known
    return 'DATABASE_ERROR'
