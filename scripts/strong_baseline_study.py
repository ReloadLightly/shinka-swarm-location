"""Execute/replay the development-only fixed-control comparison, no model calls.

A new run needs an empty output directory. --verify replays recorded deployments
and partition witnesses; it does not rerun timed solvers or redraw favorable times.
"""
from __future__ import annotations
import argparse
from datetime import datetime,timezone
from fractions import Fraction
import hashlib
import json
from math import fsum,isfinite
from pathlib import Path
import platform
import random
import sys
from time import perf_counter

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from evaluate_anytime import write_json
from swarm_location.anytime import run_anytime,score_trace
from swarm_location.baseline_proofs import verify_online_bounds
from swarm_location.certificates import ExactCoverage
from swarm_location.core import ShortestPathCoverage
from swarm_location.suite import file_sha256,load_suite
from swarm_location.strong_baselines import METHODS


def avg(values):return fsum(values)/len(values)


def summarize(records):
    rows=[]
    for dataset in sorted({r['dataset'] for r in records}):
        cases=[r for r in records if r['dataset']==dataset]
        for method in sorted(cases[0]['methods']):
            results=[c['methods'][method] for c in cases]
            bounds=[r.get('verified_search_bounds',[]) for r in results]
            rows.append({'dataset':dataset,'method':method,'trials':len(cases),
                'failed_trials':sum(not r['correct'] for r in results),
                'checkpoint_coverage_pct':100*avg([r['mean_checkpoint_coverage'] for r in results]),
                'final_coverage_pct':100*avg([r['final_coverage'] for r in results]),
                'mean_delta_vs_greedy_pp':100*avg([c['methods'][method]['mean_checkpoint_coverage']-c['methods']['greedy']['mean_checkpoint_coverage'] for c in cases]),
                'mean_checkpoint_coverage_pct':[100*avg([r['coverage_at_checkpoints'][i] for r in results]) for i in range(len(results[0]['checkpoints_seconds']))],
                'final_online_optimality_proofs':sum(bool(b and b[-1]['optimality_proved']) for b in bounds)})
    six=[c for c in records if c['dataset']=='SiouxFalls' and c['k']==6]
    detail=[]
    if six:
        for method in sorted(six[0]['methods']):
            results=[c['methods'][method] for c in six]
            detail.append({'method':method,'trials':len(results),
                'mean_final_coverage_pct':100*avg([r['final_coverage'] for r in results]),
                'matched_known_optimum_trials':sum(abs(r['final_coverage']-float(Fraction(530,601)))<1e-12 for r in results),
                'strictly_beat_completed_swap_trials':sum(r['final_coverage']>float(Fraction(9408,10818))+1e-12 for r in results)})
    return {'by_network':rows,'sioux_falls_k6':detail}


def implementation_hashes():
    paths=[ROOT/'scripts/strong_baseline_study.py',ROOT/'evaluate_anytime.py',*sorted((ROOT/'swarm_location').glob('*.py'))]
    return {str(p.relative_to(ROOT)):file_sha256(p) for p in paths}


def execute(output,suite_path,config_path):
    output=Path(output);suite_path=Path(suite_path);config_path=Path(config_path)
    if output.exists() and any(output.iterdir()):raise ValueError('use a new output directory; measurements are never overwritten')
    output.mkdir(parents=True,exist_ok=True)
    suite,instances=load_suite(suite_path,'development')
    config=json.loads(config_path.read_text());methods=config['methods'];repeats=config['repeats']
    if type(repeats) is not int or not 1<=repeats<=20 or not methods or len(set(methods))!=len(methods):raise ValueError('invalid fixed study')
    if not {'greedy','greedy_swap'} <= set(methods) or any(m not in ('topk','greedy','greedy_swap','random',*METHODS) for m in methods):raise ValueError('unknown or missing control')
    before=implementation_hashes()
    manifest={'schema_version':1,'created_utc':datetime.now(timezone.utc).isoformat(),
        'config':config,'config_sha256':file_sha256(config_path),'suite':suite,'suite_sha256':file_sha256(suite_path),
        'implementation_sha256':before,'python':platform.python_version(),'platform':platform.platform(),
        'model_calls':0,'validation_test_evaluations':0}
    write_json(output/'manifest.json',manifest)
    # Keep source bytes out of the publication, but pin the existing hashes.
    lookup={e['id']:(e,p,ShortestPathCoverage(p)) for e,p in instances}
    keys=[(e['id'],k,seed,rep) for rep in range(repeats) for e,_ in instances for k in e['budgets'] for seed in suite['seeds']]
    random.Random(20260923).shuffle(keys)
    started=perf_counter();records=[]
    for dataset,k,seed,rep in keys:
        entry,instance,oracle=lookup[dataset]
        order=list(methods);random.Random(f'strong-v1:{dataset}:{k}:{seed}:{rep}').shuffle(order)
        observed={}
        for method in order:
            observed[method]=run_anytime(instance,k,suite['checkpoints_seconds'],baseline=method,seed=seed,oracle=oracle)
            if not observed[method]['correct']:print('FAILED',dataset,k,seed,rep,method,observed[method]['error'],flush=True)
        record={'dataset':dataset,'source_graph':entry['source_graph'],'dataset_sha256':entry['sha256'],
            'k':k,'seed':seed,'repeat':rep,'execution_order':order,'methods':observed}
        records.append(record)
        # JSONL is a durable per-case checkpoint; a killed run is visibly incomplete.
        with (output/'trials.jsonl').open('a') as f:f.write(json.dumps(record,separators=(',',':'),allow_nan=False)+'\n')
        print(f'{len(records)}/{len(keys)} {dataset} k={k} seed={seed} repeat={rep}',flush=True)
    if before!=implementation_hashes():raise ValueError('implementation changed during measurements')
    failures=sum(not r['correct'] for c in records for r in c['methods'].values())
    result={'stage':'complete','paired_cases':len(records),'solver_trials':len(records)*len(methods),
        'failed_trials':failures,'wall_seconds':perf_counter()-started,'model_calls':0,'validation_test_evaluations':0,
        'trials_sha256':file_sha256(output/'trials.jsonl'),'manifest_sha256':file_sha256(output/'manifest.json'),
        'summary':summarize(records)}
    write_json(output/'summary.json',result)
    return result


def verify(output,suite_path):
    output=Path(output);saved=json.loads((output/'summary.json').read_text());manifest=json.loads((output/'manifest.json').read_text())
    if saved['stage']!='complete' or saved['manifest_sha256']!=file_sha256(output/'manifest.json') or saved['trials_sha256']!=file_sha256(output/'trials.jsonl'):
        raise ValueError('incomplete or altered record')
    if manifest['implementation_sha256']!=implementation_hashes():raise ValueError('implementation no longer matches measured source')
    suite,instances=load_suite(suite_path,'development')
    if manifest['suite_sha256']!=file_sha256(suite_path) or manifest['suite']!=suite:raise ValueError('different suite')
    lookup={e['id']:(e,p,ShortestPathCoverage(p),ExactCoverage(p)) for e,p in instances}
    records=[json.loads(line) for line in (output/'trials.jsonl').read_text().splitlines()]
    expected={(e['id'],k,seed,rep) for e,_ in instances for k in e['budgets'] for seed in suite['seeds'] for rep in range(manifest['config']['repeats'])}
    if len(records)!=len(expected) or {(r['dataset'],r['k'],r['seed'],r['repeat']) for r in records}!=expected:
        raise ValueError('missing/duplicate/extra cases')
    bounds=0;deployments=0;max_diff=0.;checkpointcerts=0
    for row in records:
        e,instance,oracle,exact=lookup[row['dataset']]
        if row['dataset_sha256']!=e['sha256'] or row['source_graph']!=e['source_graph']:raise ValueError('source identity mismatch')
        if set(row['methods'])!=set(manifest['config']['methods']) or sorted(row['execution_order'])!=sorted(row['methods']):raise ValueError('incomplete comparisons')
        for method,r in row['methods'].items():
            if r['k']!=row['k'] or r['seed']!=row['seed'] or r['checkpoints_seconds']!=suite['checkpoints_seconds']:raise ValueError('trial identity mismatch')
            checked=score_trace(instance,row['k'],suite['checkpoints_seconds'],r['events'],oracle)
            for key in checked:
                if checked[key]!=r[key]:raise ValueError('saved coverage does not match independent rescoring')
            for _,group in r['events']:
                max_diff=max(max_diff,abs(float(exact.score(group))-oracle.score(group)));deployments+=1
            events=r.get('search_bound_events',[])
            verified=verify_online_bounds(instance,row['k'],events)
            if verified!=r.get('verified_search_bounds',[]):raise ValueError('bound record differs from exact partition replay')
            for t,coverage in zip(suite['checkpoints_seconds'],r['coverage_at_checkpoints']):
                available=[b for b in verified if b['received_seconds']<=t]
                if available:
                    if coverage>float(Fraction(available[-1]['upper_exact']))+1e-12:raise ValueError('checkpoint solution exceeds verified bound')
                    checkpointcerts+=1
            bounds+=len(verified)
    if summarize(records)!=saved['summary']:raise ValueError('summary mismatch')
    if saved['solver_trials']!=sum(len(r['methods']) for r in records) or saved['paired_cases']!=len(records):raise ValueError('incorrect counts')
    failures=sum(not r['correct'] for c in records for r in c['methods'].values())
    if failures!=saved['failed_trials']:raise ValueError('failure count mismatch')
    return {'success':True,'paired_cases':len(records),'solver_trials':saved['solver_trials'],'failed_trials':failures,
        'deployments_rescored':deployments,'online_partition_snapshots_verified':bounds,
        'checkpoint_bound_pairs_verified':checkpointcerts,'max_exact_vs_float_score_difference':max_diff,
        'trials_sha256':saved['trials_sha256'],'model_calls':0,'validation_test_evaluations':0}


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--suite',type=Path,default=ROOT/'data/commissioning/suite.json')
    p.add_argument('--config',type=Path,default=ROOT/'configs/strong_baselines.json')
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--verify',action='store_true')
    a=p.parse_args()
    result=verify(a.output,a.suite) if a.verify else execute(a.output,a.suite,a.config)
    print(json.dumps(result,indent=2))
    if result.get('failed_trials'):raise SystemExit(1)
