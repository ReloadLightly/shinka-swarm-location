"""Update only the quality-certificate results block from saved study evidence."""
import argparse
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
START='<!-- QUALITY-CERTIFICATES:START -->'
END='<!-- QUALITY-CERTIFICATES:END -->'


def update(check=False):
    directory=ROOT/'results/quality-certificates'
    evidence=json.loads((directory/'verification.json').read_text())
    if not evidence['success']:
        raise ValueError('successful verification evidence required')
    table=(directory/'reference-study/table.md').read_text().rstrip()
    block='\n\n'+table+'\n\n'+(
        f"**Executed evidence:** {evidence['tests_passed']} tests passed locally; "
        f"{evidence['verified_certificates']} standalone certificates and "
        f"{evidence['verified_bound_witnesses']} bound witnesses independently recomputed. "
        f"{evidence['annotated_trials']} existing baseline trials received "
        f"{evidence['checkpoint_certificates']} checkpoint and {evidence['final_certificates']} final certificates "
        'without running candidates or changing their recorded timing. All eight Sioux Falls '
        'reference optima were proved. Anaheim LP bounds are not automatically exact optima.\n\n'
        '[Reference study and source hashes](results/quality-certificates/reference-study/study.json), '
        '[proof artifacts](results/quality-certificates/reference-study/references/), '
        '[posthoc M2 certificates](results/quality-certificates/m2-baseline-certificates.json), '
        '[verification](results/quality-certificates/verification.json), and '
        '[test transcript](results/quality-certificates/tests.txt).\n\n')
    path=ROOT/'README.md';text=path.read_text()
    if text.count(START)!=1 or text.count(END)!=1:
        raise ValueError('README requires exactly one quality marker pair')
    before,rest=text.split(START);_,after=rest.split(END)
    result=before+START+block+END+after
    if check and result!=text:raise SystemExit('quality README block differs from evidence')
    if not check:path.write_text(result)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--check',action='store_true')
    update(p.parse_args().check)
