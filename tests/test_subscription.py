"""No-account transport tests. The fake Codex never calls an LLM or the network."""
import argparse
import asyncio
from contextlib import contextmanager
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import run_evo
from swarm_location import subscription as sub
from swarm_location import local_embeddings as embed

ROOT = Path(__file__).resolve().parents[1]
FAKE = '''#!/usr/bin/env python3
import json, os, pathlib, sys, time
if '--version' in sys.argv:
    print('codex-cli 0.154.0-fixture'); raise SystemExit(0)
if 'login' in sys.argv:
    print('Logged in using ' + os.getenv('FAKE_AUTH', 'ChatGPT')); raise SystemExit(0)
assert not any(k in os.environ for k in ('OPENAI_API_KEY','CODEX_API_KEY','ANTHROPIC_API_KEY'))
assert 'forced_login_method="chatgpt"' in sys.argv
assert 'read-only' in sys.argv and '--ephemeral' in sys.argv
assert 'features.shell_tool=false' in sys.argv
prompt = sys.stdin.read()
mode = os.getenv('FAKE_MODE', 'ok')
if mode == 'timeout': time.sleep(4)
if mode == 'quota':
    print(json.dumps({'type':'turn.failed','error':{'message':'Usage limit reached'}}))
    raise SystemExit(1)
if mode == 'bad':
    print('invalid output'); raise SystemExit(0)
answer = pathlib.Path(sys.argv[sys.argv.index('--output-last-message')+1])
answer.write_text('A deterministic fixture reply, not an evolved discovery.')
print(json.dumps({'type':'turn.completed','usage':{'input_tokens':100,'output_tokens':20}}))
'''


class SubscriptionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.binary = self.root/'codex'
        self.binary.write_text(FAKE)
        self.binary.chmod(0o755)
        self.prompt = self.root/'prompt.md'
        self.prompt.write_text('Test transport with an offline fixture.')
        self.env = {**os.environ, 'SWARM_SUBSCRIPTION_DIR': str(self.root/'run'),
                    'SWARM_CODEX_BINARY': str(self.binary), 'SWARM_CODEX_TIMEOUT': '2',
                    'SHINKA_HEADLESS_TIMEOUT': '4', 'OPENAI_API_KEY': 'test-private-key',
                    'CODEX_API_KEY': 'other-private-key', 'FAKE_MODE': 'ok'}
        self.suite = self.root/'suite.json'
        instance = self.root/'instance.json'
        instance.write_text(json.dumps({'schema_version':2,'name':'fixture','nodes':[0,1],
                                       'edges':[[0,1,1]],'od':[[0,1,1]]}))
        from swarm_location.suite import file_sha256
        self.suite.write_text(json.dumps({'schema_version':2,'research_protocol':'chapter-search-v2',
          'checkpoints_seconds':[.1,1], 'seeds':[0], 'relabel_seed':90231,
          'fitness':{'coverage_weight':.5,'certificate_weight':.5},'controls':['greedy'],
          'datasets':[{'id':'fixture','source_graph':'fixture','split':'development',
          'path':instance.name,'sha256':file_sha256(instance),'budgets':[1]}]}))
    def tearDown(self):
        self.temp.cleanup()
    def argv(self, *extra):
        return ['--subscription','--codex-model','test-model','--suite',str(self.suite),
                '--docker-image','sha256:'+'a'*64, '--results-dir',str(self.root/'evo'),*extra]
    def invoke(self, env=None):
        return subprocess.run([sys.executable, str(ROOT/'scripts/codex_headless.py'),
                  'codex','--prompt-file',str(self.prompt),'--work-dir',str(self.root),
                  '--allow','read-only','--usage','--model','test-model','--reasoning-effort','high'],
                  env=env or self.env, capture_output=True, text=True, timeout=10)
    def test_complete_native_command_protocol(self):
        result = self.invoke()
        self.assertEqual(result.returncode, 0, result.stderr)
        usage = json.loads(result.stdout.splitlines()[-1])['usage']
        self.assertEqual(usage['input_tokens'], 100)
        self.assertEqual(usage['cost'], 0)
        records = list((self.root/'run/usage').glob('*.json'))
        self.assertEqual(len(records),1)
        self.assertNotIn('private-key', records[0].read_text())
    def test_api_auth_rejected_before_inference(self):
        result=self.invoke({**self.env,'FAKE_AUTH':'API key'})
        self.assertNotEqual(result.returncode,0)
        self.assertIn('ChatGPT-authenticated',result.stderr)
        self.assertTrue((self.root/'run/provider_blocked.json').exists())
    def test_quota_latches_without_retry_or_fallback(self):
        first = self.invoke({**self.env,'FAKE_MODE':'quota'})
        self.assertNotEqual(first.returncode,0)
        second=self.invoke()
        self.assertNotEqual(second.returncode,0)
        self.assertIn('no new request', second.stderr)
        self.assertEqual(len(list((self.root/'run/usage').glob('*.json'))),1)
    def test_timeout_and_bad_completion_fail_closed(self):
        result=self.invoke({**self.env,'FAKE_MODE':'timeout','SWARM_CODEX_TIMEOUT':'.1'})
        self.assertNotEqual(result.returncode,0)
        self.assertFalse(list((self.root/'run').glob('active_*.json')))
    def test_non_completed_turn_is_not_accepted(self):
        result=self.invoke({**self.env,'FAKE_MODE':'bad'})
        self.assertNotEqual(result.returncode,0)
        self.assertIn('completed-turn',result.stderr)
    def test_roles_keep_native_machinery_and_no_paid_embeddings(self):
        plan=run_evo.plan(run_evo.parser().parse_args(self.argv('--run')))
        evo=plan['evo_config']
        self.assertEqual(evo['num_generations'],200)
        self.assertEqual(plan['db_config']['num_islands'],2)
        self.assertEqual(plan['db_config']['num_archive_inspirations'],4)
        self.assertEqual(evo['llm_dynamic_selection'],'ucb')
        self.assertEqual(evo['llm_dynamic_selection_kwargs']['cost_aware_coef'],0)
        self.assertIsNone(evo['max_api_costs'])
        self.assertEqual(evo['meta_rec_interval'],10)
        self.assertEqual(evo['max_novelty_attempts'],3)
        for model in evo['llm_models']+evo['meta_llm_models']+evo['novelty_llm_models']:
            sub.validate_route(model)
        self.assertTrue(evo['embedding_model'].startswith('local/swarm-minilm'))
    def test_paid_routes_and_cost_flags_are_rejected(self):
        for extra in [('--models','gpt-paid'),('--meta-model','gpt-paid'),
                      ('--novelty-model','gpt-paid'),('--embedding-model','text-embedding-3-small'),
                      ('--max-api-cost','1')]:
            with self.subTest(extra=extra), self.assertRaises(ValueError):
                run_evo.plan(run_evo.parser().parse_args(self.argv('--run',*extra)))
    def test_missing_model_and_duplicate_arms_rejected(self):
        with self.assertRaises(ValueError):
            run_evo.plan(run_evo.parser().parse_args(['--subscription','--suite',str(self.suite)]))
        with self.assertRaises(ValueError):
            run_evo.plan(run_evo.parser().parse_args(self.argv('--codex-efforts','high','high')))
    def test_clean_env_preserves_login_but_blocks_api_credentials(self):
        env=sub.clean_env({'HOME':'/home/user','CODEX_HOME':'/home/user/custom',
           'OPENAI_API_KEY':'secret','GOOGLE_APPLICATION_CREDENTIALS':'/tmp/key',
           'OPENAI_BASE_URL':'http://remote','API_KEY':'value','GH_TOKEN':'secret'})
        self.assertEqual(env['CODEX_HOME'],'/home/user/custom')
        self.assertNotIn('API_KEY',env)
        self.assertNotIn('OPENAI_BASE_URL',env)
        self.assertEqual(env['PYTHON_DOTENV_DISABLED'],'1')
        self.assertIn('127.0.0.1',env['NO_PROXY'].split(','))
        self.assertEqual(env['NO_PROXY'],env['no_proxy'])
    def test_transport_restores_environment_and_explicit_resume(self):
        args=run_evo.parser().parse_args(self.argv('--codex-binary',str(self.binary)))
        before=dict(os.environ)
        with sub.transport(args,{}):
            root=Path(os.environ['SWARM_SUBSCRIPTION_DIR'])
            sub.block(root,'quota')
        self.assertEqual(dict(os.environ),before)
        with self.assertRaises(RuntimeError):
            with sub.transport(args,{}): pass
        args.resume_provider=True
        with sub.transport(args,{}):
            self.assertFalse((root/'provider_blocked.json').exists())
            self.assertEqual(len(list(root.glob('provider_blocked_*.json'))),1)
    def test_supervisor_cancels_native_task_on_provider_pause(self):
        class Runner:
            cleaned=False
            async def run_async(runner):
                try:
                    sub.block(self.root,'quota')
                    await asyncio.sleep(10)
                finally:
                    runner.cleaned=True
        runner=Runner()
        with self.assertRaises(RuntimeError):
            asyncio.run(sub.run_with_pause(runner,self.root))
        self.assertTrue(runner.cleaned)
    def test_asset_checksum_not_silently_repaired(self):
        (self.root/'tokenizer.json').write_text('wrong tokenizer')
        (self.root/'onnx').mkdir()
        (self.root/'onnx/model.onnx').write_bytes(b'not a model')
        with self.assertRaises(ValueError): embed.prepare(self.root)
    def test_reference_build_precedes_native_import(self):
        args=run_evo.parser().parse_args(self.argv('--run'))
        plan=run_evo.plan(args)
        with patch('run_evo.verify_native',return_value={}), \
             patch('swarm_location.isolation.require_isolation'), \
             patch('evaluate_search.build_references',side_effect=RuntimeError('reference interrupted')) as build, \
             patch.dict(os.environ,{},clear=True), self.assertRaisesRegex(RuntimeError,'reference interrupted'):
            run_evo.execute(args,plan)
        build.assert_called_once()


@unittest.skipUnless(os.environ.get('SWARM_TEST_NATIVE_SUBSCRIPTION') == '1', 'requires installed pinned native framework; no model calls')
class NativeSubscriptionTests(unittest.TestCase):
    def test_pinned_native_headless_provider_uses_bridge(self):
        from shinka.llm.providers.headless import query_headless, query_headless_async
        import shlex
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            binary=root/'codex'; binary.write_text(FAKE); binary.chmod(0o755)
            env={'SHINKA_HEADLESS_COMMAND':shlex.join([sys.executable,str(ROOT/'scripts/codex_headless.py')]),
                 'SWARM_CODEX_BINARY':str(binary),'SWARM_SUBSCRIPTION_DIR':str(root/'state'),
                 'SHINKA_PRICING_MODE':'offline','PYTHON_DOTENV_DISABLED':'1'}
            with patch.dict(os.environ,env):
                for route in ('headless/codex@fixture?effort=medium','headless/codex@fixture?effort=high'):
                    result=query_headless(None,route,'fixture','fixture',[],None,headless_work_dir=tmp)
                    self.assertEqual(result.cost,0)
                    self.assertEqual(result.input_tokens,100)
                result=asyncio.run(query_headless_async(None,route,'fixture','fixture',[],None,headless_work_dir=tmp))
                self.assertIn('fixture reply',result.content)
    def test_native_runner_constructs_all_roles_without_inference(self):
        from shinka.core import EvolutionConfig, ShinkaEvolveRunner
        from shinka.database import DatabaseConfig
        from shinka.launch import LocalJobConfig
        import shlex
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            binary=root/'codex'; binary.write_text(FAKE); binary.chmod(0o755)
            config=json.loads((ROOT/'configs/evolution_search.json').read_text())
            route='headless/codex@fixture?effort=high'
            env={'SHINKA_HEADLESS_COMMAND':shlex.join([sys.executable,str(ROOT/'scripts/codex_headless.py')]),
                 'SWARM_CODEX_BINARY':str(binary),'SWARM_SUBSCRIPTION_DIR':str(root/'state'),
                 'SHINKA_PRICING_MODE':'offline','PYTHON_DOTENV_DISABLED':'1'}
            evo=EvolutionConfig(**dict(config['evo_config'], llm_models=[route],
                meta_llm_models=[route], novelty_llm_models=[route],
                embedding_model=f'local/{embed.MODEL}@http://127.0.0.1:8877/v1',
                results_dir=str(root/'native'), init_program_path=str(ROOT/'search_initial.py')))
            with patch.dict(os.environ,env):
                runner=ShinkaEvolveRunner(evo_config=evo,
                    db_config=DatabaseConfig(**config['db_config']),
                    job_config=LocalJobConfig(eval_program_path=str(ROOT/'evaluate_search.py')),
                    max_evaluation_jobs=1,max_proposal_jobs=1,max_db_workers=1,verbose=False)
                try:
                    self.assertIsNotNone(runner.meta_summarizer)
                    self.assertIsNotNone(runner.novelty_judge)
                    self.assertIsNotNone(runner.embedding_client)
                    self.assertEqual(runner.db_config.num_islands,2)
                    self.assertEqual(runner.evo_config.num_generations,200)
                    self.assertFalse((root/'state/usage').exists())
                finally:
                    runner.scheduler.shutdown()
    def test_native_local_embeddings_real_model(self):
        import urllib.request
        import numpy as np
        directory=Path(os.environ['SWARM_TEST_EMBEDDING_DIR'])
        with embed.server(directory,0):
            # Independent direct model calls cover the entire code, not just its prefix.
            encoder=embed.Encoder(directory)
            vectors,tokens=encoder.encode(['def greedy(): return 1', 'def greedy(): return 1',
                                            ('def unused(): pass\n'*300)+'def different(): return 2'])
            self.assertEqual(len(vectors[0]),384)
            self.assertTrue(np.allclose(vectors[0],vectors[1]))
            self.assertTrue(np.allclose(np.linalg.norm(vectors,axis=1),1))
            self.assertGreater(tokens,256)
        # Exercise native OpenAI-compatible embedding client against actual loopback inference.
        from shinka.embed import AsyncEmbeddingClient
        from socket import socket
        with socket() as s:
            s.bind(('127.0.0.1',0)); port=s.getsockname()[1]
        with embed.server(directory,port):
            client=AsyncEmbeddingClient(model_name=f'local/{embed.MODEL}@http://127.0.0.1:{port}/v1')
            vector,cost=asyncio.run(client.embed_async('def monitor(): return []'))
            self.assertEqual(len(vector),384)
            self.assertEqual(cost,0)
