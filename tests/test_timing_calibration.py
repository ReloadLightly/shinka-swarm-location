"""Synthetic statistics/scheduling tests; not research timing or holdout results."""
from copy import deepcopy
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from swarm_location.timing_calibration import (NULL_ROLES, CONTROL_NAMES, make_schedule, checked_config,
    null_analysis, control_analysis, mean_curves, empirical_guard, promotion_decision, describe)

ROOT=Path(__file__).resolve().parents[1]
CONFIG=json.loads((ROOT/'configs/timing_m5.json').read_text())
SUITE={'checkpoints_seconds':[0.02,0.1,0.5,2.0], 'seeds':[0,1,2],
       'datasets':[{'id':'fixture-A','split':'development','budgets':[1,2]},
                   {'id':'fixture-B','split':'development','budgets':[1,2]}]}


def records():
    result=[]
    for item in make_schedule(CONFIG,SUITE):
        repeat=item['repeat']
        offset={'candidate_a':.02,'candidate_b':0.,'greedy_a':-.01,'greedy_b':0.,
                'early_a':.01,'early_b':0.}.get(item['role'],0)
        coverage=.4+repeat*.001+offset
        trial={'mean_checkpoint_coverage':coverage,'final_coverage':coverage,
               'coverage_at_checkpoints':[coverage]*4, 'setup_wall_seconds':.1,
               'termination':'completed', 'improvements':[{'received_seconds':0.,'coverage':0.,'selected':[]},
                   {'received_seconds':.01,'coverage':coverage,'selected':[1]}]}
        result.append({**item, 'result':trial, 'wall_seconds':.3})
    return result


class ScheduleTests(unittest.TestCase):
    def test_full_schedule_deterministic_counts_unique_slots(self):
        a=make_schedule(CONFIG,SUITE)
        self.assertEqual(a,make_schedule(CONFIG,SUITE))
        self.assertEqual(len(a),12*12*6+5*12*8)
        self.assertEqual([x['index'] for x in a],list(range(len(a))))
        self.assertEqual(len({(r['phase'],r['repeat'],r['dataset'],r['k'],r['seed'],r['role']) for r in a}),len(a))

    def test_pairs_execute_same_code_path_and_algorithm_seed(self):
        schedule=make_schedule(CONFIG,SUITE)
        for a,b in [('candidate_a','candidate_b'),('greedy_a','greedy_b'),('early_a','early_b')]:
            x=next(r for r in schedule if r['phase']=='null' and r['role']==a)
            y=next(r for r in schedule if r['phase']=='null' and r['repeat']==x['repeat'] and
                   r['dataset']==x['dataset'] and r['k']==x['k'] and r['seed']==x['seed'] and r['role']==b)
            self.assertEqual(x['baseline'],y['baseline'])
            self.assertEqual(x['seed'],y['seed'])

    def test_mirrored_role_and_case_order(self):
        schedule=make_schedule(CONFIG,SUITE)
        for phase in ('null','controls'):
            a=[r for r in schedule if r['phase']==phase and r['repeat']==0]
            b=[r for r in schedule if r['phase']==phase and r['repeat']==1]
            fields=lambda r:(r['dataset'],r['k'],r['seed'],r['role'])
            self.assertEqual(list(map(fields,a)),list(reversed(list(map(fields,b)))))

    def test_no_holdout_or_changed_primary_checkpoint(self):
        for partition in ('validation','test'):
            changed=deepcopy(SUITE);changed['datasets'][1]['split']=partition
            with self.assertRaises(ValueError):make_schedule(CONFIG,changed)
        changed=deepcopy(SUITE);changed['checkpoints_seconds'][-1]=10
        with self.assertRaises(ValueError):make_schedule(CONFIG,changed)

    def test_missing_controls_bad_repeats_padding_or_longer_budget_fail(self):
        for key,value in [('controls',['greedy']),('null_repeats',True),('control_repeats',0),
                          ('screening_floor_pp',float('nan')),('screening_padding_pp',-1),
                          ('longer_budget_assessment',10)]:
            changed=deepcopy(CONFIG);changed[key]=value
            with self.assertRaises(ValueError):checked_config(changed)


class StatisticsTests(unittest.TestCase):
    def setUp(self):self.records=records()

    def test_fresh_reference_contribution_not_cancelled(self):
        rows=null_analysis(self.records,SUITE['checkpoints_seconds'])
        values={r['probe']:r for r in rows if r['scope']=='overall' and r['metric']=='checkpoint_mean'}
        self.assertAlmostEqual(values['identical_candidate']['mean'],2.)
        self.assertAlmostEqual(values['identical_fixed_greedy']['mean'],-1.)
        self.assertAlmostEqual(values['refreshed_fitness_difference']['mean'],3.)
        self.assertAlmostEqual(values['candidate_minus_fixed_greedy_a']['mean'],3.)
        self.assertEqual(values['identical_candidate']['n_blocks'],12)  # NOT 144 cases or 576 checkpoints

    def test_guard_is_envelope_plus_declared_margin_not_significance(self):
        rows=null_analysis(self.records,SUITE['checkpoints_seconds'])
        guard=empirical_guard(rows,CONFIG)
        self.assertGreaterEqual(guard['threshold_pp'],3.05)
        self.assertLessEqual(guard['threshold_pp'],3.06)  # conservative upward rounding
        self.assertIn('NOT a confidence',guard['interpretation'])
        self.assertEqual(guard['confirmation_repeats'],5)

    def test_incomplete_probe_report_cannot_form_guard(self):
        rows=null_analysis(self.records,SUITE['checkpoints_seconds'])
        rows=[r for r in rows if r['probe']!='identical_early_hybrid']
        with self.assertRaises(ValueError):empirical_guard(rows,CONFIG)

    def test_early_and_final_are_separate(self):
        for r in self.records:
            if r['role']=='candidate_a':r['result']['final_coverage']=.4
            if r['role']=='candidate_b':r['result']['final_coverage']=.4
        rows=null_analysis(self.records,SUITE['checkpoints_seconds'])
        x=next(r for r in rows if r['scope']=='overall' and r['metric']=='final' and r['probe']=='identical_candidate')
        self.assertEqual(x['max_absolute'],0.)

    def test_strong_control_full_blocks_not_pseudo_replicates(self):
        rows=control_analysis(self.records,SUITE['checkpoints_seconds'])
        x=next(r for r in rows if r['scope']=='overall' and r['method']=='potential')
        self.assertEqual(x['trials'],60)
        self.assertEqual(x['checkpoint_mean_pct']['n_blocks'],5)
        self.assertEqual(len(x['coverage_at_checkpoints_pct']),4)
        self.assertIn('fixture-A/k=1',{r['scope'] for r in rows})

    def test_exact_mean_step_curve_matches_checkpoint_mean(self):
        curves=mean_curves(self.records,SUITE['checkpoints_seconds'])
        row=next(r for r in curves if r['scope']=='overall' and r['method']=='greedy')
        pts=row['points_seconds_coverage_pct']
        self.assertEqual(pts[0],[0.,0.])
        self.assertEqual(pts[1][0],.01)
        self.assertEqual(pts[-1][0],2.)
        summary=next(r for r in control_analysis(self.records,SUITE['checkpoints_seconds'])
                     if r['scope']=='overall' and r['method']=='greedy')
        self.assertAlmostEqual(pts[-1][1],summary['final_pct']['mean'])

    def test_finite_statistics_required(self):
        for values in ([],[float('nan')],[float('inf')]):
            with self.assertRaises(ValueError):describe(values)


class PromotionTests(unittest.TestCase):
    def test_greedy_only_improvement_is_not_enough(self):
        self.assertFalse(promotion_decision({'greedy':10.,'early_celf_swap':-.1},.2)['promote_to_confirmation'])

    def test_strict_threshold_never_claims_discovery(self):
        self.assertFalse(promotion_decision({'greedy':.2,'early_celf_swap':.3},.2)['promote_to_confirmation'])
        d=promotion_decision({'greedy':.21,'early_celf_swap':.3},.2)
        self.assertTrue(d['promote_to_confirmation']);self.assertFalse(d['discovery_established'])

    def test_missing_nonfinite_or_negative_guard_rejected(self):
        for d,t in [({'greedy':1.},.2),({'greedy':float('inf'),'early_celf_swap':1.},.2),
                    ({'greedy':1.,'early_celf_swap':1.},-.2)]:
            with self.assertRaises(ValueError):promotion_decision(d,t)

    def test_process_backend_never_substituted_for_docker(self):
        spec=importlib.util.spec_from_file_location('calibrate_timing',ROOT/'scripts/calibrate_timing.py')
        mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
        with patch.object(mod,'command',return_value=(['python'],None,{'mode':'process'})):
            with self.assertRaisesRegex(ValueError,'process-backend'):mod.probe_executor()


if __name__=='__main__':unittest.main()
