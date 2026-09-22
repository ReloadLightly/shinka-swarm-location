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

Evidence table is populated from successful software measurements and the actual
campaign status, including a blocked status when model access is absent.

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

