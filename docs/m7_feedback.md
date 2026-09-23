# M7: evidence-grounded mutation and meta feedback

## Question and scope

Does the native evolutionary loop receive enough task-specific information to
interpret measured differences and repair failed programs? This implementation
addresses information delivery, not a new optimizer, new objective, model-based
judge, or claim that richer prompts have already improved evolution. M6 remains
the fixed-control comparison profile. Historical results and configurations are
preserved; opt in through `configs/evolution_m7.json` or the new campaign request.

## Actual native routing

The pinned ShinkaEvolve source is
`9912af12d423504b8d580f4179fd15f5f88b8c50`. Its `PromptSampler` receives
`task_sys_msg` and, when enabled, `Program.text_feedback`. The native runner stores
the evaluator's `text_feedback` in its program records. The diff, full, crossover
and fix builders use those records. Public numeric display rounds values, so the
bounded feedback also writes descriptive differences to six decimal places.
That precision is formatting, not a statement of measurement accuracy.

The separate `AsyncMetaSummarizer` creates its own three prompts; the runner does
not pass `task_sys_msg` into that constructor. Merely enlarging the mutation task
would therefore not deliver the same domain context to meta analysis. M7's narrow
`EvidenceMetaClient` adapter appends the curated task and meta addendum at the
native meta-client boundary. It forwards all other arguments and responses,
including costs, unchanged. The native summarizer retains its individual-summary,
global-insight and recommendation steps, update cadence, persistence and sampling.
No substitute meta loop or synthetic recommendations are installed.

The mutation-model UCB still selects mutation arms only. The meta role remains a
separate client and is not secretly routed through that bandit. Native crossover
omits the recommendation argument supplied to `PromptSampler.sample`; M7 preserves
and checks this behavior. Crossover still receives the task and evaluation text.
Prompt co-evolution is not enabled by this change.

## Compact task knowledge

`configs/feedback_m7.json` pins `docs/m7_task_context.md`,
`docs/m7_meta_context.md` and their supporting M5/M6 development summaries by
SHA-256. Raw source summaries are not copied into prompts. The curated text
contains helper signatures, ID/index conversion, normalized versus integer-mass
scores, route guards, charged compilation, deadline semantics and the pre-existing
fixed methods. It distinguishes earlier receipt, final coverage and certificates.

The historical findings are explicitly scoped to their original development
experiments. In particular, M5's 1.97 pp guard is not a transferable constant, and
M6's earlier complete answer did not improve the declared checkpoint objective.
No selected node sets, instance solutions, optimum lookup tables or research
validation/test evidence enter the curated context. This is not a claim that
knowledge of development networks can never cause overfitting.

Task text is limited to 7,500 characters, the meta addendum to 2,500, and one
candidate's feedback to 16,000. Extra per-budget rows are explicitly omitted from
the prompt while retained in `feedback.json`. These are character limits, not
model-token or cost limits; inspirations and the native code context add further
input. The resolved context and hashes are recorded for reproducibility and resume
identity checking. Older configurations do not silently opt in.

## Evidence and hypotheses

`feedback.json` projects independently scored trajectories and paired comparisons
without node selections. It reports each executed control, checkpoint and final
quality separately, per-network/per-budget behavior, complete-answer availability,
observed outcomes, and failures. Assessment-only controls are marked NOT RUN.
`metrics.json.text_feedback` is the bounded native-facing rendering of that packet.

Interpretations follow OBSERVATION -> HYPOTHESIS -> NEXT TEST -> NOT ESTABLISHED,
within the native step's requested output format. A descriptive early gain with
unchanged final coverage can motivate a scheduling hypothesis. Receipt traces do
not establish when candidate route construction began; that requires separate
code inspection or an explicitly designed instrumentation experiment. The example
in the meta addendum is labeled a format example, not an executed result.
No LLM interpretation changes feasibility, fitness, champion selection or holdouts.

## Exception diagnostics without making stderr an authority

M7 collects stderr on a separate nonblocking pipe using the existing external
reader. Stdout incumbent messages have priority. At most a 16 KiB suffix is kept
in memory; post-stop draining is bounded. Redaction/parsing happens after timed
capture. There is no added stdout message, trusted candidate certificate channel,
network access, provider environment, host-results mount or change to the scorer.
The source code of the driver changes, and collection can affect timing; no zero-
overhead or bitwise-timing-equivalence claim is made.

The worker records phase, exception type and at most eight basename/line/function
frames on an exception. It does not collect locals or source-line text. The parent
sanitizes again, limits the stderr excerpt to 2,048 characters, and the exception
message to 640. Common credentials, URLs, paths, control characters and node-list
patterns are redacted. This is lossy best-effort redaction, not a secrecy guarantee
or a defense that makes prompt injection impossible. Arbitrary free stderr is not
inserted into mutation/meta feedback; bounded structured hints are explicitly
quoted as untrusted data.

Two fields deliberately have different authority:

| Field | Meaning |
|---|---|
| `host_category` | Parent-observed completion, deadline, setup timeout, invalid deployment, invalid bound, output limit, protocol violation or unsuccessful exit |
| `repair_category` | Parent category, optionally refined by a worker-reported import/run/return phase; not trusted for scoring |

A syntax or import exception can now reach repair as an import-failure hint with
its source line. A runtime exception after a good deployment still makes that
trial incorrect. An invalid returned node remains a parent-detected invalid
deployment, not an ordinary crash. A valid anytime search stopped at its deadline
remains valid: `search_deadline` is not automatically a failure. A setup timeout is
a failure. A silently stuck candidate after GO cannot be distinguished from legal
anytime work solely by this protocol; no invented internal phase is asserted.
Missing, truncated or forged hints never rescue an invalid trial or change a score.

`diagnostics.json` retains the bounded per-trial diagnostic records separately
from `feedback.json` and numerical measurements. Deliberate fault fixtures are
labeled synthetic; they are not research-network performance results.

## Execution evidence and limits

`scripts/commission_feedback.py` freezes source/configuration/runtime identity,
uses the pinned native scheduler on the unchanged development seed, and executes
synthetic fault cases on Docker. It checks a database feedback round-trip and the
actual native diff/full/crossover/fix input builders. All three native meta-stage
inputs are captured at the client boundary and stopped BEFORE inference. Later
meta stages use plainly labeled transport-only inputs; no fabricated provider
completion is supplied and no scratchpad/recommendation is claimed generated.

The resulting input captures establish delivery, not that an LLM used the evidence
correctly. Better mutation quality, repair rate, sample efficiency or overall
fitness require a subsequent matched evolutionary comparison. Unit fixtures also
verify sanitization, bounded floods, preserved failure semantics, unchanged reward
arithmetic and stale-artifact removal. The README reports only completed checks;
`scripts/report_feedback.py` replays their arithmetic, projections and context.

Historical scoring/timing artifacts are replayed against their own measured source.
Current source tests and a separate preservation record identify diagnostic-driver
changes explicitly instead of changing the old manifests to match new code.

## Commands

Inspect the native M7 plan without initializing model clients:

```bash
python scripts/prepare_research.py --split development --download \
  --comparison-profile configs/comparisons_m6.json --output data/commissioning_m7
python run_evo.py --config configs/evolution_m7.json \
  --suite data/commissioning_m7/suite.json --results-dir results/local_m7_plan
```

Commission on an explicit immutable local Docker image:

```bash
python scripts/commission_feedback.py --suite data/commissioning_m7/suite.json \
  --docker-image "$IMAGE_ID" --output results/local_m7_integration
```

A future host calibration must include the new instrumentation:

```bash
python scripts/calibrate_timing.py --suite data/commissioning_m7/suite.json \
  --docker-image "$IMAGE_ID" --feedback-profile m7-evidence-v1 \
  --output results/local_m7_timing
```

Calibration records the feedback profile/context; its optional screen uses that
same profile. Historical M5 evidence is not overwritten by M7 calibration. A paid
campaign remains a separate explicit action with model credentials:

```bash
python campaign.py --request configs/m7_launch_request.json --execute --download \
  --docker-image "$IMAGE_ID" --output results/local_m7_campaign
```

The inherited 100-slot target and $3 submission threshold are unchanged and do not
guarantee sufficient search effort. No paid campaign is part of this implementation.

## Primary sources

- Pinned native routing: [async runner](https://github.com/SakanaAI/ShinkaEvolve/blob/9912af12d423504b8d580f4179fd15f5f88b8c50/shinka/core/async_runner.py),
  [sampler](https://github.com/SakanaAI/ShinkaEvolve/blob/9912af12d423504b8d580f4179fd15f5f88b8c50/shinka/core/sampler.py),
  [async summarizer](https://github.com/SakanaAI/ShinkaEvolve/blob/9912af12d423504b8d580f4179fd15f5f88b8c50/shinka/core/async_summarizer.py).
- [Official core concepts](https://sakanaai.github.io/ShinkaEvolve/core_concepts/)
  describe native recommendations and their distinction from code evaluation;
  the pinned source is authoritative for this integration.
- [Python 3.11 subprocess](https://docs.python.org/3.11/library/subprocess.html)
  documents pipe deadlock risks. M7 drains bounded stderr without merging it into
  the stdout incumbent protocol; it does not use unbounded `communicate()` capture.
- [Python 3.11 traceback](https://docs.python.org/3.11/library/traceback.html)
  documents stack/frame information. M7 intentionally omits locals and source text.
- [M5 source evidence](../results/timing-calibration/study/summary.json) and
  [M6 source evidence](../results/early-controls/study/summary.json) support the
  historical development observations; the feedback format, limits and adapter
  are project-specific engineering choices, not findings attributed to the book.
