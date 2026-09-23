# Evolving anytime network-monitor placement algorithms

**Can ShinkaEvolve discover reusable search procedures that find better monitor
placements and tighter optimality certificates under limited computation?**

This project develops a program-evolution experiment grounded in §4.7.4,
“Optimizing the Locations of Surveillance and Monitoring Stations,” of
*Applied Swarm Intelligence*. The research object is an interruptible search
algorithm: how it constructs deployments, explores alternatives, revises an
incumbent, tightens bounds, and allocates computation among those decisions.

The specification below describes the **current planned experiment** and its
implementation. Evolutionary comparisons and independent-network assessment are
planned research outputs, not results reported here.

## 1. Scientific problem

Given a directed transportation graph, fixed travel-time shortest routes,
origin–destination (OD) demand, and a budget of at most $k$ monitors, choose a set
$S$ maximizing the fraction of distinct trips observed:

$$
f(S)=\frac{\sum_{s,t} OD_{s,t}\,\sigma_{s,t}(S)/\sigma_{s,t}}
           {\sum_{s,t} OD_{s,t}},\qquad |S|\leq k.
$$

Here $\sigma_{s,t}$ counts shortest routes and $\sigma_{s,t}(S)$ counts those
intersecting at least one monitor. Trip endpoints count, tied shortest routes
receive equal probability, and a trip intersecting several monitors counts only
once. Monitor placement does not reroute traffic. TNTP centroid nodes retain their
origin/destination-only transit semantics.

The chapter compares greedy placement, Depth-First Branch and Bound (DFBnB), and
Potential Search through solution quality, interrupted-search behavior, and
incumbent-to-upper-bound certificates. This experiment retains those outcomes and
adds evolution of the reusable search program. Public transportation networks
provide reproducible instances; they are not the chapter's original Israeli data.

## 2. What evolves

ShinkaEvolve edits the whole EVOLVE block in [`search_initial.py`](search_initial.py),
including imports and data structures, through this interface:

```python
def solve(problem, k, random_seed, report, time_budget):
    # report(selected_nodes) submits an incumbent; return a node list or None.
    ...
```

The search space includes construction and exchange rules, adaptive origin
sampling, cached or stale marginal gains, custom DAG computations, populations,
restarts, branching variables, frontier priorities, pruning, and allocation of
effort between finding solutions and certifying them. The seed is a starting
program, not a fixed architecture or a catalogue of permitted algorithms.

`problem.nodes`, `problem.instance`, and `problem.dags` expose the graph and
per-origin shortest-path DAGs. Each DAG provides its source, topological order,
predecessors, original route counts, and destination demands. `score(S)` and
`marginal_gains(S)` use the fixed routes. `score_origins(S, origins)` and
`marginal_gains_origins(S, origins)` return selected origins' contributions,
normalized by **total** demand, enabling selective computation without silently
changing the objective.

Candidates can submit structural certificates through `report.bound(witness)`.
The optional `DagPartition` helper maintains a complete partition of feasible
subsets; it does not prescribe the search policy. The evaluator independently
replays its split journal and bounds without enumerating every shortest route.
`report.diagnostic(...)` records mechanism-level observations.

## 3. Data and computational regime

The current [source catalogue](configs/source_catalog_search.json) pins complete
TNTP files to a TransportationNetworks commit and verifies their blob hashes.
Import preserves zero-time connectors, uses topological counting through
zero-distance ties, and records excluded intrazonal demand separately. Relevant
internal zero-cost cycles are rejected explicitly rather than perturbed.

| Development network | Nodes | Directed links | Source family |
|---|---:|---:|---|
| Winnipeg | 1,052 | 2,836 | Winnipeg |
| Chicago-Sketch | 933 | 2,950 | Chicago |
| Chicago-Regional | 12,982 | 39,018 | Chicago |

The configured monitor budgets are **20, 40, 60, 80, and 100**, with three
replicates and **12 approximately log-spaced checkpoints from 0.5 to 60 seconds**.
This produces 45 development cases per evaluated program. Common route-DAG
preparation precedes the search clock; candidate imports, custom preprocessing,
and search are timed. The one-hour search regime discussed in the chapter is a
planned longer-budget comparison, not the current default profile.

Each network/replicate has a reproducible anonymous node labeling shared by the
candidate and fixed controls. Scores are balanced by source family: Chicago's two
representations do not count as two independent networks. Independent large-network
validation and test families remain to be specified; changing random seeds or
using the other Chicago representation is not an independent-network holdout.

## 4. Fixed controls and evaluation

The current reference set comprises exact-route greedy, early-incumbent
CELF plus swaps, DAG-based DFBnB, and a utility-potential-ordered DAG search.
The latter two are project implementations of the chapter's search families,
not recovered author code. Candidate and control programs share the same input,
clock, feasibility checks, independent scorer, and certificate-verification API.

[`evaluate_search.py`](evaluate_search.py) builds fixed-control references once
for each suite and execution environment. Subsequent evaluations run only the
candidate and compare it with the cached control curves.

For case $i$ and checkpoint $t_j$, let $L_i(t_j)$ denote incumbent coverage,
$B_i$ the best final feasible control coverage, and $U_i(t_j)$ the strongest
verified submitted upper bound, defaulting to the universal coverage bound.
The evaluator reports two separate anytime outcomes:

$$
Q_i=\frac{1}{m}\sum_j\frac{L_i(t_j)}{B_i},\qquad
C_i=\frac{1}{m}\sum_j\frac{\underline{L}_i(t_j)}{U_i(t_j)}.
$$

The numerator $\underline{L}$ uses outward-rounded rational coverage bounds.
The configured evolutionary fitness is $100$ times the source-family-balanced
mean of $0.5Q_i+0.5C_i$. This equal-weight scalarization is the project's design
choice; both components, final coverage, complete curves, and differences from
each control remain separately available. $B_i$ is a feasible reference, not an
optimum or upper bound, so normalized improvements above one are retained.

Elapsed time remains the computational budget: API-call counters cannot measure
all work performed by arbitrary new representations or custom kernels. Finalist
assessment will repeat timing on the same host and report deployment improvement
separately from certificate improvement. Small-instance exact checks and valid
bounds serve different purposes: a loose bound alone does not establish room for
a better deployment.

## 5. ShinkaEvolve configuration

The [native configuration](configs/evolution_search.json) specifies **200
generations and two islands**, weighted parent selection, archive and top-program
inspirations, migration every ten generations, and diff/full/cross program edits.
A cost-aware UCB bandit chooses among the supplied mutation models. Native
meta-recommendations run every ten generations; novelty uses embeddings and a
separate model role. The meta model is separate from the mutation-model bandit.

Model identifiers and the API-spending threshold are supplied at launch. The
configuration does not force low reasoning effort for every role. The native
runner stores programs, ancestry, evaluations, and recommendations for analysis
and resumption. API-budget or worker-resource settings limit execution resources,
not the scientific program-search space.

## 6. Running the experiment

Use Python 3.10 or newer. The mathematical backend is standard-library Python;
the native runner and optional certificate analyses have separate requirements.

```bash
python -m pip install -e . -r requirements-shinka.txt -r requirements-certificates.txt
python scripts/prepare_search.py --download --output data/search
```

For an existing pinned TransportationNetworks checkout, replace `--download` with
`--raw-dir /path/to/TransportationNetworks`. Set worker memory for the chosen
network size, resolve an immutable local Docker image, and build references in
the same environment used for evolution:

```bash
docker pull python:3.11-slim
export SWARM_DOCKER_IMAGE="$(docker image inspect --format '{{.Id}}' python:3.11-slim)"
export SWARM_WORKER_MEMORY_MIB=4096
python evaluate_search.py --suite data/search/suite.json --build-references
python evaluate_search.py --suite data/search/suite.json \
  --program_path search_initial.py --results_dir results/local_search
```

Supply accessible model identifiers and an explicit spending budget before
launching the native evolutionary run:

```bash
python run_evo.py --run --suite data/search/suite.json \
  --config configs/evolution_search.json --results-dir results/local_evolution \
  --docker-image "$SWARM_DOCKER_IMAGE" \
  --models "${MUTATION_MODEL_A:?}" "${MUTATION_MODEL_B:?}" \
  --meta-model "${META_MODEL:?}" --novelty-model "${NOVELTY_MODEL:?}" \
  --embedding-model "${EMBEDDING_MODEL:?}" --max-api-cost "${API_BUDGET_USD:?}"
```

The native per-candidate job allowance is 12 hours, covering all development
cases, common setup, and independent verification; each search still uses its
suite-defined 60-second budget. Docker workers have no network or provider keys.
Without Docker, process mode is available for trusted local debugging, not for
isolating untrusted generated programs.

## 7. Planned analysis and research outputs

The experiment will compare evolved procedures with each fixed control on
coverage curves, final placements, verified certificate curves, and computational
cost. Mechanism analysis will inspect how successful programs allocate effort,
then use ablations and repeated runs to test those explanations. Frozen finalist
programs will be assessed on independent source families and longer search
budgets once those assessment suites are specified. Reusable algorithms, complete
traces, code ancestry, and evidence-grounded interpretations are the intended
outputs.

## References

- Altshuler, Y., Pentland, A., and Bruckstein, A. “Defending Large-Scale Critical
  Infrastructures Using a Swarm of Drones,” in *Applied Swarm Intelligence*,
  edited by Y. Altshuler, CRC Press, 2025; §4.7.4, pp. 198–200.
- [ShinkaEvolve documentation](https://sakanaai.github.io/ShinkaEvolve/);
  framework source is pinned in [`requirements-shinka.txt`](requirements-shinka.txt).
- [TransportationNetworks](https://github.com/bstabler/TransportationNetworks);
  exact input paths and hashes are recorded in the source catalogue.
