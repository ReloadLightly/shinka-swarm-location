import json
from pathlib import Path
import tempfile
import unittest

from evaluate import evaluate, ROOT
from swarm_location import Instance, ShortestPathCoverage


class EvaluatorTests(unittest.TestCase):
    def test_seed_evaluation(self):
        with tempfile.TemporaryDirectory() as d:
            metrics = evaluate(str(ROOT / 'initial.py'), d, str(ROOT / 'data/sioux_falls.json'), [1, 2])
            self.assertEqual(metrics['public']['mean_improvement_over_greedy_pp'], 0)
            self.assertTrue(json.loads((Path(d) / 'correct.json').read_text())['correct'])

    def test_invalid_output_overwrites_stale_success(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d)
            (p / 'correct.json').write_text('{"correct": true}')
            (p / 'bad.py').write_text('def run_experiment(**kwargs):\n    return [999999]\n')
            with self.assertRaises(ValueError):
                evaluate(str(p / 'bad.py'), d, str(ROOT / 'data/sioux_falls.json'), [1])
            self.assertFalse(json.loads((p / 'correct.json').read_text())['correct'])
            self.assertEqual(json.loads((p / 'metrics.json').read_text())['combined_score'], 0)

    def test_returned_scores_are_not_trusted(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d)
            (p / 'bad.py').write_text('def run_experiment(**kwargs):\n    return {"locations": [10], "score": 1.0}\n')
            with self.assertRaises(ValueError):
                evaluate(str(p / 'bad.py'), d, str(ROOT / 'data/sioux_falls.json'), [1])

    def test_sioux_falls_identity_and_full_coverage(self):
        inst = Instance.load(ROOT / 'data/sioux_falls.json')
        problem = ShortestPathCoverage(inst)
        self.assertEqual(len(inst.nodes), 24)
        self.assertEqual(len(inst.edges), 76)
        self.assertEqual(problem.total_demand, 360600)
        self.assertEqual(problem.score(inst.nodes), 1)


if __name__ == '__main__':
    unittest.main()
