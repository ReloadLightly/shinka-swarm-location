"""Generate scientific baseline tables from completed, independently checked evidence.

No solver runs, score changes or inferred campaign success. Historical tables stay
untouched. --check verifies the committed section and detailed comparison file.
"""
from __future__ import annotations
import argparse
from fractions import Fraction
import hashlib
import json
from pathlib import Path
import re
from statistics import median

ROOT=Path(__file__).resolve().parents[1]
START='<!-- STRONG-BASELINES:START -->'
END='<!-- STRONG-BASELINES:END -->'
LABELS={'topk':'Singleton ranking','greedy':'DAG greedy','greedy_swap':'DAG greedy + swap',
        'route_greedy':'Route greedy','celf':'Route CELF','route_swap':'Route CELF + swap',
        'early_celf_swap':'Early topk + CELF/swap','iterated':'Fixed iterated search',
        'dfbnb':'Anytime DFBnB','potential':'Utility-form APTS'}


def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def content(evidence):
    evidence=Path(evidence)
    summary=json.loads((evidence/'study/summary.json').read_text())
    manifest=json.loads((evidence/'study/manifest.json').read_text())
    verification=json.loads((evidence/'verification.json').read_text())
    tests=(evidence/'tests.txt').read_text()
    match=re.findall(r'Ran (\d+) tests? in',tests)
    if not match or not re.search(r'^OK\s*$',tests,re.M):raise ValueError('missing successful tests')
    if (summary['stage']!='complete' or not verification['success']
            or summary['trials_sha256']!=sha(evidence/'study/trials.jsonl')
            or summary['manifest_sha256']!=sha(evidence/'study/manifest.json')
            or verification['trials_sha256']!=summary['trials_sha256']
            or summary['failed_trials']!=verification['failed_trials']):
        raise ValueError('missing, incomplete or mismatched study verification')
    methods=manifest['config']['methods']
    rows={(r['dataset'],r['method']):r for r in summary['summary']['by_network']}
    datasets=sorted({r[0] for r in rows})
    table=['| Development network | Fixed method | Mean checkpoint coverage (%) | Mean final coverage (%) | Online optimum proofs / trials |',
           '|---|---|---:|---:|---:|']
    for dataset in datasets:
        for method in methods:
            r=rows[dataset,method]
            proof=f"{r['final_online_optimality_proofs']}/{r['trials']}" if method in ('dfbnb','potential') else 'Not emitted'
            table.append(f"| {dataset} | {LABELS[method]} | {r['checkpoint_coverage_pct']:.4f} | {r['final_coverage_pct']:.4f} | {proof} |")
    table.extend(['', '**Six-monitor Sioux Falls diagnostic within the timed comparison:**', '',
        '| Fixed method | Mean final coverage (%) | Trials matching known optimum | Trials strictly above completed old swap |',
        '|---|---:|---:|---:|'])
    six={r['method']:r for r in summary['summary']['sioux_falls_k6']}
    for method in methods:
        r=six[method]
        table.append(f"| {LABELS[method]} | {r['mean_final_coverage_pct']:.4f} | {r['matched_known_optimum_trials']}/{r['trials']} | {r['strictly_beat_completed_swap_trials']}/{r['trials']} |")
    table.extend(['', f"**Executed evidence:** {match[-1]} tests passed; {summary['paired_cases']} paired cases, "
        f"{summary['solver_trials']} timed trials, {summary['failed_trials']} failed trials. "
        f"Independent replay checked {verification['deployments_rescored']:,} reported deployments, "
        f"{verification['online_partition_snapshots_verified']:,} transmitted bound snapshots, and "
        f"{verification['checkpoint_bound_pairs_verified']:,} checkpoint/bound pairs. "
        f"Maximum exact-versus-production score difference: {verification['max_exact_vs_float_score_difference']:.3g}.",
        '', 'These are fixed-code results on two development networks using the recorded Linux process backend. '
        'Means pool four budgets and nine repeat/seed combinations per network. '
        'Matching a known optimum uses a numerical comparison; the separate online-proof count requires '
        'exact equality of a verified bound and a feasible value. A hard deadline can retain an earlier, looser bound. '
        'No evolutionary superiority, statistical significance, Docker timing result or held-out transfer is implied.',
        '', '[Full per-checkpoint comparison and timing costs](results/strong-baselines/comparison.md), '
        '[summary](results/strong-baselines/study/summary.json), '
        '[raw incumbent and bound journals](results/strong-baselines/study/trials.jsonl), '
        '[frozen measurement manifest](results/strong-baselines/study/manifest.json), '
        '[independent replay](results/strong-baselines/verification.json), and '
        '[test transcript](results/strong-baselines/tests.txt).'])
    detailed=['# Strong fixed baselines: detailed development comparison','',
        'Generated from the same independently checked timed records as README Section 5.5. '
        'Values are descriptive measurements on the recorded runtime, not cross-machine guarantees.','',
        f"Measured Python/platform: `{manifest['python']}` / `{manifest['platform']}`.",
        f"Complete comparison wall time: {summary['wall_seconds']:.3f} seconds. This includes parent proof checks and process startup; it is not the two-second inner search budget.",'',
        '| Network | Method | 0.02 s coverage (%) | 0.10 s | 0.50 s | 2.00 s | Mean delta vs timed DAG greedy (pp) |',
        '|---|---|---:|---:|---:|---:|---:|']
    for dataset in datasets:
        for method in methods:
            r=rows[dataset,method]
            values=' | '.join(f'{v:.4f}' for v in r['mean_checkpoint_coverage_pct'])
            detailed.append(f"| {dataset} | {LABELS[method]} | {values} | {r['mean_delta_vs_greedy_pp']:+.4f} |")
    records=[json.loads(line) for line in (evidence/'study/trials.jsonl').read_text().splitlines()]
    detailed.extend(['','## Recorded costs and interruption','',
        'Route preparation below is solver-reported diagnostic timing (not the independent submission clock). '
        'It is inside the search budget. Proof replay is parent-side measured cost after capture. '
        'A missing diagnostic is not silently treated as zero; termination counts use the external parent.', '',
        '| Network | Method | Route preparation median (ms) / recorded trials | Proof replay median (ms) | Parent deadlines / trials | Guard fallback trials |',
        '|---|---|---:|---:|---:|---:|'])
    for dataset in datasets:
        group=[r for r in records if r['dataset']==dataset]
        for method in methods:
            trials=[r['methods'][method] for r in group]
            preps=[]
            for r in trials:
                found=[d['route_preparation_seconds'] for _,d in r.get('solver_diagnostics',[]) if 'route_preparation_seconds' in d]
                if found:preps.append(found[-1])
            # The parent stores diagnostics as externally stamped (time, payload) pairs.
            prep=f'{1000*median(preps):.4f} / {len(preps)}' if preps else 'Not applicable'
            proof=[r['bound_verification_seconds'] for r in trials if 'bound_verification_seconds' in r]
            prooftext=f'{1000*median(proof):.4f}' if proof else 'Not applicable'
            fallbacks=sum(any(d.get('fallback') for _,d in r.get('solver_diagnostics',[])) for r in trials)
            deadlines=sum(r['termination']=='deadline' for r in trials)
            detailed.append(f'| {dataset} | {LABELS[method]} | {prep} | {prooftext} | {deadlines}/{len(trials)} | {fallbacks} |')
    detailed.extend(['', 'Counters from interrupted solvers are last-emitted diagnostics, not a guarantee of completed work. '
        'The raw journals retain exact bound fractions and external receipt times. '
        'No route construction is shared for free between methods.','',
        '## Per-case paired differences','',
        'Each row averages the nine repeat/seed trials of one graph/budget. These are not nine independent source networks.','',
        '| Network | Monitors | Method | Mean checkpoint coverage (%) | Final coverage range (%) | Mean delta vs DAG swap (pp) |',
        '|---|---:|---|---:|---:|---:|'])
    for dataset,k in sorted({(r['dataset'],r['k']) for r in records}):
        group=[r for r in records if r['dataset']==dataset and r['k']==k]
        for method in methods:
            trial=[r['methods'][method] for r in group]
            coverage=100*sum(r['mean_checkpoint_coverage'] for r in trial)/len(trial)
            values=[100*r['final_coverage'] for r in trial]
            delta=100*sum(r['methods'][method]['mean_checkpoint_coverage']-r['methods']['greedy_swap']['mean_checkpoint_coverage'] for r in group)/len(group)
            detailed.append(f'| {dataset} | {k} | {LABELS[method]} | {coverage:.4f} | {min(values):.4f}–{max(values):.4f} | {delta:+.4f} |')
    detailed.extend(['','Zero model calls and zero validation/test performance assessments.'])
    return '\n\n'+'\n'.join(table)+'\n\n','\n'.join(detailed)+'\n'


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--evidence',type=Path,default=ROOT/'results/strong-baselines')
    p.add_argument('--check',action='store_true')
    a=p.parse_args()
    path=ROOT/'README.md';text=path.read_text()
    if text.count(START)!=1 or text.count(END)!=1:raise ValueError('expected one strong-baseline README marker pair')
    section,detail=content(a.evidence)
    before,rest=text.split(START);_,after=rest.split(END)
    updated=before+START+section+END+after
    detailpath=a.evidence/'comparison.md'
    if a.check:
        if text!=updated or not detailpath.is_file() or detailpath.read_text()!=detail:
            raise SystemExit('strong-baseline README or detail table is stale')
    else:
        path.write_text(updated);detailpath.write_text(detail)

if __name__=='__main__':main()
