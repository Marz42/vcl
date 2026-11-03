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

MIN_FREE = 512 * 1024 * 1024
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


def staged_migrate(path, converter, *, minimum_free=MIN_FREE):
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
    source = sqlite3.connect(str(path), timeout=1)
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
            source.backup(backup)
            if backup.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
                raise sqlite3.DatabaseError('migration backup integrity check failed')
        os.chmod(backup_name, 0o600)
        with closing(sqlite3.connect(stage_name)) as stage:
            stage.row_factory = sqlite3.Row
            source.backup(stage)
            converter(stage)
            stage.execute("INSERT OR REPLACE INTO meta(key,value) VALUES('pre_v5_backup',?)", (backup_name,))
            stage.commit()
            if stage.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
                raise sqlite3.DatabaseError('migration candidate integrity check failed')
        if source.execute('PRAGMA data_version').fetchone()[0] != version:
            raise sqlite3.OperationalError('migration source changed; stop all writers before retrying')
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
