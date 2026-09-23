"""M6 paired-control contract tests. Synthetic cases are not research holdouts."""
from copy import deepcopy
from fractions import Fraction
from itertools import combinations
from pathlib import Path
import types
import unittest
from unittest.mock import patch

from test_strong_baselines import problem, Recorder
from swarm_location import strong_baselines as strong
from swarm_location.route_search import RouteSearch, SearchDeadline, RouteLimit
from swarm_location.bounded_search import PartitionSearch
from swarm_location.certificates import ExactCoverage
from swarm_location.baseline_proofs import verify_online_bounds
from swarm_location.anytime import run_anytime
from swarm_location.comparisons import load_profile, bind_profile, evaluation_methods

ROOT = Path(__file__).resolve().parents[1]


class EarlyControlTests(unittest.TestCase):
    def test_registry_maps_to_existing_search_modes(self):
        self.assertEqual(strong.EARLY_PARENTS, {'early_iterated':'iterated',
            'early_dfbnb':'dfbnb','early_potential':'potential'})
        self.assertTrue({'early_dfbnb','early_potential'} <= set(strong.BOUND_METHODS))

    def test_complete_singleton_prefix_precedes_representation_and_uses_same_deadline(self):
        p = problem(); k = 3
        gains = p.marginal_gains([])
        expected = sorted(gains, key=lambda v:(-gains[v],v))[:k]
        for name in strong.EARLY_PARENTS:
            r = Recorder()
            def delayed_build(problem, *, deadline, max_routes):
                self.assertEqual(r.groups, [[],expected])
                self.assertEqual(deadline, 12.0)  # not a new deadline after prefix
                raise SearchDeadline()
            with patch.object(strong,'perf_counter',side_effect=[10.,11.,11.5]), \
                    patch.object(strong,'check_time'), patch.object(strong,'RouteSearch',side_effect=delayed_build):
                result = strong.solve(p,k,0,r,2.,name)
            self.assertEqual(result,expected)
            self.assertEqual(r.stats[-1]['method'],name)

    def test_legacy_methods_do_not_acquire_the_prefix(self):
        for name in ('iterated','dfbnb','potential'):
            r = Recorder()
            with patch.object(strong,'RouteSearch',side_effect=SearchDeadline()):
                result = strong.solve(problem(),3,0,r,2.,name)
            self.assertEqual(r.groups,[[]]); self.assertEqual(result,[])

    def test_zero_time_does_not_grant_free_initialization(self):
        for name in strong.EARLY_PARENTS:
            p=problem();r=Recorder()
            with patch.object(strong,'check_time',side_effect=SearchDeadline()), \
                    patch.object(p,'marginal_gains',side_effect=AssertionError('free prefix')):
                strong.solve(p,3,0,r,0.,name)
            self.assertEqual(r.groups,[[]])

    def test_zero_monitor_budget_has_valid_empty_answer_and_bound(self):
        for name in strong.EARLY_PARENTS:
            p=problem();r=Recorder()
            self.assertEqual(strong.solve(p,0,0,r,1.,name),[])
            if name in strong.BOUND_METHODS:
                self.assertEqual(verify_online_bounds(p.instance,0,r.bounds)[-1]['upper_exact'],'0')

    def test_worse_later_warm_start_cannot_discard_early_incumbent(self):
        for name in strong.EARLY_PARENTS:
            p=problem();k=3;r=Recorder();seen=[]
            real=PartitionSearch
            def tree(route,k,initial,mode):
                seen.append(tuple(initial))
                return real(route,k,initial,mode,max_splits=0)
            with patch.object(strong,'greedy',return_value=((),{})), \
                    patch.object(strong,'descent',return_value=((),0)), \
                    patch('swarm_location.bounded_search.PartitionSearch',side_effect=tree):
                result=strong.solve(p,k,0,r,10.,name,max_cycles=0)
            expected=r.groups[1]
            self.assertEqual(set(result),set(expected))
            if seen:
                self.assertEqual(set(RouteSearch(p).ids(seen[0])),set(expected))
                verified=verify_online_bounds(p.instance,k,r.bounds)
                self.assertGreaterEqual(Fraction(verified[-1]['upper_exact']),ExactCoverage(p.instance).score(expected))

    def test_exact_small_instances_and_best_so_far_reports(self):
        for seed in range(5):
            p=problem(seed);exact=ExactCoverage(p.instance)
            for k in (1,3,7):
                optimum=max(exact.score(s) for s in combinations(p.nodes,k))
                for name in strong.EARLY_PARENTS:
                    r=Recorder();result=strong.solve(p,k,seed,r,1e6,name,max_cycles=3)
                    values=[exact.score(s) for s in r.groups]
                    self.assertEqual(values,sorted(values))
                    self.assertEqual(exact.score(result),max(values))
                    if name in strong.BOUND_METHODS:
                        self.assertEqual(exact.score(result),optimum)
                        v=verify_online_bounds(p.instance,k,r.bounds)
                        self.assertEqual(Fraction(v[-1]['upper_exact']),optimum)
                        self.assertTrue(v[-1]['optimality_proved'])

    def test_route_guard_fallback_preserves_prefix(self):
        for name in strong.EARLY_PARENTS:
            p=problem();r=Recorder()
            result=strong.solve(p,3,0,r,10.,name,route_limit=1,max_cycles=0)
            self.assertTrue(r.stats[-1]['fallback'])
            self.assertGreaterEqual(p.score(result),p.score(r.groups[1]))

    def test_legacy_search_trajectories_match_frozen_m5_code_at_fixed_work(self):
        old=types.ModuleType('swarm_location._m5_fixture')
        old.__package__='swarm_location'
        exec(compile((ROOT/'tests/fixtures/strong_baselines_m5.py').read_text(),
                     'strong_baselines_m5.py','exec'),old.__dict__)
        for seed in range(3):
            for name in old.METHODS:
                a,b=Recorder(),Recorder()
                result_a=old.solve(problem(seed),3,seed,a,1e6,name,max_cycles=2)
                result_b=strong.solve(problem(seed),3,seed,b,1e6,name,max_cycles=2)
                self.assertEqual(result_a,result_b)
                self.assertEqual(a.groups,b.groups)
                self.assertEqual(a.bounds,b.bounds)
                strip=lambda d:{k:v for k,v in d.items() if not k.endswith('seconds')}
                self.assertEqual([strip(d) for d in a.stats],[strip(d) for d in b.stats])

    def test_real_external_workers_accept_all_new_controls_and_verify_bounds(self):
        p=problem()
        for name in strong.EARLY_PARENTS:
            r=run_anytime(p.instance,3,[.1,.3],baseline=name,seed=0)
            self.assertTrue(r['correct'],r['error'])
            self.assertEqual(r['coverage_at_checkpoints'],sorted(r['coverage_at_checkpoints']))
            if name in strong.BOUND_METHODS:self.assertTrue(r['verified_search_bounds'])

    def test_m6_profile_is_opt_in_and_all_assessment_controls_propagate(self):
        legacy=load_profile(ROOT/'configs/comparisons_m4.json')
        new=load_profile(ROOT/'configs/comparisons_m6.json')
        self.assertEqual(legacy['definition']['baseline_sets']['development'],
                         new['definition']['baseline_sets']['development'])
        for stage in ('development','validation','test'):
            p=bind_profile({},new,stage)
            methods=evaluation_methods(p,stage)
            self.assertEqual(len(methods),5 if stage=='development' else 11)
            self.assertEqual(set(strong.EARLY_PARENTS) & set(methods),
                             set() if stage=='development' else set(strong.EARLY_PARENTS))
        self.assertEqual(len(legacy['definition']['baseline_sets']['test']),7)



class PairedStudyTests(unittest.TestCase):
    def config_suite(self):
        import json
        config=json.loads((ROOT/'configs/early_controls_m6.json').read_text())
        suite={'checkpoints_seconds':[.02,.1,.5,2.],'seeds':[0,1],
               'datasets':[{'id':'synthetic','split':'development','budgets':[1,2]}]}
        return config,suite

    def test_schedule_is_complete_unique_and_counterbalanced(self):
        from scripts.early_control_study import schedule
        config,suite=self.config_suite();plan=schedule(config,suite)
        self.assertEqual(plan,schedule(config,suite))
        self.assertEqual(len(plan),6*4*9)
        self.assertEqual(len({(r['repeat'],r['dataset'],r['k'],r['seed'],r['role']) for r in plan}),len(plan))
        for pair in (0,2,4):
            a=[(r['dataset'],r['k'],r['seed'],r['role']) for r in plan if r['repeat']==pair]
            b=[(r['dataset'],r['k'],r['seed'],r['role']) for r in plan if r['repeat']==pair+1]
            self.assertEqual(a,b[::-1])

    def test_holdout_changed_deadline_or_missing_parent_is_rejected(self):
        from scripts.early_control_study import schedule
        c,s=self.config_suite()
        for key,value in [('methods',[]),('repeats',3),('longer_budget_assessment',10)]:
            bad=deepcopy(c);bad[key]=value
            with self.assertRaises(ValueError):schedule(bad,s)
        s['datasets'][0]['split']='test'
        with self.assertRaises(ValueError):schedule(c,s)

    def test_paired_arithmetic_preserves_early_final_and_negative_differences(self):
        from scripts.early_control_study import summarize,METHODS
        rows=[]
        for rep in range(2):
            for role in METHODS+['early_celf_swap_duplicate']:
                early=role in strong.EARLY_PARENTS
                scores=[.5,.6,.6,.6] if early else [0,.7,.7,.7]
                rows.append({'dataset':'synthetic','k':1,'seed':0,'repeat':rep,'role':role,
                    'result':{'mean_checkpoint_coverage':sum(scores)/4,'final_coverage':scores[-1],
                    'coverage_at_checkpoints':scores,'events':[[.01 if early else .03,[0]]],
                    'improvements':[{'received_seconds':0,'coverage':0},{'received_seconds':.01,'coverage':scores[-1]}]}})
        _,pairs,_=summarize(rows,[.02,.1,.5,2.])
        row=next(r for r in pairs if r['scope']=='overall' and r['early']=='early_iterated')
        self.assertAlmostEqual(row['metrics']['checkpoint_mean']['mean'],5.)
        self.assertAlmostEqual(row['metrics']['final']['mean'],-10.)
        self.assertEqual(row['metrics']['checkpoint_mean']['n_blocks'],2)

if __name__=='__main__': unittest.main()
