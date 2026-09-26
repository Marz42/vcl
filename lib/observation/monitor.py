"""Foreground, bounded polling service shared by CLI and cache-only UI."""

from __future__ import annotations

import concurrent.futures
import importlib.util
import math
import os
import random
import sqlite3
import subprocess
import threading
import time
from pathlib import Path

_spec = importlib.util.spec_from_file_location("vcl_monitor_store", Path(__file__).with_name("store.py"))
store_module = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(store_module)
Store = store_module.Store


class MonitorLock:
    """Dedicated local lock: a long-running monitor never holds the Fleet mutation lock."""
    def __init__(self, path):
        self.path, self.handle = path, None

    def __enter__(self):
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        fd = os.open(self.path, os.O_RDWR | os.O_CREAT, 0o600)
        self.handle = os.fdopen(fd, "r+b")
        try:
            if os.name == "nt":
                import msvcrt
                if self.path.stat().st_size == 0:
                    self.handle.write(b"0")
                    self.handle.flush()
                self.handle.seek(0)
                msvcrt.locking(self.handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(self.handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            self.handle.close()
            self.handle = None
            raise ValueError("MONITOR_BUSY: another monitor holds this cache") from None
        return self

    def __exit__(self, *_):
        if self.handle:
            if os.name == "nt":
                import msvcrt
                self.handle.seek(0)
                msvcrt.locking(self.handle.fileno(), msvcrt.LK_UNLCK, 1)
            self.handle.close()


class Monitor:
    def __init__(self, nodes, store, fetch, *, interval=30, timeout=5, concurrency=8,
                 probe=None, clock=time.monotonic, wall_clock=time.time, rng=None):
        if not 1 <= len(nodes) <= 1024:
            raise ValueError("monitor requires 1..1024 enabled nodes")
        if not math.isfinite(interval) or not 1 <= interval <= 3600:
            raise ValueError("interval must be 1..3600 seconds")
        if not math.isfinite(timeout) or not 0 < timeout <= 300:
            raise ValueError("timeout must be >0 and <=300 seconds")
        if not 1 <= concurrency <= 64:
            raise ValueError("concurrency must be 1..64")
        if len({n["node_id"] for n in nodes}) != len(nodes):
            raise ValueError("duplicate monitoring identity")
        self.nodes, self.store, self.fetch, self.probe = nodes, store, fetch, probe
        self.interval, self.timeout, self.concurrency = interval, timeout, concurrency
        self.clock, self.wall_clock, self.rng = clock, wall_clock, rng or random.Random()
        self.due = {node["node_id"]: clock() for node in nodes}
        self.failures = {node["node_id"]: 0 for node in nodes}

    def delay(self, node_id, result):
        failed = result.get("state") not in ("OK", "UNSUPPORTED")
        self.failures[node_id] = min(10, self.failures[node_id] + 1) if failed else 0
        delay = min(300, self.interval * (2 ** self.failures[node_id])) if failed else self.interval
        return min(300, delay * self.rng.uniform(.9, 1.1)) if failed else delay * self.rng.uniform(.9, 1.1)

    def collect(self, node):
        try:
            result = self.fetch(node, timeout=self.timeout)
        except subprocess.TimeoutExpired:
            result = {"state": "TIMEOUT"}
        except (Exception, SystemExit):
            # Do not expose exceptions, argv, SSH stderr, or user credentials.
            result = {"state": "ERROR"}
        probe_result = None
        if self.probe and result.get("state") == "OK":
            try:
                probe_result = self.probe(node, timeout=self.timeout)
            except subprocess.TimeoutExpired:
                probe_result = {"success": False, "reason": "TIMEOUT"}
            except (Exception, SystemExit):
                probe_result = {"success": None, "reason": "INVALID_CONFIG"}
        return result, probe_result

    def run(self, *, once=False, stop=None, emit=None):
        stop = stop or threading.Event()
        completed, write_errors, pending = set(), 0, {}
        with MonitorLock(self.store.path.with_suffix(".lock")):
            with concurrent.futures.ThreadPoolExecutor(max_workers=self.concurrency) as pool:
                try:
                    while not stop.is_set():
                        busy = {node["node_id"] for node in pending.values()}
                        candidates = sorted(self.nodes, key=lambda n: self.due[n["node_id"]])
                        for node in candidates:
                            nid = node["node_id"]
                            if len(pending) >= self.concurrency:
                                break
                            if nid in busy or (once and nid in completed) or self.due[nid] > self.clock():
                                continue
                            pending[pool.submit(self.collect, node)] = node
                        if not pending:
                            if once:
                                break
                            stop.wait(min(.25, max(.01, min(self.due.values()) - self.clock())))
                            continue
                        done, _ = concurrent.futures.wait(pending, timeout=.25, return_when=concurrent.futures.FIRST_COMPLETED)
                        for future in done:
                            node = pending.pop(future)
                            result, probe = future.result()
                            self.due[node["node_id"]] = self.clock() + self.delay(node["node_id"], result)
                            completed.add(node["node_id"])
                            try:
                                record = self.store.record(node, result, self.wall_clock(), probe)
                                if emit:
                                    emit({"name": node["name"], "state": record["overall"], "observation_state": record["observation_state"]})
                            except (sqlite3.Error, OSError, ValueError):
                                write_errors += 1
                                if emit:
                                    emit({"name": node["name"], "state": "CACHE_WRITE_FAILED"})
                        if once and len(completed) == len(self.nodes):
                            break
                except KeyboardInterrupt:
                    stop.set()
                finally:
                    for future in pending:
                        future.cancel()
        return {"sampled_nodes": len(completed), "cache_write_errors": write_errors}


def active_nodes(host, name=None):
    registry = host.load_registry()
    nodes = [host.require_node(registry, name)] if name else registry["nodes"]
    return [node for node in nodes if host.node_is_active(node) and node.get("enabled", True)]


def cache_path(host):
    return host.fleet_db_path().with_name("observation.db")


def cached_health(host, name=None):
    nodes = active_nodes(host, name)
    if len(nodes) > 1024:
        raise ValueError("monitor view supports at most 1024 nodes")
    return Store(cache_path(host)).read(nodes, time.time())


def run_cli(host, args):
    import json
    import sys
    nodes = active_nodes(host, args.name)
    store = Store(cache_path(host))
    probe = None
    if args.probe_profiles:
        module = store_module.sibling("probe")
        path = Path(args.probe_profiles).resolve()
        # Workspace is portable; private probe profiles must remain workstation-local.
        if host.workspace_manifest_path().is_file() and path.is_relative_to(host.fleet_home().resolve()):
            raise ValueError("probe profiles must be outside the portable Workspace")
        profiles = module.read_profiles(path)
        probe = module.ProxyProbe(profiles, sing_box=args.probe_sing_box)
    def emit(event):
        if not args.as_json:
            print(f"{event['name']}: {event['state']}", flush=True)
    monitor = Monitor(nodes, store, host.fetch_node_telemetry, interval=args.interval,
                      timeout=args.timeout, concurrency=args.concurrency, probe=probe)
    result = monitor.run(once=args.once, emit=emit)
    doc = store.read(nodes, time.time())
    doc["run"] = result
    if args.as_json:
        sys.stdout.write(json.dumps(doc, allow_nan=False) + "\n")
    return 2 if result["cache_write_errors"] or any(n["observation_state"] in ("ERROR", "TIMEOUT", "AUTH_FAILED") for n in doc["nodes"]) else 0
