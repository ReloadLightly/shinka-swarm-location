"""Run/replay a frozen, development-only calibration on the unchanged Docker backend.

No evolutionary or model calls. No holdout access. New measurements require an
empty output directory; interrupted measurements are preserved, not retried.
"""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
from functools import lru_cache
import gzip
import hashlib
import json
from math import isfinite
import os
from pathlib import Path
import platform
import subprocess
import sys
import tempfile
from time import perf_counter, get_clock_info

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from evaluate_anytime import write_json, evaluate
from swarm_location.anytime import run_anytime, score_trace
from swarm_location.baseline_proofs import verify_online_bounds
from swarm_location.certificates import ExactCoverage
from swarm_location.core import ShortestPathCoverage
from swarm_location.isolation import checked_image, command, cleanup
from swarm_location.suite import file_sha256, load_suite
from swarm_location.timing_calibration import (make_schedule, checked_config, null_analysis,
    control_analysis, mean_curves, empirical_guard, promotion_decision, avg)

BASE = '4c4838f0135812e90a5444657a4719c077c22be4'
START, END = '<!-- M5-TIMING:START -->', '<!-- M5-TIMING:END -->'


def digest(data):
    return hashlib.sha256(json.dumps(data, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def read_json(path):
    return json.loads(Path(path).read_text())


def git(*args):
    return subprocess.check_output(['git', *args], cwd=ROOT, text=True).strip()


def implementations():
    paths = [ROOT/'evaluate_anytime.py', ROOT/'anytime_initial.py', Path(__file__),
             ROOT/'configs/comparisons_m4.json', *sorted((ROOT/'swarm_location').glob('*.py'))]
    return {str(p.relative_to(ROOT)): file_sha256(p) for p in paths}


def continuity():
    # Preserve all existing scientific code/config/data/results; README may append a section.
    protected = git('ls-tree', '-r', '--name-only', BASE).splitlines()
    protected = [p for p in protected if p.startswith(('swarm_location/', 'configs/', 'results/', 'data/'))
                 or p in ('evaluate_anytime.py', 'evaluate.py', 'anytime_initial.py', 'initial.py',
                          'run_evo.py', 'campaign.py', 'scripts/prepare_research.py')]
    extensions = {}
    for p in protected:
        original = subprocess.check_output(['git', 'show', f'{BASE}:{p}'], cwd=ROOT)
        if (ROOT/p).read_bytes() != original:
            if p not in {'swarm_location/strong_baselines.py','swarm_location/anytime.py',
                         'swarm_location/anytime_worker.py','evaluate_anytime.py','run_evo.py','campaign.py'}:
                raise ValueError(f'protected scientific file changed: {p}')
            # M6 extends fixed method dispatch; do not relabel those bytes unchanged.
            # Current execution is pinned separately by implementations().
            extensions[p] = {'historical_sha256': hashlib.sha256(original).hexdigest(),
                             'current_sha256': file_sha256(ROOT/p)}
    old = subprocess.check_output(['git', 'show', f'{BASE}:README.md'], cwd=ROOT).decode()
    current = (ROOT/'README.md').read_text()
    names = ['RESULTS-TABLE','M2-RESULTS','M3-RESULTS','QUALITY-CERTIFICATES',
             'EXCHANGE-LANDSCAPE','STRONG-BASELINES','M4-INTEGRATION']
    for name in names:
        a,b = f'<!-- {name}:START -->', f'<!-- {name}:END -->'
        if current.split(a)[1].split(b)[0] != old.split(a)[1].split(b)[0]:
            raise ValueError(f'historical README block changed: {name}')
    return {'base_commit': BASE, 'protected_files': len(protected),
            'historical_readme_blocks': names, 'unchanged': not extensions,
            'declared_source_extensions': extensions, 'historical_evidence_unchanged': True}


def read_optional(path):
    try:
        return Path(path).read_text().strip()
    except OSError:
        return None


def environment(image):
    checked_image(image)
    resolved = subprocess.check_output(['docker','image','inspect',image,'--format','{{.Id}}'], text=True).strip()
    if resolved != image:
        raise ValueError('executor image identity mismatch')
    docker = json.loads(subprocess.check_output(['docker','version','--format','{{json .Server}}'], text=True))
    boot = read_optional('/proc/sys/kernel/random/boot_id')
    if boot is None:
        raise ValueError('a Linux host-session identity is required')
    cpu = sorted(set(line.split(':',1)[1].strip() for line in Path('/proc/cpuinfo').read_text().splitlines()
                     if line.startswith('model name')))
    identity = {'image_id': image, 'host_python': platform.python_version(),
        'kernel': platform.release(), 'machine': platform.machine(), 'cpu_models': cpu,
        'logical_cpus': os.cpu_count(), 'parent_affinity': sorted(os.sched_getaffinity(0)),
        'docker_version': docker['Version'], 'docker_api': docker['ApiVersion'],
        'host_cpu_max': read_optional('/sys/fs/cgroup/cpu.max'),
        'host_memory_max': read_optional('/sys/fs/cgroup/memory.max')}
    return {'identity': identity, 'hardware_runtime_key': digest(identity),
        'session_key': digest({'boot_sha256': hashlib.sha256(boot.encode()).hexdigest(), **identity}),
        'clock': vars(get_clock_info('perf_counter')), 'load_average': list(os.getloadavg()),
        'mem_available_kib': next((int(line.split()[1]) for line in Path('/proc/meminfo').read_text().splitlines()
                                  if line.startswith('MemAvailable:')), None),
        'governor_cpu0': read_optional('/sys/devices/system/cpu/cpu0/cpufreq/scaling_governor'),
        'captured_utc': datetime.now(timezone.utc).isoformat()}


def probe_executor():
    """Read cgroup/runtime facts in a separate probe using the actual launch helper."""
    code = """import json,os,platform,pathlib
read=lambda p:pathlib.Path(p).read_text().strip() if pathlib.Path(p).exists() else None
print(json.dumps({'uid':os.getuid(),'python':platform.python_version(),'affinity':sorted(os.sched_getaffinity(0)),
'cpu_max':read('/sys/fs/cgroup/cpu.max'),'memory_max':read('/sys/fs/cgroup/memory.max'),
'pids_max':read('/sys/fs/cgroup/pids.max'),'cgroup_v1_cpu_quota':read('/sys/fs/cgroup/cpu/cpu.cfs_quota_us'),
'cgroup_v1_cpu_period':read('/sys/fs/cgroup/cpu/cpu.cfs_period_us')}))"""
    with tempfile.TemporaryDirectory(prefix='swarm-calibration-probe-') as tmp:
        work = Path(tmp); package = work/'swarm_location'; package.mkdir()
        argv, name, mode = command(work, package)
        if mode['mode'] != 'docker':
            raise ValueError('calibration refuses a process-backend substitute')
        try:
            raw = subprocess.check_output(argv[:-5] + ['python','-I','-c',code], text=True, timeout=60)
            facts = json.loads(raw)
        finally:
            cleanup(name, {'PATH': os.defpath})
    if facts['uid'] != 65534:
        raise ValueError('unexpected contained executor identity')
    if facts['cpu_max'] is not None:
        quota, period = facts['cpu_max'].split()
        if quota == 'max' or int(quota) != int(period):
            raise ValueError('one-CPU quota not applied')
        if facts['memory_max'] != str(768*1024*1024) or facts['pids_max'] != '64':
            raise ValueError('executor resource contract changed')
    return {'isolation': mode, 'facts': facts, 'scope': 'Separate diagnostic container, not a timed solver trial'}


def execute(output, suite_path, config_path, image, feedback_profile=None):
    from swarm_location.feedback import checked_profile
    checked_profile(feedback_profile)
    output, suite_path = Path(output), Path(suite_path).resolve()
    if output.exists() and any(output.iterdir()):
        raise ValueError('new measurement requires an empty directory; never retry over observations')
    config = checked_config(read_json(config_path))
    if config['base_commit'] != BASE:
        raise ValueError('unexpected base scientific protocol')
    suite, instances = load_suite(suite_path, 'development')
    schedule = make_schedule(config, suite)
    expected = {e['source_graph'] for e in read_json(ROOT/'configs/source_catalog_m3.json')['datasets']
                if e['split'] == 'development'}
    if {e['source_graph'] for e,_ in instances} != expected:
        raise ValueError('only the original complete development networks are calibrated')
    os.environ['SWARM_DOCKER_IMAGE'] = checked_image(image)
    env = environment(image)
    probe = probe_executor()
    output.mkdir(parents=True, exist_ok=True)
    write_json(output/'schedule.json', schedule)
    write_json(output/'suite.json', suite)
    manifest = {'schema_version': 1, 'config': config, 'config_sha256': file_sha256(config_path),
        'source_commit': git('rev-parse','HEAD'), 'suite_sha256': file_sha256(suite_path),
        'schedule_sha256': file_sha256(output/'schedule.json'), 'implementation_sha256': implementations(),
        'environment': env, 'executor_probe': probe, 'continuity': continuity(),
        'expected_trials': len(schedule), 'candidate_sha256': file_sha256(ROOT/'anytime_initial.py'),
        'same_code_probe': 'candidate_a and candidate_b are copied from the very same unchanged file; '
            'greedy and early pairs use identical baseline IDs and identical worker dispatch',
        'execution': 'serial; independently timed original run_anytime; mirrored shuffled roles/cases; '
            'null and control blocks interleaved by frozen schedule; startup excluded only from inner clock',
        'github_run': os.environ.get('GITHUB_RUN_ID'), 'model_calls': 0,
        'research_validation_test_trials': 0, 'created_utc': datetime.now(timezone.utc).isoformat()}
    if feedback_profile:
        from swarm_location.feedback import load_context
        manifest['feedback_profile'] = feedback_profile
        manifest['feedback_context_sha256'] = load_context()['source_sha256']
    write_json(output/'manifest.json', manifest)  # Frozen BEFORE any calibration solver runs.
    lookup = {e['id']: (instance, ShortestPathCoverage(instance)) for e,instance in instances}
    start, completed = perf_counter(), 0
    write_json(output/'status.json', {'status':'running', 'completed_trials':0})
    try:
        with (output/'trials.jsonl').open('x') as journal:
            last_block = None
            for item in schedule:
                instance, oracle = lookup[item['dataset']]
                tick = perf_counter()
                result = run_anytime(instance, item['k'], config['checkpoints_seconds'],
                    baseline=item['baseline'], program_path=ROOT/'anytime_initial.py' if item['baseline'] is None else None,
                    seed=item['seed'], oracle=oracle, **({'feedback_profile':feedback_profile} if feedback_profile else {}))
                record = {**item, 'wall_seconds': perf_counter()-tick, 'result': result}
                journal.write(json.dumps(record, separators=(',', ':'), allow_nan=False)+'\n')
                journal.flush()
                completed += 1
                block = (item['phase'], item['repeat'])
                if block != last_block or completed % 24 == 0:
                    write_json(output/'status.json', {'status':'running', 'completed_trials':completed,
                        'expected_trials':len(schedule), 'phase':item['phase'], 'repeat':item['repeat'],
                        'wall_seconds':perf_counter()-start, 'load_average':list(os.getloadavg())})
                    print(f'{completed}/{len(schedule)} phase={item["phase"]} block={item["repeat"]}', flush=True)
                last_block = block
        if implementations() != manifest['implementation_sha256'] or file_sha256(suite_path) != manifest['suite_sha256']:
            raise ValueError('measured source or suite changed')
        after = environment(image)
        if after['session_key'] != env['session_key']:
            raise ValueError('host/runtime changed inside calibration')
        raw = (output/'trials.jsonl').read_bytes()
        (output/'trials.jsonl.gz').write_bytes(gzip.compress(raw, mtime=0))
        if gzip.decompress((output/'trials.jsonl.gz').read_bytes()) != raw:
            raise ValueError('journal compression did not preserve evidence')
        (output/'trials.jsonl').unlink()
        write_json(output/'complete.json', {'manifest_sha256': file_sha256(output/'manifest.json'),
            'journal_sha256': file_sha256(output/'trials.jsonl.gz'),
            'completed_trials':completed, 'wall_seconds':perf_counter()-start, 'environment_after':after})
        result = verify(output, suite_path, write=True)
        write_json(output/'status.json', {'status':'complete', 'completed_trials':completed,
            'all_trials_correct':result['failed_trials']==0, 'wall_seconds':perf_counter()-start})
        return result
    except BaseException as exc:
        write_json(output/'status.json', {'status':'interrupted_or_failed', 'completed_trials':completed,
                                         'error':f'{type(exc).__name__}: {exc}'})
        raise


def verify(output, suite_path, write=False):
    output = Path(output)
    manifest, complete = read_json(output/'manifest.json'), read_json(output/'complete.json')
    if complete['manifest_sha256'] != file_sha256(output/'manifest.json') or complete['journal_sha256'] != file_sha256(output/'trials.jsonl.gz'):
        raise ValueError('frozen evidence hash mismatch')
    suite, instances = load_suite(suite_path, 'development')
    if file_sha256(suite_path) != manifest['suite_sha256'] or suite != read_json(output/'suite.json'):
        raise ValueError('replay suite mismatch')
    # Production solver/clock/scoring bytes must match; analysis provenance remains in manifest.
    for p, sha in manifest['implementation_sha256'].items():
        if file_sha256(ROOT/p) != sha:
            raise ValueError(f'measured implementation changed: {p}')
    schedule = make_schedule(manifest['config'], suite)
    if file_sha256(output/'schedule.json') != manifest['schedule_sha256'] or read_json(output/'schedule.json') != schedule:
        raise ValueError('schedule changed')
    with gzip.open(output/'trials.jsonl.gz','rt') as f:
        records = [json.loads(line) for line in f]
    if len(records) != len(schedule) or len(records) != complete['completed_trials']:
        raise ValueError('incomplete calibration; no guard can be derived')
    lookup = {}
    for entry, instance in instances:
        exact = ExactCoverage(instance)
        @lru_cache(maxsize=None)
        def exact_score(group, p=exact):
            return float(p.score(group))
        lookup[entry['id']] = (instance, ShortestPathCoverage(instance), exact_score)
    failures, deployments, max_difference, bounds = [], 0, 0.0, 0
    for planned, row in zip(schedule, records):
        if {k:row[k] for k in planned} != planned:
            raise ValueError('missing/reordered/altered trial in frozen schedule')
        result = row['result']; instance, oracle, exact_score = lookup[row['dataset']]
        if (result['isolation'] != manifest['executor_probe']['isolation'] or result['seed'] != row['seed']
                or result['k'] != row['k'] or result['instance'] != instance.name):
            raise ValueError('solver identity/isolation mismatch')
        if manifest.get('feedback_profile') and result.get('diagnostics',{}).get('profile') != manifest['feedback_profile']:
            raise ValueError('diagnostic mode differs from calibration manifest')
        if not result['correct']:
            failures.append({'index':row['index'], 'error':result['error']})
            continue
        scored = score_trace(instance,row['k'],suite['checkpoints_seconds'],result['events'],oracle)
        if any(scored[k] != result[k] for k in scored):
            raise ValueError('saved trajectory differs from external-clock replay')
        for _, selected in result['events']:
            difference = abs(exact_score(tuple(selected)) - oracle.score(selected))
            max_difference = max(difference,max_difference); deployments += 1
        if max_difference > 1e-12:
            raise ValueError('independent exact-route scorer mismatch')
        if row['baseline'] in ('dfbnb','potential'):
            verified = verify_online_bounds(instance,row['k'],result['search_bound_events'])
            if verified != result['verified_search_bounds']:
                raise ValueError('online bound replay mismatch')
            bounds += len(verified)
    nulls = null_analysis(records,suite['checkpoints_seconds']) if not failures else []
    controls = control_analysis(records,suite['checkpoints_seconds']) if not failures else []
    curves = mean_curves(records,suite['checkpoints_seconds']) if not failures else []
    summary = {'schema_version':1, 'study_id':manifest['config']['study_id'], 'complete':True,
        'solver_trials':len(records), 'failed_trials':len(failures), 'failures':failures,
        'null_blocks':manifest['config']['null_repeats'], 'control_blocks':manifest['config']['control_repeats'],
        'cases_per_block':len({(r['dataset'],r['k'],r['seed']) for r in records}),
        'independently_rescored_deployments':deployments, 'verified_bound_snapshots':bounds,
        'max_exact_vs_DAG_difference':max_difference,
        'guard':empirical_guard(nulls,manifest['config']) if not failures else None,
        'null_analysis':nulls, 'control_analysis':controls,
        'session_key':manifest['environment']['session_key'],
        'image_id':manifest['environment']['identity']['image_id'],
        'wall_seconds':complete['wall_seconds'], 'model_calls':0, 'evolved_descendants':0,
        'research_validation_test_trials':0,
        'scope':'One Docker host session; finite deterministic probes; no universal error rate or transfer claim',
        'manifest_sha256':file_sha256(output/'manifest.json'), 'journal_sha256':complete['journal_sha256']}
    if manifest.get('feedback_profile'):
        from swarm_location.feedback import load_context
        if load_context()['source_sha256'] != manifest['feedback_context_sha256']:
            raise ValueError('feedback context differs from calibration manifest')
        summary['feedback_profile'] = manifest['feedback_profile']
    for name,data in [('summary.json',summary),('curves.json',curves)]:
        if write:
            if (output/name).exists():
                raise ValueError('refusing to replace an existing report')
            write_json(output/name,data)
        elif read_json(output/name) != data:
            raise ValueError(f'report is not reproducible from frozen journal: {name}')
    return summary


def readme_block(s):
    guard = s['guard']
    lines = [f"**Executed:** {s['null_blocks']} complete null blocks and {s['control_blocks']} complete strong-control blocks, "
             f"{s['cases_per_block']} development cases per block; **{s['solver_trials']:,} Docker solver trials**, "
             f"{s['failed_trials']} failed trials. Independent replay rescored {s['independently_rescored_deployments']:,} "
             f"deployments and {s['verified_bound_snapshots']:,} online bound snapshots.", '',
             '| Suite-level timing probe (percentage points) | Mean | SD across blocks | Range |',
             '|---|---:|---:|---:|']
    for r in s['null_analysis']:
        if r['scope']=='overall' and r['metric']=='checkpoint_mean':
            lines.append(f"| {r['probe']} | {r['mean']:+.4f} | {r['sd_between_blocks']:.4f} | {r['min']:+.4f} to {r['max']:+.4f} |")
    if guard:
        lines += ['', f"**Host-session promotion guard: strictly greater than {guard['threshold_pp']:.2f} pp** "
            f"over both freshly measured greedy and the early hybrid. The observed six-probe envelope was "
            f"{guard['observed_envelope_pp']:.4f} pp. This is a conservative **screening heuristic**, not statistical "
            "significance or proof of superiority. It does not alter Shinka fitness or automatically open holdouts."]
    lines += ['', '| Network / method | 20 ms (%) | 100 ms (%) | 500 ms (%) | 2 s (%) | Mean checkpoints (%) |',
               '|---|---:|---:|---:|---:|---:|']
    for r in s['control_analysis']:
        if r['scope'] not in ('SiouxFalls','Anaheim') or r['method']=='candidate':
            continue
        cells = ' | '.join(f"{x['mean']:.4f}" for x in r['coverage_at_checkpoints_pct'])
        lines.append(f"| {r['scope']} / {r['method']} | {cells} | {r['checkpoint_mean_pct']['mean']:.4f} |")
    lines += ['', 'Means describe five complete repetitions on one host, not five independent networks. '
        'The exact mean step-function curves, all per-network/budget/checkpoint null distributions, final-coverage '
        'ranges, and all raw trials are retained. CPU quota is not a dedicated core. **Recalibrate on the actual '
        'future campaign host/session**; these thresholds are not portable to another Actions VM or WSL.', '',
        '**Model calls: 0; evolved descendants: 0; research validation/test trials: 0.** '
        'No longer-budget result was substituted for the unchanged two-second protocol.', '',
        '[Summary and full distributions](results/timing-calibration/study/summary.json), '
        '[frozen schedule and runtime](results/timing-calibration/study/manifest.json), '
        '[exact coverage curves](results/timing-calibration/study/curves.json), '
        '[losslessly compressed raw journal](results/timing-calibration/study/trials.jsonl.gz).']
    return '\n'.join(lines)


def update_readme(summary):
    if summary.get('feedback_profile'):
        raise ValueError('M7 calibration must not replace the historical M5 README block')
    path=ROOT/'README.md'; text=path.read_text()
    if text.count(START)!=1 or text.count(END)!=1:
        raise ValueError('unique M5 README markers required')
    before,rest=text.split(START); _,after=rest.split(END)
    path.write_text(before+START+'\n\n'+readme_block(summary)+'\n\n'+END+after)


def screen(calibration, suite, program, output, image):
    """Explicit optional screen. No native scoring/selection policy is silently changed."""
    calibration, output, program = Path(calibration), Path(output), Path(program).resolve()
    saved = read_json(calibration/'summary.json'); manifest=read_json(calibration/'manifest.json')
    if (file_sha256(calibration/'manifest.json') != saved['manifest_sha256'] or saved['guard'] is None
            or file_sha256(suite) != manifest['suite_sha256']):
        raise ValueError('successful matching calibration required')
    current = environment(image)
    if current['session_key'] != saved['session_key']:
        raise ValueError('calibration belongs to another host/runtime session; recalibrate here')
    if implementations() != manifest['implementation_sha256']:
        raise ValueError('execution/analysis source changed since calibration')
    verify(calibration, suite)  # Re-derive the guard; no trusted hand-edited threshold.
    if output.exists():
        raise ValueError('use a new screen output; no favorable rerun selection')
    output.mkdir(parents=True)
    frozen = output/'candidate.py'; frozen.write_bytes(program.read_bytes())
    write_json(output/'screen_identity.json', {'candidate_sha256':file_sha256(frozen), 'environment':current,
        'calibration_summary_sha256':file_sha256(calibration/'summary.json'), 'holdout_access':False})
    os.environ['SWARM_DOCKER_IMAGE']=checked_image(image)
    metrics = evaluate(frozen, output/'evaluation', suite, 'development',
                       **({'feedback_profile':manifest['feedback_profile']} if manifest.get('feedback_profile') else {}))
    if not read_json(output/'evaluation/correct.json')['correct']:
        raise ValueError('failed screening evaluation; cannot promote')
    deltas = {m:metrics['public'][f'delta_vs_{m}_pp'] for m in ('greedy','early_celf_swap')}
    decision = promotion_decision(deltas,saved['guard']['threshold_pp'])
    decision['confirmation_repeats']=saved['guard']['confirmation_repeats']
    decision['next_step']='Freeze code, then five fresh development assessments against the full declared assessment profile; '
    decision['next_step']+='report every result; do not test until ordinary frozen selection protocol is satisfied.'
    write_json(output/'promotion.json',decision)
    return decision


if __name__ == '__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--suite',type=Path,default=ROOT/'data/commissioning_m4/suite.json')
    p.add_argument('--config',type=Path,default=ROOT/'configs/timing_m5.json')
    p.add_argument('--docker-image')
    p.add_argument('--feedback-profile',choices=['m7-evidence-v1'])
    p.add_argument('--verify',action='store_true')
    p.add_argument('--update-readme',action='store_true')
    p.add_argument('--screen-program',type=Path)
    p.add_argument('--calibration',type=Path)
    a=p.parse_args()
    if a.feedback_profile and (a.verify or a.screen_program):
        target=a.calibration if a.screen_program else a.output
        if read_json(target/'manifest.json').get('feedback_profile') != a.feedback_profile:
            p.error('feedback profile must match the saved calibration')
    if a.screen_program:
        if not a.calibration or not a.docker_image or a.verify or a.update_readme:
            p.error('screen requires calibration and Docker image; no verify/update flags')
        result=screen(a.calibration,a.suite,a.screen_program,a.output,a.docker_image)
    else:
        if not a.verify and not a.docker_image:
            p.error('execution requires an explicit immutable Docker image ID')
        result=verify(a.output,a.suite) if a.verify else execute(a.output,a.suite,a.config,a.docker_image,a.feedback_profile)
        if a.update_readme:
            update_readme(result)
    print(json.dumps({k:v for k,v in result.items() if k not in ('null_analysis','control_analysis')},indent=2))
    if result.get('failed_trials'):
        sys.exit(1)
