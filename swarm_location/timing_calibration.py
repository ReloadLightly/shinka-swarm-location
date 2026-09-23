"""Analysis for a host-local timing experiment; never changes numerical fitness.

Replicates are COMPLETE development-suite blocks. Checkpoints, budgets and solver
seeds inside a block are not independent networks or independent repetitions.
"""
from __future__ import annotations
from collections import defaultdict
from math import fsum, isfinite
from decimal import Decimal, ROUND_CEILING
import random
from statistics import stdev

NULL_ROLES = {
    'candidate_a': None, 'candidate_b': None,
    'greedy_a': 'greedy', 'greedy_b': 'greedy',
    'early_a': 'early_celf_swap', 'early_b': 'early_celf_swap',
}
CONTROL_NAMES = ['greedy', 'greedy_swap', 'topk', 'early_celf_swap',
                 'iterated', 'dfbnb', 'potential']


def avg(values):
    values = list(values)
    if not values or any(not isfinite(v) for v in values):
        raise ValueError('nonempty finite measurements required')
    return fsum(values) / len(values)


def describe(values):
    values = list(values)
    return {'n_blocks': len(values), 'mean': avg(values),
            'sd_between_blocks': stdev(values) if len(values) > 1 else None,
            'min': min(values), 'max': max(values),
            'max_absolute': max(map(abs, values)),
            'positive_blocks': sum(v > 0 for v in values), 'values': values}


def checked_config(config):
    if config.get('schema_version') != 1 or not config.get('study_id'):
        raise ValueError('timing config schema 1 and study ID required')
    for key in ('null_repeats', 'control_repeats', 'confirmation_repeats'):
        if type(config.get(key)) is not int or config[key] < 2:
            raise ValueError('at least two complete repeat blocks required')
    if type(config.get('order_seed')) is not int:
        raise ValueError('integer schedule seed required')
    if config.get('controls') != CONTROL_NAMES:
        raise ValueError('retain all seven M4 assessment controls in the calibration')
    for key in ('screening_floor_pp', 'screening_padding_pp'):
        v = config.get(key)
        if isinstance(v, bool) or not isinstance(v, (int, float)) or not isfinite(v) or v <= 0:
            raise ValueError('positive declared screening floor/padding required')
    if config.get('longer_budget_assessment') is not None:
        raise ValueError('longer-budget measurements require a separate protocol')
    return config


def make_schedule(config, suite):
    checked_config(config)
    if suite['checkpoints_seconds'] != config['checkpoints_seconds']:
        raise ValueError('primary checkpoints must remain unchanged')
    if any(e['split'] != 'development' for e in suite['datasets']):
        raise ValueError('calibration may not include a research holdout')
    cases = [(e['id'], k, seed) for e in suite['datasets']
             for k in e['budgets'] for seed in suite['seeds']]
    if not cases or len(cases) != len(set(cases)):
        raise ValueError('nonempty unique calibration cases required')
    blocks = [(phase, r) for phase, n in [('null', config['null_repeats']),
               ('controls', config['control_repeats'])] for r in range(n)]
    random.Random(config['order_seed']).shuffle(blocks)
    schedule = []
    for phase, repeat in blocks:
        ordered = list(cases)
        random.Random(f"{config['order_seed']}:{phase}:{repeat//2}").shuffle(ordered)
        if repeat % 2:
            ordered.reverse()
        roles = list(NULL_ROLES) if phase == 'null' else config['controls'] + ['candidate']
        for dataset, k, seed in ordered:
            order = list(roles)
            random.Random(f"{config['order_seed']}:{phase}:{repeat//2}:{dataset}:{k}:{seed}").shuffle(order)
            if repeat % 2:
                order.reverse()
            for position, role in enumerate(order):
                schedule.append({'index': len(schedule), 'phase': phase, 'repeat': repeat,
                    'dataset': dataset, 'k': k, 'seed': seed, 'position': position,
                    'role': role, 'baseline': NULL_ROLES[role] if phase == 'null'
                        else (None if role == 'candidate' else role)})
    return schedule


def metric(result, name):
    if name == 'checkpoint_mean':
        return 100 * result['mean_checkpoint_coverage']
    if name == 'final':
        return 100 * result['final_coverage']
    return 100 * result['coverage_at_checkpoints'][int(name.split(':')[1])]


def groups(rows):
    yield 'overall', rows
    for dataset in sorted({r['dataset'] for r in rows}):
        subset = [r for r in rows if r['dataset'] == dataset]
        yield dataset, subset
        for k in sorted({r['k'] for r in subset}):
            yield f'{dataset}/k={k}', [r for r in subset if r['k'] == k]


def null_analysis(records, checkpoints):
    rows = []
    metrics = ['checkpoint_mean', 'final'] + [f'checkpoint:{i}' for i in range(len(checkpoints))]
    for scope, selected in groups([r for r in records if r['phase'] == 'null']):
        blocks = sorted({r['repeat'] for r in selected})
        for name in metrics:
            samples = defaultdict(list)
            for repeat in blocks:
                block = [r for r in selected if r['repeat'] == repeat]
                value = {role: avg(metric(r['result'], name) for r in block if r['role'] == role)
                         for role in NULL_ROLES}
                samples['identical_candidate'].append(value['candidate_a'] - value['candidate_b'])
                samples['identical_fixed_greedy'].append(value['greedy_a'] - value['greedy_b'])
                samples['identical_early_hybrid'].append(value['early_a'] - value['early_b'])
                a = value['candidate_a'] - value['greedy_a']
                b = value['candidate_b'] - value['greedy_b']
                samples['refreshed_fitness_difference'].append(a - b)
                # Same greedy rule, DIFFERENT loading/dispatch paths. Not byte-identical null.
                samples['candidate_minus_fixed_greedy_a'].append(a)
                samples['candidate_minus_fixed_greedy_b'].append(b)
            for probe, values in samples.items():
                rows.append({'scope': scope, 'metric': name, 'probe': probe,
                             'block_ids': blocks, **describe(values)})
    return rows


def control_analysis(records, checkpoints):
    rows = []
    selected = [r for r in records if r['phase'] == 'controls']
    for scope, subset in groups(selected):
        for role in CONTROL_NAMES + ['candidate']:
            trials = [r for r in subset if r['role'] == role]
            blocks = sorted({r['repeat'] for r in trials})
            block_values = [avg(metric(r['result'], 'checkpoint_mean') for r in trials if r['repeat']==b)
                            for b in blocks]
            final_values = [avg(metric(r['result'], 'final') for r in trials if r['repeat']==b)
                            for b in blocks]
            rows.append({'scope': scope, 'method': role, 'trials': len(trials),
                'checkpoint_mean_pct': describe(block_values), 'final_pct': describe(final_values),
                'coverage_at_checkpoints_pct': [describe([avg(100*r['result']['coverage_at_checkpoints'][i]
                    for r in trials if r['repeat']==b) for b in blocks]) for i in range(len(checkpoints))],
                'mean_setup_seconds': avg(r['result']['setup_wall_seconds'] for r in trials),
                'mean_total_wall_seconds': avg(r['wall_seconds'] for r in trials),
                'deadlines': sum(r['result']['termination']=='deadline' for r in trials)})
    return rows


def mean_curves(records, checkpoints):
    """Exact mean step functions: no interpolation or invented intermediate solutions."""
    curves = []
    selected = [r for r in records if r['phase'] == 'controls']
    for scope, subset in groups(selected):
        for role in CONTROL_NAMES + ['candidate']:
            trials = [r for r in subset if r['role'] == role]
            changes = defaultdict(list)
            for row in trials:
                previous = 0.0
                for item in row['result']['improvements']:
                    changes[item['received_seconds']].append(100*(item['coverage']-previous)/len(trials))
                    previous = item['coverage']
            level = 0.0
            points = []
            for t in sorted(changes):
                level += fsum(changes[t])
                points.append([t, level])
            if points[-1][0] < checkpoints[-1]:
                points.append([checkpoints[-1], level])
            curves.append({'scope': scope, 'method': role, 'trials': len(trials),
                           'points_seconds_coverage_pct': points, 'interpolation': 'previous'})
    return curves


def empirical_guard(null_rows, config):
    rows = [r for r in null_rows if r['scope']=='overall' and r['metric']=='checkpoint_mean']
    if len(rows) != 6 or any(r['n_blocks'] != config['null_repeats'] for r in rows):
        raise ValueError('guard requires every complete suite-level probe')
    envelope = max(r['max_absolute'] for r in rows)
    threshold = float((Decimal(str(max(config['screening_floor_pp'], envelope)))
                       + Decimal(str(config['screening_padding_pp']))).quantize(
                           Decimal('0.01'), rounding=ROUND_CEILING))
    return {'metric': 'mean_checkpoint_coverage_pp', 'observed_envelope_pp': envelope,
            'threshold_pp': threshold, 'rule': 'ceil_0.01(max(floor, max_abs_all_six_probes) + padding)',
            'floor_pp': config['screening_floor_pp'], 'padding_pp': config['screening_padding_pp'],
            'confirmation_repeats': config['confirmation_repeats'],
            'interpretation': 'Empirical host-session screening guard, NOT a confidence interval, '
                              'p-value, guaranteed false-positive rate or a discovery threshold.'}


def promotion_decision(deltas, threshold):
    """A screen sends a program to confirmation, not to research test or victory."""
    if (set(deltas) != {'greedy', 'early_celf_swap'} or
            any(isinstance(x,bool) or not isinstance(x,(float,int)) or not isfinite(x)
                for x in [threshold, *deltas.values()]) or threshold <= 0):
        raise ValueError('finite paired greedy and early-hybrid deltas and positive guard required')
    return {'promote_to_confirmation': all(d > threshold for d in deltas.values()),
            'threshold_pp': threshold, 'paired_deltas_pp': deltas,
            'discovery_established': False,
            'rule': 'Both paired checkpoint-mean deltas must strictly exceed the empirical guard; '
                    'freeze code and run the declared independent development confirmation next.'}
