"""Native M3 run request with authenticated preflight and sealed holdout stages.

No substitute mutation loop, hardcoded descendants or fake provider responses.
A missing model route is written as BLOCKED before any inference or test scoring.
"""
from __future__ import annotations
import argparse
from dataclasses import asdict
from datetime import datetime,timezone
import json
from math import isfinite
import os
from pathlib import Path
import subprocess
import sys

from evaluate_anytime import evaluate,write_json
from scripts.prepare_research import prepare,catalog_checked
from swarm_location.isolation import checked_image
from swarm_location.selection import snapshot_population,freeze_champion,evaluate_frozen_test
from swarm_location.suite import file_sha256
from run_evo import verify_native,main as native_main

ROOT=Path(__file__).resolve().parent


def checked_request(path: Path) -> dict:
    request=json.loads(Path(path).read_text())
    if request.get('schema_version') != 1:
        raise ValueError('expected campaign request schema 1')
    if type(request['generations']) is not int or request['generations'] < 1 or type(request['seed']) is not int:
        raise ValueError('positive integer generations and integer seed required')
    cap=request['max_api_cost_usd']
    if isinstance(cap,bool) or not isinstance(cap,(float,int)) or not isfinite(cap) or cap <= 0:
        raise ValueError('finite positive API threshold required')
    if type(request['shortlist_size']) is not int or request['shortlist_size'] < 1:
        raise ValueError('shortlist_size must be positive')
    roles=request['models']
    if not isinstance(roles['mutation'],list) or len(set(roles['mutation'])) < 2:
        raise ValueError('at least two distinct mutation arms required for this campaign')
    if any(not isinstance(m,str) or not m.strip() for m in roles['mutation']+[roles['meta'],roles['novelty'],roles['embedding']]):
        raise ValueError('all model roles must be explicit')
    return request


def start(request_path:Path,output:Path,docker_image:str|None,execute:bool,download:bool):
    request_path,output=(Path(request_path).resolve(),Path(output).resolve());output.mkdir(parents=True,exist_ok=True)
    request=checked_request(request_path)
    catalog=ROOT/'configs/source_catalog_m3.json'; config=ROOT/'configs/evolution_m3.json'
    catalog_checked(catalog)
    state={'requested_utc':datetime.now(timezone.utc).isoformat(),
        'request_sha256':file_sha256(request_path),'catalog_sha256':file_sha256(catalog),
        'request':request,'status':'preflight','inference_calls':0,'native_runner_started':False,
        'valid_evolved_descendants':0,'validation_solver_evaluations':0,'test_solver_evaluations':0}
    state_path=output/'campaign_status.json'
    if state_path.exists() and json.loads(state_path.read_text()).get('native_runner_started'):
        raise ValueError('campaign already started; resume its native run explicitly without replacing evidence')
    write_json(state_path,state)
    try:
        installed=verify_native(request['framework_commit']);state['native_installation']=installed
        from shinka.model_availability import validate_model_env_access,find_model_env_access_issues
        from shinka.core import EvolutionConfig
        from shinka.llm.kwargs import sample_model_kwargs
        roles=request['models']; llms=list(dict.fromkeys(roles['mutation']+[roles['meta'],roles['novelty']]))
        ec=EvolutionConfig(**json.loads(config.read_text())['evo_config'])
        # Check the pinned native model-kwargs path before any inference. In M2,
        # omitting reasoning_efforts could send an empty effort to reasoning APIs.
        state['sampled_native_model_kwargs']={m:sample_model_kwargs(model_names=m,**ec.llm_kwargs) for m in roles['mutation']}
        issues=find_model_env_access_issues(llm_models=llms,embedding_models=[roles['embedding']])
        state['access_issues']=[asdict(i) for i in issues]
        if issues:
            state.update(status='blocked_model_access',reason='Required model credentials are not available to this execution environment')
            write_json(state_path,state);return state
        validate_model_env_access(llm_models=llms,embedding_models=[roles['embedding']])
        if not docker_image:
            state.update(status='blocked_isolation',reason='An explicit immutable Docker image ID is required for generated candidates')
            write_json(state_path,state);return state
        checked_image(docker_image)
        inspected=subprocess.run(['docker','image','inspect',docker_image,'--format','{{.Id}}'],
                                 capture_output=True,text=True,check=True,timeout=30)
        if inspected.stdout.strip()!=docker_image:raise ValueError('container image identity mismatch')
        state['docker_image_id']=docker_image
        if not execute:
            state['status']='ready_not_executed';write_json(state_path,state);return state
        prepare(catalog,output/'development',output/'raw-development','development',download)
        identity={'request':request,'request_sha256':file_sha256(request_path),
            'catalog_sha256':file_sha256(catalog),'evolution_config_sha256':file_sha256(config),
            'development_suite_sha256':file_sha256(output/'development/suite.json'),
            'docker_image_id':docker_image,
            'source_sha256':{str(p.relative_to(ROOT)):file_sha256(p) for p in
                [ROOT/'anytime_initial.py',ROOT/'run_evo.py',ROOT/'campaign.py',ROOT/'evaluate_anytime.py',
                 ROOT/'scripts/prepare_research.py',*sorted((ROOT/'swarm_location').glob('*.py'))]}}
        write_json(output/'campaign_manifest.json',identity) # Before the first model call.
        state.update(status='running_native',native_runner_started=True,inference_calls=None)
        write_json(state_path,state)
        native_main(['--run','--config',str(config),'--suite',str(output/'development/suite.json'),
            '--results-dir',str(output/'native'),'--models',*roles['mutation'],
            '--meta-model',roles['meta'],'--novelty-model',roles['novelty'],
            '--embedding-model',roles['embedding'],'--max-api-cost',str(request['max_api_cost_usd']),
            '--generations',str(request['generations']),'--seed',str(request['seed']),
            '--docker-image',docker_image])
        state['status']='native_returned';write_json(state_path,state)
        if any(file_sha256(ROOT/path) != value for path,value in identity['source_sha256'].items()):
            raise RuntimeError('research implementation changed during evolution')
        frozen=output/'selection'
        shortlist=snapshot_population(output/'native/evolution_db.sqlite',frozen,ROOT/'anytime_initial.py',request['shortlist_size'])
        state['valid_evolved_descendants']=shortlist['valid_unique_nonseed_descendants']
        state['population_records']=shortlist['population_records']
        state['max_generation_observed']=shortlist['max_generation_observed']
        # The native run has ended before any validation performance is measured.
        prepare(catalog,output/'validation-data',output/'raw-validation','validation',download)
        state.update(status='selecting_on_validation',validation_solver_evaluations=None)
        write_json(state_path,state)
        champion=freeze_champion(frozen,output/'validation-data/suite.json',evaluate,docker_image)
        state['validation_solver_evaluations']=sum(
            sum(len(c['methods']) for c in json.loads((frozen/'validation'/row['sha256']/'traces.json').read_text())['cases'])
            for row in champion['validation_results'])
        state['selected_program_sha256']=champion['selected']['sha256']
        state['selected_is_reference_seed']=champion['selected']['is_reference_seed']
        # Only now can test data enter a performance-evaluation workspace.
        prepare(catalog,output/'test-data',output/'raw-test','test',download)
        state.update(status='testing_frozen_program',test_solver_evaluations=None)
        write_json(state_path,state)
        metrics=evaluate_frozen_test(frozen,output/'test-data/suite.json',evaluate,docker_image)
        state['test_solver_evaluations']=sum(len(c['methods']) for c in json.loads((frozen/'test/traces.json').read_text())['cases'])
        state.update(status='completed',test_metrics=str(frozen/'test/metrics.json'),
                     test_correct=json.loads((frozen/'test/correct.json').read_text())['correct'])
        write_json(state_path,state);return state
    except Exception as exc:
        # Do not persist provider error bodies, headers or credentials.
        state.update(status='failed',error_type=type(exc).__name__,
                     reason='See the local execution log; failure preserved without provider response bodies')
        write_json(state_path,state)
        raise


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--request',type=Path,default=ROOT/'configs/m3_launch_request.json')
    p.add_argument('--output',type=Path,default=ROOT/'results/local_m3_campaign')
    p.add_argument('--docker-image')
    p.add_argument('--execute',action='store_true')
    p.add_argument('--download',action='store_true')
    a=p.parse_args();state=start(a.request,a.output,a.docker_image,a.execute,a.download)
    print(json.dumps(state,indent=2))
    if state['status'].startswith('blocked'):raise SystemExit(2)

if __name__=='__main__':main()
