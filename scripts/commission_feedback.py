"""M7 Docker integration evidence: real evaluations, explicit offline native probes.

Not an evolutionary campaign or a timing calibration. The historical checkpoints,
fitness and solver code are preserved; receiver instrumentation has changed.
"""
from __future__ import annotations
import argparse
import asyncio
from collections import Counter
import hashlib
import json
import os
from pathlib import Path
import re
import sys

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT));sys.path.insert(0,str(ROOT/'tests'))
from evaluate_anytime import write_json
from run_evo import main as native_main, verify_native
from swarm_location.anytime import run_anytime,score_trace
from swarm_location.core import ShortestPathCoverage
from swarm_location.comparisons import comparison_spec,paired_comparisons
from swarm_location.feedback import task_context,evaluation_feedback
from swarm_location.isolation import checked_image
from swarm_location.suite import load_suite,file_sha256
from scripts.check_feedback_continuity import check as continuity
from scripts.check_feedback_native import check as native_check
from test_feedback import FAULTS
from test_anytime import diamond
from test_comparisons import synthetic_catalog
from scripts.prepare_research import prepare

START,END='<!-- M7-FEEDBACK:START -->','<!-- M7-FEEDBACK:END -->'


def read(path):return json.loads(Path(path).read_text())


def replay(seed:Path,suite:Path):
    raw=read(seed/'traces.json');metrics=read(seed/'metrics.json');feedback=read(seed/'feedback.json')
    protocol,instances=load_suite(suite,'development');instances={e['id']:i for e,i in instances}
    rescored=0
    for row in raw['cases']:
        oracle=ShortestPathCoverage(instances[row['dataset']])
        for result in row['methods'].values():
            scored=score_trace(instances[row['dataset']],row['k'],protocol['checkpoints_seconds'],result['events'],oracle)
            for key,value in scored.items():
                if result[key]!=value:raise ValueError('deployment replay mismatch: '+key)
            rescored+=len(result['events'])
    comparisons=paired_comparisons(raw['cases'],'candidate',comparison_spec(protocol,'development'))
    assert comparisons==read(seed/'comparisons.json')==metrics['extra_data']['comparisons']
    packet=evaluation_feedback(raw['cases'],'candidate','development',comparisons)
    for k,v in packet.items():assert feedback[k]==v
    assert feedback==metrics['extra_data']['feedback']
    assert metrics['text_feedback']==packet['text_feedback']
    count=len(raw['cases']);mean=lambda xs:__import__('math').fsum(xs)/len(xs)
    expected=100+100*mean([r['methods']['candidate']['mean_checkpoint_coverage']-r['methods']['greedy']['mean_checkpoint_coverage'] for r in raw['cases']])
    failed=sum(not v['correct'] for r in raw['cases'] for v in r['methods'].values())
    assert metrics['combined_score']==(0. if failed else expected)
    return {'paired_cases':count,'solver_trials':sum(len(r['methods']) for r in raw['cases']),
            'failed_trials':failed,'deployments_rescored':rescored,'scalar_recomputed_exactly':True,
            'feedback_recomputed_exactly':True}


def readme_block(summary):
    n=summary['native_payload_check'];r=summary['development_seed'];f=summary['fault_probes']
    return (f"**Executed integration:** {summary['test_count']} tests passed. The pinned native scheduler evaluated "
        f"the unchanged seed on {r['paired_cases']} development cases with four fixed controls: "
        f"**{r['solver_trials']} Docker trials, {r['failed_trials']} failures**, and {r['deployments_rescored']} "
        "independently rescored deployments. The scalar and generated feedback were independently recomputed.\n\n"
        f"**Repair probes:** {len(f)} deliberately constructed synthetic Docker programs returned their expected "
        "parent verdicts and diagnostic categories, including import/syntax failure, runtime exception, invalid "
        "deployment, protocol violation, hard exit, deadline stops and bounded stderr flooding. Expected broken "
        "programs are not benchmark failures. A separate native-scheduler synthetic failure evaluation returned "
        "zero fitness while preserving the sanitized missing-symbol traceback in feedback.\n\n"
        f"**Native routing:** all {len(n['mutation_formats_checked'])} diff/full/cross/fix paths were inspected, "
        "together with all three native meta stages, the native SQLite feedback roundtrip and saved/restored "
        "meta state. These request-boundary tests use clearly labelled offline transport fixtures, "
        "**not LLM responses**. Crossover's native omission of meta recommendations is preserved; its task brief "
        "and parent feedback are present.\n\n"
        f"Continuity checks preserve {summary['continuity']['unchanged_file_count']} historical files and "
        f"all {len(summary['continuity']['historical_readme_blocks_unchanged'])} previous README evidence blocks. "
        "The receiver and worker diagnostic code changes are explicitly recorded. **Model calls: 0; evolved "
        "descendants: 0; research validation/test trials: 0.** This establishes feedback plumbing, not a "
        "measured increase in mutation quality or evolutionary performance. No old host-session timing guard "
        "is treated as calibrated for the new receiver.\n")


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--suite',type=Path,required=True);p.add_argument('--docker-image',required=True)
    p.add_argument('--update-readme',action='store_true');a=p.parse_args()
    a.output.mkdir(parents=True,exist_ok=True);os.environ['SWARM_DOCKER_IMAGE']=checked_image(a.docker_image)
    context=task_context();write_json(a.output/'task-context.json',context)
    write_json(a.output/'status.json',{'complete':False,'model_calls':0})
    version=verify_native('9912af12d423504b8d580f4179fd15f5f88b8c50')
    native_main(['--native-seed','--feedback-context','m7','--config',str(ROOT/'configs/evolution_m3.json'),
        '--suite',str(a.suite),'--docker-image',a.docker_image,'--results-dir',str(a.output/'native')])
    seed=replay(a.output/'native/seed',a.suite)
    faults=[];sources=a.output/'synthetic-fault-sources';sources.mkdir(exist_ok=True)
    for name,(source,expected,correct) in FAULTS.items():
        code=sources/(name+'.py');code.write_text(source)
        write_json(a.output/'fault-progress.json',{'next_probe':name,'completed_probes':len(faults)})
        try:
            result=run_anytime(diamond(),2,[.1,.4],program_path=code)
        except Exception as exc:
            from swarm_location.diagnostics import sanitize
            write_json(a.output/'fault-interruption.json',{'probe':name,'error':sanitize(str(exc)),
                'completed_probes':len(faults),'success':False})
            raise
        assert result['correct']==correct,(name,result)
        assert result['diagnostic']['category']==expected,(name,result)
        assert len(result['diagnostic']['excerpt'])<=2048
        if name=='stderr_flood':assert result['diagnostic']['tail_truncated'] and result['final_coverage']==1
        if name=='redaction':
            for secret in ('EXAMPLE_SECRET','sk-exampletoken123456','/home/private'):
                assert secret not in json.dumps(result['diagnostic'])
        faults.append({'name':name,'expected_category':expected,'expected_correct':correct,'result':result})
        write_json(a.output/'fault-probes.json',faults)
    write_json(a.output/'fault-probes.json',faults)
    # A real native failed-evaluation path, on a synthetic fixture only.
    catalog,raw=synthetic_catalog(a.output/'synthetic')
    prepare(catalog,a.output/'synthetic/suite',raw,'development',False,
            comparison_profile=ROOT/'configs/comparisons_m6.json')
    from shinka.launch import LocalJobConfig
    from shinka.launch.scheduler import JobScheduler
    job=LocalJobConfig(eval_program_path=str(ROOT/'evaluate_anytime.py'),python_executable=sys.executable,
        numeric_threads_per_job=1,extra_cmd_args={'suite':str((a.output/'synthetic/suite/suite.json').resolve()),
                                               'split':'development','feedback_context':'m7'})
    scheduler=JobScheduler('local',job,verbose=True,max_workers=1)
    try:failed,seconds=scheduler.run(str((sources/'runtime_name.py').resolve()),str((a.output/'native-failure').resolve()))
    finally:scheduler.executor.shutdown(wait=True)
    assert not failed['correct']['correct'] and failed['metrics']['combined_score']==0
    assert 'missing_symbol_m7' in failed['metrics']['text_feedback']
    native=asyncio.run(native_check(a.output/'native-payloads',a.suite,a.output/'native/seed',
                                  a.output/'native-failure',sources/'runtime_name.py'))
    c=continuity();write_json(a.output/'continuity.json',c)
    testlog=(a.output/'tests.txt').read_text();match=re.search(r'Ran (\d+) tests',testlog)
    assert match and '\nOK' in testlog
    summary={'schema_version':1,'stage':'m7_feedback_integration','success':True,**version,
        'test_count':int(match[1]),'development_seed':seed,
        'fault_probes':[{'name':f['name'],'category':f['result']['diagnostic']['category'],
                        'correct':f['result']['correct']} for f in faults],
        'synthetic_failed_evaluation_trials':sum(len(c['methods']) for c in read(a.output/'native-failure/traces.json')['cases']),
        'native_payload_check':native,'continuity':{k:v for k,v in c.items() if k!='unchanged_sha256'},
        'docker_image_id':a.docker_image,'workflow_run':os.environ.get('GITHUB_RUN_ID'),
        'source_commit':__import__('subprocess').check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
        'model_calls':0,'evolved_descendants':0,'research_validation_test_trials':0,
        'scope':'Functional integration, NOT a timing calibration, LLM efficacy ablation or evolutionary campaign'}
    write_json(a.output/'summary.json',summary)
    if a.update_readme:
        text=(ROOT/'README.md').read_text();assert text.count(START)==text.count(END)==1
        text=text.split(START)[0]+START+'\n\n'+readme_block(summary)+'\n'+END+text.split(END)[1]
        (ROOT/'README.md').write_text(text)
    write_json(a.output/'status.json',{'complete':True,'model_calls':0})
    print(json.dumps({k:v for k,v in summary.items() if k not in ('continuity','fault_probes')},indent=2))

if __name__=='__main__':main()
