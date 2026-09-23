# M4: staged strong-control integration

## Research boundary

This is the integration of the already implemented fixed controls into a new,
explicitly versioned campaign. It is not another solver, a changed coverage
objective, a new traffic model, or evidence that program evolution outperforms
fixed algorithms. The immutable comparison profile is
`configs/comparisons_m4.json` (`m4-staged-controls-v1`); the opt-in native request is
`configs/m4_launch_request.json` (`m4-staged-controls-100-v1`, request schema 2).

The original M1–M3 configurations, data catalog, checkpoints, solver seeds, seed
programs, fixed solvers, execution clock, routing and coverage code are retained.
The old request remains the default for backward compatibility. New M4 runs must
use a new results directory and the explicit request below. Restoring/resuming an
old campaign requires its original code and manifest, not silently upgrading its
evaluation protocol. New evaluator source hashes necessarily differ.

## Research basis and project decisions

| Source | Relevant finding or methodological principle | Consequence here |
|---|---|---|
| Altshuler, Pentland and Bruckstein, *Applied Swarm Intelligence*, §4.7.4, printed pp. 198–200 [1] | Marginal greedy, DFBnB and Potential Search address the same group-coverage placement problem; anytime quality and incumbent/upper-bound certificates matter | Keep chapter-aligned greedy and include both implemented bound-guided controls in assessment |
| Stern, Puzis and Felner (2011) [2] | Potential Search is a bounded-cost search algorithm with an anytime extension | Reuse the repository's documented utility-form adaptation; do not relabel it as recovered author code |
| Beiranvand, Hare and Lucet (2017) [3]; Bartz-Beielstein et al. (2020) [4] | Benchmarking requires suitable algorithms, explicit performance measures, considered experimental design and reproducible reporting | State the comparator sets before execution; retain paired cases, failures and per-checkpoint/final differences |
| Cawley and Talbot (2010) [5] | Optimizing a noisy finite-sample selection criterion can itself induce selection bias | Preserve the development/validation/test separation and frozen shortlist; do not select or tune the fixed control set using test performance |
| Lange, Imajuku and Cetin (2025), §3.3 [6]; native task contract [7] | Scalar fitness, public measurements and textual feedback have distinct roles in program evolution and meta-scratchpad updates | Keep the native scalar score while exposing informative comparisons to stronger controls |

The sources do **not** prescribe our exact four/seven controls, these particular
transportation datasets, a 20 ms checkpoint, or this campaign's monetary threshold.
Those are explicit project choices. This work does not reproduce the book's
Israeli-network numerical results or introduce decentralized robot control.

## Comparator sets

| Fixed control | Development screening | Validation | Test | Reason |
|---|:---:|:---:|:---:|---|
| `greedy` | Yes | Yes | Yes | Chapter-aligned reference and unchanged fitness anchor |
| `greedy_swap` | Yes | Yes | Yes | Continuity with existing local-improvement evidence |
| `topk` | Yes | Yes | Yes | Cheap complete-deployment control |
| `early_celf_swap` | Yes | Yes | Yes | Strong existing early-answer/refinement hybrid |
| `iterated` | No | Yes | Yes | Existing perturbation, descent and restart control |
| `dfbnb` | No | Yes | Yes | Chapter-aligned bound-guided search |
| `potential` | No | Yes | Yes | Documented utility-form anytime Potential Search |

Every listed control receives its own full, identical inner search budget; this
is not a shared portfolio with a divided budget. Method-specific preparation,
warm starts and reporting remain inside the unchanged external clock. The
screening set is chosen using the existing development-only study: it exposes
the early-reporting advantage without repeatedly paying for every tree search or
full-budget iterated search during mutation. Full route greedy/CELF/route-swap
representation ablations remain available in the separate stronger-baseline study.
No new solver or early-answer wrapper is introduced in M4.

With the unchanged source catalog, each development candidate has 24 paired
cases: **96 fixed-control invocations + 24 candidate invocations = 120 trials**.
Each validation candidate and the single test champion has 40 paired cases:
**280 fixed-control invocations + 40 candidate invocations = 320 trials**.
For the maximum six-member shortlist, validation requires up to 1,920 solver
invocations. These counts are not runtime or inference-cost estimates. Compared
with running all seven controls on the same 24 development cases (192 trials),
screening avoids 72 invocations (37.5%). Relative to historical M3's three fixed
controls, development adds one fixed control, not a free comparison.

## Fitness, feedback and interpretation

The scalar remains

    combined_score = 100 + 100 * mean_cases(
        mean_checkpoints(C_candidate) - mean_checkpoints(C_greedy))

Any failed required candidate or control trial makes the evaluation incorrect and
its scalar zero, as before. No successful subset is used to hide failed cases.
Validation still selects the highest direct mean checkpoint coverage, not the
largest difference from a separately retimed baseline. The original seed remains
a no-improvement alternative in the frozen shortlist. Neither the comparison
profile nor an LLM interpretation changes this selection rule.

A common fixed reference is just an additive shift: replacing one constant
reference with another cannot improve ranking. Freshly measured reference times
are not literally a common constant, however, and their noise can affect ranking.
M4 does not calibrate that noise or solve this separate timing issue.

Each M4 evaluation additionally saves `comparisons.json` and an identical
`metrics.json.extra_data.comparisons` object. For each fixed method, the report
contains paired differences in mean checkpoint coverage, final coverage, and
coverage at every checkpoint. Summaries are given overall, per source and per
source/budget; case counts and failed pairs are retained. Invalid comparisons have
no apparently successful delta. Overall checkpoint and final differences are
also exposed as native public metrics. Text feedback identifies each executed
control, separates early and final behavior, and explicitly identifies assessment
methods **not run** in development screening. No result for those methods is
invented or fed back from holdouts.

There is no pointwise maximum across controls presented as an executable baseline,
no average of weak and strong methods presented as the strongest competitor, no
p-value, and no automatic 'discovery' flag. An advantage over greedy alone is
insufficient. A later claim must identify the stronger methods it beats, the
metric, deadline, networks and uncertainty, and demonstrate that the difference
survives the intended repeated, matched-backend assessment. Winning on an early
checkpoint is not automatically better final optimization or better certification.
The existing online bounds are still emitted only by the trusted fixed methods;
candidate bound reporting is not added here.

## Implementation path and integrity

`prepare_research.prepare(..., comparison_profile=...)` embeds the complete
profile, its canonical-definition digest, original file digest and stage into the
suite. Prepared network bytes, dataset hashes, OD demand, budgets and seeds are
unchanged by choosing a profile. `extra_baselines` must agree with the embedded
stage. Unknown/duplicate controls, missing original references, inconsistent
validation/test sets and stale digests fail before solver work. A prepared suite
cannot be silently downgraded to the legacy comparator set.

`campaign.py` reads a schema-2 request explicitly, records the profile and trial
plan before inference, and uses the same profile through all three preparation
calls. A change to its file is detected before entering a later stage.
`run_evo.py` records the screening plan and appends the named screening/assessment
controls to the native task message. The framework pin, island configuration,
mutation-model UCB, inspirations, crossover, novelty and separate meta-model
configuration are unchanged. No new evolutionary loop is introduced.

`selection.py` requires versioned comparison evidence when using a versioned
suite. Cached validation evidence cannot omit a required control or use another
profile. The champion records its validation comparison identity; a test suite
with a different assessment profile is rejected before the one-time test-open
marker is created. Legacy suites keep their earlier compatibility path.

## Execution and recorded evidence

The standalone unit tests include real workers on explicitly labelled synthetic
three-node fixtures, all three stage routes, failure injection, unchanged fitness
arithmetic, default-M3 behavior, native-plan propagation, and shortlist/champion
checks. Those fixtures are **not research holdout results or evolved programs**.

The dedicated `Staged comparator integration` workflow runs the full test suite,
checks protected historical bytes, installs the pinned native framework and runs
its unchanged greedy seed on the two development networks under Docker. It then
independently replays the saved deployments and comparison arithmetic. It has no
model credentials and no step that launches paid evolution or scores a research
validation/test network. Measured evidence is in README §5.6 and
`results/step4/integration/`; planned trial counts above are not substituted for
executed counts.

Prepare development data and inspect the native plan without model calls:

```bash
python scripts/prepare_research.py --split development --download \
  --comparison-profile configs/comparisons_m4.json --output data/commissioning_m4
python run_evo.py --config configs/evolution_m3.json \
  --suite data/commissioning_m4/suite.json --results-dir results/local_m4_plan
```

For a later explicitly authorized native campaign, using a resolved immutable
image ID and credentials in the execution environment:

```bash
python campaign.py --request configs/m4_launch_request.json \
  --execute --download --docker-image "$IMAGE_ID" \
  --output results/local_m4_campaign
```

The copied model pool, 100-slot target and $3 submission threshold are unchanged
from M3. This integration neither authorizes a run nor establishes that the
threshold can fund the intended search effort. Resume requires matching original
manifests. Docker timing calibration, changes to the initial-answer policy,
additional source families, repeated evolutionary campaigns and prompt
co-evolution are separate follow-on work, not silently bundled into Priority 1.

## References

1. Y. Altshuler, A. Pentland and A. M. Bruckstein. Chapter 4, especially §4.7.4, in Y. Altshuler (ed.), *Applied Swarm Intelligence*, CRC Press, first edition 2025. https://doi.org/10.1201/9780429276378. Supplied book consulted; not redistributed.
2. R. Stern, R. Puzis and A. Felner. *Potential Search: A Bounded-Cost Search Algorithm*. ICAPS 21(1), 234–241, 2011. https://doi.org/10.1609/icaps.v21i1.13455. Implementation mapping remains in `strong_baselines.md`.
3. V. Beiranvand, W. Hare and Y. Lucet. *Best practices for comparing optimization algorithms*. Optimization and Engineering 18, 815–848, 2017. https://doi.org/10.1007/s11081-017-9366-1.
4. T. Bartz-Beielstein et al. *Benchmarking in Optimization: Best Practice and Open Issues*. 2020. https://arxiv.org/abs/2007.03488.
5. G. C. Cawley and N. L. C. Talbot. *On Over-fitting in Model Selection and Subsequent Selection Bias in Performance Evaluation*. JMLR 11, 2079–2107, 2010. https://jmlr.org/papers/v11/cawley10a.html.
6. R. T. Lange, Y. Imajuku and E. Cetin. *ShinkaEvolve: Towards Open-Ended And Sample-Efficient Program Evolution*. 2025, §3.3. https://arxiv.org/html/2509.19349v1.
7. SakanaAI. *ShinkaEvolve: Core Concepts*, task contract, execution/world feedback and runtime separation. https://sakanaai.github.io/ShinkaEvolve/core_concepts/. Consulted 2026-09-23; the executable framework remains pinned to `9912af12d423504b8d580f4179fd15f5f88b8c50`, not to the moving documentation.
