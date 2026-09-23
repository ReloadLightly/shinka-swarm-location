"""Render point-2 findings exclusively from verified saved development evidence."""
import argparse
from fractions import Fraction
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from swarm_location.suite import file_sha256

START, END = '<!-- EXCHANGE-LANDSCAPE:START -->', '<!-- EXCHANGE-LANDSCAPE:END -->'


def render(directory: Path):
    record = json.loads((directory/'study.json').read_text())
    verified = json.loads((directory/'verification.json').read_text())
    if not verified['success'] or verified['study_sha256'] != file_sha256(directory/'study.json'):
        raise ValueError('missing matching verified landscape evidence')
    science = record['science']; census = science['census']; plateau = science['neutral_component']
    barrier = science['minimum_loss_escape']
    if (science['dataset'] != 'SiouxFalls' or science['k'] != 6 or not census['complete']
            or not plateau['complete'] or barrier['status'] != 'proved'
            or any(r['strictly_better_than_initial'] for member in science['neutral_member_radius_checks']
                   for r in member['spheres'])):
        raise ValueError('this published narrative requires the verified Sioux Falls six-monitor findings')
    text = (directory/'tests.txt').read_text()
    counts = re.findall(r'Ran (\d+) tests? in', text)
    if not counts or not re.search(r'^OK\s*$', text, re.M):
        raise ValueError('complete successful test transcript required')
    rows = ['| Simultaneous replacements | Deployments checked | Worse | Equal | Better |',
            '|---:|---:|---:|---:|---:|']
    for row in census['spheres']:
        rows.append('| '+ ' | '.join(f"{row[key]:,}" for key in ['radius','evaluated','worse','equal','better'])+' |')
    headroom = ['| Monitors | Greedy coverage (%) | Completed swap (%) | Proved optimum (%) | Actual swap gap (pp) |',
                '|---:|---:|---:|---:|---:|']
    for row in science['headroom']:
        headroom.append(f"| {row['k']} | " + ' | '.join(f"{float(100*Fraction(row[key])):.6f}" for key in
            ['greedy_exact','greedy_swap_exact','optimum_exact','swap_gap_exact'])+' |')
    rows += ['', f"**Executed evidence:** all {int(counts[-1])} tests passed. The exact census covers "
        f"**{census['total_deployments']:,}** distinct {science['k']}-monitor deployments, including the starting deployment. "
        f"Only **{census['strict_improving_deployments']}** are strictly better; the smallest improving simultaneous exchange "
        f"replaces **{census['smallest_improving_radius']}** monitors.", '',
        f"The exactly neutral single-exchange component contains **{len(plateau['members'])}** deployments. "
        'Neither member has an improving exchange of one, two or three monitors. This closes the '
        'previously unexamined neutral-plateau question for this starting deployment.', '',
        f"For paths restricted to single-monitor replacements, the minimum temporary coverage drop needed "
        f"to reach any strictly better deployment is **approximately {barrier['verification']['minimum_loss_pp']:.6f} "
        'percentage points**. A feasible path attains that bottleneck; an independently checked '
        f"**{barrier['verification']['cut_states']}-state cut** proves that a smaller drop cannot suffice.", '',
        'The drop concerns an exploratory working solution: the algorithm can retain and report its '
        'best deployment throughout. The proof is not a requirement to deploy a worse operational solution.', '',
        '[Exact headroom table](results/exchange-landscape/headroom.md), '
        '[full census and path/cut witnesses](results/exchange-landscape/study.json), '
        '[independent verification](results/exchange-landscape/verification.json), and '
        '[test transcript](results/exchange-landscape/tests.txt).']
    return '\n'.join(rows)+'\n', '\n'.join(headroom)+'\n'


INTRO = '''## 5.4 Exact headroom and exchange-landscape diagnosis

The exact Sioux Falls optima for budgets 1–8 and the quality certificates were
already implemented in Section 5.3. This additional development-only study
reuses and independently verifies those reference proofs; it does not present
another implementation of branch and bound as new progress.

The new contribution is a complete exchange census around the six-monitor
completed greedy+swap deployment, exhaustive exploration of its neutral plateau,
and a path-plus-cut proof of the smallest temporary loss required for a sequence
of one-for-one replacements to escape. All comparisons use exact integer mass.
This is an exploratory diagnosis of a selected development case, not an evolved
algorithm or the chapter's original Israeli-network experiment. The production
evaluator, fixed controls, seeds, fitness and held-out performance remain unchanged.
See [the definitions, proof and source distinction](docs/exchange_landscape.md).

'''
OUTRO = '''
These results motivate testing larger exchanges or controlled temporary losses,
while preserving the best-so-far deployment. They do not prove that any particular
restart, evolutionary proposal, or heuristic will improve the timed campaign.
The hypothesis is about reusable search behavior, not hardcoding these node sets.

Reproduce without model calls (the two development files must be prepared):

```bash
python scripts/prepare_suite.py --download
python scripts/exchange_study.py --output results/local_exchange_study
python scripts/exchange_study.py --output results/local_exchange_study --verify
```

The complete census is deliberately limited to tractable small development cases;
large requests fail explicitly rather than becoming unreported samples. No new
algorithm is silently inserted into the frozen ShinkaEvolve campaign.

'''


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--evidence', type=Path, default=ROOT/'results/exchange-landscape')
    p.add_argument('--check', action='store_true')
    a = p.parse_args(); rendered, headroom = render(a.evidence)
    path = ROOT/'README.md'; text = path.read_text()
    if START not in text:
        anchor = '## 6. Reproduce the first milestone'
        if text.count(anchor) != 1:
            raise ValueError('README insertion anchor is missing or ambiguous')
        text = text.replace(anchor, INTRO+START+'\n\n'+END+'\n'+OUTRO+anchor)
    if text.count(START) != 1 or text.count(END) != 1:
        raise ValueError('README landscape markers missing or repeated')
    before, rest = text.split(START); _, after = rest.split(END)
    updated = before+START+'\n\n'+rendered+'\n'+END+after
    table_path = a.evidence/'headroom.md'
    if a.check:
        if updated != path.read_text() or not table_path.is_file() or table_path.read_text() != headroom:
            raise SystemExit('landscape README/table does not match verified evidence')
    else:
        path.write_text(updated); table_path.write_text(headroom)


if __name__ == '__main__':
    main()
