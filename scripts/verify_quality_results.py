"""Recheck all saved reference proofs and historical checkpoint certificates.

Uses only the standard library. No solver proposal, candidate, LLM or holdout
performance is executed. Supply the same hash-verified development suite.
"""
import argparse
import json
from pathlib import Path
import sys
import tempfile

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from scripts.quality_study import verify_study
from swarm_location.suite import file_sha256
from certify import annotate


def verify(suite: Path, directory: Path) -> dict:
    directory=Path(directory)
    study=json.loads((directory/'reference-study/study.json').read_text())
    for path,digest in study['source_sha256'].items():
        if file_sha256(ROOT/path)!=digest:
            raise ValueError('recorded study implementation differs: '+path)
    result=verify_study(suite,directory/'reference-study')
    saved=json.loads((directory/'m2-baseline-certificates.json').read_text())
    with tempfile.TemporaryDirectory() as temp:
        actual=annotate(suite,ROOT/'results/step2/ci/baselines/traces.json',Path(temp)/'recomputed.json',
                        directory/'reference-study/references')
    for field in ['trials','source_trace_sha256','suite_sha256','reference_sha256','split','model']:
        if saved[field]!=actual[field]:
            raise ValueError('certificate sidecar differs from independent recomputation: '+field)
    valid=[row for row in saved['trials'] if row['status']=='certified']
    if len(valid)!=len(saved['trials']):
        raise ValueError('this reference study expects no invalid baseline trials')
    return dict(result,annotated_trials=len(valid),checkpoint_certificates=sum(len(r['checkpoints']) for r in valid),
                final_certificates=len(valid),success=True,candidate_reexecutions_for_sidecars=0)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--suite',type=Path,required=True)
    p.add_argument('--directory',type=Path,default=ROOT/'results/quality-certificates')
    a=p.parse_args()
    print(json.dumps(verify(a.suite,a.directory),indent=2))
