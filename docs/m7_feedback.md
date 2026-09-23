# M7: evidence-grounded mutation context and bounded repair diagnostics

## Question and scope

Can the benchmark deliver the information needed to propose and repair meaningful
search procedures through the **actual native mutation and meta-memory paths**?
This milestone verifies that delivery. It does not test whether an LLM becomes a
better optimizer, establish an evolutionary improvement, or open research holdouts.
The mathematical problem remains the §4.7.4-based fixed-route, demand-weighted,
endpoint-inclusive group coverage problem; no drone controller is introduced.

The scalar, four checkpoint times, fixed solvers, initial candidate, comparator
sets, model roles, islands, mutation-model bandit, inspirations, and selection
rules are unchanged. The new `configs/m7_launch_request.json` explicitly selects
`feedback_context: "m7"` and the existing M6 comparison profile. Old requests do
not silently acquire the new historical prior. The corrected stderr transport is
shared by current evaluations; archived results remain associated with old source.

## Native paths inspected at the existing framework pin

The authoritative implementation is ShinkaEvolve commit
`9912af12d423504b8d580f4179fd15f5f88b8c50`, not an assumed current API.

* `shinka/core/sampler.py`: `PromptSampler.sample` places `task_sys_msg` in the
  system message and `Program.text_feedback` in mutation/inspiration context.
  `sample_fix` includes incorrect-program feedback. Diff/full formats consume
  sampled meta recommendations; **native crossover deliberately omits those
  recommendations**, while retaining task/parent feedback. M7 preserves this.
* `shinka/core/async_runner.py`: evaluator `metrics.text_feedback` is loaded into
  the native `Program` record. Mutation and meta clients are distinct instances.
* `shinka/core/async_summarizer.py` and `summarizer.py`: the native three-stage
  individual-summary / global-scratchpad / recommendation process uses its own
  system-message constants. It **does not inherit `task_sys_msg`**.
* `shinka/prompts/prompts_base.py`: compact numerical displays round float metrics
  to two decimals. M7 also supplies six-decimal checkpoint/final differences in
  text, so small observed differences are not silently rendered as identical.
  The native phrase “passes all validation tests” refers to functional correctness,
  not this benchmark's research validation split; the task brief makes that explicit.

Accordingly, the launcher appends the compact brief to the mutation task and adds
an **instance-local forwarding adapter** to `runner.meta_summarizer.async_llm_client`.
The adapter only augments `system_msg` on `query` and `batch_kwargs_query`. It
returns the native responses unchanged: no fabricated summaries, new model calls,
altered costs, extra judge, global monkeypatch, or replacement evolutionary loop.
The native summarizer continues to manage scratchpad state, recommendation history,
persistence and sampling. The mutation model's UCB does not route the separate meta
model. Prompt co-evolution is not enabled or substituted for meta recommendations.

## The compact brief

`swarm_location.feedback.task_context()` constructs a versioned, deterministic
brief. It includes the actual DAG and route-helper interfaces, node-ID versus
internal-index conversions, normalized coverage versus integer mass (`p.scale`),
absolute deadline versus remaining-duration conventions, and representation guards.
It describes the construction/refinement/perturbation/bound-search costs and the
named early-prefix controls. Helpers are options, **not a finite permitted catalogue**.
Nothing is moved before GO to make an algorithm appear faster.

Historical observations are projected only from two hardcoded, SHA-256-bound
**development** summaries: M5 timing and M6 early-prefix measurements. No raw
journal, optimum deployment, selected node ID, or research holdout result enters
this brief. The M6 negative result is included. The historical measurements are
explicitly not current-candidate results, and timing values/thresholds are not
portable across host sessions or the now-modified receiver.

The native plan/run manifest records the exact brief, its digest, and its evidence
source hashes. Campaign preflight records the same identity. `--feedback-context
m7` is required to opt in. The evaluator snapshots and checks that context; unknown
modes and changed evidence fail explicitly rather than silently changing a prior.

## Evidence per evaluated program

`feedback.json` and `metrics.extra_data.feedback` contain identical structured
feedback. `metrics.text_feedback` carries a bounded rendering into native storage
and subsequent prompts. Facts include per-network/budget checkpoint coverage,
final coverage, first-complete receipt counts/latency, paired checkpoint and final
differences from each executed control, and the assessment controls **not run** in
screening. Failed comparisons are not described using only successful cases.

The intended interpretation is:

> Observation: identify the program, network/budget, metric and named comparator.
> Hypothesis: explain a possible mechanism, without upgrading it to a measured fact.
> Next test: freeze the code and compare an appropriate matched fixed control.
> Falsifier: identify what result would weaken that mechanism explanation.

For example, an early-only improvement suggests testing a matched early-initialized
control; it does **not** prove when the candidate constructed its routes. Inspect
code and compare mechanisms. A faster first feasible deployment is not necessarily
a faster equally good solution. A certificate is a separate claim, still governed
by the existing trusted fixed-code proof interface.

## Stderr and correctness boundary

The parent now captures stdout and stderr through separate nonblocking pipes.
Deployment stdout is serviced first whenever both are readable. Only a fixed
**16,384-byte stderr tail** is retained; excess output is drained. At most one
bounded stderr read occurs per ordinary selector pass, with the existing deadline
check. After process/container termination, draining is bounded to 16 reads of
64 KiB; escaped children cannot make the parent wait indefinitely for stderr EOF.
Raw stderr is not written to disk. Capture counts can be a lower bound if the
post-termination drain limit is reached.

Only after timed capture does the parent sanitize and render diagnostics: terminal
controls/bidirectional format characters, absolute path directories, recognized
credentials/tokens, URLs, and private-key blocks are stripped or redacted. Excerpts
are capped at **2,048 characters**. A worker failure record includes at most eight
traceback frames (basename, line, function), exception type, and a capped message;
**no locals or source lines** are captured. The worker imports the failure formatter
only after an exception. M7 feedback includes at most three repair examples of
900 excerpt characters each and is capped at 12,000 characters overall.

The parent records its own observation (`worker_exit`, `invalid_deployment`,
`protocol_violation`, `output_limit`, `setup_timeout`, etc.). Worker-reported
import/runtime/return phases are separately marked **untrusted diagnostic hints**.
A candidate can forge stderr; it cannot award itself a score or turn a failed
parent verdict into success. Successful-run stderr is not promoted into scientific
observations or mutation instructions. Recognizable redaction and warning labels
are best-effort mitigations, **not a proof of prompt-injection resistance or removal
of every possible encoded secret**. Worker isolation and the minimal environment
remain essential. Model credentials are not passed to the worker or sanitizer.

A hard search deadline is normal anytime truncation. It retains the last valid
incumbent (or zero if none) under the existing rules and is labelled
`deadline_reached`, not automatically failed. Without an exception record the
parent cannot know whether an import or search loop was interrupted. A crash after
a good incumbent still fails the required trial. Invalid deployments still fail.
Stderr and diagnostic text never enter coverage, feasibility or scalar arithmetic.

## Verification and limits

`scripts/commission_feedback.py` executes a native JobScheduler unchanged-seed
assessment on development through Docker and independently replays every reported
deployment, the scalar arithmetic and generated feedback. It also executes named
synthetic fault/flood/forgery probes and a native-scheduler failing evaluation.
Expected failing synthetic programs are distinct from benchmark failures.

`scripts/check_feedback_native.py` uses those real evaluation artifacts to exercise
the pinned PromptSampler, native SQLite feedback roundtrip, all three native meta
stages, and saved/restored native meta state. **Only the model transport in this
verification script uses clearly labelled offline fixtures.** Their placeholder
responses are not LLM summaries or discovered hypotheses. Captured request payloads
establish routing at the model-client boundary; they do not demonstrate LLM
comprehension, repair success from an LLM, or better evolutionary search.

The receiver instrumentation changed. Although the mathematical objective and GO
boundary remain, no numerical timing equivalence with M5/M6 is claimed. Fresh
calibration belongs on the intended campaign host. The new historical prior also
changes the information given to the designer: later claims about its benefit
need matched inference-budget context/diagnostic ablations. Context adds input
cost; no speedup or cost saving is claimed here.

## Commands

```bash
# Dependency-free plan; does not call models.
python scripts/prepare_research.py --split development --download \
  --comparison-profile configs/comparisons_m6.json --output data/commissioning_m7
python run_evo.py --config configs/evolution_m3.json \
  --suite data/commissioning_m7/suite.json --feedback-context m7

# Native seed only; resolve an immutable image first.
python run_evo.py --config configs/evolution_m3.json --native-seed \
  --suite data/commissioning_m7/suite.json --feedback-context m7 \
  --docker-image "$IMAGE_ID" --results-dir results/local_m7_seed

# Later explicitly authorized evolutionary campaign (not this integration test).
python campaign.py --request configs/m7_launch_request.json --execute --download \
  --docker-image "$IMAGE_ID" --output results/local_m7_campaign
```

## Primary implementation references

- [Pinned native sampler](https://github.com/SakanaAI/ShinkaEvolve/blob/9912af12d423504b8d580f4179fd15f5f88b8c50/shinka/core/sampler.py)
- [Pinned async summarizer](https://github.com/SakanaAI/ShinkaEvolve/blob/9912af12d423504b8d580f4179fd15f5f88b8c50/shinka/core/async_summarizer.py)
- [Pinned async runner](https://github.com/SakanaAI/ShinkaEvolve/blob/9912af12d423504b8d580f4179fd15f5f88b8c50/shinka/core/async_runner.py)
- [Official Shinka task contract and runtime layers](https://sakanaai.github.io/ShinkaEvolve/core_concepts/)
- [Python 3.11 subprocess: separate pipes, return codes, timeouts and pipe deadlocks](https://docs.python.org/3.11/library/subprocess.html)
- [Python 3.11 traceback: stack/exception representation](https://docs.python.org/3.11/library/traceback.html)

The adapter, size limits and feedback layout are project implementation choices,
not prescribed by the book or claimed to be upstream Shinka features.

### Integration interruption and cleanup follow-up

The first native/Docker attempt (Actions run 35857061681) completed its
120-trial development seed evaluation, then stopped in the synthetic malformed
stdout probe because the old forced-removal helper raised a generic cleanup
error. That attempt is retained separately; it was not a complete pass. The
old error omitted the daemon response, so the exact cause is not established.
The cleanup helper now verifies absence following a failed remove, retries only
a reported removal-in-progress condition a bounded number of times, and otherwise
fails with a sanitized daemon diagnostic. It does not treat arbitrary daemon
errors as success. The timed Docker command, inner deadline, and scorer are
unchanged by this cleanup follow-up. Synthetic probe records are now checkpointed
after every returned result, with explicit interruption records. A fresh complete
functional integration checks the final source; no favorable timing sample is
selected from the incomplete attempt.
