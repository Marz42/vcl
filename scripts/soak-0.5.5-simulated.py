#!/usr/bin/env python3
"""Real-clock >=10-node scheduler/caching exercise; all telemetry is synthetic.

No SSH, real credentials, real proxy, Node mutation or Live acceptance. Default
duration is two actual hours. A shorter invocation is explicitly smoke-only.
Run from the source checkout, not an installed Controller distribution.
"""
import argparse
import copy
import hashlib
import json
import os
from pathlib import Path
import random
import sys
import threading
import time
import uuid

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tests'))
import test_monitor as fixtures


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--duration-seconds',type=float,default=7200)
    parser.add_argument('--nodes',type=int,default=10)
    parser.add_argument('--interval',type=float,default=30)
    parser.add_argument('--source-commit',default='UNBOUND')
    args=parser.parse_args()
    if args.duration_seconds < 1 or args.nodes < 10 or args.nodes > 1024:
        parser.error('require >=1 second and 10..1024 synthetic nodes')
    output=args.output.resolve()
    output.mkdir(parents=True,exist_ok=True)
    if (output/'observation.db').exists():
        parser.error('output already contains a database; use a new directory')
    hashes={str(path.relative_to(ROOT)):hashlib.sha256(path.read_bytes().replace(b'\r\n',b'\n')).hexdigest()
            for path in sorted((ROOT/'lib/observation').glob('*.py'))}
    hashes['tests/fixtures/schemas/telemetry/v1-valid.json']=hashlib.sha256((ROOT/'tests/fixtures/schemas/telemetry/v1-valid.json').read_bytes().replace(b'\r\n',b'\n')).hexdigest()
    for relative in ('tests/test_monitor.py','scripts/soak-0.5.5-simulated.py'):
        hashes[relative]=hashlib.sha256((ROOT/relative).read_bytes().replace(b'\r\n',b'\n')).hexdigest()
    nodes=[{'name':f'synthetic-{i:02d}','node_id':str(uuid.uuid5(uuid.NAMESPACE_OID,f'vcl-055-synthetic-{i}')),'enabled':True} for i in range(args.nodes)]
    stats={n['node_id']:{'samples':0,'last_at':None,'maximum_gap_seconds':0} for n in nodes}
    counters={n['node_id']:0 for n in nodes}
    mutex=threading.Lock()
    active=maximum_active=observation_errors=0

    def fetch(node,**_kwargs):
        nonlocal active,maximum_active
        with mutex:
            active+=1;maximum_active=max(active,maximum_active)
            counters[node['node_id']]+=1
            count=counters[node['node_id']]
        try:
            time.sleep(.02)
            result=fixtures.ok(time.time(),node_id=node['node_id'],instance_id=str(uuid.uuid5(uuid.NAMESPACE_OID,node['node_id'])))
            result['snapshot']['network'].update(rx_bytes=count*1000,tx_bytes=count*2000)
            return result
        finally:
            with mutex:active-=1

    def emit(event):
        nonlocal observation_errors
        now=time.monotonic()
        node=next(n for n in nodes if n['name']==event['name'])
        with mutex:
            if event.get('observation_state') != 'OK':
                observation_errors+=1
            record=stats[node['node_id']]
            if record['last_at'] is not None:
                record['maximum_gap_seconds']=max(record['maximum_gap_seconds'],now-record['last_at'])
            record['last_at']=now;record['samples']+=1

    stop=threading.Event()
    timer=threading.Timer(args.duration_seconds,stop.set)
    start=time.monotonic()
    def progress():
        while not stop.is_set():
            with mutex:
                data={'state':'RUNNING SYNTHETIC','source_commit':args.source_commit,
                      'elapsed_seconds':time.monotonic()-start,
                      'samples':sum(s['samples'] for s in stats.values()),
                      'maximum_concurrency':maximum_active,'observation_errors':observation_errors}
            staged=output/'PROGRESS.tmp'
            staged.write_text(json.dumps(data)+'\n',encoding='utf-8')
            os.replace(staged,output/'PROGRESS.json')
            stop.wait(30)
    progress_thread=threading.Thread(target=progress,daemon=True)
    (output/'START.json').write_text(json.dumps({'source_commit':args.source_commit,'inputs':hashes,'requested_seconds':args.duration_seconds},indent=2)+'\n',encoding='utf-8')
    progress_thread.start()
    timer.start()
    try:
        service=fixtures.monitor.Monitor(nodes,fixtures.store_mod.Store(output/'observation.db'),fetch,interval=args.interval,timeout=5,concurrency=8,rng=random.Random(55))
        result=service.run(stop=stop,emit=emit)
    finally:
        stop.set();timer.cancel();timer.join();progress_thread.join()
    elapsed=time.monotonic()-start
    summaries=[{'name':n['name'],'samples':stats[n['node_id']]['samples'],
                'maximum_gap_seconds':stats[n['node_id']]['maximum_gap_seconds']} for n in nodes]
    enough=all(r['samples']>=max(1,int(elapsed/args.interval*.85)) and r['maximum_gap_seconds']<=args.interval*2.5+1 for r in summaries)
    passed=enough and observation_errors==0 and maximum_active<=8 and result['cache_write_errors']==0
    report={'evidence_kind':'SYNTHETIC_REAL_CLOCK','source_commit':args.source_commit,'inputs':hashes,
            'requested_seconds':args.duration_seconds,'elapsed_seconds':elapsed,'nodes':summaries,
            'maximum_concurrency':maximum_active,'scheduler':result,
            'observation_errors':observation_errors,
            'two_hour_matrix':bool(passed and elapsed>=7200 and args.nodes>=10),
            'state':('PASS OFFLINE' if elapsed>=7200 else 'PASS OFFLINE SMOKE') if passed else 'FAIL OFFLINE',
            'proxy_live':'NOT RUN','inspect_live':'NOT RUN','human_acceptance':'NOT SIGNED',
            'database_bytes':(output/'observation.db').stat().st_size}
    (output/'SUMMARY.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({k:report[k] for k in ('state','elapsed_seconds','two_hour_matrix','maximum_concurrency')}),flush=True)
    return 0 if passed else 1


if __name__=='__main__':
    raise SystemExit(main())
