"""Exact arithmetic/proof tests; synthetic fixtures are not experiment results."""
from copy import deepcopy
from dataclasses import replace
from fractions import Fraction
from itertools import combinations
import json
from pathlib import Path
import random
import tempfile
import unittest

from swarm_location.certificates import (ExactCoverage, bound_witness, certificate,
                                        decimal_bound, verify_bound)
from swarm_location.certificate_references import branch_bound, lp_bound
from swarm_location.core import Instance


def make(nodes, edges, od, first_thru_node=None):
    return Instance.from_dict({'schema_version': 1, 'name': 'certificate-unit-fixture',
        'nodes': nodes, 'edges': edges, 'od': od, 'first_thru_node': first_thru_node})


def diamond():
    return make([1,2,3,4], [[1,2,1],[1,3,1],[2,4,1],[3,4,1]], [[1,4,10]])


def all_groups(nodes, k):
    return [s for size in range(k + 1) for s in combinations(nodes, size)]


class ExactBoundsTests(unittest.TestCase):
    def test_endpoint_overlap_and_tied_routes(self):
        oracle = ExactCoverage(diamond())
        self.assertEqual(oracle.score([2]), Fraction(1,2))
        self.assertEqual(oracle.score([2,3]), 1)
        self.assertEqual(oracle.score([1,2]), 1)
        self.assertEqual(oracle.score([4]), 1)
        self.assertEqual(oracle.score([]), 0)
        self.assertEqual(oracle.score_and_gains([2])[1][3], Fraction(1,2))

    def test_exact_rational_means_loaded_binary_demand_not_decimal_rounding(self):
        oracle = ExactCoverage(make([1,2,3], [[1,3,1],[2,3,1]], [[1,3,.1],[2,3,.3]]))
        expected = Fraction(.1)/(Fraction(.1)+Fraction(.3))
        self.assertEqual(oracle.score([1]), expected)
        self.assertNotEqual(expected, Fraction(1,4))

    def test_top_k_not_remaining_slots_counterexample(self):
        oracle = ExactCoverage(make([1,2,3], [[1,3,1],[2,3,1]], [[1,3,1],[2,3,1]]))
        self.assertEqual(oracle.score([1]), Fraction(1,2))
        self.assertEqual(oracle.submodular_upper(1, [1]), 1)
        # k-|anchor| would yield .5 and falsely certify the bad anchor optimal.
        cert = certificate(oracle, [1], 1)
        self.assertEqual(cert['quality_lower_bound_exact'], '1/2')
        self.assertFalse(cert['deployment_optimality_proved'])

    def test_any_algorithm_not_just_greedy(self):
        oracle = ExactCoverage(diamond())
        result = certificate(oracle, [2], 1, feasible_references=[[1]])
        self.assertEqual(result['remaining_gain_lower_pp'], '50.000000')
        self.assertEqual(result['remaining_gain_upper_pp'], '50.000000')
        self.assertTrue(result['optimum_value_proved'])
        self.assertFalse(result['deployment_optimality_proved'])

    def test_zero_budget_and_empty_deployment(self):
        oracle = ExactCoverage(diamond())
        zero = certificate(oracle, [], 0)
        self.assertEqual(zero['quality_lower_bound_exact'], '1')
        self.assertTrue(zero['deployment_optimality_proved'])
        nonzero = certificate(oracle, [], 2)
        self.assertEqual(nonzero['quality_lower_bound_exact'], '0')
        self.assertFalse(nonzero['deployment_optimality_proved'])

    def test_invalid_groups_never_receive_quality_certificate(self):
        oracle = ExactCoverage(diamond())
        for selected, k in [([1,1],2), ([99],1), ([True],1), ([1,2],1), ([],True), ([],9)]:
            with self.subTest(selected=selected,k=k), self.assertRaises(ValueError):
                certificate(oracle,selected,k)
        with self.assertRaises(ValueError):
            certificate(oracle,[],1,feasible_references=[[1,2]])

    def test_display_guarantees_round_conservatively(self):
        for value in [Fraction(2,3), Fraction(-2,3), Fraction(100), Fraction(1,10**10)]:
            self.assertLessEqual(Fraction(decimal_bound(value)),value)
            self.assertGreaterEqual(Fraction(decimal_bound(value,upper=True)),value)

    def test_no_marginal_cache_mutation(self):
        oracle = ExactCoverage(diamond())
        _, gains = oracle.score_and_gains([])
        gains[1] = Fraction(-100)
        self.assertEqual(oracle.score_and_gains([])[1][1],1)

    def test_budget_model_and_instance_identity_checked(self):
        oracle = ExactCoverage(diamond())
        witness = bound_witness(oracle,1)
        for field,value in [('k',2),('model','wrong'),('instance_sha256','0'*64),('upper_bound','1/3')]:
            wrong = dict(witness,**{field:value})
            with self.subTest(field=field),self.assertRaises(ValueError):
                verify_bound(oracle,1,wrong)
        other = ExactCoverage(make([1,2,3,4], [[1,2,1],[1,3,2],[2,4,1],[3,4,1]], [[1,4,10]]))
        with self.assertRaises(ValueError):verify_bound(other,1,witness)

    def test_route_convention_is_part_of_certificate_identity(self):
        instance = make([0, 1, 2], [[0, 1, 1], [1, 2, 1], [0, 2, 2]], [[0, 2, 1]])
        time_only = ExactCoverage(instance)
        fewest_links = ExactCoverage(replace(instance, shortest_path_ties='min_time_min_hops'))
        # Even with strictly positive links, the two route populations differ.
        self.assertEqual(time_only.score([1]), Fraction(1, 2))
        self.assertEqual(fewest_links.score([1]), 0)
        self.assertNotEqual(time_only.identity, fewest_links.identity)
        for source, target in [(time_only, fewest_links), (fewest_links, time_only)]:
            witness = bound_witness(source, 1)
            self.assertEqual(verify_bound(source, 1, witness), 1)
            # Both bounds happen to be 1; numeric agreement must not bypass
            # the requirement that a certificate belongs to its route model.
            with self.assertRaisesRegex(ValueError, 'instance.*mismatch'):
                verify_bound(target, 1, witness)

    def test_route_limit_does_not_force_sampling_or_prevent_DAG_bound(self):
        layers=30
        edges=[[0,1,1],[0,2,1]]
        for i in range(1,layers):
            edges += [[u,v,1] for u in [2*i-1,2*i] for v in [2*i+1,2*i+2]]
        target=2*layers+1
        edges += [[target-2,target,1],[target-1,target,1]]
        oracle=ExactCoverage(make(list(range(target+1)),edges,[[0,target,1]]))
        self.assertEqual(oracle.score_and_gains([])[1][1],Fraction(1,2))
        with self.assertRaisesRegex(ValueError,'routes exceed'):oracle.exact_routes(100)
        self.assertEqual(certificate(oracle,[1],1)['quality_lower_bound_exact'],'1/2')

    def test_centroid_restrictions_unchanged(self):
        oracle=ExactCoverage(make([1,2,3,4],[[1,2,1],[2,4,1],[1,3,2],[3,4,2]],[[1,4,1]],3))
        self.assertEqual(oracle.score([2]),0)
        self.assertEqual(oracle.score([3]),1)

    def test_exact_gains_and_global_bounds_on_all_small_subsets(self):
        for seed in range(8):
            rng=random.Random(1200+seed)
            n=5
            edges={(v,(v+1)%n):rng.randint(1,3) for v in range(n)}
            edges.update({(u,v):rng.randint(1,3) for u in range(n) for v in range(n)
                          if u!=v and rng.random()<.3})
            oracle=ExactCoverage(make(list(range(n)),[[u,v,w] for (u,v),w in edges.items()],
                                     [[s,t,rng.randint(1,8)] for s in range(n) for t in range(n) if s!=t]))
            # Independent all-simple-path enumeration (existing M1 test routine).
            from test_core import independent_routes
            routes=independent_routes(oracle.instance)
            for selected in all_groups(oracle.nodes,n):
                score,gains=oracle.score_and_gains(selected)
                expected=sum(q for route,q in routes if route.intersection(selected))
                self.assertAlmostEqual(float(score),expected,places=12)
                for v,gain in gains.items():
                    self.assertEqual(gain,oracle.score([*selected,v])-score)
                for k in range(n+1):
                    optimum=max(oracle.score(s) for s in all_groups(oracle.nodes,k))
                    self.assertGreaterEqual(oracle.submodular_upper(k,selected),optimum)


class ReferenceProofTests(unittest.TestCase):
    def test_exact_and_interrupted_partition_proofs_against_exhaustive(self):
        for seed in range(12):
            rng=random.Random(seed)
            n=6
            edges={(v,(v+1)%n):1 for v in range(n)}
            edges.update({(u,v):rng.randint(1,4) for u in range(n) for v in range(n)
                          if u!=v and rng.random()<.3})
            oracle=ExactCoverage(make(list(range(n)),[[u,v,w] for (u,v),w in edges.items()],
                                     [[s,t,rng.randint(1,8)] for s in range(n) for t in range(n) if s!=t]))
            for k in range(n+1):
                optimum=max(oracle.score(s) for s in all_groups(oracle.nodes,k))
                for limit in [0,1,1000]:
                    proof=branch_bound(oracle,k,max_expansions=limit)
                    upper=verify_bound(oracle,k,proof)
                    lower=oracle.score(proof['feasible_selected'])
                    self.assertLessEqual(lower,optimum)
                    self.assertGreaterEqual(upper,optimum)
                    if limit==1000:
                        self.assertEqual(upper,optimum)
                        self.assertEqual(lower,optimum)

    def test_partition_cannot_drop_change_or_duplicate_branches(self):
        oracle=ExactCoverage(diamond())
        proof=branch_bound(oracle,1)
        self.assertGreater(len(proof['tokens']),1)
        for tokens in [proof['tokens'][:-1],proof['tokens']+[-1],[999,-1,-1],[True,-1,-1]]:
            with self.subTest(tokens=tokens), self.assertRaises(ValueError):
                verify_bound(oracle,1,dict(proof,tokens=tokens))
        with self.assertRaises(ValueError):
            verify_bound(oracle,1,dict(proof,upper_bound='1/2'))

    def test_false_optimality_or_lower_claim_rejected(self):
        oracle=ExactCoverage(diamond())
        proof=branch_bound(oracle,1)
        for patch in [{'optimality_proved':False},{'lower_bound':'1/2'},{'feasible_selected':[99]}]:
            with self.subTest(patch=patch),self.assertRaises(ValueError):
                verify_bound(oracle,1,dict(proof,**patch))

    def test_reference_limits(self):
        oracle=ExactCoverage(diamond())
        with self.assertRaises(ValueError):branch_bound(oracle,1,max_nodes=2)
        with self.assertRaises(ValueError):branch_bound(oracle,1,max_expansions=-1)
        with self.assertRaises(ValueError):branch_bound(oracle,1,max_routes=1)

    def test_dual_feasibility_independent_of_solver(self):
        oracle=ExactCoverage(diamond())
        routes=oracle.exact_routes()
        proof={'model':bound_witness(oracle,1)['model'],'instance_sha256':oracle.identity,'k':1,
               'kind':'route_dual','alpha':[str(w) for _,w in routes], 'upper_bound':'1'}
        self.assertEqual(verify_bound(oracle,1,proof),1)
        for alpha in [['-1']*len(routes),['2']*len(routes),[],[.1]*len(routes)]:
            with self.subTest(alpha=alpha),self.assertRaises(ValueError):
                verify_bound(oracle,1,dict(proof,alpha=alpha))

    def test_optional_LP_verified_after_proposal(self):
        try:import scipy
        except ImportError:self.skipTest('optional SciPy not installed')
        oracle=ExactCoverage(diamond())
        proof=lp_bound(oracle,1)
        self.assertGreaterEqual(verify_bound(oracle,1,proof),1)
        self.assertLessEqual(verify_bound(oracle,1,proof),1)


class TraceCertificateTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        self.instance=diamond()
        (self.root/'network.json').write_text(json.dumps(self.instance.to_dict()))
        from swarm_location.suite import file_sha256
        self.suite={'schema_version':2,'checkpoints_seconds':[.1,.2],'seeds':[0],
                    'datasets':[{'id':'tiny','source_graph':'tiny','split':'development',
                        'path':'network.json','sha256':file_sha256(self.root/'network.json'),'budgets':[1]}]}
        self.path=self.root/'suite.json';self.path.write_text(json.dumps(self.suite))
        from swarm_location.anytime import score_trace
        events=[[.05,[2]],[.15,[1]]]
        result=score_trace(self.instance,1,[.1,.2],events)
        measured=dict(result,correct=True,events=events)
        self.trace={'stage':'m2_complete','split':'development','protocol':self.suite,
                    'suite_sha256':file_sha256(self.path),'cases':[{'dataset':'tiny','source_graph':'tiny',
                        'k':1,'seed':0,'methods':{'unit_fixture':measured}}]}
        self.tp=self.root/'traces.json'

    def tearDown(self):self.temp.cleanup()

    def run_annotation(self):
        from certify import annotate
        self.tp.write_text(json.dumps(self.trace))
        return annotate(self.path,self.tp,self.root/'sidecar.json')

    def test_records_certified_checkpoint_coverage_without_execution_or_rewriting(self):
        result=self.run_annotation()
        self.assertEqual(result['candidate_executions'],0)
        self.assertEqual(result['trials'][0]['checkpoints'][0]['certificate']['quality_lower_bound_exact'],'1/2')
        self.assertTrue(result['trials'][0]['final']['deployment_optimality_proved'])
        self.assertEqual(json.loads(self.tp.read_text()),self.trace)
        from certify import annotate
        with self.assertRaises(FileExistsError):annotate(self.path,self.tp,self.root/'sidecar.json')

    def test_unmatched_tampered_or_incomplete_source_rejected(self):
        from certify import annotate
        for field,value in [('suite_sha256','0'*64),('split','test'),('stage','m2_in_progress')]:
            bad=dict(self.trace,**{field:value});self.tp.write_text(json.dumps(bad))
            with self.subTest(field=field),self.assertRaises(ValueError):
                annotate(self.path,self.tp,self.root/'sidecar.json')
        self.trace['cases'][0]['methods']['unit_fixture']['coverage_at_checkpoints'][0]=.6
        with self.assertRaises(ValueError):self.run_annotation()

    def test_no_incomplete_or_duplicate_cases(self):
        self.trace['cases']*=2
        with self.assertRaises(ValueError):self.run_annotation()
        self.trace['cases']=[]
        with self.assertRaises(ValueError):self.run_annotation()

    def test_source_family_and_mean_mismatch_rejected(self):
        self.trace['cases'][0]['source_graph']='wrong-family'
        with self.assertRaises(ValueError):self.run_annotation()
        self.trace['cases'][0]['source_graph']='tiny'
        self.trace['cases'][0]['methods']['unit_fixture']['mean_checkpoint_coverage']=.9
        with self.assertRaises(ValueError):self.run_annotation()

    def test_incorrect_trial_is_not_relabelled_certified(self):
        self.trace['cases'][0]['methods']['unit_fixture']['correct']=False
        result=self.run_annotation()
        self.assertEqual(result['trials'][0]['status'],'not_certified_invalid_trial')


if __name__=='__main__':unittest.main()
