# Chapter-search feasibility observations (2026-09-24)

These are local diagnostics on Linux/Python 3.12, without Docker or a Codex
subscription session. They are not an evolutionary result, author-code
reproduction, or matched-budget comparison on the intended execution host.
The pinned TNTP files were checked against the catalog's Git blob IDs. The
source book is not redistributed.

## Import and exact route construction

| Split | Network | Positive OD pairs | Route origins | Route-DAG construction (s) |
|---|---|---:|---:|---:|
| Development | Winnipeg | 4,344 | 135 | 0.27 |
| Development | Chicago-Sketch | 93,135 | 386 | 0.87 |
| Development | Chicago-Regional | 2,296,227 | 1,771 | 136.07 |
| Validation | Philadelphia | 1,149,795 | 1,489 | 83.19 |
| Validation | GoldCoast | 542,698 | 1,064 | 17.35 |
| Test | Barcelona | 7,922 | 97 | 0.14 |
| Test | Birmingham | 470,805 | 898 | 48.55 |

Validation/test checks built route DAGs only. No candidate placements, fitness,
control scores, budget tuning, or source-family selection used held-out outcomes.
The four held-out constructions ran sequentially in one process, whose overall
peak resident memory was about 813 MiB. Chicago-Regional's separate first build
peaked around 1.3 GiB. Its content-addressed compressed preparation was about
65.7 MB, took 181.9 s to build and serialize, and hydrated in about 37.6 s;
the measured peak after hydration was about 1.7 GiB. Caching reuses this work
for the same relabeled instance and implementation.

## Development headroom and primitive cost

| Network | Greedy coverage by monitor budget |
|---|---|
| Winnipeg | k=5: 43.95%; 10: 62.22%; 20: 79.54%; 30: 88.60%; 40: 93.58%; 60: 97.98%; 80: 99.55%; 100: 99.99% |
| Chicago-Sketch | k=20: 46.06%; 40: 66.30%; 60: 78.48%; 80: 86.20%; 100: 91.12% |

These curves justify replacing Winnipeg's near-saturated k=60/80/100 cases
with k=5/10/30. Coverage below 100% does not by itself establish improvement
over the best control or proximity to optimum.

For Chicago-Regional, one full score fell from 10.39 s to 3.89 s, and one
all-node gain pass from 26.64 s to 13.29 s, after replacing repeated compact
predecessor tuple materialization with indexed passes. The graph, OD demand,
route counts, and exact-route objective were unchanged. A 60-s search can
therefore make several selective-origin gain passes; the initial seed's
sampled-origin decisions are editable by ShinkaEvolve. The measured import and
verification costs do not count against the candidate's GO-to-deadline search
clock but do count toward wall time and the native job allowance.

A single trusted-local Chicago-Regional k=20 seed case, independently checked
in a 4,096 MiB resource-limited process, improved from its 11.096% placement
at the first checkpoint to 12.099% by 40 s and 12.700% by 60 s. The checker
accepted all three reported placements. Worker setup took 37.4 s and checker
replay took 106.8 s beyond the 60-s search clock. Only a universal upper bound
was reported, so its certified-quality curve tracked raw coverage: 11.096%,
12.099%, 12.700%. This diagnostic used 8 checkpoints rather than the suite's
12 and is a seed feasibility check on **one development case**, not a matched
control comparison or evidence of ShinkaEvolve improvement.
In a separate untimed diagnostic on this same graph, constructing the k=20
`DagPartition` root took 36.7 s and yielded an independently replayable upper
bound of 58.615% rather than 100%. It can fit in a 60-s search if prioritized
early, but competes with the construction work that improved the seed's
placement. This creates a real coverage-versus-certificate allocation decision.

The revised Potential Search control then underwent the same 60-s trusted-local
diagnostic and independent checker. It reported the root certificate at 38.1 s;
the accepted upper bound was 58.615%, making certified quality 18.930% by 40 s.
Its placement remained at 11.096%. Verification took 124.1 s beyond the search
clock. The seed and control used the same graph, k=20, and 8 checkpoints, but
these two exploratory cases are **not** the complete pinned reference suite.
They demonstrate that certificate quality can vary independently of coverage
when the search spends its clock on a verified bound.

## Scope of these observations

The suite has 45 development cases per candidate. Their 60-s search clocks alone
sum to 2,700 s (45 min), before worker hydration and independent verification;
one native evaluation runs at a time. The intended 200-generation run is a
substantial multi-day operation, potentially longer with provider pauses.
This host has no Docker daemon or authenticated local Codex CLI, so neither
the pinned container performance nor a native subscription run is established
here. The certificate-weight spread across matched 60-s controls and full-suite
candidate runtime still require measurement on the execution host. The two
diagnostics establish a real local tradeoff, but do not calibrate the equal
coverage/certificate weighting across all budgets and source families.
