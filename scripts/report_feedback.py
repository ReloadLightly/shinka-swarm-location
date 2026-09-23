"""Replay M7 evidence and render only its own README section; no solver/model calls."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import re
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from evaluate_anytime import write_json
from swarm_location.anytime import score_trace
from swarm_location.core import ShortestPathCoverage
from swarm_location.suite import file_sha256,load_suite
from swarm_location.comparisons import paired_comparisons,comparison_spec
from swarm_location.feedback import load_context,evidence_packet,text_feedback

START='<!-- M7-FEEDBACK:START -->';END='<!-- M7-FEEDBACK:END -->'


def verify(evidence:Path,suite:Path):
    read=lambda p:json.loads((evidence/p).read_text())
    manifest=read('manifest.json');summary=read('summary.json')
    if not summary['success'] or manifest['context']!=load_context():raise ValueError('context/incomplete evidence mismatch')
    for p,h in manifest['implementation_sha256'].items():
        if file_sha256(ROOT/p)!=h:raise ValueError('feedback implementation differs from measured source: '+p)
    if file_sha256(suite)!=manifest['suite_sha256']:raise ValueError('suite differs from commissioning source')
    protocol,instances=load_suite(suite,'development');lookup={e['id']:instance for e,instance in instances}
    counts=0;trials=0
    for prefix,selected_suite in [('native/seed',suite),('native/import-failure',evidence/'synthetic/suite.json')]:
        _,selected_instances=load_suite(selected_suite,'development')
        local_lookup={e['id']:instance for e,instance in selected_instances}
        raw=read(prefix+'/traces.json');metrics=read(prefix+'/metrics.json');correct=read(prefix+'/correct.json')
        for row in raw['cases']:
            oracle=ShortestPathCoverage(local_lookup[row['dataset']])
            for method,t in row['methods'].items():
                rescored=score_trace(local_lookup[row['dataset']],row['k'],raw['protocol']['checkpoints_seconds'],t['events'],oracle)
                if any(rescored[k]!=t[k] for k in rescored):raise ValueError('rescoring mismatch')
                if t['isolation'].get('image_id')!=manifest['docker_image_id']:raise ValueError('executor image mismatch')
                if prefix=='native/seed':counts+=len(t['events']);trials+=1
        comp=paired_comparisons(raw['cases'],'candidate',comparison_spec(raw['protocol'],'development'))
        if comp!=read(prefix+'/comparisons.json'):raise ValueError('paired evidence mismatch')
        packet=evidence_packet(raw['cases'],comp,'development')
        if packet!=read(prefix+'/feedback.json') or packet!=metrics['extra_data']['feedback']:raise ValueError('feedback projection mismatch')
        if text_feedback(packet)!=metrics['text_feedback']:raise ValueError('prompt feedback differs from observations')
        expected=100+next(r['delta_mean_checkpoint_pp'] for r in comp['rows'] if r['scope']=='overall' and r['baseline']=='greedy') if correct['correct'] else 0.
        if abs(expected-metrics['combined_score'])>1e-12:raise ValueError('feedback altered numeric fitness')
    if trials!=summary['development_solver_trials'] or counts!=summary['independently_rescored_deployments']:
        raise ValueError('summary count mismatch')
    for case in summary['synthetic_results']:
        t=read('synthetic/'+case['name']+'.json')
        if t['correct']!=case['expected_correct'] or t['diagnostics']['repair_category']!=case['repair_category']:
            raise ValueError('synthetic diagnostic case mismatch')
        if 'FAKE_M7_CANARY_NEVER_REAL' in json.dumps(t):raise ValueError('synthetic canary was not redacted')
    context=manifest['context'];mut=read('prompt_transport/mutation_inputs.json');meta=read('prompt_transport/meta_inputs.json')
    if [m['route'] for m in mut]!=['diff','full','cross','fix'] or len(meta)!=3:raise ValueError('missing native prompt routes')
    for m in mut:
        if context['task_context'] not in m['system'] or 'M7 EVIDENCE' not in m['user']:raise ValueError('mutation inputs missing context')
    if 'ModuleNotFoundError' not in mut[-1]['user']:raise ValueError('repair input lacks diagnostic')
    for m in meta:
        if context['task_context'] not in m['system_msg'] or context['meta_context'] not in m['system_msg']:raise ValueError('meta inputs missing context')
    matches=re.findall(r'Ran (\d+) tests', (evidence/'tests.txt').read_text())
    if not matches or not (evidence/'tests.txt').read_text().rstrip().endswith('OK'):raise ValueError('missing passing full test evidence')
    return {'verified':True,'test_count':int(matches[-1]),'development_solver_trials':trials,
            'deployments_rescored':counts,'native_mutation_routes':len(mut),'native_meta_input_stages':len(meta),
            'numeric_fitness_unchanged_on_replay':True,'provider_calls':0,
            'scope':'Independent arithmetic/projection replay and captured native inputs; no LLM completions'}


def block(summary,verified,continuity):
    return f'''**Executed feedback integration:** {verified['test_count']} tests passed. The pinned native
`JobScheduler` evaluated the unchanged seed on {summary['development_cases']} development cases with the
four screening controls: **{summary['development_solver_trials']} Docker solver trials, zero failed development
trials**. Replay independently rescored **{verified['deployments_rescored']} deployments** and verified
that paired coverage differences and the scalar are unaffected by diagnostic text.

The synthetic fault checks include {summary['synthetic_direct_worker_trials']} direct Docker worker cases and a separate
{summary['synthetic_native_solver_trials']}-trial native evaluator check. Deliberate import/syntax/runtime/invalid-output
failures remain incorrect; an anytime deadline, bounded stderr flood and forged
stderr score do not override independently measured correctness or coverage.
These expected failures are not benchmark algorithm failures or evolved programs.

Native database round-trip and **diff, full, crossover and fix prompt inputs** were
exercised. All three native meta-stage request inputs contained the task context
and evidence discipline. Provider-bound requests were captured and stopped before
inference; **no synthetic model completion was substituted**. The recommendation
sentinel checks transport only: native crossover still omits that recommendation
field, while retaining task context and evaluation feedback.

The curated task context is {summary['task_context_characters']:,} characters and the meta addendum is
{summary['meta_context_characters']:,} characters; the seed's evaluated feedback is {summary['seed_text_feedback_characters']:,} characters.
These are character counts, not token usage or provider costs. The 16,000-character
feedback limit and explicit omission markers bound prompt growth.

**Historical preservation:** {continuity['protected_unchanged']} protected files and all
{len(continuity['historical_readme_blocks'])} previous README result/figure blocks are unchanged. Diagnostic-driver and
feedback-routing source edits are listed separately, not called byte-identical.

**Model calls: 0; evolved descendants: 0; generated recommendations: 0; research
validation/test trials: 0.** This establishes feedback delivery and repair observability,
not better mutations, faster repair, timing equivalence, or evolutionary superiority.

[Integration summary](results/feedback/integration/summary.json),
[replay](results/feedback/integration/replay.json),
[actual mutation inputs](results/feedback/integration/prompt_transport/mutation_inputs.json),
[actual meta-stage inputs](results/feedback/integration/prompt_transport/meta_inputs.json),
[seed feedback](results/feedback/integration/native/seed/feedback.json), and
[failed-import feedback](results/feedback/integration/native/import-failure/feedback.json).'''


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--evidence',type=Path,required=True)
    p.add_argument('--suite',type=Path,required=True);p.add_argument('--readme',type=Path,default=ROOT/'README.md')
    p.add_argument('--update-readme',action='store_true');p.add_argument('--check-readme',action='store_true')
    a=p.parse_args();result=verify(a.evidence,a.suite)
    summary=json.loads((a.evidence/'summary.json').read_text());keep=json.loads((a.evidence/'continuity.json').read_text())
    expected=block(summary,result,keep);text=a.readme.read_text()
    if text.count(START)!=1 or text.count(END)!=1:raise ValueError('unique M7 markers required')
    if a.update_readme:
        before,rest=text.split(START);_,after=rest.split(END)
        a.readme.write_text(before+START+'\n\n'+expected+'\n\n'+END+after)
        write_json(a.evidence/'replay.json',result)
    if a.check_readme and text.split(START)[1].split(END)[0].strip()!=expected.strip():raise ValueError('M7 README differs from evidence')
    print(json.dumps(result,indent=2))

if __name__=='__main__':main()
