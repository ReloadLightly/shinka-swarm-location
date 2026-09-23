"""Fixed-control mathematics, interruption and protocol tests; no model calls."""
from copy import deepcopy
from fractions import Fraction
from itertools import combinations
import random
from pathlib import Path
import tempfile
from time import perf_counter
import unittest

from swarm_location.core import Instance,ShortestPathCoverage
from swarm_location.search import SearchProblem
from swarm_location.certificates import ExactCoverage
from swarm_location.route_search import RouteSearch,RouteLimit,SearchDeadline
from swarm_location.strong_baselines import METHODS,solve,greedy,descent
from swarm_location.bounded_search import PartitionSearch,potential_key
from swarm_location.baseline_proofs import verify_online_bounds
from swarm_location.anytime import run_anytime
from test_core import make

ROOT=Path(__file__).resolve().parents[1]


def problem(seed=0):
    rng=random.Random(seed);n=7
    edges={(i,(i+1)%n):rng.randint(1,3) for i in range(n)}
    edges.update({(i,j):rng.randint(1,4) for i in range(n) for j in range(n) if i!=j and rng.random()<.2})
    return SearchProblem(make(list(range(n)),[(i,j,w) for (i,j),w in edges.items()],
        [(i,j,rng.randint(1,9)) for i in range(n) for j in range(n) if i!=j]))


class Recorder:
    def __init__(self):self.groups=[];self.bounds=[];self.stats=[]
    def __call__(self,s):self.groups.append(list(s))
    def bound(self,event):self.bounds.append((float(len(self.bounds)),deepcopy(event)))
    def diagnostic(self,event):self.stats.append(deepcopy(event))


class RouteTests(unittest.TestCase):
    def test_exact_routes_against_existing_independent_dag_on_all_subsets(self):
        for seed in range(10):
            original=problem(seed);p=RouteSearch(original);oracle=ExactCoverage(original.instance)
            self.assertEqual(p.routes,oracle.exact_routes())
            for k in range(8):
                for s in combinations(range(7),k):
                    self.assertEqual(Fraction(p.score(s),p.scale),oracle.score(p.ids(s)))

    def test_guards_never_sample_and_deadline_interrupts_construction(self):
        original=problem()
        with self.assertRaises(RouteLimit):RouteSearch(original,max_routes=1)
        with self.assertRaises(RouteLimit):RouteSearch(original,max_visits=1)
        with self.assertRaises(SearchDeadline):RouteSearch(original,deadline=0)
        for cap in [0,True,-1,20001]:
            with self.assertRaises(ValueError):RouteSearch(original,max_routes=cap)

    def test_binary_demand_exactness_centroid_and_ties(self):
        instance=make([1,2,3,4,5],[(1,2,'.1'),(2,4,'.1'),(1,3,'.2'),(3,4,'.2'),
                     (1,5,'.3'),(5,4,'.1')],[(1,4,.1),(1,5,.3)],3)
        p=RouteSearch(SearchProblem(instance));o=ExactCoverage(instance)
        for k in range(6):
            for s in combinations(p.nodes,k):
                self.assertEqual(Fraction(p.score(p.indices(s)),p.scale),o.score(s))

    def test_celf_matches_exact_full_greedy_with_ties(self):
        for seed in range(12):
            p=RouteSearch(problem(seed))
            for k in range(8):
                a,ac=greedy(p,k,float('inf'),lambda _:None)
                b,bc=greedy(p,k,float('inf'),lambda _:None,lazy=True)
                self.assertEqual(a,b)
                if k>1:self.assertLessEqual(bc['gain_evaluations'],ac['gain_evaluations'])


class BoundSearchTests(unittest.TestCase):
    def test_both_searches_and_interrupted_frontiers_against_exhaustive(self):
        for seed in range(8):
            original=problem(seed);p=RouteSearch(original)
            for k in (1,2,3,4):
                optimum=max(p.score(s) for s in combinations(range(7),k))
                for mode in ('dfbnb','potential'):
                    for limit in (0,1,3,1000):
                        search=PartitionSearch(p,k,(),mode,max_splits=limit)
                        recorder=Recorder();search.run(recorder,recorder.bound,float('inf'))
                        verified=verify_online_bounds(original.instance,k,recorder.bounds)
                        self.assertLessEqual(search.best,optimum)
                        self.assertGreaterEqual(search.upper(),optimum)
                        self.assertEqual(Fraction(search.upper(),p.scale),Fraction(verified[-1]['upper_exact']))
                        if limit==1000:
                            self.assertEqual(search.best,optimum)
                            self.assertEqual(search.upper(),optimum)
                            self.assertTrue(verified[-1]['optimality_proved'])

    def test_deadline_during_expansion_keeps_parent_and_valid_bound(self):
        from unittest.mock import patch
        p=RouteSearch(problem());tree=PartitionSearch(p,3,())
        before=dict(tree.leaves)
        with patch('swarm_location.bounded_search.check_time',side_effect=[None,SearchDeadline()]):
            with self.assertRaises(SearchDeadline):tree.step()
        self.assertEqual(tree.leaves,before)
        self.assertEqual(tree.splits,0)
        r=verify_online_bounds(p.instance,3,[(0.,tree.snapshot())])
        self.assertGreaterEqual(Fraction(r[-1]['upper_exact']),max(Fraction(p.score(s),p.scale) for s in combinations(range(7),3)))

    def test_shared_route_interface_does_not_mix_search_budgets(self):
        p=RouteSearch(problem());a=PartitionSearch(p,1,());b=PartitionSearch(p,4,())
        while a.step():pass
        while b.step():pass
        self.assertEqual(a.best,max(p.score(s) for s in combinations(range(7),1)))
        self.assertEqual(b.best,max(p.score(s) for s in combinations(range(7),4)))

    def test_priority_is_utility_tail_not_cost_or_best_bound_order(self):
        # Best-bound would prefer upper=100. Utility potential prefers 20/10 over 100/90.
        self.assertLess(potential_key(80,100,90),potential_key(0,100,90))
        self.assertLess(potential_key(90,90,90),potential_key(80,100,90))
        self.assertLess(potential_key(0,100,90),potential_key(0,89,90))

    def test_corrupted_missing_reordered_duplicate_proofs_rejected(self):
        p=RouteSearch(problem());tree=PartitionSearch(p,3,(),max_splits=4)
        while tree.step():pass
        event=tree.snapshot();self.assertTrue(event['ops'])
        changes=[]
        bad=deepcopy(event);bad['upper']='0';changes.append(bad)
        bad=deepcopy(event);bad['ops']=bad['ops'][1:];changes.append(bad)
        bad=deepcopy(event);bad['ops'].append(bad['ops'][0]);bad['splits']+=1;changes.append(bad)
        bad=deepcopy(event);bad['ops'][0][1]=999;changes.append(bad)
        bad=deepcopy(event);bad['selected']=[True];changes.append(bad)
        for bad in changes:
            with self.assertRaises(ValueError):verify_online_bounds(p.instance,3,[(0.,bad)])

    def test_final_certificates_not_inferred_from_stopping_reason(self):
        p=RouteSearch(problem());tree=PartitionSearch(p,3,(),max_splits=0)
        event=tree.snapshot();event['termination']='exhausted'
        got=verify_online_bounds(p.instance,3,[(0.,event)])
        self.assertFalse(got[-1]['optimality_proved'])

    def test_zero_budget_and_frontier_resource_limits(self):
        p=RouteSearch(problem())
        for mode in ('dfbnb','potential'):
            tree=PartitionSearch(p,0,(),mode);r=Recorder();tree.run(r,r.bound,float('inf'))
            self.assertEqual(tree.upper(),0)
            self.assertTrue(verify_online_bounds(p.instance,0,r.bounds)[-1]['optimality_proved'])
            tree=PartitionSearch(p,3,(),mode,max_open=1)
            self.assertFalse(tree.step());self.assertEqual(tree.termination,'resource_limit')
            self.assertGreater(tree.upper(),0)

    def test_improvement_rekeys_potential_frontier(self):
        p=RouteSearch(SearchProblem(Instance.load(ROOT/'data/sioux_falls.json')))
        initial,_=greedy(p,6,float('inf'),lambda _:None)
        initial,_=descent(p,initial,float('inf'),lambda _:None)
        tree=PartitionSearch(p,6,initial,'potential');r=Recorder();tree.run(r,r.bound,float('inf'))
        self.assertGreater(tree.rekeys,1)
        self.assertEqual(Fraction(tree.best,p.scale),Fraction(530,601))


class IntegrationTests(unittest.TestCase):
    def test_all_methods_use_existing_external_scorer(self):
        p=problem();oracle=ShortestPathCoverage(p.instance)
        for method in METHODS:
            r=run_anytime(p.instance,3,[.03,.15],baseline=method)
            self.assertTrue(r['correct'],(method,r['error']))
            self.assertEqual(r['final_coverage'],oracle.score(r['selected']))
            if method in ('dfbnb','potential'):
                self.assertTrue(r['verified_search_bounds'])

    def test_opt_in_evolution_comparisons_keep_existing_fitness(self):
        import json
        from evaluate_anytime import evaluate
        from swarm_location.suite import file_sha256
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);network=root/'network.json'
            network.write_text(json.dumps(problem().instance.to_dict()))
            suite=root/'suite.json'
            suite.write_text(json.dumps({'schema_version':2,'checkpoints_seconds':[.2],
                'seeds':[0],'extra_baselines':['celf','potential'],
                'datasets':[{'id':'unit','source_graph':'unit','split':'development',
                    'path':'network.json','sha256':file_sha256(network),'budgets':[2]}]}))
            metrics=evaluate(ROOT/'anytime_initial.py',root/'out',suite)
            self.assertEqual(metrics['public']['failed_cases'],0)
            self.assertAlmostEqual(metrics['combined_score'],100)
            trace=json.loads((root/'out/traces.json').read_text())
            self.assertEqual(set(trace['cases'][0]['methods']),{'candidate','greedy','greedy_swap','celf','potential'})

    def test_candidate_cannot_claim_a_trusted_bound(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'candidate.py'
            path.write_text('import sys\ndef solve(p,k,s,r,b):\n sys.__stdout__.write(\'{"search_bound":{"upper":"0"}}\\n\')\n sys.__stdout__.flush()\n')
            r=run_anytime(problem().instance,3,[.05,.1],program_path=path)
            self.assertFalse(r['correct'])

    def test_guard_fallback_reports_reason_and_feasible_deployment(self):
        p=problem();r=Recorder()
        result=solve(p,3,0,r,1,'celf',route_limit=1)
        self.assertTrue(any(s.get('fallback') for s in r.stats))
        p.instance.validate_selection(result,3)
        self.assertGreater(p.score(result),0)

    def test_route_construction_is_after_go_and_charged(self):
        # A tiny externally enforced budget cannot credit an expensive preparation.
        r=run_anytime(problem().instance,3,[.000001],baseline='potential')
        self.assertTrue(r['correct'],r)
        self.assertEqual(r['final_coverage'],0)

    def test_iterated_reproducible_by_cycles_retains_best_and_can_escape(self):
        p=SearchProblem(Instance.load(ROOT/'data/sioux_falls.json'))
        outputs=[]
        for _ in range(2):
            r=Recorder();result=solve(p,6,0,r,30,'iterated',max_cycles=40)
            outputs.append(result)
            values=[p.score(s) for s in r.groups]
            self.assertEqual(values,sorted(values))
            self.assertGreater(p.score(result),.869661675)
            self.assertGreater(r.stats[-1]['accepted_worse_working_states'],0)
        self.assertEqual(*outputs)

if __name__=='__main__':unittest.main()
