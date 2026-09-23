# Shinka Swarm Location
## A chapter-grounded benchmark for evolving network-monitor deployment algorithms

**Status: M3 campaign remains `blocked_model_access`; quality certificates implemented and locally verified. See Sections 5.2–5.3.**

### Abstract

This project investigates whether LLM-guided program evolution can improve the
quality-runtime trade-off of network-monitor placement. Its mathematical starting
point is Chapter 4 of *Applied Swarm Intelligence*, especially Section 4.7.4 [1].
The intended evolving object is a reusable search procedure that selects monitoring
locations on a directed transportation network, rather than a fixed deployment or
a drone flight controller. The first milestone implements endpoint-inclusive,
origin-destination-weighted group coverage, marginal-greedy deployment, comparison
algorithms, independent scoring, and an offline evaluation entrypoint. A documented
Sioux Falls benchmark substitution [3] establishes a working reference result. A
fixed one-for-one swap procedure improves on greedy at several monitor budgets;
for three and four monitors it matches exhaustive enumeration. These are baseline
results, not evidence of evolutionary improvement or large-scale generalization.

M2 adds an all-node marginal-gain backend that does not enumerate routes, externally
timed incumbent reporting, a hash-verified two-network development suite, strong
same-budget controls, and a launcher using the pinned native ShinkaEvolve runner.
The model remains fixed-route group coverage. Evidence is reported separately
from the untouched historical M1 calculations; no LLM-generated discovery is claimed.

| Research component | Current evidence |
|---|---|
| Chapter-grounded coverage objective and marginal greedy | Implemented; source deviations documented |
| Directed, tied-shortest-path, endpoint-inclusive evaluator | Implemented and cross-checked |
| Baseline results on a pinned public debugging network | Executed; artifacts committed |
| Local M1 seed-program evaluator | Executed; seed equals reference greedy |
| Native `run_shinka_eval` adapter | Subsequently executed in M2 commissioning; no model calls |
| Independent anytime worker / fast DAG gains | Implemented; M2 checks and measured results below |
| Native scheduler and full-run configuration | Seed path checked separately from unexecuted paid evolution |
| Coverage + verified quality certificates | Implemented separately; see Section 5.3 |
| LLM-generated descendants / evolutionary runs | **0 / 0** |
| Original Israeli-network numerical reproduction | Original code/data not recovered |
| Matched-time comparison | Two development networks; no validation/test result |

## 1. Research question

> Can ShinkaEvolve discover a reusable anytime search procedure that achieves
> greater covered OD demand, or comparable coverage sooner, than strong fixed
> deployment algorithms on previously unseen transportation-network instances?

The intended outer search evolves algorithms. Each candidate's inner search selects
monitor locations. A future champion is therefore executable deployment-search
code, not a particular junction set, an individual drone, or an evolved road graph.
The current milestone establishes the task and reference algorithms before testing
this research question. It does not claim a novel algorithm.

## 2. Mathematical model and source fidelity

Let $G=(V,E)$ be a directed graph with positive edge costs and let $D_{st}$ denote
nonnegative origin-destination demand. Let $\sigma_{st}$ be the number of shortest
routes from $s$ to $t$, and $\sigma_{st}(S)$ the number encountering at least one
monitor in $S\subseteq V$. The deployment objective is

$$
C(S)=\frac{\sum_{s,t}D_{st}\,\sigma_{st}(S)/\sigma_{st}}
{\sum_{s,t}D_{st}},\qquad |S|\leq k.
$$

A route is counted once even if it encounters several monitors. Origins and
destinations count as monitoring opportunities, following Section 4.7.1 [1].
For each OD pair, demand is distributed uniformly over all equally short routes.
That is a modeling convention, not measured route-choice behavior.

**Explicit emendation.** The printed Equation 4.15 on p. 198 inverts the route
fraction. This implementation uses covered routes divided by total routes,
consistent with the surrounding definition. The correction is documented; it is
not presented as author-confirmed errata. Further Gompertz discrepancies are
recorded in [the source-fidelity note](docs/source_fidelity.md), but Gompertz curves
and the economic fleet-size model are not used as fitness in this milestone.

Monitor placement does **not** delete junctions or change routes. Recomputing
shortest paths after removing monitors would evaluate a different problem.
No drone kinematics, decentralized sensing, threat pursuit, or real-world detection
outcome is modeled here. Equal fixed monitor quality and a fixed location budget
isolate the placement problem.

## 3. Data and implementation

### 3.1 M1 commissioning dataset

| Property | Value |
|---|---:|
| Benchmark | Sioux Falls, free-flow routing |
| Nodes / eligible locations | 24 |
| Directed edges | 76 |
| Positive OD pairs | 528 |
| Total supplied OD demand | 360,600 |
| Exactly shortest routes across positive OD pairs | 564 |
| Distinct node-set route masks after exact aggregation | 282 |
| Monitor budgets | 1 through 8 |

Upstream commit: `977ee75c6906337c0c7d229a1336107c7cdb533e`.
Both source TNTP files were verified against their upstream Git blob hashes. The
conversion script preserves free-flow edge costs, positive OD entries, directed
links, and TNTP centroid-through restrictions. The committed fixture and each
result carry provenance or content hashes. See [data provenance](data/README.md).

**This is a substitution, not the chapter's empirical dataset.** Its maintainers
explicitly describe Sioux Falls as a debugging network that is not realistic [3].
The results do not establish contemporary traffic conditions or large-scale
infrastructure performance. None of this network is held out from development.

### 3.2 Coverage calculation

`ShortestPathCoverage` builds a shortest-path directed acyclic graph for each
positive-demand origin. It counts original shortest routes that avoid the
monitored set and subtracts that count from the total. Rational arithmetic
(`Fraction`) decides edge-distance ties; integer arithmetic counts paths. Demand
aggregation and reported coverage use double precision.

For this small benchmark, `compile_routes()` also produces an equivalent weighted
route-mask representation. This enumerates **all** shortest routes, never a sample,
and fails explicitly above a configurable route-count limit. The independent
DAG scorer recalculates candidate coverage. M1's route-mask path is retained for
historical reproduction. M2 uses the DAG backend without route enumeration; this
does not establish scaling to arbitrary large networks.

### 3.3 Reference algorithms

| Algorithm | Method | Relationship to chapter |
|---|---|---|
| Random | Uniformly choose $k$ distinct locations | Random deployment reference |
| Individual BC | Rank singleton OD-weighted, endpoint-inclusive coverage | Individual-centrality comparison under the fixed routing model |
| Greedy GBC | Repeatedly maximize marginal group coverage | Section 4.7.4 rule |
| Greedy + swap | Greedy followed by improving best one-for-one exchanges | Additional fixed control, not a chapter algorithm |
| Exhaustive | Score every size-$k$ subset | Small-instance reference; not DFBnB or Potential Search |

Greedy ties use the smallest node ID. Swap accepts coverage gains exceeding
$10^{-12}$. Exhaustive search is run only for $k=1,2,3,4$, checking respectively
24, 276, 2,024, and 10,626 groups. Reported optima are exhaustive best values under
the specified model and numerical scoring, not general guarantees for other data.

## 4. Historical M1 experimental protocol

The commissioning comparison uses the fixed unperturbed fixture, all eight monitor
budgets, and 100 independent pseudorandom seeds (0-99) for random deployment at
each budget. Deterministic algorithms are run once per budget. Random mean and
sample standard deviation describe variation between deployments of this same
network; they are not cross-network confidence intervals. Per-seed coverage values
are preserved in `results/step1/random_coverages.json`.

Deterministic solver timings are recorded for transparency, with shared
preprocessing reported separately. They are single descriptive measurements,
**not** a matched-runtime, anytime, or hardware-normalized comparison. The swap
algorithm receives more computation than greedy in this baseline run.

`evaluate.py` separately executes the reviewed `initial.py` seed in a local child
process for each budget, validates returned node IDs and cardinality, and computes
coverage in the parent. Candidate-reported scores are never accepted. Invalid
runs overwrite any stale success artifacts with a failure record.

The historical M1 commissioning fitness is simply

$$
F_{\mathrm{step1}}(A)=\frac{100}{8}\sum_{k=1}^{8} C(S_A(k)).
$$

It is explicitly **not** the multi-network anytime research fitness.

## 5. Historical M1 measured results

<!-- RESULTS-TABLE:START -->

| Monitors | Random mean +/- SD (%) | Individual BC (%) | Greedy GBC (%) | Greedy + swap (%) | Exact optimum (%) |
|---:|---:|---:|---:|---:|---:|
| 1 | 14.1409 +/- 6.8813 | 34.0821 | 34.0821 | 34.0821 | 34.0821 |
| 2 | 28.1061 +/- 9.5055 | 49.1126 | 50.9151 | 50.9151 | 50.9151 |
| 3 | 38.3775 +/- 10.0760 | 62.0078 | 64.5036 | 66.9163 | 66.9163 |
| 4 | 47.8939 +/- 10.1784 | 69.4121 | 73.4332 | 74.6811 | 74.6811 |
| 5 | 56.4010 +/- 10.4239 | 76.8719 | 80.2551 | 81.4199 | Not computed |
| 6 | 63.3441 +/- 9.6615 | 78.7576 | 85.8014 | 86.9662 | Not computed |
| 7 | 69.5695 +/- 9.0743 | 79.4232 | 91.0704 | 91.0704 | Not computed |
| 8 | 75.4053 +/- 8.5999 | 86.2451 | 93.8991 | 94.2318 | Not computed |

<!-- RESULTS-TABLE:END -->

The seed's mean coverage over the eight budgets is **71.745008%**, with **0.000000
percentage-point difference** from reference greedy, as expected from the same
selection rule. For three monitors, fixed swap improves coverage from **64.5036%**
to **66.9163%** and matches exhaustive enumeration. For four monitors it likewise
matches the computed optimum. These observations show a greedy gap on this
benchmark, but also show that a straightforward fixed improvement procedure can
close it. Any later evolutionary claim must compare against that stronger control,
not only against random placement or plain greedy.

**No ShinkaEvolve improvement is claimed.** No LLM calls, evolved descendants,
train/validation/test selection, or held-out champion evaluations occurred.

### Evidence files

- [Baseline measurements and source hashes](results/step1/baselines.json)
- [Random-deployment per-seed coverage](results/step1/random_coverages.json)
- [Seed metrics](results/step1/seed/metrics.json) and [correctness record](results/step1/seed/correct.json)
- [Local test transcript](results/step1/tests.txt)

The local M1 suite passed **23 tests** on Python **3.13.5**. It includes independent
all-simple-path enumeration on 10 small directed graphs, comparing both backends
on all 64 monitoring subsets per graph. Other checks cover decimal ties, unequal
branching with uniform route weighting, endpoints, overlap, no rerouting,
centroid restrictions, invalid outputs, and a compact DAG with $2^{26}$ shortest
routes. Passing these checks supports implementation correctness for the tested
cases, not empirical validity of the transportation assumptions.

## 5.1 M2 anytime method and executed evidence

The new candidate contract is `solve(problem, k, random_seed, report, time_budget)`
in [`anytime_initial.py`](anytime_initial.py). A candidate evolves its deployment
search; it does not evolve the graph, routing, coverage measure, or evaluation clock.
[`SearchProblem`](swarm_location/search.py) computes all marginal gains in two
passes over each original shortest-path DAG. It uses no route sampling or route
enumeration. The original M1 avoiding-path scorer independently checks submitted
deployments. The derivation, arithmetic assumptions, timing semantics, and research
sources are in [the M2 methods note](docs/m2_method.md).

A parent process starts the search clock after common fixed DAG preprocessing,
before candidate import. It stamps each complete received incumbent, kills the
process group at the deadline, and retains the best valid earlier submission.
Partial groups are allowed under the same `|S| <= k` constraint. Scoring is deferred
until capture finishes; candidate-reported scores and timestamps are rejected.
This is a **warm prepared-problem** comparison, not an end-to-end latency claim.
Common startup/preprocessing is recorded separately.

The pinned public development suite contains Sioux Falls (24 nodes, 76 directed
links) and Anaheim's historical 1992 network (416 nodes, 914 directed links).
Sioux Falls budgets are 1, 3, 4, 6; Anaheim budgets are 3, 6, 12, 24. Each uses
seeds 0, 1, 2 and checkpoints 0.02, 0.10, 0.50, 2.00 seconds: **24 paired cases**.
The parser preserves positive demands, exact free-flow edge weights, and centroid
through-node restrictions, verifying original Git hashes and prepared-data SHA-256.
**Neither network is held out.** A suite can declare whole-source-graph partitions;
relabelled or perturbed copies must retain their source identity.

The research statistic is mean checkpoint improvement over same-budget greedy,
in percentage points. Native `combined_score` is `100 + improvement`; the +100 is
an affine shift, not a second objective. Fixed greedy+swap is also reported. Any
candidate or reference failure invalidates that evaluation instead of being omitted.
Identical-rule seed and greedy runs can differ at early checkpoints due to imports,
OS scheduling and message-receipt jitter. Tiny timing differences are not discovery.

<!-- M2-RESULTS:START -->

| Development dataset | Method | Mean checkpoint coverage (%) | Mean final coverage (%) |
|---|---|---:|---:|
| Anaheim | greedy | 63.3847 | 79.9092 |
| Anaheim | greedy_swap | 63.3849 | 79.9100 |
| Anaheim | random | 33.6964 | 33.6964 |
| Anaheim | topk | 69.8779 | 69.8779 |
| SiouxFalls | greedy | 64.4551 | 64.4551 |
| SiouxFalls | greedy_swap | 65.6614 | 65.6614 |
| SiouxFalls | random | 32.6724 | 32.6724 |
| SiouxFalls | topk | 61.0649 | 61.0649 |

| Dataset | Reference gain pass (median ms) | Reverse-dependency pass (median ms) | Speed ratio | Max. absolute difference |
|---|---:|---:|---:|---:|
| SiouxFalls | 7.6442 | 0.4874 | 15.68x | 0 |
| Anaheim | 2568.0292 | 12.9373 | 198.50x | 2.78e-17 |

**Executed evidence:** 47 tests passed; 24 paired cases; 2 development source networks; zero failed baseline trials. Native seed correctness: `True`; native score: `100.231474`. The native score includes a +100 affine offset; its checkpoint difference can vary with timing.

[Protocol and raw baseline trajectories](results/step2/ci/baselines/traces.json), [baseline metrics](results/step2/ci/baselines/metrics.json), [native integration record](results/step2/ci/native/native_seed_check.json), [native seed metrics](results/step2/ci/native/seed/metrics.json), [gain-pass timings](results/step2/ci/marginals.json), and [tests](results/step2/ci/tests.txt).

These are fixed-baseline and reviewed-seed calculations, not evolved results. The gain-pass comparison uses three alternating-order measurements at the empty selection; its speed ratio is not an end-to-end algorithm speedup. The tables average budgets and seeds within each dataset and do not establish cross-network confidence intervals.

<!-- M2-RESULTS:END -->

## 5.2 M3 whole-network holdouts and native campaign

M3 continues the same objective and evaluator rather than rebuilding them. The
new [source catalog](configs/source_catalog_m3.json) keeps Sioux Falls and Anaheim
as development data, assigns the complete published Eastern Massachusetts highway
benchmark to validation, and reserves Barcelona for test. The complete published
benchmark is used, not a random subset of its nodes. EMA itself is a highway
subnetwork, not every road in the region.

The [M3 protocol and research note](docs/m3_protocol.md) explains source selection,
excluded incompatible datasets, recorded header-roundoff handling, native model
configuration, validation selection and one-time test access. It distinguishes
new project decisions from Chapter 4 and preserves the historical M1/M2 results.
Winnipeg, Berlin-Tiergarten and Chicago-Sketch are not silently simplified to fit
our model. No positive trip is dropped, no zero-time link receives an invented
epsilon weight, and the coverage objective is unchanged.

`campaign.py` invokes the pinned **native** runner using the existing anytime
entrypoint. It does not generate substitute descendants. After a real native run,
it freezes at most five development leaders plus the original seed, evaluates that
fixed shortlist on validation, freezes one program, and only then evaluates test
performance. Code, source-family, suite, population and container identities are
checked. Both held-out graphs remain unscored until their corresponding stage.

The worker now has an opt-in Docker backend: no network, non-root, read-only code
and root filesystem, no host-repository/secret/socket mount, bounded resources and
explicit immutable image identity. The existing parent clock and independent
scorer remain in charge. Docker startup is outside the warm search budget and
is recorded in total trial cost. Controlled probes are not a formal security proof.

<!-- M3-RESULTS:START -->

| Source network | Partition | Nodes | Directed links | Positive OD pairs |
|---|---|---:|---:|---:|
| SiouxFalls | development | 24 | 76 | 528 |
| Anaheim | development | 416 | 914 | 1406 |
| Eastern-Massachusetts | validation | 74 | 258 | 1113 |
| Barcelona | test | 1020 | 2522 | 7922 |

**Measured software evidence:** 63 tests passed; Docker containment/deadline probes passed; native development seed completed 24 paired cases successfully. The seed run made zero model calls and is not an evolutionary result.

**Campaign state: `blocked_model_access`.** Native evolutionary runner started: `False`. Recorded campaign inference calls: `0`; valid evolved descendants: `0`. Validation solver trials: `0`; test solver trials: `0`.

For `blocked_model_access`, no model credential was available to the verified native preflight. No validation/test performance or champion is fabricated to fill that gap.

[Summary](results/step3/ci/summary.json), [input audit](results/step3/ci/audit/data_audit.json), [container probes](results/step3/ci/container.json), [native seed](results/step3/ci/native/native_seed_check.json), [campaign status](results/step3/ci/campaign/campaign_status.json), and [test transcript](results/step3/ci/tests.txt).

<!-- M3-RESULTS:END -->

### Execute the first bounded campaign

The explicit request targets 100 native slots, four islands and a $3 submission
threshold with a two-model mutation pool. It is neither a claim of completed
generations nor a guarantee that 100 slots fit that cost. See
[`configs/m3_launch_request.json`](configs/m3_launch_request.json). The threshold
may overshoot with in-flight calls; there is no automatic top-up or fallback.
Mutation-model bandit selection remains separate from interpretation-model routing.

With an authenticated model route available securely in the execution environment:

```bash
python -m pip install -e . -r requirements-shinka.txt
docker pull python:3.11-slim
IMAGE_ID=$(docker image inspect python:3.11-slim --format '{{.Id}}')
python campaign.py --execute --download --docker-image "$IMAGE_ID" \
  --output results/local_m3_campaign
```

The driver materializes development data first and does not open validation/test
performance during evolution. Without its required model credential it exits with
`blocked_model_access` before inference. Put credentials in environment variables
or repository Actions secrets, never in source files or the chat. The GitHub
**M3 research** workflow also supports an explicit manual campaign request; ordinary
check reruns do not automatically spend a provider budget. A started/interrupted
campaign is preserved, not silently overwritten; continuation must retain its
original native manifest and separately document any interrupted holdout assessment.

## 5.3 Coverage plus independently verified quality certificates

The certificate perspective from Chapter 4, printed p. 200 and Figure 4.11, is now
implemented as a separate, tested reporting path. For **any** feasible deployment
with coverage L and a verified upper bound U on the optimum, L/U is a guaranteed
lower bound on its fraction of optimal coverage. Coverage and certified quality
are reported separately, alongside an interval for remaining possible improvement.

The general method computes exact-rational submodular upper bounds on the original
shortest-path DAGs, without enumerating routes. Optional small-instance DFBnB
partition proofs and exactly checked LP-dual witnesses supply stronger reference
bounds. None relies on an LLM judgment or accepts a candidate's claimed score.
See [the mathematical derivation and source mapping](docs/quality_certificates.md).

This adds **posthoc certificates**, not a new fitness. The production scorer,
checkpoints, mutable seed, campaign configuration and historical M1/M2/M3 evidence
remain unchanged. A certificate attached to a past checkpoint uses an offline
bound; it is not a claim that the solver had that bound available at that time.
No validation/test performance was evaluated and no evolutionary run was started.

<!-- QUALITY-CERTIFICATES:START -->

| Development network | Monitors | Completed swap coverage (%) | Verified optimum upper bound (%) | Quality guarantee (%) | Remaining gain at most (pp) |
|---|---:|---:|---:|---:|---:|
| SiouxFalls | 1 | 34.082085 | 34.082086 | 100.000000 | 0.000000 |
| SiouxFalls | 2 | 50.915141 | 50.915142 | 100.000000 | 0.000000 |
| SiouxFalls | 3 | 66.916251 | 66.916251 | 100.000000 | 0.000000 |
| SiouxFalls | 4 | 74.681087 | 74.681088 | 100.000000 | 0.000000 |
| SiouxFalls | 5 | 81.419856 | 81.780367 | 99.559172 | 0.360511 |
| SiouxFalls | 6 | 86.966167 | 88.186357 | 98.616352 | 1.220189 |
| SiouxFalls | 7 | 91.070438 | 91.735996 | 99.274486 | 0.665558 |
| SiouxFalls | 8 | 94.231836 | 94.647810 | 99.560503 | 0.415974 |
| Anaheim | 3 | 52.468327 | 52.468327 | 99.999999 | 0.000001 |
| Anaheim | 6 | 74.498063 | 75.054206 | 99.259012 | 0.556143 |
| Anaheim | 12 | 93.123701 | 94.166702 | 98.892388 | 1.043001 |
| Anaheim | 24 | 99.549833 | 100.000000 | 99.549832 | 0.450168 |

**Executed evidence:** 86 tests passed locally; 48 standalone certificates and 24 bound witnesses independently recomputed. 96 existing baseline trials received 384 checkpoint and 96 final certificates without running candidates or changing their recorded timing. All eight Sioux Falls reference optima were proved. Anaheim LP bounds are not automatically exact optima.

[Reference study and source hashes](results/quality-certificates/reference-study/study.json), [proof artifacts](results/quality-certificates/reference-study/references/), [posthoc M2 certificates](results/quality-certificates/m2-baseline-certificates.json), [verification](results/quality-certificates/verification.json), and [test transcript](results/quality-certificates/tests.txt).

<!-- QUALITY-CERTIFICATES:END -->

The table describes **completed fixed greedy+swap** on development cases, not a
new matched-runtime comparison. Sioux Falls k=2,5,7,8 are supplementary reference
budgets, not additions to the frozen campaign. Upper bounds are rounded up and
quality guarantees down; exact proof flags use rational equality, never displayed
rounding. An upper bound can be loose: its gap is not a promise of achievable gain.

For example, at six monitors in Sioux Falls, fixed swap covers about 86.9662% of
demand and is certified to reach at least 98.6163% of the optimum. The proved
optimum covers about 88.1864%. That leaves an actual gap of about 1.2202 percentage
points. This is a baseline/reference finding, **not an evolved discovery**.

Reproduce this first certificate study (no API keys or model calls):

```bash
python scripts/prepare_suite.py --download
python -m pip install -r requirements-certificates.txt   # Optional LP proposals.
python scripts/quality_study.py --suite data/commissioning/suite.json \
  --output results/local_quality --exact-small --extended-small --lp
python scripts/quality_study.py --suite data/commissioning/suite.json \
  --output results/local_quality --verify
python certify.py --suite data/commissioning/suite.json \
  --traces results/step2/ci/baselines/traces.json \
  --reference-dir results/local_quality/references \
  --output results/local_quality/m2-sidecar.json
```

Omit `--lp` to use only standard-library bounds and small-instance proof search.
Omit `--reference-dir` for generic DAG bounds without precomputed references.
`certify.py` requires a completed trace with exactly matching suite/data hashes;
its new output must not already exist. It never executes the candidate program.

For a deployment already available in Python:

```python
from swarm_location.core import Instance
from swarm_location.certificates import ExactCoverage, certificate

problem = ExactCoverage(Instance.load("data/sioux_falls.json"))
report = certificate(problem, selected=[3, 7, 12], k=3)
print(report["coverage_pct"], report["quality_lower_bound_pct"])
```

Those IDs are an arbitrary feasible example, not the champion or an optimality
claim. Supply verified reference witnesses to tighten the default bound. The
code records exact loaded floating-point demand as rationals rather than silently
reinterpreting the source decimals; this distinction is documented in the methods.

## 6. Reproduce the first milestone

The local path uses only Python's standard library; it needs no API key or GPU.
Python 3.10 or newer is required; the committed local run used 3.13.5.

```bash
git clone https://github.com/ReloadLightly/shinka-swarm-location.git
cd shinka-swarm-location
python3 -m venv .venv
source .venv/bin/activate
python -m unittest discover -s tests -v
python benchmark.py --output results/local_baselines
python evaluate.py --program_path initial.py --results_dir results/local_seed
```

To regenerate the committed result location and refresh the README table:

```bash
python benchmark.py --output results/step1
python evaluate.py --results_dir results/step1/seed
python -m unittest discover -s tests -v > results/step1/tests.txt 2>&1
python scripts/update_readme.py
```

Coverage values should reproduce; wall-clock times and timestamps will differ.
Review the prose, stage label, and limitations after each substantive experiment;
updating a table alone does not update its scientific interpretation.

### Optional native evaluator adapter

`--backend shinka` calls SakanaAI's `run_shinka_eval` with `run_experiment`, one
worker, fixed budget-specific arguments, and independent aggregation. The API
signature was checked against commit
`9912af12d423504b8d580f4179fd15f5f88b8c50` [4]. The package was **not installed or
executed during M1**. A subsequent M2 commissioning job installed this exact pin
and executed the M1 native adapter successfully. M1's local results alone did not
certify that adapter; the M2 native evidence is distinct.

```bash
python -m pip install -e .
python -m pip install -r requirements-shinka.txt
python evaluate.py --backend shinka --program_path initial.py --results_dir results/local_native
```

These commands evaluate a candidate, not an evolutionary population. The
`--timeout` option applies only to the local backend. Neither this worker nor the
native adapter is claimed to be a hostile-code security sandbox.

### Reproduce M2 or launch native evolution

The anytime worker uses Linux/WSL. Local baselines need only the standard library;
preparing the historical benchmark files requires internet access once.

```bash
python scripts/prepare_suite.py --download
python -m unittest discover -s tests -v
python scripts/benchmark_marginals.py
python evaluate_anytime.py --baselines-only --results_dir results/local_m2_baselines
python evaluate_anytime.py --results_dir results/local_m2_seed
python run_evo.py                         # Inspect the plan; no model calls.
python -m pip install -e . -r requirements-shinka.txt
python run_evo.py --check-native --results-dir results/local_native_check
python run_evo.py --native-seed --results-dir results/local_native_check
```

For a real run, set supported model identifiers and provider credentials outside the
repo, and supply the model roles and spending threshold explicitly:

```bash
python run_evo.py --run --generations 100 --seed 0 \
  --models "$MUTATION_MODEL_1" "$MUTATION_MODEL_2" \
  --meta-model "$META_MODEL" --novelty-model "$NOVELTY_MODEL" \
  --embedding-model "$EMBEDDING_MODEL" --max-api-cost "$API_BUDGET_USD" \
  --results-dir results/local_evolution_01
```

This command calls `ShinkaEvolveRunner.run()` with four native islands,
archive/inspiration sampling, migration, diff/full/cross proposals, cost-aware UCB,
novelty, and meta-recommendations every ten generations. The single evaluation
worker avoids concurrent timing trials and excess memory duplication. Configuration
is editable in [`configs/evolution.json`](configs/evolution.json). The meta model
is **separate** from the mutation-model bandit; model roles are not silently
assigned to an expensive default. The native API-cost threshold can overshoot due
to in-flight requests. No real run was invoked to generate M2's results.

Reuse a results directory to resume only with the same recorded source, data and
configuration identity. A reviewed seed job is not a test of actual mutations,
model routing, migrations, novelty judgments, or interpretation calls.

The source checks, fresh working directory, and stripped child environment are not
an adversarial security boundary. Use a disposable isolated execution environment
for generated candidates; independently re-evaluate finalists in a clean worker.

To regenerate the M2 evidence table after producing the documented CI-shaped
results directory:

```bash
python scripts/update_m2_readme.py --evidence results/step2/ci
python scripts/update_m2_readme.py --evidence results/step2/ci --check
```

## 7. Evolution boundary and next experiment

The historical mutable M1 seed is `initial.py`. M2's mutable seed is
`anytime_initial.py`, with the reporting contract documented above. Evolution may
change construction, exchanges, restarts, search scheduling, and conditional
strategies. The graph, OD demand, routing assumptions, feasibility checks, scoring
code, benchmark splits, and computational budget remain external to that region.

Next: establish additional whole-network validation/test instances, calibrate timing
variation before selecting champions, and execute a predeclared native campaign
with explicit models/budget in an isolated worker. Compare against fixed
greedy+swap, not merely weak placement baselines. Meta interpretations must follow
measured per-source/per-budget evidence and cannot award fitness.

The detailed handoff is in [docs/next_step.md](docs/next_step.md).

## 8. Limitations

The original Israeli graph, demand matrix, calibration, and original code have
not been recovered. M1 used one small substituted network; M2 adds a second
historical development network, not a held-out test. Current routes are free-flow
shortest routes, not congestion-aware empirical trajectory distributions. Sampling
quality, costs, heterogeneous fleets, failures, relocation, and dynamic response
are not implemented. An improved simulated coverage score is not a demonstrated
reduction in infrastructure losses.

M1's contribution is a transparent executable reference task and measured
baselines. M2 adds the efficient anytime evaluator and native job integration, not
evidence of evolutionary superiority. Neither is a full Chapter 4 numerical
replication or a completed algorithm-discovery study.

## 9. References

[1] Altshuler, Y., Pentland, A., and Bruckstein, A. (2025). Defending Large-Scale
Critical Infrastructures Using a Swarm of Drones. In Y. Altshuler (ed.), *Applied
Swarm Intelligence*, Chapter 4, pp. 180-209. CRC Press.
[Book DOI](https://doi.org/10.1201/9780429276378). The supplied copyright page says 2025.

[2] Altshuler, Y., Pentland, A., Bekhor, S., Shiftan, Y., and Bruckstein, A. (2016).
Optimal Dynamic Coverage Infrastructure for Large-Scale Fleets of Reconnaissance
UAVs. [arXiv:1611.05735](https://arxiv.org/abs/1611.05735). Earlier related source;
not treated as an original code/data release.

[3] Transportation Networks for Research Core Team. *Transportation Networks for
Research*, Sioux Falls dataset, pinned commit above. Accessed 2026-09-22.
[Dataset documentation](https://github.com/bstabler/TransportationNetworks/blob/977ee75c6906337c0c7d229a1336107c7cdb533e/SiouxFalls/README.md).

[4] SakanaAI. *ShinkaEvolve*, pinned code commit above.
[Native evaluation implementation](https://github.com/SakanaAI/ShinkaEvolve/blob/9912af12d423504b8d580f4179fd15f5f88b8c50/shinka/core/wrap_eval.py).

[5] Lange, R. T., Imajuku, Y., and Cetin, E. (2025). ShinkaEvolve: Towards
Open-Ended and Sample-Efficient Program Evolution.
[arXiv:2509.19349](https://arxiv.org/abs/2509.19349).

Additional benchmarking research, exact pin references, and the Anaheim source are
listed in [the M2 methods note](docs/m2_method.md).

## Licensing

Original code and documentation: [MIT](LICENSE). Upstream-derived data retain
academic-research-only terms and attribution requirements; see
[data/README.md](data/README.md). The book and third-party page images are not
included or relicensed. No secrets or real-world drone-deployment instructions
are included.
