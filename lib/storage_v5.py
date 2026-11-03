"""Shared 0.5.5 time, staged SQLite migration and durable rollup primitives.

Stdlib only. No service, network, environment credentials or implicit repair.
"""
from datetime import datetime, timezone
from contextlib import closing, contextmanager
import hashlib
import json
import os
import re
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
            candidate = value.replace("Z", "+00:00").replace("z", "+00:00")
            candidate = re.sub(r"\.(\d+)(?=[+-]\d{2}:\d{2}$)", lambda m: "."+(m[1]+"000000")[:6], candidate)
            when = datetime.fromisoformat(candidate)
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


@contextmanager
def _migration_gate(path, deadline):
    """Serialize competing schema-5 activations, including across processes."""
    path=Path(path)
    limit=deadline if deadline is not None else time.monotonic()+5
    with path.with_name('.'+path.name+'.v5-migration.lock').open('a+b') as lock:
        os.chmod(lock.name,0o600)
        lock.seek(0,2)
        if lock.tell()==0:
            lock.write(b'0');lock.flush()
        while True:
            try:
                if os.name=='nt':
                    import msvcrt
                    lock.seek(0);msvcrt.locking(lock.fileno(),msvcrt.LK_NBLCK,1)
                else:
                    import fcntl
                    fcntl.flock(lock.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
                break
            except OSError:
                if time.monotonic()>=limit:
                    raise sqlite3.OperationalError('BUDGET_EXHAUSTED: migration lock is busy')
                time.sleep(.01)
        try:
            yield
        finally:
            if os.name=='nt':
                lock.seek(0);msvcrt.locking(lock.fileno(),msvcrt.LK_UNLCK,1)
            else:
                fcntl.flock(lock.fileno(),fcntl.LOCK_UN)


def staged_migrate(path, converter, *, minimum_free=MIN_FREE, deadline=None):
    with _migration_gate(path,deadline):
        with closing(sqlite3.connect(Path(path).resolve().as_uri()+'?mode=ro',uri=True,timeout=0)) as probe:
            row=probe.execute("SELECT value FROM meta WHERE key='schema_version'").fetchone() if probe.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='meta'").fetchone() else None
            if row and str(row[0])=='5':
                return None  # another migrator completed while this caller waited
        return _staged_migrate(path,converter,minimum_free=minimum_free,deadline=deadline)


def _staged_migrate(path, converter, *, minimum_free=MIN_FREE, deadline=None):
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
    source = sqlite3.connect(str(path), timeout=0 if deadline is not None else 1)
    try:
        if source.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
            raise sqlite3.DatabaseError('migration source integrity check failed')
        # A WAL must not survive activation beside a different database file.
        result = source.execute('PRAGMA wal_checkpoint(TRUNCATE)').fetchone()
        if result and result[0]:
            raise sqlite3.OperationalError('migration source is busy')
        source.execute('PRAGMA journal_mode=DELETE')
        source_identity=(path.stat().st_dev,path.stat().st_ino,path.stat().st_size,path.stat().st_mtime_ns)
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
        if (path.stat().st_dev,path.stat().st_ino,path.stat().st_size,path.stat().st_mtime_ns)!=source_identity:
            raise sqlite3.OperationalError('migration source identity changed; activation refused')
        check_deadline()
        source.close()
        os.chmod(stage_name, 0o600)
        os.replace(stage_name, path)
        if os.name!='nt':
            directory=os.open(path.parent,os.O_RDONLY|os.O_DIRECTORY)
            try:os.fsync(directory)
            finally:os.close(directory)
        return backup_name
    finally:
        source.close()
        if os.path.exists(stage_name):
            os.unlink(stage_name)


def _adjust(conn, contribution, sign):
    date, user_id, user_tag, host, up, down = contribution
    existing = conn.execute('SELECT upload_bytes,download_bytes,connection_count FROM daily_usage WHERE date=? AND user_id=? AND destination_host=?', (date,user_id,host)).fetchone()
    before = tuple(existing) if existing is not None else (0,0,0)
    if any(type(value) is not int or not 0 <= value <= 2**63-1 for value in (before[0]+sign*up,before[1]+sign*down,before[2]+sign)):
        raise sqlite3.IntegrityError('daily contribution exceeds the integer accounting range')
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
        cursor = conn.execute("""SELECT c.event_id,c.started_at,c.user_id,c.user_tag,
            COALESCE(NULLIF(c.destination_host,''),NULLIF(c.destination_ip,''),'(unknown)'),
            c.upload_bytes,c.download_bytes FROM connections c
            LEFT JOIN daily_contributions d ON d.event_id=c.event_id
            WHERE d.event_id IS NULL OR d.upload_bytes!=c.upload_bytes OR d.download_bytes!=c.download_bytes
            OR d.user_id!=c.user_id OR d.user_tag IS NOT c.user_tag OR d.date!=substr(c.started_at,1,10)
            OR d.destination_host!=COALESCE(NULLIF(c.destination_host,''),NULLIF(c.destination_ip,''),'(unknown)')
            ORDER BY c.event_id""")
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
        conn.execute("INSERT OR REPLACE INTO meta VALUES('daily_last_rollup_at',?)",(utc(datetime.now(timezone.utc)),))
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
    if type(policy['schema_version']) is not int or policy['schema_version'] != 1 or any(type(policy[k]) is not int for k in ('max_bytes','min_free_bytes')) or policy['max_bytes'] < 16384 or policy['min_free_bytes'] < 0 or isinstance(policy['warning_fraction'], bool) or not isinstance(policy['warning_fraction'], (int,float)) or not 0 < policy['warning_fraction'] < 1:
        raise ValueError('invalid machine-local cache policy')
    return policy


def cache_status(path, policy, conn=None, *, timeout=.1, deadline=None, reserve_journal=True):
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
        coverage = json.loads(row[0]) if row else {"status":"LEGACY_UNVERIFIED"}
        if not isinstance(coverage, dict):
            raise ValueError('invalid history coverage')
        report['history_coverage'] = coverage
    try:
        if conn is not None:
            read(conn)
        elif path.is_file():
            # Windows SQLite's native busy handler can exceed short budgets by
            # several hundred ms; fail fast rather than spend the run budget here.
            timeout = 0 if deadline is not None else timeout
            with closing(sqlite3.connect(path.resolve().as_uri()+'?mode=ro',uri=True,timeout=timeout)) as reader:
                read(reader)
    except sqlite3.Error as exc:
        report.update(state='BUSY' if 'locked' in str(exc).lower() or 'busy' in str(exc).lower() else 'CACHE_CORRUPT',error_code='DATABASE_ERROR',import_allowed=False)
    except ValueError:
        report.update(state='CACHE_CORRUPT',error_code='DATABASE_ERROR',import_allowed=False)
    report['database_bytes'] = allocated
    reserve = max(0,allocated-aux) if reserve_journal else 0
    report['journal_reserve_bytes'] = reserve
    report['required_free_bytes'] = policy['min_free_bytes']+reserve
    if free < report['required_free_bytes']:
        report.update(state='STOPPED',error_code='DISK_SPACE_LOW',import_allowed=False)
    elif allocated >= policy['max_bytes']:
        report.update(state='STOPPED',error_code='CACHE_LIMIT_REACHED',import_allowed=False)
    elif allocated >= policy['max_bytes']*policy['warning_fraction'] and report['import_allowed']:
        report['state'] = 'WARNING'
    return report


class CacheConnection(sqlite3.Connection):
    capacity_path = None
    policy = None

    def check_capacity(self, reserve_journal=False):
        if self.capacity_path is not None:
            report = cache_status(self.capacity_path, self.policy, self, reserve_journal=reserve_journal)
            if not report['import_allowed']:
                raise CapacityError(report['error_code'])

    def execute(self, sql, parameters=(), /):
        if sql.lstrip().split(' ',1)[0].upper() in ('BEGIN','SAVEPOINT'):
            self.check_capacity(reserve_journal=not self.in_transaction)
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
    conn.check_capacity(reserve_journal=True)
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
