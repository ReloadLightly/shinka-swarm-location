"""Native ShinkaEvolve launcher: preflight, no-model native seed, or real evolution.

No handwritten evolutionary loop. An evolution run requires explicit model roles
and an API spending threshold; --native-seed and --check-native make no model calls.
"""
from __future__ import annotations
import argparse
import importlib.metadata
import json
from math import isfinite
import os
from pathlib import Path
import random
import sys

from evaluate_anytime import write_json
from swarm_location.suite import file_sha256, load_suite
from swarm_location.comparisons import comparison_plan

ROOT = Path(__file__).resolve().parent
TASK = """Evolve a reusable anytime algorithm for endpoint-inclusive OD-weighted group
coverage on fixed directed shortest routes. Change only the EVOLVE block. The API
is solve(problem, k, random_seed, report, time_budget); return a node list or None.
problem.nodes, problem.instance, problem.dags, problem.score(selected), and
problem.marginal_gains(selected) are available. The latter computes exact-route
marginal gains using DAG dependencies, not sampled paths. Call report(selected)
to submit feasible incumbents; partial deployments with <=k distinct nodes are
valid. The external clock includes candidate imports and all search work, after
common graph preprocessing. Only complete reports received by a checkpoint count.
The objective is 100 plus mean checkpoint-coverage improvement in percentage
points over a same-budget greedy control. Numerical score and feasibility are
independently checked. Fixed greedy+swap is also compared, so beating greedy alone
does not establish a discovery. All search construction, revision, exchange,
restart and compute-allocation logic may change; there is no finite catalogue of
allowed algorithms. Never hardcode node IDs or instance answers. Do not modify
routing, OD demand, score, clocks, benchmark files or runtime isolation. Standard
library is available; no model calls inside a candidate. Propose explanations
supported by measured per-source/per-budget differences, then test those mechanisms.
A positive development score is not held-out transfer or real-world detection.
"""



SEARCH_TASK = """Evolve a complete reusable search procedure for chapter 4.7.4:
place at most k monitors to cover distinct trips on fixed directed shortest routes.
The whole EVOLVE block is editable, including imports, data structures, construction,
revision, sampling, local search, populations, restarts, frontier policy, branching,
pruning and compute allocation. There is no finite candidate catalogue.
API: solve(problem, k, random_seed, report, time_budget), returning a node list or None.
problem.nodes and instance expose the anonymous graph and fixed OD demands.
problem.dags is a sequence of per-origin shortest-path DAGs: source, topological
order, predecessors[v], counts[v] (number of original shortest paths), destinations
(target, demand). Endpoints count; no monitor-induced rerouting. The same vehicle
is counted once even if its route intersects several monitors.
problem.score(S) and marginal_gains(S) are exact-route numerical queries.
score_origins(S, origins) and marginal_gains_origins(S, origins) return selected
origins' contributions normalized by FULL demand. origin_demand and origin_arcs
support adaptive estimation. Raw DAGs remain available for custom kernels.
Call report(S) for feasible incumbents. report.bound(witness) supports independently
replayed universal_v1, online_partition_v1 or dag_partition_v2 certificates.
The optional DagPartition helper maintains a complete proof partition without
route enumeration; call split(parent_id, node_id) and report.bound(snapshot(S)).
You choose the search policy; helper use is optional. Report all completed journal
operations since the previous snapshot. Candidate-supplied bare scores and bounds
are not trusted. report.diagnostic accepts compact measured mechanism diagnostics.
Fitness reports normalized anytime coverage and certified lower/upper quality
separately, plus their suite-declared weighted mean. Normalizers are offline best
feasible fixed controls, NOT optimal values; improvements may exceed one. Every
fixed control uses the same API and timing. Baselines are NOT rerun per candidate.
Common route DAGs are prepared once; every worker hydrates private data before GO.
A failed program receives a redacted diagnostic tail. Completed cases resume;
a verifier retry replays the same captured search, not a new favorable trial.
Use per-case evidence to explain tradeoffs and propose the next testable mechanism.
Candidate imports, custom preprocessing and search run within the elapsed-time
budget. API work counters are incomplete diagnostics, not the computation budget.
Do not modify the evaluator, graph, fixed routes, OD demands or execution protocol.
"""


def parser():
    p = argparse.ArgumentParser(description=__doc__)
    action = p.add_mutually_exclusive_group()
    action.add_argument('--run', action='store_true')
    action.add_argument('--native-seed', action='store_true')
    action.add_argument('--check-native', action='store_true')
    p.add_argument('--config', type=Path, default=ROOT/'configs/evolution_search.json')
    p.add_argument('--suite', type=Path, default=ROOT/'data/search/suite.json')
    p.add_argument('--results-dir', type=Path, default=ROOT/'results/local_evolution')
    p.add_argument('--models', nargs='+')
    p.add_argument('--meta-model')
    p.add_argument('--novelty-model')
    p.add_argument('--embedding-model')
    p.add_argument('--max-api-cost', type=float)
    p.add_argument('--generations', type=int)
    p.add_argument('--references', type=Path, help='Identity-pinned offline reference file')
    p.add_argument('--dag-cache', type=Path, help='Reusable evaluator-owned common DAG cache')
    p.add_argument('--trusted-local', action='store_true', help='Trusted no-model seed debugging only; never --run')
    p.add_argument('--docker-image', help='Immutable local sha256 Docker image ID for generated-program isolation')
    p.add_argument('--seed', type=int, default=0, help='Host RNG seed; provider calls are not bitwise deterministic')
    p.add_argument('--evaluation-time', help='Native per-candidate job timeout, HH:MM:SS')
    return p


def plan(args):
    if args.run and (not args.docker_image or args.trusted_local):
        raise ValueError('real evolution requires --docker-image; --trusted-local cannot authorize generated code')
    if args.native_seed and not args.docker_image and not args.trusted_local:
        raise ValueError('native seed needs Docker or explicit --trusted-local debugging')
    if args.docker_image:
        from swarm_location.isolation import checked_image
        checked_image(args.docker_image)
    config = json.loads(args.config.read_text())
    suite, instances = load_suite(args.suite, 'development')
    for role in ('models', 'meta_model', 'novelty_model', 'embedding_model'):
        value = getattr(args, role)
        if args.run and (not value or (isinstance(value, str) and not value.strip())):
            raise ValueError(f'--{role.replace("_", "-")} is required for real evolution')
    if args.models and (len(set(args.models)) != len(args.models) or any(not m.strip() for m in args.models)):
        raise ValueError('model pool entries must be nonempty and unique')
    if args.run and (args.max_api_cost is None or not isfinite(args.max_api_cost) or args.max_api_cost <= 0):
        raise ValueError('set a finite positive --max-api-cost; native threshold may overshoot with in-flight calls')
    generations = args.generations if args.generations is not None else config['evo_config']['num_generations']
    if type(generations) is not int or generations < 1:
        raise ValueError('generations must be a positive integer')
    output = args.results_dir.resolve()
    comparisons = comparison_plan(suite, 'development',
        sum(len(e['budgets']) for e, _ in instances) * len(suite['seeds']))
    new_search = suite.get('research_protocol') == 'chapter-search-v2'
    task = SEARCH_TASK if new_search else TASK
    seed_path = ROOT/('search_initial.py' if new_search else 'anytime_initial.py')
    eval_path = ROOT/('evaluate_search.py' if new_search else 'evaluate_anytime.py')
    if comparisons is not None:
        task += ("\nVersioned screening controls: " + ', '.join(comparisons['baselines'])
            + ". Frozen validation/test controls: " + ', '.join(comparisons['assessment_baselines'])
            + ". Comparisons report each fixed method separately; there is no oracle portfolio. "
            "Beating timed greedy alone is not a discovery. Distinguish checkpoint improvements "
            "from final-coverage improvements. Assessment data never enter development feedback.\n")
    evo = dict(config['evo_config'], num_generations=generations,
        task_sys_msg=task, job_type='local', language='python',
        init_program_path=str(seed_path), results_dir=str(output),
        llm_models=args.models or [], meta_llm_models=[args.meta_model] if args.meta_model else [],
        novelty_llm_models=[args.novelty_model] if args.novelty_model else [],
        embedding_model=args.embedding_model, max_api_costs=args.max_api_cost)
    job = {'eval_program_path': str(eval_path),
           'extra_cmd_args': {'suite': str(args.suite.resolve()), 'split': 'development'},
           'python_executable': sys.executable, 'numeric_threads_per_job': 1,
           'eval_verbose': True, 'time': getattr(args, 'evaluation_time', None) or config.get('evaluation_job_time', '01:00:00')}
    if args.references:
        job['extra_cmd_args']['references'] = str(args.references.resolve())
    if args.dag_cache:
        job['extra_cmd_args']['dag-cache'] = str(args.dag_cache.resolve())
    if args.trusted_local:
        job['extra_cmd_args']['trusted-local'] = True
    db = dict(config['db_config'], db_path=str(output/'evolution_db.sqlite'))
    resolved = {'framework_commit': config['framework_commit'], 'evo_config': evo,
        'db_config': db, 'job_config': job,
        'max_evaluation_jobs': config['max_evaluation_jobs'],
        'max_proposal_jobs': config['max_proposal_jobs'], 'max_db_workers': config['max_db_workers'],
        'suite_sha256': file_sha256(args.suite),
        'candidate_sha256': file_sha256(seed_path), 'host_seed': args.seed,
        'docker_image_id': args.docker_image,
        'development_cases': sum(len(e['budgets']) for e, _ in instances)*len(suite['seeds']),
        'source_networks': len(instances), 'checkpoints_seconds': suite['checkpoints_seconds'],
        'research_protocol': suite.get('research_protocol', 'historical'),
        'model_calls_enabled': args.run,
        'scope': 'Development evaluation only. No held-out result is implied.'}
    if comparisons is not None:
        resolved['comparison_plan'] = comparisons
    return resolved


def verify_native(commit):
    distribution = importlib.metadata.distribution('shinka-evolve')
    origin = json.loads(distribution.read_text('direct_url.json') or '{}')
    actual = origin.get('vcs_info', {}).get('commit_id')
    if actual != commit:
        raise RuntimeError(f'Install requirements-shinka.txt: expected native commit {commit}; installed {actual}')
    return {'package_version': distribution.version, 'installed_commit': actual}


def main(argv=None):
    args = parser().parse_args(argv)
    resolved = plan(args)
    if args.docker_image:
        os.environ['SWARM_DOCKER_IMAGE'] = args.docker_image
    elif os.environ.get('SWARM_DOCKER_IMAGE'):
        raise ValueError('pass --docker-image explicitly to record an inherited container setting')
    output = args.results_dir.resolve()
    print(json.dumps(resolved, indent=2))
    if not (args.run or args.native_seed or args.check_native):
        return  # Dependency-free plan; no framework/client initialization.
    if args.run or args.native_seed:
        from swarm_location.isolation import require_isolation
        require_isolation(args.trusted_local, check_available=True)
    version = verify_native(resolved['framework_commit'])
    from shinka.core import EvolutionConfig, ShinkaEvolveRunner
    from shinka.database import DatabaseConfig
    from shinka.launch import LocalJobConfig
    from shinka.launch.scheduler import JobScheduler
    evo = EvolutionConfig(**resolved['evo_config'])
    db = DatabaseConfig(**resolved['db_config'])
    job = LocalJobConfig(**resolved['job_config'])
    output.mkdir(parents=True, exist_ok=True)
    if args.check_native:
        write_json(output/'native_config_check.json', {**version, 'configuration_constructed': True,
            'model_calls': 0, 'islands': db.num_islands, 'mutation_bandit': evo.llm_dynamic_selection,
            'meta_is_separate': True, 'runner_imported': ShinkaEvolveRunner.__name__})
        return
    if args.native_seed:
        scheduler = JobScheduler('local', job, verbose=True, max_workers=1)
        try:
            results, seconds = scheduler.run(resolved['evo_config']['init_program_path'], str(output/'seed'))
        finally:
            scheduler.executor.shutdown(wait=True)
        correct = results.get('correct', {}).get('correct', False)
        write_json(output/'native_seed_check.json', {**version, 'correct': correct,
            'native_scheduler': type(scheduler).__name__, 'wall_seconds': seconds,
            'model_calls': 0, 'evolved_descendants': 0,
            'combined_score': results.get('metrics', {}).get('combined_score'),
            'suite_sha256': resolved['suite_sha256']})
        if not correct:
            raise RuntimeError('native seed evaluation failed; inspect seed/correct.json')
        return
    manifest = output/'run_manifest.json'
    identity = {**resolved, **version,
        'source_sha256': {str(p.relative_to(ROOT)): file_sha256(p)
                          for p in [Path(resolved['job_config']['eval_program_path']), ROOT/'run_evo.py',
                                    *sorted((ROOT/'swarm_location').glob('*.py'))]}}
    if manifest.exists() and json.loads(manifest.read_text()) != identity:
        raise RuntimeError('resume identity changed; use a new results directory, or restore the original protocol')
    if not manifest.exists() and (output/'evolution_db.sqlite').exists():
        raise RuntimeError('existing database without this experiment manifest; use a new results directory')
    write_json(manifest, identity)
    random.seed(args.seed)
    import numpy as np
    np.random.seed(args.seed)
    os.chdir(ROOT)
    runner = ShinkaEvolveRunner(evo_config=evo, job_config=job, db_config=db,
        max_evaluation_jobs=resolved['max_evaluation_jobs'],
        max_proposal_jobs=resolved['max_proposal_jobs'], max_db_workers=resolved['max_db_workers'],
        verbose=True, debug=False)
    runner.run()


if __name__ == '__main__':
    main()
