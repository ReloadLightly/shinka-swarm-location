"""Render measured M3 status, never promote a blocked run to research success."""
import argparse
import json
from pathlib import Path
import re
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from evaluate_anytime import write_json
from swarm_location.suite import file_sha256

START,END='<!-- M3-RESULTS:START -->','<!-- M3-RESULTS:END -->'

def report(evidence):
    evidence=Path(evidence).resolve()
    load=lambda p:json.loads((evidence/p).read_text())
    audit=load('audit/data_audit.json');container=load('container.json')
    native=load('native/native_seed_check.json');state=load('campaign/campaign_status.json')
    metrics=load('native/seed/metrics.json');correct=load('native/seed/correct.json')
    tests=(evidence/'tests.txt').read_text();matches=re.findall(r'Ran (\d+) tests? in',tests)
    if not matches or not re.search(r'^OK\s*$',tests,re.M) or not container['success'] or not native['correct'] or not correct['correct']:
        raise ValueError('cannot publish M3 readiness as verified when checks failed')
    rows=audit['datasets']
    summary={'stage':'m3','campaign_status':state['status'],'test_count':int(matches[-1]),
        'accepted_source_networks':len(rows),'source_partitions':{r['id']:r['split'] for r in rows},
        'docker_probe_passed':True,'native_development_seed_correct':True,
        'development_cases':metrics['public']['paired_cases'],
        'native_development_model_calls':native['model_calls'],
        'campaign_native_runner_started':state['native_runner_started'],
        'campaign_inference_calls':state['inference_calls'],
        'valid_evolved_descendants':state['valid_evolved_descendants'],
        'validation_solver_evaluations':state['validation_solver_evaluations'],
        'test_solver_evaluations':state['test_solver_evaluations'],
        'image_id':container['image_id'],'catalog_sha256':audit['catalog_sha256'],
        'scope':'Readiness results and actual campaign state; no inferred completion',
        'evidence_sha256':{p:file_sha256(evidence/p) for p in ['tests.txt','audit/data_audit.json','container.json',
            'native/native_seed_check.json','native/seed/metrics.json','campaign/campaign_status.json']}}
    write_json(evidence/'summary.json',summary)
    table=['| Source network | Partition | Nodes | Directed links | Positive OD pairs |',
           '|---|---|---:|---:|---:|']
    for row in rows:table.append(f"| {row['id']} | {row['split']} | {row['nodes']} | {row['edges']} | {row['positive_od_pairs']} |")
    table.extend(['',f"**Measured software evidence:** {summary['test_count']} tests passed; Docker containment/deadline probes passed; "
        f"native development seed completed {summary['development_cases']} paired cases successfully. "
        'The seed run made zero model calls and is not an evolutionary result.',
        '',f"**Campaign state: `{state['status']}`.** Native evolutionary runner started: `{state['native_runner_started']}`. "
        f"Recorded campaign inference calls: `{state['inference_calls']}`; valid evolved descendants: `{state['valid_evolved_descendants']}`. "
        f"Validation solver trials: `{state['validation_solver_evaluations']}`; test solver trials: `{state['test_solver_evaluations']}`.",
        '', 'For `blocked_model_access`, no model credential was available to the verified native preflight. '
        'No validation/test performance or champion is fabricated to fill that gap.',
        '', '[Summary](results/step3/ci/summary.json), [input audit](results/step3/ci/audit/data_audit.json), '
        '[container probes](results/step3/ci/container.json), [native seed](results/step3/ci/native/native_seed_check.json), '
        '[campaign status](results/step3/ci/campaign/campaign_status.json), and [test transcript](results/step3/ci/tests.txt).'])
    path=ROOT/'README.md';text=path.read_text()
    if START not in text:
        addition=(ROOT/'docs/m3_readme.md').read_text()
        text=text.replace('## 6. Reproduce the first milestone',addition+'## 6. Reproduce the first milestone')
    text=re.sub(r'\*\*Status:.*?\*\*',
        '**Status: M3 holdout/campaign pipeline implemented; actual campaign state: `'+state['status']+'`. See Section 5.2.**',text,count=1)
    if text.count(START)!=1 or text.count(END)!=1:raise ValueError('missing or repeated README M3 markers')
    before,rest=text.split(START);_,after=rest.split(END)
    path.write_text(before+START+'\n\n'+'\n'.join(table)+'\n\n'+END+after)
    print(json.dumps(summary,indent=2))

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--evidence',type=Path,default=ROOT/'results/step3/ci')
    report(p.parse_args().evidence)
