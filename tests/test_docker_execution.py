"""Real-container regressions. Enabled explicitly by the current CI workflow."""
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from test_evaluation_path import instance, fixture
from swarm_location.prepared import ensure_prepared
from swarm_location.anytime import run_anytime
from swarm_location.persistence import file_digest
from swarm_location.verification import limits_from
from evaluate_search import evaluate, build_references


@unittest.skipUnless(os.environ.get('SWARM_TEST_DOCKER_IMAGE'), 'requires an explicitly supplied local Docker image')
class DockerExecutionTests(unittest.TestCase):
    def environment(self):
        return patch.dict(os.environ, {'SWARM_DOCKER_IMAGE': os.environ['SWARM_TEST_DOCKER_IMAGE'],
                                       'SWARM_WORKER_MEMORY_MIB':'512',
                                       'SWARM_PRIVATE_SENTINEL':'must-not-reach-worker'})

    def test_read_only_prepared_data_and_no_provider_environment_or_network(self):
        with tempfile.TemporaryDirectory() as d, self.environment():
            root = Path(d); prepared = ensure_prepared(instance(), root/'cache')
            p = root/'probe.py'
            p.write_text('''def solve(p,k,seed,report,budget):
 import os, socket
 assert "SWARM_PRIVATE_SENTINEL" not in os.environ
 try:
  open("prepared.jsonl.gz", "wb")
 except OSError:
  pass
 else:
  raise AssertionError("prepared artifact writable")
 try:
  open("/work/candidate.py", "w")
 except OSError:
  pass
 else:
  raise AssertionError("source writable")
 s=socket.socket(); s.settimeout(.2)
 try:
  s.connect(("198.51.100.1",9))
 except OSError:
  pass
 else:
  raise AssertionError("unexpected network access")
 finally:
  s.close()
 report([0])
 report.bound({"kind":"universal_v1","upper":"1","selected":[0]})
''')
            result = run_anytime(instance(),1,[1.],program_path=p,allow_candidate_bounds=True,
                prepared_path=prepared[0],prepared_sha256=prepared[1],
                verification_limits=limits_from({'verification_timeout_seconds':10,'verification_memory_mib':512}))
            self.assertTrue(result['correct'], result.get('error'))
            self.assertEqual(result['isolation']['mode'], 'docker')
            self.assertEqual(file_digest(prepared[0]), prepared[1])
            self.assertTrue(result['verified_search_bounds'])
            print(json.dumps({'image':os.environ['SWARM_DOCKER_IMAGE'],'verified':True}))

    def test_real_docker_evaluation_reuses_completed_trials(self):
        with tempfile.TemporaryDirectory() as d, self.environment():
            root = Path(d); suite, refs, candidate = fixture(root, (1,))
            build_references(suite, refs)
            first = evaluate(candidate,root/'result',suite,refs)
            with patch('evaluate_search.run', side_effect=AssertionError('completed Docker trial rerun')):
                second = evaluate(candidate,root/'result',suite,refs)
            self.assertEqual(first['combined_score'],second['combined_score'])
            self.assertEqual(second['public']['solver_runs_this_evaluation'],0)
            self.assertEqual(second['public']['completed_cases_reused'],1)


if __name__ == '__main__': unittest.main()
