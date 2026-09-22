# Shinka Swarm Location
## A chapter-grounded benchmark for evolving network-monitor deployment algorithms

**Status: first executable milestone complete; no evolutionary run yet.**

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

| Research component | Current evidence |
|---|---|
| Chapter-grounded coverage objective and marginal greedy | Implemented; source deviations documented |
| Directed, tied-shortest-path, endpoint-inclusive evaluator | Implemented and cross-checked |
| Baseline results on a pinned public debugging network | Executed; artifacts committed |
| Local seed-program evaluator | Executed; seed equals reference greedy |
| Native `run_shinka_eval` adapter | Written and signature-checked against pinned source; not executed here |
| LLM-generated descendants / evolutionary runs | **0 / 0** |
| Original Israeli-network numerical reproduction | Original code/data not recovered |
| Multi-network held-out or anytime comparison | Planned; not conducted |

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

### 3.1 Commissioning dataset

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
DAG scorer recalculates candidate coverage. Large-network optimization of this
backend remains work to do; the route-mask commissioning path is not advertised
as scalable to every network.

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

## 4. Experimental protocol

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

The current commissioning fitness is simply

$$
F_{\mathrm{step1}}(A)=\frac{100}{8}\sum_{k=1}^{8} C(S_A(k)).
$$

It is explicitly **not** the proposed multi-network anytime research fitness.

## 5. Measured results

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

The local suite passed **23 tests** on Python **3.13.5**. It includes independent
all-simple-path enumeration on 10 small directed graphs, comparing both backends
on all 64 monitoring subsets per graph. Other checks cover decimal ties, unequal
branching with uniform route weighting, endpoints, overlap, no rerouting,
centroid restrictions, invalid outputs, and a compact DAG with $2^{26}$ shortest
routes. Passing these checks supports implementation correctness for the tested
cases, not empirical validity of the transportation assumptions.

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
executed in this milestone**; the local results do not certify this adapter's
end-to-end integration.

```bash
python -m pip install -e .
python -m pip install -r requirements-shinka.txt
python evaluate.py --backend shinka --program_path initial.py --results_dir results/local_native
```

These commands evaluate a candidate, not an evolutionary population. The
`--timeout` option applies only to the local backend. Neither this worker nor the
native adapter is claimed to be a hostile-code security sandbox.

## 7. Evolution boundary and next experiment

The mutable region in `initial.py` contains `solve(problem, k, random_seed)`.
Future evolution may change construction, exchanges, restarts, search scheduling,
and conditional strategies. The graph, OD demand, routing assumptions, feasibility
checks, scoring code, benchmark splits, and computational budget remain external
to that evolving region.

Next: establish a computationally practical multi-network evaluator, measure
strong-baseline headroom, add independently timed anytime incumbents, and connect
the seed to a genuine native ShinkaEvolve run [5]. Use whole-network held-out
splits and repeat independent evolutionary runs. Native islands, inspiration
sampling, mutation-model bandit selection, novelty, and meta-recommendations are
planned integration components, **not features already exercised by this repo**.
Meta interpretations must follow numerical evidence; they do not award fitness.
The mutation-model bandit and the meta-analysis model client are distinct.

The detailed handoff is in [docs/next_step.md](docs/next_step.md).

## 8. Limitations

The original Israeli graph, demand matrix, calibration, and original code have
not been recovered. Only one small substituted network has been evaluated. The
current routes are free-flow shortest routes, not congestion-aware empirical
trajectory distributions. Sampling quality, costs, heterogeneous fleets, failures,
relocation, and dynamic response are not implemented. An improved simulated
coverage score is not a demonstrated reduction in infrastructure losses.

The first milestone's contribution is a transparent, executable reference task
and measured baselines. It is neither a full Chapter 4 numerical replication nor
a completed algorithm-discovery study.

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

## Licensing

Original code and documentation: [MIT](LICENSE). Upstream-derived data retain
academic-research-only terms and attribution requirements; see
[data/README.md](data/README.md). The book and third-party page images are not
included or relicensed. No secrets or real-world drone-deployment instructions
are included.
