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


def parser():
    p = argparse.ArgumentParser(description=__doc__)
    action = p.add_mutually_exclusive_group()
    action.add_argument('--run', action='store_true')
    action.add_argument('--native-seed', action='store_true')
    action.add_argument('--check-native', action='store_true')
    p.add_argument('--config', type=Path, default=ROOT/'configs/evolution.json')
    p.add_argument('--suite', type=Path, default=ROOT/'data/commissioning/suite.json')
    p.add_argument('--results-dir', type=Path, default=ROOT/'results/local_evolution')
    p.add_argument('--models', nargs='+')
    p.add_argument('--meta-model')
    p.add_argument('--novelty-model')
    p.add_argument('--embedding-model')
    p.add_argument('--max-api-cost', type=float)
    p.add_argument('--generations', type=int)
    p.add_argument('--docker-image', help='Immutable local sha256 image ID; opt-in for M2, required by M3 campaign')
    p.add_argument('--seed', type=int, default=0, help='Host RNG seed; provider calls are not bitwise deterministic')
    return p


def plan(args):
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
    task = TASK
    feedback_context = None
    if config.get("feedback_profile") is not None:
        from swarm_location.feedback import checked_profile, load_context
        checked_profile(config["feedback_profile"])
        feedback_context = load_context()
        task += "\n" + feedback_context["task_context"]
    if comparisons is not None:
        task += ("\nVersioned screening controls: " + ', '.join(comparisons['baselines'])
            + ". Frozen validation/test controls: " + ', '.join(comparisons['assessment_baselines'])
            + ". Comparisons report each fixed method separately; there is no oracle portfolio. "
            "Beating timed greedy alone is not a discovery. Distinguish checkpoint improvements "
            "from final-coverage improvements. Assessment data never enter development feedback.\n")
    evo = dict(config['evo_config'], num_generations=generations,
        task_sys_msg=task, job_type='local', language='python',
        init_program_path=str(ROOT/'anytime_initial.py'), results_dir=str(output),
        llm_models=args.models or [], meta_llm_models=[args.meta_model] if args.meta_model else [],
        novelty_llm_models=[args.novelty_model] if args.novelty_model else [],
        embedding_model=args.embedding_model, max_api_costs=args.max_api_cost)
    job = {'eval_program_path': str(ROOT/'evaluate_anytime.py'),
           'extra_cmd_args': {'suite': str(args.suite.resolve()), 'split': 'development'},
           'python_executable': sys.executable, 'numeric_threads_per_job': 1,
           'eval_verbose': True, 'time': '01:00:00'}
    if feedback_context:
        job['extra_cmd_args']['feedback_profile'] = feedback_context['profile_id']
    db = dict(config['db_config'], db_path=str(output/'evolution_db.sqlite'))
    resolved = {'framework_commit': config['framework_commit'], 'evo_config': evo,
        'db_config': db, 'job_config': job,
        'max_evaluation_jobs': config['max_evaluation_jobs'],
        'max_proposal_jobs': config['max_proposal_jobs'], 'max_db_workers': config['max_db_workers'],
        'suite_sha256': file_sha256(args.suite),
        'candidate_sha256': file_sha256(ROOT/'anytime_initial.py'), 'host_seed': args.seed,
        'docker_image_id': args.docker_image,
        'development_cases': sum(len(e['budgets']) for e, _ in instances)*len(suite['seeds']),
        'source_networks': len(instances), 'checkpoints_seconds': suite['checkpoints_seconds'],
        'model_calls_enabled': args.run,
        'scope': 'Development evaluation only. No held-out result is implied.'}
    if feedback_context:
        resolved['feedback_context'] = feedback_context
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
    version = verify_native(resolved['framework_commit'])
    from shinka.core import EvolutionConfig, ShinkaEvolveRunner
    from shinka.database import DatabaseConfig
    from shinka.launch import LocalJobConfig
    from shinka.launch.scheduler import JobScheduler
    evo = EvolutionConfig(**resolved['evo_config'])
    db = DatabaseConfig(**resolved['db_config'])
    job = LocalJobConfig(**resolved['job_config'])
    output.mkdir(parents=True, exist_ok=True)
    if resolved.get('feedback_context'):
        write_json(output/'feedback_context.json', resolved['feedback_context'])
    if args.check_native:
        write_json(output/'native_config_check.json', {**version, 'configuration_constructed': True,
            'model_calls': 0, 'islands': db.num_islands, 'mutation_bandit': evo.llm_dynamic_selection,
            'meta_is_separate': True, 'runner_imported': ShinkaEvolveRunner.__name__})
        return
    if args.native_seed:
        scheduler = JobScheduler('local', job, verbose=True, max_workers=1)
        try:
            results, seconds = scheduler.run(str(ROOT/'anytime_initial.py'), str(output/'seed'))
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
                          for p in [ROOT/'evaluate_anytime.py', ROOT/'run_evo.py',
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
    if resolved.get('feedback_context'):
        from swarm_location.feedback import attach_meta_context
        attach_meta_context(runner, resolved['feedback_context'], output)
    runner.run()


if __name__ == '__main__':
    main()
