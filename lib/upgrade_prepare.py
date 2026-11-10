#!/usr/bin/env python3
"""Durable, bounded upgrade preparation. Linux only; never performs migration."""
from __future__ import annotations
import argparse
import fcntl
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
import uuid

ROOT = Path('/var/lib/vincula/upgrade-operations')
TERMINAL = {'SUCCEEDED', 'FAILED', 'CANCELLED'}


def save(path, doc):
    tmp = path.with_suffix('.tmp')
    with tmp.open('w') as out:
        json.dump(doc, out)
        out.flush()
        os.fsync(out.fileno())
    os.chmod(tmp, 0o600)
    os.replace(tmp, path)
    fd = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def lock(root):
    root.mkdir(mode=0o700, parents=True, exist_ok=True)
    if root.is_symlink() or root.stat().st_uid != os.geteuid() or root.stat().st_mode & 0o077:
        raise ValueError('unsafe operation directory')
    fd = os.open(root / 'prepare.lock', os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        os.close(fd)
        return None
    return fd


def read_status(path):
    doc = json.loads(path.read_text())
    if doc['state'] == 'RUNNING':
        fd = lock(path.parent.parent)
        if fd is not None:
            os.close(fd)
            doc = dict(doc, state='UNKNOWN', code='WORKER_LOST')
    return doc


def start(root, op, binding, helper, seconds):
    path = root / op / 'status.json'
    if path.exists():
        doc = read_status(path)
        if doc['binding'] != binding:
            raise ValueError('operation binding mismatch')
        return doc
    fd = lock(root)
    if fd is None:
        return {'state': 'UNKNOWN', 'code': 'PREPARATION_BUSY', 'operation_id': op}
    try:
        # Recheck after acquiring the lock, including abandoned operations.
        for old in root.glob('*/status.json'):
            doc = json.loads(old.read_text())
            if doc['state'] not in TERMINAL:
                return {'state': 'UNKNOWN', 'code': 'UNRESOLVED_PREPARATION',
                        'operation_id': doc['operation_id']}
        path.parent.mkdir(mode=0o700)
        doc = {'state': 'RUNNING', 'phase': 'backup', 'operation_id': op,
               'binding': binding, 'helper': str(helper), 'seconds': seconds,
               'started_at': time.time(), 'migrate_started': False}
        save(path, doc)
        with (path.parent / 'worker.log').open('ab') as log:
            subprocess.Popen([sys.executable, str(Path(__file__).resolve()),
                              'worker', op, '--lock-fd', str(fd)],
                             stdin=subprocess.DEVNULL, stdout=log, stderr=log,
                             start_new_session=True, pass_fds=(fd,))
        return doc
    finally:
        os.close(fd)


def worker(root, op, fd, state_dir=Path("/etc/vincula")):
    path = root / op / 'status.json'
    doc = json.loads(path.read_text())
    deadline = time.monotonic() + doc['seconds']
    proc = None
    os.nice(15)
    # Best effort where ionice is absent; record what was actually applied.
    try:
        doc['ionice_applied'] = subprocess.run(
            ['ionice', '-c', '3', '-p', str(os.getpid())],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode == 0
    except FileNotFoundError:
        doc['ionice_applied'] = False
    doc['nice'] = os.getpriority(os.PRIO_PROCESS, 0)
    try:
        state = json.loads((state_dir / 'state.json').read_text())['node']
        version = (state_dir / 'VERSION').read_text().strip()
        expected = doc['binding']
        if any(state.get(k) != expected[k] for k in ('node_id', 'instance_id')) or version != expected['source_version']:
            raise ValueError('node identity/version changed')
        for phase, args in [('backup', ['backup', 'create', '--json']),
                            ('checkpoint', ['upgrade', 'checkpoint', '--json'])]:
            doc['phase'] = phase
            save(path, doc)
            began = time.monotonic()
            with (path.parent / (phase + '.json')).open('wb') as out, (path.parent / (phase + '.log')).open('wb') as err:
                proc = subprocess.Popen(['bash', doc['helper'], *args], stdout=out,
                                        stderr=err, start_new_session=True, pass_fds=(fd,))
                try:
                    rc = proc.wait(timeout=max(0.01, deadline - time.monotonic()))
                except subprocess.TimeoutExpired:
                    os.killpg(proc.pid, signal.SIGTERM)
                    try:
                        proc.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        pass
                    # The shell may exit before its child: kill the whole owned group.
                    try:
                        os.killpg(proc.pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
                    proc.wait()
                    doc.update(state='CANCELLED', code='PREPARATION_DEADLINE')
                    return
            if rc:
                raise ValueError(phase + ' command failed')
            result = json.loads((path.parent / (phase + '.json')).read_text())
            if result.get('ok') is not True or not result.get('path'):
                raise ValueError(phase + ' invalid result')
            if phase == 'backup' and any(result.get('source_' + k) != expected[k] for k in ('node_id', 'instance_id')):
                raise ValueError('backup identity mismatch')
            if phase == 'checkpoint' and result.get('source_version') != version:
                raise ValueError('checkpoint version mismatch')
            doc[phase] = result
            doc[phase + '_seconds'] = time.monotonic() - began
        doc.update(state='SUCCEEDED', phase='prepared')
    except Exception as exc:
        doc.update(state='FAILED', code='PREPARATION_FAILED', detail=str(exc))
    finally:
        doc['finished_at'] = time.time()
        save(path, doc)
        os.close(fd)


def main():
    os.umask(0o077)
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=['start', 'status', 'worker'])
    parser.add_argument('operation_id')
    parser.add_argument('--binding')
    parser.add_argument('--helper')
    parser.add_argument('--seconds', type=int, default=900)
    parser.add_argument('--lock-fd', type=int)
    args = parser.parse_args()
    op = str(uuid.UUID(args.operation_id))
    if op != args.operation_id or not 30 <= args.seconds <= 7200:
        raise ValueError('invalid operation parameters')
    if args.action == 'worker':
        worker(ROOT, op, args.lock_fd)
        return
    if args.action == 'start':
        helper = Path(args.helper).resolve(strict=True)
        if helper != Path(__file__).resolve().parent.parent / 'bin/vincula':
            raise ValueError('helper must belong to this payload')
        doc = start(ROOT, op, json.loads(args.binding), helper, args.seconds)
    else:
        doc = read_status(ROOT / op / 'status.json')
    print(json.dumps(doc))


if __name__ == '__main__':
    main()
