"""M6: frozen, paired, development-only early-incumbent experiment and replay."""
from __future__ import annotations
import argparse
from collections import defaultdict
from datetime import datetime, timezone
from functools import lru_cache
import gzip
import hashlib
import json
from math import fsum
import os
from pathlib import Path
import random
import re
import subprocess
import sys
from time import perf_counter

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from evaluate_anytime import write_json
from scripts.calibrate_timing import environment, probe_executor, digest
from swarm_location.anytime import run_anytime,score_trace
from swarm_location.baseline_proofs import verify_online_bounds
from swarm_location.certificates import ExactCoverage
from swarm_location.core import ShortestPathCoverage
from swarm_location.suite import load_suite,file_sha256
from swarm_location.strong_baselines import BOUND_METHODS, EARLY_PARENTS
from swarm_location.timing_calibration import describe,avg

BASE='deabcf2cc2dfacb1455a337dc0912124331ae38b'
START,END='<!-- M6-EARLY-CONTROLS:START -->','<!-- M6-EARLY-CONTROLS:END -->'
METHODS=['iterated','early_iterated','dfbnb','early_dfbnb','potential','early_potential','topk','early_celf_swap']

def read(path):return json.loads(Path(path).read_text())

def git(*args):return subprocess.check_output(['git',*args],cwd=ROOT)

def sources():
    files=[Path(__file__), ROOT/'scripts/calibrate_timing.py',ROOT/'evaluate_anytime.py',
           ROOT/'configs/early_controls_m6.json',ROOT/'configs/comparisons_m6.json',
           *sorted((ROOT/'swarm_location').glob('*.py'))]
    return {str(p.relative_to(ROOT)):file_sha256(p) for p in files}

def continuity():
    names=git('ls-tree','-r','--name-only',BASE).decode().splitlines()
    changed={'swarm_location/strong_baselines.py','scripts/check_m4_continuity.py','scripts/calibrate_timing.py'}
    protected=[p for p in names if p.startswith(('configs/','results/','data/','swarm_location/'))
               or p in ('evaluate.py','evaluate_anytime.py','anytime_initial.py','initial.py','run_evo.py','campaign.py')]
    unchanged={}
    for p in protected:
        old=git('show',f'{BASE}:{p}')
        if p not in changed:
            if (ROOT/p).read_bytes()!=old:raise ValueError('historical evidence or fixed core changed: '+p)
            unchanged[p]=hashlib.sha256(old).hexdigest()
    if (ROOT/'tests/fixtures/strong_baselines_m5.py').read_bytes()!=git('show',f'{BASE}:swarm_location/strong_baselines.py'):
        raise ValueError('legacy trajectory test fixture is not the actual M5 implementation')
    old=git('show',f'{BASE}:README.md').decode();new=(ROOT/'README.md').read_text()
    blocks=re.findall(r'<!-- ([A-Z0-9-]+):START -->',old)
    for b in blocks:
        a,z=f'<!-- {b}:START -->',f'<!-- {b}:END -->'
        if new.count(a)!=1 or new.count(z)!=1 or old.split(a)[1].split(z)[0]!=new.split(a)[1].split(z)[0]:
            raise ValueError('historical README block changed: '+b)
    return {'base_commit':BASE,'unchanged_files':len(unchanged),'sha256':unchanged,
            'historical_readme_blocks':blocks,'declared_source_changes':sorted(changed),
            'legacy_trajectory_fixture_matches_base':True}

def schedule(config,suite):
    if (config.get('schema_version')!=1 or config.get('base_commit')!=BASE or
        config.get('methods')!=METHODS or config.get('null_baseline')!='early_celf_swap' or
        config.get('longer_budget_assessment') is not None or type(config.get('order_seed')) is not int or
        type(config.get('repeats')) is not int or config['repeats']<2 or config['repeats']%2 or
        suite['checkpoints_seconds']!=config['checkpoints_seconds'] or
        config['checkpoints_seconds']!=[.02,.1,.5,2.]):raise ValueError('invalid M6 protocol')
    if any(e['split']!='development' for e in suite['datasets']):raise ValueError('development only')
    cases=[(e['id'],k,s) for e in suite['datasets'] for k in e['budgets'] for s in suite['seeds']]
    if not cases or len(cases)!=len(set(cases)):raise ValueError('nonempty unique cases required')
    items=[]
    for repeat in range(config['repeats']):
        ordered=list(cases);random.Random(f"{config['order_seed']}:{repeat//2}").shuffle(ordered)
        if repeat%2:ordered.reverse()
        for dataset,k,seed in ordered:
            roles=METHODS+['early_celf_swap_duplicate']
            random.Random(f"{config['order_seed']}:{repeat//2}:{dataset}:{k}:{seed}").shuffle(roles)
            if repeat%2:roles.reverse()
            for pos,role in enumerate(roles):
                items.append({'index':len(items),'repeat':repeat,'dataset':dataset,'k':k,'seed':seed,
                              'position':pos,'role':role,'baseline':config['null_baseline'] if role.endswith('_duplicate') else role})
    return items

def scopes(records):
    yield 'overall',records
    for dataset in sorted({r['dataset'] for r in records}):
        subset=[r for r in records if r['dataset']==dataset];yield dataset,subset
        for k in sorted({r['k'] for r in subset}):yield f'{dataset}/k{k}',[r for r in subset if r['k']==k]

def summarize(records,checkpoints):
    rows=[];pairs=[];curves=[]
    metrics={'checkpoint_mean':lambda r:100*r['mean_checkpoint_coverage'],
             'final':lambda r:100*r['final_coverage']}
    for i in range(len(checkpoints)):metrics[f'checkpoint_{i}']=lambda r,i=i:100*r['coverage_at_checkpoints'][i]
    for scope,subset in scopes(records):
        blocks=sorted({r['repeat'] for r in subset})
        by_role={m:[r for r in subset if r['role']==m] for m in METHODS+['early_celf_swap_duplicate']}
        for role,trials in by_role.items():
            stats={name:describe([avg(fn(r['result']) for r in trials if r['repeat']==b) for b in blocks])
                   for name,fn in metrics.items()}
            first=[next((t for t,s in r['result']['events'] if len(s)==r['k']),None) for r in trials]
            rows.append({'scope':scope,'method':role,'trials':len(trials),'metrics':stats,
                'complete_answer_received':sum(x is not None for x in first),
                'complete_by_checkpoint':[sum(x is not None and x<=t for x in first) for t in checkpoints],
                'first_complete_seconds':{'mean':avg([x for x in first if x is not None]) if any(x is not None for x in first) else None,
                    'min':min([x for x in first if x is not None],default=None),
                    'max':max([x for x in first if x is not None],default=None)},
                'optimality_proofs':sum(bool(r['result'].get('verified_search_bounds') and r['result']['verified_search_bounds'][-1]['optimality_proved']) for r in trials)})
            changes=defaultdict(list)
            for r in trials:
                previous=0.
                for e in r['result']['improvements']:
                    changes[e['received_seconds']].append(100*(e['coverage']-previous)/len(trials));previous=e['coverage']
            level=0.;points=[]
            for t in sorted(changes):level+=fsum(changes[t]);points.append([t,level])
            if points[-1][0]<checkpoints[-1]:points.append([checkpoints[-1],level])
            curves.append({'scope':scope,'method':role,'points_seconds_coverage_pct':points,'interpolation':'previous'})
        for early,parent in [*EARLY_PARENTS.items(),('early_celf_swap_duplicate','early_celf_swap')]:
            lookup={(r['repeat'],r['dataset'],r['k'],r['seed']):r['result'] for r in by_role[parent]}
            deltas={}
            for name,fn in metrics.items():
                values=[]
                for b in blocks:
                    values.append(avg(fn(r['result'])-fn(lookup[(b,r['dataset'],r['k'],r['seed'])])
                                      for r in by_role[early] if r['repeat']==b))
                deltas[name]=describe(values)
            pairs.append({'scope':scope,'early':early,'parent':parent,'null':early.endswith('_duplicate'),
                          'paired_cases':len(lookup),'metrics':deltas})
    return rows,pairs,curves

def execute(output,suite_path,config_path,image):
    if not image:raise ValueError('actual Docker backend required')
    os.environ['SWARM_DOCKER_IMAGE']=image
    env=environment(image);probe=probe_executor()
    output=Path(output)
    if output.exists() and any(output.iterdir()):raise ValueError('use new output; no retries or overwrites')
    output.mkdir(parents=True,exist_ok=True)
    suite,instances=load_suite(suite_path,'development');config=read(config_path);plan=schedule(config,suite)
    # Freeze source, configuration, schedule and datasets before the first solver.
    sha=sources();keep=continuity()
    write_json(output/'schedule.json',plan);write_json(output/'suite.json',suite)
    manifest={'schema_version':1,'config':config,'config_sha256':file_sha256(config_path),
        'suite_sha256':file_sha256(suite_path),'source_commit':git('rev-parse','HEAD').decode().strip(),
        'implementation_sha256':sha,'environment':env,'executor_probe':probe,'continuity':keep,
        'schedule_sha256':file_sha256(output/'schedule.json'),'expected_trials':len(plan),
        'created_utc':datetime.now(timezone.utc).isoformat(),'github_run':os.environ.get('GITHUB_RUN_ID'),
        'model_calls':0,'evolved_descendants':0,'research_validation_test_trials':0}
    write_json(output/'manifest.json',manifest)
    lookup={e['id']:(instance,ShortestPathCoverage(instance)) for e,instance in instances}
    started=perf_counter();completed=0
    try:
        with (output/'trials.jsonl').open('x') as journal:
            for item in plan:
                instance,oracle=lookup[item['dataset']];tick=perf_counter()
                result=run_anytime(instance,item['k'],suite['checkpoints_seconds'],baseline=item['baseline'],seed=item['seed'],oracle=oracle)
                journal.write(json.dumps({**item,'wall_seconds':perf_counter()-tick,'result':result},separators=(',',':'),allow_nan=False)+'\n');journal.flush()
                completed+=1
                if completed%24==0:
                    state={'status':'running','completed_trials':completed,'expected_trials':len(plan)}
                    write_json(output/'status.json',state);print(json.dumps(state),flush=True)
        after=environment(image)
        if sha!=sources() or after['session_key']!=env['session_key']:raise ValueError('source/runtime changed')
        raw=(output/'trials.jsonl').read_bytes();compressed=gzip.compress(raw,mtime=0)
        if gzip.decompress(compressed)!=raw:raise ValueError('compression mismatch')
        (output/'trials.jsonl.gz').write_bytes(compressed);(output/'trials.jsonl').unlink()
        write_json(output/'complete.json',{'completed_trials':completed,'wall_seconds':perf_counter()-started,
            'manifest_sha256':file_sha256(output/'manifest.json'),'journal_sha256':file_sha256(output/'trials.jsonl.gz'),
            'environment_after':after})
        result=verify(output,suite_path,write=True)
        write_json(output/'status.json',{'status':'complete','solver_trials':completed,'failed_trials':result['failed_trials']})
        return result
    except BaseException as exc:
        write_json(output/'status.json',{'status':'interrupted_or_failed','completed_trials':completed,'error':f'{type(exc).__name__}: {exc}'})
        raise

def verify(output,suite_path,write=False):
    output=Path(output);m=read(output/'manifest.json');c=read(output/'complete.json')
    if c['manifest_sha256']!=file_sha256(output/'manifest.json') or c['journal_sha256']!=file_sha256(output/'trials.jsonl.gz'):raise ValueError('evidence changed')
    for p,s in m['implementation_sha256'].items():
        if file_sha256(ROOT/p)!=s:raise ValueError('measured source mismatch: '+p)
    suite,instances=load_suite(suite_path,'development')
    if file_sha256(suite_path)!=m['suite_sha256'] or suite!=read(output/'suite.json'):raise ValueError('suite changed')
    plan=schedule(m['config'],suite)
    if plan!=read(output/'schedule.json') or m['schedule_sha256']!=file_sha256(output/'schedule.json'):raise ValueError('schedule changed')
    with gzip.open(output/'trials.jsonl.gz','rt') as f:records=[json.loads(line) for line in f]
    if len(records)!=len(plan) or len(records)!=c['completed_trials']:raise ValueError('incomplete study')
    lookup={}
    for e,instance in instances:
        exact=ExactCoverage(instance);oracle=ShortestPathCoverage(instance)
        @lru_cache(maxsize=None)
        def scores(group,p=exact,o=oracle):return float(p.score(group)),o.score(group)
        lookup[e['id']]=(instance,oracle,scores)
    deployments=bounds=0;max_diff=0.;failures=[]
    for item,r in zip(plan,records):
        if {k:r[k] for k in item}!=item:raise ValueError('trial identity/order mismatch')
        result=r['result'];instance,oracle,scores=lookup[r['dataset']]
        if result['isolation']!=m['executor_probe']['isolation'] or result['seed']!=r['seed'] or result['k']!=r['k'] or result['instance']!=instance.name:raise ValueError('worker identity changed')
        if not result['correct']:
            failures.append({'index':r['index'],'error':result['error']});continue
        scored=score_trace(instance,r['k'],suite['checkpoints_seconds'],result['events'],oracle)
        if any(scored[k]!=result[k] for k in scored):raise ValueError('trajectory replay mismatch')
        for _,group in result['events']:
            a,b=scores(tuple(group));max_diff=max(max_diff,abs(a-b));deployments+=1
        if max_diff>1e-12:raise ValueError('independent exact score mismatch')
        if r['baseline'] in BOUND_METHODS:
            v=verify_online_bounds(instance,r['k'],result['search_bound_events'])
            if v!=result['verified_search_bounds']:raise ValueError('bound replay mismatch')
            bounds+=len(v)
    rows,pairs,curves=summarize(records,suite['checkpoints_seconds']) if not failures else ([],[],[])
    summary={'schema_version':1,'study_id':m['config']['study_id'],'complete':True,'solver_trials':len(records),
        'failed_trials':len(failures),'failures':failures,'repeats':m['config']['repeats'],
        'cases_per_block':len(plan)//(m['config']['repeats']*(len(METHODS)+1)),
        'independently_rescored_deployments':deployments,'verified_bound_snapshots':bounds,'max_exact_vs_DAG_difference':max_diff,
        'by_method':rows,'paired_differences':pairs,'wall_seconds':c['wall_seconds'],
        'image_id':m['environment']['identity']['image_id'],'session_key':m['environment']['session_key'],
        'model_calls':0,'evolved_descendants':0,'research_validation_test_trials':0,
        'scope':'Descriptive paired host-session ablation; no universal noise guard or held-out superiority claim'}
    for name,data in [('summary.json',summary),('curves.json',curves)]:
        if write:
            if (output/name).exists():raise ValueError('refusing to replace report')
            write_json(output/name,data)
        elif read(output/name)!=data:raise ValueError('saved report not reproducible: '+name)
    return summary

def readme_block(s):
    lines=[f"**Executed:** {s['repeats']} complete paired development blocks, {s['cases_per_block']} cases per block; **{s['solver_trials']:,} Docker solver trials**, {s['failed_trials']} failures. Independent replay rescored {s['independently_rescored_deployments']:,} deployments and verified {s['verified_bound_snapshots']:,} online bound snapshots.",'',
        '| Early control minus original (pp) | Mean checkpoint difference | SD across blocks | Block range | Final difference |',
        '|---|---:|---:|---:|---:|']
    for r in s['paired_differences']:
        if r['scope']!='overall' or r['null']:continue
        d=r['metrics']['checkpoint_mean'];f=r['metrics']['final']
        lines.append(f"| {r['early']} − {r['parent']} | {d['mean']:+.6f} | {d['sd_between_blocks']:.6f} | {d['min']:+.6f} to {d['max']:+.6f} | {f['mean']:+.6f} |")
    null=next(r for r in s['paired_differences'] if r['scope']=='overall' and r['null'])['metrics']['checkpoint_mean']
    lines+=['',f"The same-session identical-`early_celf_swap` probe ranged from **{null['min']:+.6f} to {null['max']:+.6f} pp** across complete blocks. This is a descriptive control, not a significance test or a replacement for the M5 calibration. The historical 1.97 pp threshold is not imported into this different host/session.",'',
        '| Network / control | 20 ms (%) | 100 ms (%) | 500 ms (%) | 2 s (%) | Complete by 20 ms |',
        '|---|---:|---:|---:|---:|---:|']
    for r in s['by_method']:
        if r['scope'] not in ('SiouxFalls','Anaheim') or r['method'].endswith('_duplicate'):continue
        values=' | '.join(f"{r['metrics'][f'checkpoint_{i}']['mean']:.4f}" for i in range(4))
        lines.append(f"| {r['scope']} / {r['method']} | {values} | {r['complete_by_checkpoint'][0]}/{r['trials']} |")
    lines+=['','All six block values, per-source/per-budget paired differences, exact mean incumbent curves, final-coverage variability and the full raw journal are retained. These repetitions are not six independent networks. An early prefix can consume time and change warm-start pruning or improvement-triggered restart decisions; no universal dominance is claimed.',
            '', '**Model calls: 0; evolved descendants: 0; research validation/test trials: 0.** The objective, four checkpoint deadlines and scalar fitness are unchanged.']
    return '\n'.join(lines)+'\n'

def update_readme(summary):
    path=ROOT/'README.md';text=path.read_text();block=readme_block(summary)
    if START in text:
        text=text.split(START)[0]+START+'\n\n'+block+'\n'+END+text.split(END)[1]
    else:
        intro='''### 5.8 M6 — Early incumbents for advanced fixed controls

The [M6 protocol](docs/m6_early_controls.md) compares `early_iterated`,
`early_dfbnb`, and `early_potential` with their original methods. Each reports the
same complete singleton-ranked deployment used by `early_celf_swap` before
building the exact route representation, then continues the existing search while
retaining the best incumbent. Prefix work and all later search share one deadline.
No new optimizer family, alternative routing model, or free preprocessing is added.

'''
        tail='''

[Summary and full block distributions](results/early-controls/study/summary.json),
[frozen source, schedule and runtime](results/early-controls/study/manifest.json),
[raw trials](results/early-controls/study/trials.jsonl.gz), and
[complete coverage curves](results/early-controls/study/curves.json).

The opt-in [`comparisons_m6.json`](configs/comparisons_m6.json) keeps the four
M4 development controls and adds all three early variants to validation/test:
**ten fixed controls, 440 solver invocations per 40-case assessment** including the
candidate. [`m6_launch_request.json`](configs/m6_launch_request.json) selects this
profile. The M4 configuration and previous evidence remain unchanged. These are
planned assessment counts, not executed holdout results. No measured winner was
selected to redefine the comparison set, and native Shinka search remains unrestricted.

'''
        text=text.replace('## 6. Reproduce the first milestone',intro+START+'\n\n'+block+'\n'+END+tail+'## 6. Reproduce the first milestone',1)
    path.write_text(text)

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--suite',default='data/commissioning_m4/suite.json')
    p.add_argument('--config',default='configs/early_controls_m6.json')
    p.add_argument('--output',default='results/local_early_controls')
    p.add_argument('--docker-image');p.add_argument('--verify',action='store_true')
    p.add_argument('--update-readme',action='store_true')
    a=p.parse_args();result=verify(a.output,a.suite) if a.verify else execute(a.output,a.suite,a.config,a.docker_image)
    if a.update_readme:update_readme(result)
    print(json.dumps({k:v for k,v in result.items() if k not in ('by_method','paired_differences')},indent=2))
    if result['failed_trials']:sys.exit(1)
