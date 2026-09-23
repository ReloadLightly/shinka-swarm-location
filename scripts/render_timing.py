"""Render frozen M5 coverage curves and refresh status, without running solvers."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import platform

ROOT = Path(__file__).resolve().parents[1]


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def render(study: Path, output: Path, update_readme: bool = False) -> None:
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    import numpy
    summary = json.loads((study/'summary.json').read_text())
    curves = json.loads((study/'curves.json').read_text())
    if not summary['complete'] or summary['failed_trials'] or summary['guard'] is None:
        raise ValueError('only a complete successful frozen study can be rendered')
    if sha(study/'manifest.json') != summary['manifest_sha256'] or sha(study/'trials.jsonl.gz') != summary['journal_sha256']:
        raise ValueError('frozen evidence identity mismatch')
    output.mkdir(parents=True, exist_ok=True)
    labels = {'greedy':'DAG greedy', 'greedy_swap':'DAG greedy + swap',
              'topk':'Singleton ranking', 'early_celf_swap':'Early topk + CELF/swap',
              'iterated':'Iterated search', 'dfbnb':'DFBnB', 'potential':'Utility-form APTS',
              'candidate':'Unchanged greedy seed'}
    rendered = []
    for network, title in [('SiouxFalls','Sioux Falls'), ('Anaheim','Anaheim')]:
        rows = [r for r in curves if r['scope']==network]
        if len(rows)!=8 or {r['method'] for r in rows} != set(labels):
            raise ValueError('missing or repeated plotted method')
        fig, ax = plt.subplots(figsize=(10, 5.7))
        for row in rows:
            times, coverage = zip(*row['points_seconds_coverage_pct'])
            ax.step(times, coverage, where='post', label=labels[row['method']], linewidth=1.6)
        ax.set_xscale('symlog', linthresh=0.002)
        ax.set_xlim(0, 2.0)
        ax.set_ylim(0, 100)
        ax.set_xticks([0, 0.002, 0.02, 0.1, 0.5, 2.0],
                      ['0', '2', '20', '100', '500', '2,000'])
        ax.set_xlabel('Milliseconds after external GO (nonlinear time axis)')
        ax.set_ylabel('Mean covered OD demand (%)')
        ax.set_title(f'{title}: {summary["control_blocks"]} complete Docker repetition blocks')
        ax.grid(True, alpha=0.25)
        ax.legend(loc='lower right', ncol=2, fontsize=8)
        fig.tight_layout()
        path = output/(network+'.png')
        fig.savefig(path, dpi=150, metadata={'Software':'Matplotlib; frozen M5 mean step functions'})
        plt.close(fig)
        rendered.append({'network':network,'path':path.name,'sha256':sha(path)})
    probes = [r for r in summary['null_analysis']
              if r['scope']=='overall' and r['metric']=='checkpoint_mean']
    if len(probes)!=6 or any(len(r['values'])!=summary['null_blocks'] for r in probes):
        raise ValueError('complete suite-level null distributions required')
    probe_labels = {'identical_candidate':'Candidate A − B',
        'identical_fixed_greedy':'Greedy A − B', 'identical_early_hybrid':'Early hybrid A − B',
        'refreshed_fitness_difference':'Refreshed fitness A − B',
        'candidate_minus_fixed_greedy_a':'Candidate − fixed greedy A',
        'candidate_minus_fixed_greedy_b':'Candidate − fixed greedy B'}
    fig, ax = plt.subplots(figsize=(11, 5.7))
    ax.boxplot([r['values'] for r in probes])
    ax.set_xticks(range(1,7), [probe_labels[r['probe']] for r in probes], rotation=18, ha='right')
    ax.axhline(0, linewidth=0.8)
    ax.set_ylabel('Difference in mean checkpoint coverage (percentage points)')
    ax.set_title(f"Docker timing probes: {summary['null_blocks']} complete-suite blocks per probe")
    ax.grid(True, axis='y', alpha=0.25)
    fig.tight_layout()
    path=output/'null-distributions.png'
    fig.savefig(path, dpi=150, metadata={'Software':'Matplotlib; all M5 null block values'})
    plt.close(fig)
    rendered.append({'scope':'overall-null','path':path.name,'sha256':sha(path)})
    (output/'renderer.json').write_text(json.dumps({
        'source_curves_sha256':sha(study/'curves.json'), 'source_summary_sha256':sha(study/'summary.json'),
        'script_sha256':sha(Path(__file__)), 'python':platform.python_version(),
        'matplotlib':matplotlib.__version__, 'numpy':numpy.__version__,
        'plots':rendered, 'scope':'Exact mean step functions; no interpolation, solver calls or new measurements'
    },indent=2)+'\n')
    if update_readme:
        readme = ROOT/'README.md'; text=readme.read_text()
        old='**Status: M4 staged strong-control campaign integration implemented; native development commissioning and verification are reported in Section 5.6. No evolutionary campaign completed.**'
        new='**Status: M5 Docker timing calibration completed; identical-code noise, repeated strong controls and a host-session screening guard are reported in Section 5.7. No evolutionary campaign completed.**'
        if old not in text and new not in text:
            raise ValueError('unexpected README status; review before changing it')
        text=text.replace(old,new)
        anchor='| LLM-generated descendants / evolutionary runs | **0 / 0** |'
        addition='| Staged native campaign comparisons | Four screening and seven assessment controls; Section 5.6 |\n| Docker timing calibration | '+f'{summary["solver_trials"]:,} trials; empirical host-session guard; Section 5.7 |\n'
        if '| Docker timing calibration |' not in text:
            if text.count(anchor)!=1: raise ValueError('unique evidence table anchor required')
            text=text.replace(anchor,addition+anchor)
        def control(method):
            return next(r for r in summary['control_analysis'] if r['scope']=='Anaheim' and r['method']==method)
        h,g,t=control('early_celf_swap'),control('greedy'),control('topk')
        interpretation=(
            '**Backend-specific finding.** On Anaheim, the early-answer hybrid averaged '
            f"{h['coverage_at_checkpoints_pct'][0]['mean']:.4f}% coverage at 20 ms on this Docker host, "
            f"versus {g['coverage_at_checkpoints_pct'][0]['mean']:.4f}% for DAG greedy and "
            f"{t['coverage_at_checkpoints_pct'][0]['mean']:.4f}% for singleton ranking. By 100 ms it reached "
            f"{h['coverage_at_checkpoints_pct'][1]['mean']:.4f}%. The method name does not guarantee "
            'an early received answer: the previous process-backend ranking is not portable. These '
            'measurements do not isolate Docker overhead from hardware, imports, transport or scheduling, '
            'and no timing boundary or algorithm was changed after seeing this result.\n\n')
        screen=study.parent/'seed-screen-check/promotion.json'
        if screen.is_file():
            decision=json.loads(screen.read_text())
            d=decision['paired_deltas_pp']
            outcome='promoted for confirmation (not declared a discovery)' if decision['promote_to_confirmation'] else 'not promoted'
            interpretation+=(
                '**Fresh unchanged-seed screen.** A separate 120-trial M4 development evaluation returned '
                f"{d['greedy']:+.4f} pp against freshly timed greedy and {d['early_celf_swap']:+.4f} pp "
                f"against the early hybrid. Under the {decision['threshold_pp']:.2f} pp guard the seed was **{outcome}**. "
                'This exercises the screen, not a universal false-positive guarantee. Those 120 trials '
                f"are separate from the {summary['solver_trials']:,}-trial calibration; no LLM evolution "
                'or research holdout assessment occurred. '
                '[Saved promotion decision](results/timing-calibration/seed-screen-check/promotion.json).\n\n')
        start,end='<!-- M5-VISUALS:START -->','<!-- M5-VISUALS:END -->'
        body=('\n\n'+start+'\n\n'+interpretation+
              'The plots show the complete mean incumbent step functions for all seven controls and the unchanged seed. '
              'The time axis is nonlinear to make the 20-millisecond region visible; each network mean pools its '
              'four budgets and three solver seeds within each of five repetition blocks. Overlapping lines are retained. '
              'These are descriptive curves, not confidence bands or an evolutionary result.\n\n'
              '![Complete-suite timing differences](results/timing-calibration/figures/null-distributions.png)\n\n'
              'The timing boxes summarize all 12 block values (including displayed outliers). The last two probes use '
              'the same greedy rule through different loading paths; they are not byte-identical nulls. No significance '
              'test is implied.\n\n'
              '![Sioux Falls Docker anytime coverage](results/timing-calibration/figures/SiouxFalls.png)\n\n'
              '![Anaheim Docker anytime coverage](results/timing-calibration/figures/Anaheim.png)\n\n'+end)
        if start in text:
            before, rest = text.split(start); _,after = rest.split(end)
            text=before+body.strip()+after
        else:
            marker='<!-- M5-TIMING:END -->'
            if text.count(marker)!=1: raise ValueError('unique M5 result marker required')
            text=text.replace(marker,marker+body)
        readme.write_text(text)


if __name__ == '__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--study',type=Path,default=ROOT/'results/timing-calibration/study')
    p.add_argument('--output',type=Path,default=ROOT/'results/timing-calibration/figures')
    p.add_argument('--update-readme',action='store_true')
    a=p.parse_args(); render(a.study,a.output,a.update_readme)
