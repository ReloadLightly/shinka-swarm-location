"""Inspect actual pinned native prompt/meta paths with explicit offline fixtures.

No provider/model requests occur. Captured payloads prove context routing at the
client boundary, not that an LLM understood it or that evolution improved.
"""
from __future__ import annotations
import argparse
import asyncio
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import sys
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from evaluate_anytime import write_json
from run_evo import verify_native, parser, plan
from swarm_location.feedback import task_context, attach_meta_context

FIXTURE = 'OFFLINE_TEST_FIXTURE_NO_LLM'


class CaptureTransport:
    """Only used by this verification script, never wired into a real campaign."""
    def __init__(self):self.requests=[]
    async def batch_kwargs_query(self,**kwargs):
        self.requests.append({'call':'batch_kwargs_query',**kwargs})
        return [SimpleNamespace(content=FIXTURE+' individual summary '+str(i),cost=0.)
                for i in range(kwargs['num_samples'])]
    async def query(self,**kwargs):
        self.requests.append({'call':'query',**kwargs})
        text=(FIXTURE+' global scratchpad' if len(self.requests)==2 else
              '1. '+FIXTURE+' preserve observations separately from hypotheses.')
        return SimpleNamespace(content=text,cost=0.)


def program_from_evaluation(path:Path,code:Path,ident:str,Program):
    m=json.loads((path/'metrics.json').read_text());ok=json.loads((path/'correct.json').read_text())['correct']
    return Program(id=ident,code=code.read_text(),generation=0,correct=ok,
        combined_score=m['combined_score'],public_metrics=m.get('public',{}),
        private_metrics=m.get('private',{}),text_feedback=m['text_feedback'],
        metadata={'patch_name':ident,'scope':'Hand-inserted integration probe, NOT an evolved descendant'})


async def check(output:Path,suite:Path,seed:Path,failure:Path,failure_code:Path):
    pin='9912af12d423504b8d580f4179fd15f5f88b8c50';version=verify_native(pin)
    from shinka.core.sampler import PromptSampler
    from shinka.core.summarizer import MetaSummarizer
    from shinka.core.async_summarizer import AsyncMetaSummarizer
    from shinka.database import Program,ProgramDatabase,DatabaseConfig
    context=task_context()
    resolved=plan(parser().parse_args(['--config',str(ROOT/'configs/evolution_m3.json'),
        '--suite',str(suite),'--feedback-context','m7','--results-dir',str(output/'unused-run')]))
    good=program_from_evaluation(seed,ROOT/'anytime_initial.py','unchanged-seed-probe',Program)
    bad=program_from_evaluation(failure,failure_code,'synthetic-failure-probe',Program)
    assert good.correct and not bad.correct and bad.combined_score==0
    output.mkdir(parents=True,exist_ok=True)
    # Actual native SQLite roundtrip, isolated from all research population files.
    db=ProgramDatabase(DatabaseConfig(db_path=str(output/'probe-only.sqlite')))
    try:
        db.add(good,defer_maintenance=True);db.add(bad,defer_maintenance=True)
        good_again,bad_again=db.get(good.id),db.get(bad.id)
        assert good_again.text_feedback==good.text_feedback
        assert bad_again.text_feedback==bad.text_feedback
    finally:db.close()
    # Exercise the actual pinned three-step meta implementation. Only transport is a test fixture.
    sync=MetaSummarizer(language='python',use_text_feedback=True,max_recommendations=5,async_mode=True)
    transport=CaptureTransport();meta=AsyncMetaSummarizer(sync,transport)
    mutation_marker,novelty_marker=object(),object()
    binding=SimpleNamespace(meta_summarizer=meta,llm=mutation_marker,novelty_judge=novelty_marker)
    attach_meta_context(binding,context)
    assert binding.llm is mutation_marker and binding.novelty_judge is novelty_marker
    sync.add_evaluated_program(good_again);sync.add_evaluated_program(bad_again)
    recommendations,cost=await meta.update_meta_memory_async(good_again)
    assert cost==0 and FIXTURE in recommendations and len(transport.requests)==3
    assert sync.total_programs_processed==2 and not sync.evaluated_since_last_meta
    assert recommendations in sync.meta_recommendations_history
    for request in transport.requests:
        assert context['text'] in request['system_msg']
    individual=transport.requests[0]['msg']
    assert good.text_feedback in individual[0] and bad.text_feedback in individual[1]
    assert 'missing_symbol_m7' in individual[1]
    sync.save_meta_state(str(output/'test-only-meta-state.json'))
    restored=MetaSummarizer(use_text_feedback=True,async_mode=True)
    assert restored.load_meta_state(str(output/'test-only-meta-state.json'))
    assert restored.meta_scratch_pad==sync.meta_scratch_pad
    assert restored.meta_recommendations_history==sync.meta_recommendations_history
    payloads={}
    for mode in ('diff','full','cross'):
        sampler=PromptSampler(task_sys_msg=resolved['evo_config']['task_sys_msg'],use_text_feedback=True,
                              patch_types=[mode],patch_type_probs=[1.])
        system,user,kind=sampler.sample(good_again,[good_again],[good_again],recommendations)
        assert kind==mode and context['text'] in system and good.text_feedback in user
        assert (FIXTURE in system)==(mode!='cross') # native crossover deliberately omits meta recommendations
        payloads[mode]={'system':system,'user':user,'patch_type':kind}
    system,user,kind=sampler.sample_fix(bad_again,[good_again])
    assert kind=='fix' and context['text'] in system and bad.text_feedback in user
    assert 'missing_symbol_m7' in user and 'UNTRUSTED' in user
    payloads['fix']={'system':system,'user':user,'patch_type':kind}
    write_json(output/'captured-request-fixtures.json',{'scope':FIXTURE,
        'model_calls':0,'mutation_payloads':payloads,'meta_requests':transport.requests})
    summary={**version,'success':True,'mutation_formats_checked':['diff','full','cross','fix'],
        'native_meta_stages_checked':3,'native_meta_individual_programs':2,
        'native_sqlite_feedback_roundtrip':True,'native_meta_state_roundtrip':True,
        'meta_context_in_all_three_requests':True,'failure_feedback_in_native_fix':True,
        'crossover_meta_recommendation_behavior':'Native omission preserved; task brief and parent feedback present',
        'context_sha256':context['sha256'],'context_characters':len(context['text']),
        'mutation_bandit_and_novelty_clients_untouched':True,
        'model_calls':0,'evolved_descendants':0,'scope':FIXTURE+': transport responses are labelled fixtures, not model output'}
    write_json(output/'summary.json',summary)
    return summary


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output',type=Path,required=True);p.add_argument('--suite',type=Path,required=True)
    p.add_argument('--seed',type=Path,required=True);p.add_argument('--failure',type=Path,required=True)
    p.add_argument('--failure-code',type=Path,required=True)
    a=p.parse_args();print(json.dumps(asyncio.run(check(a.output,a.suite,a.seed,a.failure,a.failure_code)),indent=2))
