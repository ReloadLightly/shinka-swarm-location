# Next executable research step

The step-1 code and measured results are complete; zero evolutionary generations
have been run. Continue from these files rather than rebuilding scaffolding.

First benchmark the DAG evaluator and an efficient marginal-gain backend on
additional documented transportation networks. Keep all shortest routes and the
same OD objective; if an approximation is proposed, label and measure it instead
of silently replacing the model. Inspect each network's terms, centroid
restrictions, directed/parallel links, and demand conventions. Resolve the
original Israeli dataset/code availability separately. Do not call alternative
data a reproduction of its reported curves.

Use whole source networks for train/validation/test separation. Demand variants
and relabeled copies of one network are not independent empirical networks. All
of Sioux Falls is public development/commissioning data; none of its runs is a
held-out test. The exact small-instance results already show that a fixed swap
control closes the greedy gap at k=3 and k=4. Beating greedy alone is therefore
not adequate evidence of an evolutionary contribution.

Implement independently timed anytime incumbent reporting and isolate candidate
execution from writable evaluators and benchmark artifacts. Preserve the best
valid solution before a normal deadline; fail malformed outputs. Step 1's local
process timeout is not this anytime protocol and is not a hostile-code sandbox.

Then connect the existing `initial.py`/`evaluate.py` to the actual pinned native
Shinka runner. The optional `--backend shinka` calls `run_shinka_eval`, but its
integration has only been source-checked here, not executed with the installed
package. Do not replace native evolution with a handwritten loop and call it
ShinkaEvolve. Native islands, parent/inspiration sampling, diff/rewrite/crossover,
novelty, economical mutation-model bandit, and meta-recommendations belong in the
next integration. Meta interpretation uses its separate model client; do not
assert the mutation bandit automatically selects the meta model.

For the research protocol, replace the explicitly labeled commissioning fitness
(mean final coverage over budgets on one graph) with the predeclared matched-time
coverage comparison across development instances. Report coverage, solver time,
preprocessing, failures, per-instance differences, and uncertainty separately.
The proposed 3 independent runs x 100 generation slots remains a plan, not an
executed protocol. Size and time it from measured evaluation throughput, then
record the chosen protocol before collecting comparative evidence. Models and
paid-run budgets must be explicit; no credentials go into the repository.

At each session end update README methods/status and conclusions from artifacts.
Record actual unique valid descendants, not just attempted slots. Preserve
negative results. A champion is reusable deployment-search code, not a fixed set
of locations, a drone, or a social network.
