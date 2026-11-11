#!/usr/bin/env python3
"""Durable, bounded upgrade preparation. Linux only; never performs migration.

Lifecycle model
---------------
``start`` creates the operation lock/status and launches a small supervisor.
The supervisor creates a private PID namespace and forks the worker as PID 1
of that namespace.  Every helper and helper descendant therefore lives in the
same namespace.  Kernel semantics give two important properties:

* if the worker (namespace init) dies, the kernel kills every task left in the
  namespace before the worker can be reaped;
* if the supervisor dies, the worker receives ``PR_SET_PDEATHSIG`` and dies,
  which in turn makes the kernel clear the namespace.

The supervisor is the primary process that enforces the deadline.  The worker
also starts one deadline-guard thread with the **same absolute** monotonic
deadline, so a stopped supervisor cannot leave the worker/helper running past
it.  The guard is not a second budget.  After forking the worker, the supervisor
closes its own lock fd; the worker and all helpers inherit the only copy, so
the kernel namespace teardown releases it only after the worker tree is gone.
If the supervisor is killed, the lock is still held by the worker until
``PDEATHSIG`` completes, and ``read_status`` reconciles a stale RUNNING record
only after it can acquire the lock.
"""
from __future__ import annotations
import argparse
import ctypes
import fcntl
import importlib.util
import json
import os
from pathlib import Path
import signal
import stat
import subprocess
import sys
import threading
import time
import traceback
import uuid

ROOT = Path('/var/lib/vincula/upgrade-operations')
BACKUP_ROOT = Path(os.environ.get('VCL_BACKUP_ROOT', '/var/backups/vincula'))
TERMINAL = {'SUCCEEDED', 'FAILED', 'CANCELLED'}
CLONE_NEWNS = 0x00020000
CLONE_NEWPID = 0x20000000
MS_REC = 16384
MS_PRIVATE = 1 << 18
MS_NOSUID = 2
MS_NODEV = 4
MS_NOEXEC = 8
PR_SET_PDEATHSIG = 1

_libc = ctypes.CDLL(None, use_errno=True)
_libc.unshare.argtypes = [ctypes.c_int]
_libc.unshare.restype = ctypes.c_int
_libc.mount.argtypes = [ctypes.c_char_p, ctypes.c_char_p, ctypes.c_char_p,
                        ctypes.c_ulong, ctypes.c_void_p]
_libc.mount.restype = ctypes.c_int
_libc.prctl.argtypes = [ctypes.c_int, ctypes.c_ulong, ctypes.c_ulong,
                        ctypes.c_ulong, ctypes.c_ulong]
_libc.prctl.restype = ctypes.c_int


def _errno_error(what):
    err = ctypes.get_errno()
    return OSError(err, f'{what}: {os.strerror(err)}')


def _unshare(flags):
    if _libc.unshare(flags) != 0:
        raise _errno_error('unshare')


def _mount(source, target, fstype, flags, data=None):
    if _libc.mount(source, target, fstype, flags, data) != 0:
        raise _errno_error('mount ' + str(target))


def _pdeathsig(sig):
    if _libc.prctl(PR_SET_PDEATHSIG, int(sig), 0, 0, 0) != 0:
        raise _errno_error('prctl(PR_SET_PDEATHSIG)')


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
            # Acquiring the operation lock proves that no worker, supervisor or
            # helper (all inherit the lock fd) is still alive.  Converge the
            # status instead of leaving RUNNING behind forever.
            try:
                doc = dict(doc, state='FAILED', code='WORKER_LOST',
                           detail='operation lock is free and no lifecycle owner is alive',
                           finished_at=time.time())
                save(path, doc)
            finally:
                os.close(fd)
    return doc


def lifecycle_available():
    """Probe CLONE_NEWPID without changing this process's namespace."""
    try:
        pid = os.fork()
    except OSError:
        return False
    if pid == 0:
        try:
            _unshare(CLONE_NEWPID)
            os._exit(0)
        except OSError:
            os._exit(1)
    try:
        _, status = os.waitpid(pid, 0)
    except OSError:
        return False
    return os.waitstatus_to_exitcode(status) == 0


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
        # The operation lock is held, so every non-terminal record belongs to a
        # dead worker/supervisor and cannot make progress.  Reconcile it here
        # rather than blocking every later start with UNRESOLVED_PREPARATION.
        for old in root.glob('*/status.json'):
            doc = json.loads(old.read_text())
            if doc.get('state') not in TERMINAL:
                doc.update(state='FAILED', code='WORKER_LOST',
                           detail='abandoned operation recovered while acquiring the lock',
                           finished_at=time.time())
                save(old, doc)
        path.parent.mkdir(mode=0o700, exist_ok=True)
        base = {'operation_id': op, 'binding': binding, 'helper': str(helper),
                'seconds': seconds, 'started_at': time.time(),
                'migrate_started': False}
        if not lifecycle_available():
            doc = dict(base, state='FAILED', code='LIFECYCLE_UNAVAILABLE',
                       detail='CLONE_NEWPID is unavailable; refusing to run without a bounded process tree',
                       finished_at=time.time())
            save(path, doc)
            return doc
        doc = dict(base, state='RUNNING', phase='backup')
        save(path, doc)
        deadline = time.monotonic() + seconds
        try:
            with (path.parent / 'worker.log').open('ab') as log:
                subprocess.Popen(
                    [sys.executable, str(Path(__file__).resolve()), 'supervise', op,
                     '--lock-fd', str(fd), '--deadline', repr(deadline)],
                    stdin=subprocess.DEVNULL, stdout=log, stderr=log,
                    start_new_session=True, pass_fds=(fd,))
        except Exception as exc:
            doc.update(state='FAILED', code='LIFECYCLE_UNAVAILABLE',
                       detail=f'cannot start supervisor: {exc}', finished_at=time.time())
            save(path, doc)
        return doc
    finally:
        os.close(fd)


def _status_or(path, fallback):
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return fallback


def _exit_facts(status):
    if os.WIFSIGNALED(status):
        return {'signal': os.WTERMSIG(status), 'exit_code': None}
    return {'signal': None, 'exit_code': os.WEXITSTATUS(status)}


def supervise(root, op, fd, deadline):
    """Own the deadline, the lock and the whole worker process tree."""
    path = root / op / 'status.json'
    base = _status_or(path, {'operation_id': op, 'state': 'FAILED'})
    private_mounts = False
    try:
        _unshare(CLONE_NEWNS | CLONE_NEWPID)
        try:
            _mount(None, b'/', None, MS_REC | MS_PRIVATE, None)
            private_mounts = True
        except OSError as exc:
            print(f'supervisor: mount propagation not privatized: {exc}', file=sys.stderr, flush=True)
        read_fd, write_fd = os.pipe()
        worker_pid = os.fork()
        if worker_pid == 0:
            # PID 1 of the new namespace.  Do not leak the supervisor's pipe.
            os.close(write_fd)
            try:
                # The worker is PID 1, so a parent-death handler can persist a
                # terminal status before namespace teardown.  This converges the
                # record even when the supervisor is SIGKILLed and no later
                # status query happens.
                def _parent_died(_signum, _frame):
                    status_path = root / op / 'status.json'
                    doc = _status_or(status_path, {})
                    if doc.get('state') == 'RUNNING':
                        doc.update(state='FAILED', code='WORKER_LOST',
                                   detail='supervisor died before the worker published a terminal status',
                                   finished_at=time.time())
                        try:
                            save(status_path, doc)
                        except OSError:
                            pass
                    os._exit(1)
                signal.signal(signal.SIGUSR1, _parent_died)
                _pdeathsig(signal.SIGUSR1)
                # Close the post-fork race: if the supervisor died before the
                # PDEATHSIG was installed, the handshake pipe is at EOF.
                if os.read(read_fd, 1) != b'1':
                    os._exit(4)
                os.close(read_fd)
                if private_mounts:
                    try:
                        _mount(b'proc', b'/proc', b'proc', MS_NOSUID | MS_NODEV | MS_NOEXEC, None)
                    except OSError as exc:
                        print(f'worker: private /proc not mounted: {exc}', file=sys.stderr, flush=True)
                os.environ['VCL_PREPARE_DEADLINE_MONO'] = repr(deadline)
                worker(root, op, fd)
                os._exit(0)
            except BaseException:
                traceback.print_exc()
                os._exit(1)
        os.close(read_fd)
        # From this point the worker and all helpers inherit the only lock fd.
        # The supervisor must not retain a duplicate: if the supervisor is
        # SIGSTOPed, its fd would otherwise keep the lock after the worker
        # guard has already torn the namespace down.  Kernel teardown of the
        # PID namespace closes the inherited helper fds, so the lock cannot be
        # released before the worker tree is gone.
        try:
            os.close(fd)
        except OSError:
            pass
        fd = -1
        save(path.parent / 'lifecycle.json', {
            'operation_id': op,
            'supervisor_pid': os.getpid(),
            'worker_host_pid': worker_pid,
            'deadline_mono': deadline,
            'pid_namespace': True,
            'proc_isolated': private_mounts,
            'created_at': time.time(),
        })
        try:
            os.write(write_fd, b'1')
        except BrokenPipeError:
            pass
        os.close(write_fd)

        timed_out = False
        worker_status = None
        while True:
            try:
                got, status = os.waitpid(worker_pid, os.WNOHANG)
            except ChildProcessError:
                got, status = worker_pid, 0
            if got == worker_pid:
                worker_status = status
                break
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                timed_out = True
                try:
                    os.kill(worker_pid, signal.SIGTERM)
                except ProcessLookupError:
                    pass
                grace = time.monotonic() + 5
                while time.monotonic() < grace:
                    try:
                        got, status = os.waitpid(worker_pid, os.WNOHANG)
                    except ChildProcessError:
                        got, status = worker_pid, 0
                    if got == worker_pid:
                        worker_status = status
                        break
                    time.sleep(0.05)
                if worker_status is None:
                    try:
                        os.kill(worker_pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
                    try:
                        _, worker_status = os.waitpid(worker_pid, 0)
                    except ChildProcessError:
                        worker_status = 0
                break
            time.sleep(min(0.2, max(0.01, remaining)))

        doc = _status_or(path, base)
        if doc.get('state') == 'RUNNING':
            facts = _exit_facts(worker_status or 0)
            if timed_out:
                doc.update(state='CANCELLED', code='PREPARATION_DEADLINE',
                           detail='deadline expired; worker namespace terminated')
            else:
                doc.update(state='FAILED', code='WORKER_LOST',
                           detail='worker exited before publishing a terminal status')
            doc['worker_exit'] = facts
            doc['finished_at'] = time.time()
            save(path, doc)
    except Exception as exc:
        print(f'supervisor: {exc}', file=sys.stderr, flush=True)
        traceback.print_exc()
        doc = _status_or(path, base)
        if doc.get('state') == 'RUNNING':
            doc.update(state='FAILED', code='LIFECYCLE_UNAVAILABLE',
                       detail=f'supervisor failed: {exc}', finished_at=time.time())
            save(path, doc)
    finally:
        if fd >= 0:
            try:
                os.close(fd)
            except OSError:
                pass


def _load_backup_module():
    """Load the payload's trusted archive verifier (same file as the helper)."""
    path = Path(__file__).resolve().with_name('vincula-backup.py')
    spec = importlib.util.spec_from_file_location('prepare_backup_verify', path)
    if spec is None or spec.loader is None:
        raise RuntimeError('backup verifier module is unavailable')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _verify_backup(path_doc, expected, evidence_dir):
    """Verify the backup handoff from a pinned fd, before checkpoint starts."""
    began = time.monotonic()
    raw_path = path_doc.get('path')
    if not isinstance(raw_path, str) or not raw_path:
        raise ValueError('backup result has no path')
    path = Path(raw_path)
    if not path.is_absolute():
        raise ValueError('backup path is not absolute')
    root = BACKUP_ROOT.resolve()
    if path.parent.resolve() != root:
        raise ValueError('backup path is outside the backup root')
    st = os.lstat(path)
    if stat.S_ISLNK(st.st_mode) or not stat.S_ISREG(st.st_mode):
        raise ValueError('backup path is not a regular file')
    if st.st_uid != os.geteuid():
        raise ValueError('backup file owner mismatch')
    if st.st_mode & 0o077:
        raise ValueError('backup file permissions are too broad')
    fd = os.open(path, os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW)
    try:
        opened = os.fstat(fd)
        if (opened.st_dev, opened.st_ino) != (st.st_dev, st.st_ino) or opened.st_size != st.st_size:
            raise ValueError('backup path changed while it was being opened')
        module = _load_backup_module()
        result = module.verify_archive_fd(fd)
        evidence = {'schema_version': 1, 'path': str(path), 'ok': bool(result.get('ok'))}
        if result.get('ok'):
            evidence.update({k: result.get(k) for k in (
                'source_node_id', 'source_instance_id', 'vincula_version',
                'secret_bearing', 'encryption', 'archive_sha256', 'archive_size',
                'archive_dev', 'archive_ino', 'archive_mtime_ns')})
            if result.get('source_node_id') != expected['node_id'] or \
                    result.get('source_instance_id') != expected['instance_id']:
                evidence.update(ok=False, error='identity_mismatch')
            elif result.get('vincula_version') != expected['source_version']:
                evidence.update(ok=False, error='version_mismatch')
            elif result.get('secret_bearing') or result.get('encryption') != 'none':
                evidence.update(ok=False, error='archive_encrypted')
            elif result.get('archive_dev') != st.st_dev or result.get('archive_ino') != st.st_ino:
                evidence.update(ok=False, error='archive_changed')
        else:
            evidence['error'] = result.get('error', 'invalid_archive')
        evidence['seconds'] = time.monotonic() - began
        save(evidence_dir / 'backup.verify.json', evidence)
        if not evidence['ok']:
            raise ValueError('backup verification failed: ' + str(evidence.get('error')))
        os.fstat(fd)  # fd must still refer to the same live inode
        return evidence, fd
    except Exception:
        try:
            os.close(fd)
        except OSError:
            pass
        raise


def _check_archive_unchanged(fd, evidence):
    st = os.fstat(fd)
    current = os.stat(evidence['path'], follow_symlinks=False)
    if (st.st_dev, st.st_ino, st.st_size, st.st_mtime_ns) != (
            current.st_dev, current.st_ino, current.st_size, current.st_mtime_ns):
        raise ValueError('backup archive changed during preparation')
    if (st.st_dev, st.st_ino) != (evidence.get('archive_dev'), evidence.get('archive_ino')):
        raise ValueError('backup archive inode changed during preparation')


def worker(root, op, fd, state_dir=None):
    if state_dir is None:
        state_dir = Path(os.environ.get('VCL_STATE_DIR', '/etc/vincula'))
    path = root / op / 'status.json'
    doc = json.loads(path.read_text())
    proc = None
    archive_fd = None
    status_lock = threading.Lock()
    deadline_fired = threading.Event()
    proc_holder = {'proc': None}
    raw_deadline = os.environ.get('VCL_PREPARE_DEADLINE_MONO', '').strip()
    try:
        deadline = float(raw_deadline) if raw_deadline else None
    except ValueError:
        raise ValueError('invalid VCL_PREPARE_DEADLINE_MONO')

    def save_status(current):
        # Once the absolute deadline has fired, no later main-thread write may
        # resurrect a RUNNING or SUCCEEDED record.
        with status_lock:
            if deadline_fired.is_set() and current.get('state') != 'CANCELLED':
                current.update(state='CANCELLED', code='PREPARATION_DEADLINE',
                               detail='absolute preparation deadline expired (worker guard)',
                               finished_at=time.time(), deadline_owner='worker_guard')
            save(path, current)

    def _deadline_guard():
        # Independent of proc.wait(), snapshot_sqlite() and archive
        # verification: this thread only depends on the supervisor-provided
        # absolute monotonic deadline.  It is not a new 900 s budget.
        if deadline is None:
            return
        left = deadline - time.monotonic()
        if left > 0:
            time.sleep(left)
        with status_lock:
            try:
                current = json.loads(path.read_text())
            except (OSError, ValueError):
                return
            if current.get('state') != 'RUNNING':
                return
            current.update(state='CANCELLED', code='PREPARATION_DEADLINE',
                           detail='absolute preparation deadline expired while supervisor was not scheduling',
                           finished_at=time.time(), deadline_owner='worker_guard')
            save(path, current)
            deadline_fired.set()
            helper = proc_holder.get('proc')
        if helper is not None:
            try:
                os.killpg(helper.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
        # Same 5 s grace as the supervisor.  If the helper ignores TERM, the
        # worker (namespace PID 1) exits and the kernel clears the namespace.
        time.sleep(5)
        os._exit(1)

    if deadline is not None:
        threading.Thread(target=_deadline_guard, name='deadline-guard', daemon=True).start()

    os.nice(15)
    try:
        doc['ionice_applied'] = subprocess.run(
            ['ionice', '-c', '3', '-p', str(os.getpid())],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode == 0
    except FileNotFoundError:
        doc['ionice_applied'] = False
    doc['nice'] = os.getpriority(os.PRIO_PROCESS, 0)

    def _on_term(_signum, _frame):
        # The supervisor deadline sends SIGTERM to namespace init.  Ask the
        # helper group to stop, then let namespace teardown clean up anything
        # that ignores TERM.  SystemExit skips the generic FAILED handler.
        if proc is not None:
            try:
                os.killpg(proc.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
        raise SystemExit(143)

    signal.signal(signal.SIGTERM, _on_term)
    try:
        state = json.loads((state_dir / 'state.json').read_text())['node']
        version = (state_dir / 'VERSION').read_text().strip()
        expected = doc['binding']
        if any(state.get(k) != expected[k] for k in ('node_id', 'instance_id')) or version != expected['source_version']:
            raise ValueError('node identity/version changed')
        for phase, args in [('backup', ['backup', 'create', '--json']),
                            ('checkpoint', ['upgrade', 'checkpoint', '--json'])]:
            doc['phase'] = phase
            save_status(doc)
            began = time.monotonic()
            with (path.parent / (phase + '.json')).open('wb') as out, (path.parent / (phase + '.log')).open('wb') as err:
                proc = subprocess.Popen(['bash', doc['helper'], *args], stdout=out,
                                        stderr=err, start_new_session=True, pass_fds=(fd,))
                proc_holder['proc'] = proc
                try:
                    rc = proc.wait()
                finally:
                    proc_holder['proc'] = None
            if rc:
                raise ValueError(phase + ' command failed')
            result = json.loads((path.parent / (phase + '.json')).read_text())
            if result.get('ok') is not True or not result.get('path'):
                raise ValueError(phase + ' invalid result')
            if phase == 'backup' and any(result.get('source_' + k) != expected[k] for k in ('node_id', 'instance_id')):
                raise ValueError('backup identity mismatch')
            if phase == 'checkpoint' and result.get('source_version') != version:
                raise ValueError('checkpoint version mismatch')
            if phase == 'backup':
                doc['backup'] = result
                try:
                    evidence, archive_fd = _verify_backup(result, expected, path.parent)
                except Exception:
                    verification_path = path.parent / 'backup.verify.json'
                    if verification_path.exists():
                        try:
                            doc['backup_verification'] = json.loads(verification_path.read_text())
                        except ValueError:
                            pass
                    save_status(doc)
                    raise
                doc['backup_verification'] = evidence
            else:
                doc['checkpoint'] = result
            doc[phase + '_seconds'] = time.monotonic() - began
            save_status(doc)
        if archive_fd is not None:
            _check_archive_unchanged(archive_fd, doc['backup_verification'])
        doc.update(state='SUCCEEDED', phase='prepared')
    except Exception as exc:
        doc.update(state='FAILED', code='PREPARATION_FAILED', detail=str(exc))
    finally:
        if archive_fd is not None:
            try:
                os.close(archive_fd)
            except OSError:
                pass
        doc['finished_at'] = time.time()
        save_status(doc)
        os.close(fd)


def main():
    os.umask(0o077)
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=['start', 'status', 'worker', 'supervise'])
    parser.add_argument('operation_id')
    parser.add_argument('--binding')
    parser.add_argument('--helper')
    parser.add_argument('--seconds', type=int, default=900)
    parser.add_argument('--lock-fd', type=int)
    parser.add_argument('--deadline', type=float)
    args = parser.parse_args()
    op = str(uuid.UUID(args.operation_id))
    if op != args.operation_id or not 30 <= args.seconds <= 7200:
        raise ValueError('invalid operation parameters')
    if args.action == 'supervise':
        if args.lock_fd is None or args.deadline is None:
            raise ValueError('supervise requires --lock-fd and --deadline')
        supervise(ROOT, op, args.lock_fd, args.deadline)
        return
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
