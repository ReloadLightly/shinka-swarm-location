# M3: whole-network holdouts and the first native campaign

## Scope and status

M3 extends the existing M2 experiment; it does not replace its coverage objective,
search interface, marginal-gain implementation, or independently timed scorer.
The source remains Chapter 4, especially the location-selection problem in
Section 4.7.4 of *Applied Swarm Intelligence*. Source emendations remain in
[source_fidelity.md](source_fidelity.md). New dataset partitioning, container
execution and model-selection procedures below are project research decisions,
not protocols claimed to appear in that chapter.

The requested native campaign has a concrete model-access prerequisite. The access
audit found no provider credentials or Codex authentication in either reachable
execution environment. `campaign.py` checks the installed native framework's
model-availability functions before starting the evolutionary runner. An absent
credential produces `blocked_model_access`, not a simulated successful run. A
green software workflow must not be read as a completed evolutionary campaign.

## Why these additions

Cawley and Talbot [1] show that optimizing a noisy finite-sample selection criterion
can itself overfit and bias performance estimates. Optimization benchmarking
research [2] emphasizes explicit problem definitions, appropriate comparisons,
measurement design and reproducibility. We therefore separate development,
validation and test **source networks**, freeze a limited shortlist before
validation, and freeze one program before evaluating test performance. Repeated
solver seeds on one road network are not independent networks.

ShinkaEvolve [3] supplies the actual outer program-evolution loop. We retain its
islands, mutation-model selection, inspirations, novelty and meta-recommendations,
rather than constructing a substitute evolutionary loop. Docker's documented
runtime controls [4] permit the existing protocol worker to execute with a
read-only filesystem, isolated network, non-root identity and resource limits.
These are execution controls, not proof against every kernel/container vulnerability.

## Source selection and data fidelity

All selected files are pinned to Transportation Networks for Research revision
`977ee75c6906337c0c7d229a1336107c7cdb533e` [5]. The catalog records original Git blob
hashes; the importer verifies those bytes and records prepared-data SHA-256 hashes.
Each published benchmark graph is used intact. In particular, “whole network”
means the complete published benchmark, not every road in the named metropolitan area.

| Source family | Partition | Nodes / directed links | Provenance and limits |
|---|---|---|---|
| Sioux Falls | Development | 24 / 76 | Debugging network; upstream explicitly says it is not realistic |
| Anaheim | Development | 416 / 914 | Historical 1992 data; Jeff Ban and Ray Jayakrishnan |
| Eastern Massachusetts | Validation | 74 / 258 | Published highway subnetwork; April 2012 PM; not the entire EMA road system |
| Barcelona | Test | 1,020 / 2,522 | Published historical benchmark; donor, scenario date and units remain unspecified upstream |

Eastern Massachusetts's accompanying research estimates OD demand and latency
functions from traffic data [6]. We use its supplied OD table and free-flow weights,
not its fitted degree-eight congestion model. Barcelona's sparse documentation is
preserved as a limitation [7]; no contemporary real-world validity is invented.
All files retain academic-research-only terms and source-attribution requirements.

The frozen catalog was chosen using provenance and input/model compatibility,
**not holdout solver performance**. Structure, positive-demand reachability and
checksums may be audited before search; no deployment is scored in that audit.

Three considered inputs were excluded rather than silently repaired:

- Winnipeg has a positive within-zone trip (demand 9); M2 excludes positive
  intrazonal OD pairs. No such demand was dropped or reinterpreted.
- Berlin-Tiergarten contains 206 zero-free-flow links.
- Chicago-Sketch contains 774 zero-free-flow links. Its five documented TNTP
  comment lines are valid formatting, not missing demand.

The latter two violate the unchanged positive-weight DAG assumptions. Replacing
zero weights with epsilon, deleting links, or collapsing nodes would alter the
route model and is not performed. Exclusions constrain external validity; these
networks could be a separate explicitly extended model in future work.

### Header totals are not individual demand records

The strict M2 parser also exposed rounding-size differences between metadata
`TOTAL OD FLOW` and the exact sum of supplied decimal OD entries. M3 permits only
`abs(sum-header) <= max(1e-9, 1e-12 * max(abs(sum),abs(header)))`.
For EMA the exact sum is 65,576.375431, versus header 65,576.37543099989: a difference
of +0.00000000011. Every OD entry is retained unchanged and the scorer normalizes
by the sum of those entries. No demand is rescaled. The original source bytes,
original header, exact sum, discrepancy, and tolerance are preserved in provenance.
The unchanged strict parser receives only the exact metadata total and ignores
standard `~` comment lines; substantive differences and malformed records still fail.

## Frozen experimental protocol

The M2 checkpoints remain 0.02, 0.10, 0.50 and 2.00 seconds after common DAG setup.
Sioux Falls retains budgets 1, 3, 4, 6. Other accepted source graphs use 3, 6, 12, 24.
Development seeds remain 0, 1, 2 (24 paired cases). Validation uses seeds 100–109
(40 cases per frozen program); test uses 1000–1009 (40 cases for one selected
program). These repetitions address solver/timing variation within a source,
not uncertainty over a population of transportation networks.

The fitness remains M2's `100 + mean checkpoint improvement over timed greedy`,
in percentage points. The +100 is an affine offset. Candidate results are also
compared with fixed greedy+swap. M3 additionally executes the fixed `topk` control:
M2 showed that an inexpensive early answer could outperform slower construction
under an anytime criterion. Adding a comparison does not change the primary fitness.
All methods use the same container/timing protocol. Parent-side exact scoring is
unchanged. M1/M2 results were not rerun or overwritten with container timings.

Before inference, the driver records source/configuration/data hashes, native
commit, model roles, search seed, API threshold and immutable container image ID.
Only development data are materialized into the native search workspace.

After the native runner exits, `selection.py` copies its real SQLite population
using SQLite's backup API. It deduplicates valid programs by code SHA-256, avoiding
inflated descendant counts from island copies. The five highest development-score
programs form a frozen shortlist; the original greedy seed is always included as
a no-improvement alternative. This is at most six programs. A seed-only or wholly
invalid population cannot masquerade as a completed discovery run: holdouts remain
unopened when there is no valid unique non-seed descendant.

The frozen shortlist is evaluated once on validation. The chosen program maximizes
mean checkpoint coverage; exact ties use its code hash. Using direct validation
coverage avoids selecting on separately timed baseline noise. Correctness,
candidate identity, suite identity and container identity must match the saved
measurement. Code, population and validation evidence hashes are verified again
before opening test. The test pass evaluates only that frozen program and the
same fixed controls. An exclusive `test_opened.json` record prevents automatic
repeated test attempts or reselection after seeing results.

An interruption is preserved, not silently retried until a favorable result occurs.
The native runner retains its ordinary database/resume machinery. The outer driver
refuses to overwrite an already-started campaign; a resumed native run or interrupted
holdout assessment must use its original manifest and a separately recorded continuation.
This first driver does not provide automatic recovery of every multi-stage failure.

## Native configuration and bounded launch

The native pin remains `9912af12d423504b8d580f4179fd15f5f88b8c50` (package 0.0.7).
The requested first campaign targets 100 slots on four islands with one evaluation
worker. Diff/full/cross proposals, archive/inspirations, cost-aware UCB, migration,
novelty and meta-recommendations every ten generations remain enabled. The target
is not a claim that 100 valid descendants exist, or three independent campaigns
have been completed.

The explicit initial model pool is `gpt-5-mini` and `gpt-4.1-mini`, with a separate
`gpt-4.1-mini` interpretation/novelty client and `text-embedding-3-small` embeddings.
Official documentation lists standard input/output prices per million text tokens
of $0.25/$2.00 and $0.40/$1.60 for these two LLMs respectively, as checked
2026-09-22 [8,9]. These are economical candidates, not a claim of the globally
cheapest suitable models. Model access and actual charges are not established by
documentation. Aliases are not immutable weights; preserve native returned model
metadata and recheck availability before a later launch.

`configs/m3_launch_request.json` makes the first submission threshold $3.00 explicit.
This is a chosen bounded request, not a completed charge or a guarantee that 100
slots fit into $3. The framework may stop early and in-flight requests can overshoot
its threshold. There is no automatic budget top-up or undisclosed provider fallback.
Actual usage and valid descendants must be counted from native evidence.

Source inspection also found that the pinned model-kwargs sampler can produce an
empty reasoning effort when it is omitted. `evolution_m3.json` explicitly sets low
reasoning effort for supported reasoning models; native sampling is checked before
inference. This does not assert that a paid M2 call failed—M2 made no such calls.

## Contained execution and timing interpretation

M3 requires an explicit locally resolved `sha256:` Docker image ID. The worker has
only its supplied trial code mounted at `/work`, read-only; the repository,
provider credentials, held-out files and Docker socket are not mounted. It runs as
UID/GID 65534, with no network, no added capabilities, no-new-privileges, a read-only
root, 768 MiB memory, one CPU and a PID limit. Small temporary storage is separate.
The parent starts its original timing boundary only after common preprocessing
reports READY; Docker startup is therefore excluded from the search budget but
included in recorded total trial cost. Cleanup removes the specifically named
container when a deadline terminates its CLI process.

Controlled probes check non-root identity, absent host canary/socket/credentials,
read-only code, capability/no-new-privileges state, denied external connection and
incumbent retention at a deadline. Passing these probes does not establish formal
sandbox security. CPU quotas, host scheduling and transport still affect short
checkpoints; M2 and M3 wall-clock scores should not be conflated.

## Interpretation limits

One validation family and one test family can establish transfer to those specific
unseen-during-search benchmark graphs. They do not support broad generalization
across all road systems, contemporary traffic, or real infrastructure defense.
Public benchmark exposure during LLM pretraining cannot be ruled out. Code hash
and source-family controls prevent local leakage, not unknowable pretraining overlap.
Failure to improve, selection of the original seed, invalid descendants, budget
termination and access failures are all reportable outcomes.

The scientific question is answered only after real native evolution, frozen
selection and independent test assessment. Software tests, fixed-seed jobs and
mock evaluator callbacks used solely in unit tests are not evolutionary evidence.

## References

[1] Cawley, G. C., & Talbot, N. L. C. (2010). On Over-fitting in Model Selection and
Subsequent Selection Bias in Performance Evaluation. JMLR 11:2079–2107.
https://www.jmlr.org/papers/v11/cawley10a.html

[2] Bartz-Beielstein et al. (2020). Benchmarking in Optimization: Best Practice and
Open Issues. https://arxiv.org/abs/2007.03488

[3] Lange, Imajuku & Cetin (2025). ShinkaEvolve.
https://arxiv.org/abs/2509.19349 and pinned native source:
https://github.com/SakanaAI/ShinkaEvolve/tree/9912af12d423504b8d580f4179fd15f5f88b8c50

[4] Docker. Running containers. https://docs.docker.com/engine/containers/run/

[5] Transportation Networks for Research Core Team, source revision above.
https://github.com/bstabler/TransportationNetworks

[6] Eastern Massachusetts source documentation and its original-study references:
https://github.com/bstabler/TransportationNetworks/blob/977ee75c6906337c0c7d229a1336107c7cdb533e/Eastern-Massachusetts/README.md

[7] Barcelona source documentation:
https://github.com/bstabler/TransportationNetworks/blob/977ee75c6906337c0c7d229a1336107c7cdb533e/Barcelona/README.md

[8] OpenAI. GPT-5 Mini. https://developers.openai.com/api/docs/models/gpt-5-mini
[9] OpenAI. GPT-4.1 Mini. https://developers.openai.com/api/docs/models/gpt-4.1-mini
