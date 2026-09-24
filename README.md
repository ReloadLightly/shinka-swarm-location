# Evolving anytime network-monitor placement algorithms

**Can ShinkaEvolve discover reusable search procedures that find better monitor
placements and tighter optimality certificates under limited computation?**

This program-evolution experiment is grounded in §4.7.4, “Optimizing the Locations
of Surveillance and Monitoring Stations,” of *Applied Swarm Intelligence*. The
research object is the interruptible search algorithm: how it constructs and
revises deployments, explores alternatives, tightens bounds, and allocates effort.
This README specifies the current experiment; evolutionary comparisons and
independent-network assessment are planned research outputs.

## 1. Scientific problem

Given a directed transportation graph, fixed travel-time shortest routes,
origin–destination (OD) demand, and at most $k$ monitors, choose $S$ maximizing the
fraction of distinct trips observed:

$$
f(S)=\frac{\sum_{s,t} OD_{s,t}\,\sigma_{s,t}(S)/\sigma_{s,t}}
           {\sum_{s,t} OD_{s,t}},\qquad |S|\leq k.
$$

Here $\sigma_{s,t}$ counts shortest routes and $\sigma_{s,t}(S)$ those intersecting
at least one monitor. Endpoints count, tied shortest routes have equal probability,
and a trip crossing several monitors counts once. Placement does not reroute
traffic. TNTP centroids retain their endpoint-only transit semantics.

The chapter compares greedy, Depth-First Branch and Bound (DFBnB), and Potential
Search through deployment quality, interrupted-search behavior, and
incumbent-to-upper-bound certificates. This project retains those outcomes and
evolves the reusable search program. Public inputs and the evolutionary fitness
are explicit adaptations, not numerical reproduction of the original Israeli
network. The equation emendation is documented in [source fidelity](docs/source_fidelity.md).

## 2. What evolves

ShinkaEvolve edits the **whole EVOLVE block** in [search_initial.py](search_initial.py),
including imports and data structures:

```python
def solve(problem, k, random_seed, report, time_budget):
    # report(selected_nodes) submits an incumbent; return a node list or None.
    ...
```

Construction and exchange rules, adaptive origin sampling, cached or stale gains,
custom DAG computations, populations, restarts, branching variables, frontier
priorities, pruning, and effort allocation can change. The seed is a starting
program, not an immutable architecture or a finite catalogue of algorithms.

`problem.nodes`, `problem.instance`, and `problem.dags` expose the anonymous graph
and per-origin shortest-path DAGs: source, topological order, predecessors, original
route counts, and destination demands. `score(S)` and `marginal_gains(S)` use the
fixed routes. Their `score_origins(S, origins)` and
`marginal_gains_origins(S, origins)` counterparts return selected origins'
contributions normalized by **total demand**, supporting selective computation.

`report.bound(witness)` submits a structurally checkable certificate; bare claimed
scores or bounds are not accepted. The supported witness families are
`universal_v1`, `online_partition_v1`, and `dag_partition_v2`. The optional
`DagPartition` helper preserves a complete subset partition without enumerating
routes. Its branch policy is editable; its trusted bound formula is not evolved.
Discovering other bounding formulas would require corresponding independent
witness verification. `report.diagnostic(...)` records compact mechanism evidence.

## 3. Data, splits, and time profiles

The [catalogue](configs/source_catalog_search.json) pins complete TNTP files and
blob hashes to one TransportationNetworks commit. Splits are by geographic source
family, not by random seeds or subgraphs.

| Split | Network | Nodes | Directed links | Source family |
|---|---|---:|---:|---|
| Development | Winnipeg | 1,052 | 2,836 | Winnipeg |
| Development | Chicago-Sketch | 933 | 2,950 | Chicago |
| Development | Chicago-Regional | 12,982 | 39,018 | Chicago |
| Validation | Philadelphia | 13,389 | 40,003 | Philadelphia |
| Validation | GoldCoast | 4,807 | 11,140 | GoldCoast |
| Test | Barcelona | 1,020 | 2,522 | Barcelona |
| Test | Birmingham | 14,639 | 33,937 | Birmingham |

Each network uses $k\in\{20,40,60,80,100\}$ and three declared replicates:
**45 development, 30 validation, and 30 test cases** per program and time profile.
Chicago's two representations share one source-family weight. Reproducible node
relabelings are shared by candidates and controls; they are not additional
independent networks.

The default `standard` profile has 12 approximately log-spaced checkpoints from
0.5 to **60 seconds**. The opt-in `chapter-hour` profile has 12 checkpoints through
**3,600 seconds**, including 60 seconds. It implements the chapter's one-hour
search allowance while retaining this project's public inputs and monitor-budget
grid. Both profiles require separate matched-budget runs: a program told that it
has an hour may make different decisions from one given a minute.

Import preserves zero-time connectors and counts through zero-distance ties in
topological order. Positive intrazonal trips are excluded with exact mass
accounting; no supplied interzonal demand is rescaled. GoldCoast's pinned rows sum
to 139,256.434, versus 139,253 in its header: a source-specific tolerance records
that 3.434 discrepancy without changing rows. Relevant internal zero-cost cycles
and parallel directed links remain explicit unsupported representations, not
silently perturbed or collapsed.

## 4. Evaluation and reliable execution

The fixed controls are exact-route greedy, early-incumbent CELF plus swaps,
DAG-based DFBnB, and utility-potential-ordered DAG search. The search controls are
project implementations of the chapter's algorithm families, not recovered author
code. Candidates and controls share inputs, clocks, feasibility checks, and the
independent scoring and certificate-verification interface.

[evaluate_search.py](evaluate_search.py) builds fixed-control references once.
Subsequent candidate evaluations reuse those curves. For case $i$, checkpoint
$t_j$, incumbent coverage $L_i(t_j)$, best final feasible control coverage $B_i$,
and strongest verified upper bound $U_i(t_j)$:

$$
Q_i=\frac1m\sum_j\frac{L_i(t_j)}{B_i},\qquad
C_i=\frac1m\sum_j\frac{\underline L_i(t_j)}{U_i(t_j)}.
$$

The lower numerator uses outward-rounded rational bounds; absent a verified
certificate the universal coverage upper bound applies. Evolutionary fitness is
$100$ times the source-family-balanced mean of $0.5Q_i+0.5C_i$. This weighting is a
project design choice, not the chapter's equation. Coverage and certificate
outcomes, final placements, full curves, and comparisons with each control remain
separate. $B_i$ is feasible, not optimal; improvements above one are retained.

Common route DAGs are built once in an evaluator-owned, content-addressed cache.
Artifacts are checksum-verified data-only JSONL/gzip, preserving exact integer
route counts. Every worker hydrates private objects before the external GO signal;
candidate-specific imports, custom preprocessing, and search remain timed. Raw
DAG access is retained. API-call counts are diagnostics, not a substitute for the
elapsed-time budget of arbitrary evolved programs.

Completed control trials and candidate cases are atomically checkpointed. Running
the same command with the same identities resumes only unfinished work. Timed
candidate output is saved before independent verification, so an interrupted
checker replays the **same capture**, not another timing attempt. Invalid candidate
trials remain terminal; a new independent repetition uses a new results directory.
Code, data, protocol, reference, or execution-identity changes cannot silently reuse
completed cases. Concurrent writers to one evaluation directory are rejected.

Candidate stderr is drained separately from incumbent messages, retaining only a
16 KiB tail with common credential patterns redacted. Import/runtime failures,
invalid reports, and verifier resource failures are distinguishable in feedback.
No provider environment is passed to the worker. Diagnostics remain untrusted text.

Generated programs require a pinned Docker image: no network, provider keys,
repository mount, elevated capabilities, or writable preparation. The CLI never
silently falls back to a same-user process. Independent scoring and certificate
replay run trusted code in a separate process with wall, CPU, memory, and output
limits; no candidate code is imported there. An unverified bound earns no credit.
Verifier costs are recorded separately from the search clock. The default checker
allowance is 1,800 seconds per case and its memory follows the worker setting;
suite fields can explicitly specify different verification limits.

## 5. Native ShinkaEvolve configuration

The [configuration](configs/evolution_search.json) uses **200 generations and two
islands**, weighted parent selection, archive/top-program inspirations, migration
every ten generations, and diff/full/cross edits. A cost-aware UCB bandit selects
mutation models. Meta-recommendations run every ten generations; the meta model is
separate from mutation-bandit routing. Novelty uses embeddings and a separate role.

Model identifiers and an explicit API-spending threshold are supplied at launch.
Native programs, ancestry, evaluations, and recommendations are retained for
resumption and mechanism analysis. Resource budgets limit execution, not the
scientific program-search space. No mandatory pilot is inserted before evolution.

## 6. Running and resuming

Use Python 3.10+ on Linux/WSL and Docker for generated programs:

```bash
python -m pip install -e . -r requirements-shinka.txt -r requirements-certificates.txt
python scripts/prepare_search.py --download --output data/search

docker pull python:3.11-slim
export SWARM_DOCKER_IMAGE="$(docker image inspect --format '{{.Id}}' python:3.11-slim)"
export SWARM_WORKER_MEMORY_MIB=4096
python evaluate_search.py --suite data/search/suite.json --build-references
python evaluate_search.py --suite data/search/suite.json \
  --program_path search_initial.py --results_dir results/local_search
```

A pinned local TransportationNetworks checkout can replace `--download` with
`--raw-dir /path/to/TransportationNetworks`. `--dag-cache /path/to/cache` shares
common preparation across suites; `--references /path/to/references.json` selects
an explicit reference file. Rerun an interrupted command with the same paths.
Existing compatible references are reused; incompatible files are not overwritten.

```bash
python run_evo.py --run --suite data/search/suite.json \
  --config configs/evolution_search.json --results-dir results/local_evolution \
  --docker-image "$SWARM_DOCKER_IMAGE" \
  --models "${MUTATION_MODEL_A:?}" "${MUTATION_MODEL_B:?}" \
  --meta-model "${META_MODEL:?}" --novelty-model "${NOVELTY_MODEL:?}" \
  --embedding-model "${EMBEDDING_MODEL:?}" --max-api-cost "${API_BUDGET_USD:?}"
```

The native per-candidate job allowance is 12 hours for the standard development
suite; individual searches retain their 60-second deadline. Unfinished evaluation
cases survive native job interruption. `--evaluation-time` explicitly changes the
job allowance. For no-model, explicitly trusted local debugging, use
`evaluate_search.py --trusted-local` or `run_evo.py --native-seed --trusted-local`.
The latter flag is rejected with real `--run` evolution.

## 7. Independent assessment and planned analysis

Freeze the development shortlist by code hash before validation, include the
original seed, and select the highest source-balanced joint validation score
(ties by code hash). Freeze that selected program before test access. Report all
control comparisons and the coverage/certificate components, not just the chosen
scalar score. Assessment output does not enter native development feedback.

Prepare each split in a separate directory. Select the one-hour comparison
explicitly; preparation does not launch search or spend API credits:

```bash
python scripts/prepare_search.py --download --split validation \
  --time-profile chapter-hour --output data/search_validation_hour
python evaluate_search.py --suite data/search_validation_hour/suite.json \
  --split validation --build-references
python evaluate_search.py --suite data/search_validation_hour/suite.json \
  --split validation --program_path "$FROZEN_PROGRAM" \
  --frozen-program-sha256 "$FROZEN_SHA256" --results_dir results/local_validation_hour
```

For the primary 60-second assessment use `--time-profile standard`; for final test
use `--split test` and its own output directory. Validation/test evaluation requires
the matching frozen program hash. Apply the already frozen finalists to the
one-hour comparison without modifying them in response to its test results.
Independent timing repetitions use new result/reference paths and remain separate
from interrupted-case resumption. Report uncertainty by source family; seeds do
not turn four assessment regions into a large population of independent networks.

Planned outputs are reusable search procedures, matched-budget quality and
certificate curves, complete cost accounting, and ablations explaining discovered
effort-allocation mechanisms. Engineering checks and import audits are not evidence
of an evolutionary improvement or of completed held-out assessment.

## References

- Altshuler, Y., Pentland, A., and Bruckstein, A. “Defending Large-Scale Critical
  Infrastructures Using a Swarm of Drones,” in *Applied Swarm Intelligence*,
  edited by Y. Altshuler, CRC Press, 2025; §4.7.4, pp. 198–200.
- [ShinkaEvolve documentation](https://sakanaai.github.io/ShinkaEvolve/);
  framework commit pinned in [requirements-shinka.txt](requirements-shinka.txt).
- [TransportationNetworks](https://github.com/bstabler/TransportationNetworks);
  input paths, hashes, splits, and time profiles are pinned in the catalogue.
