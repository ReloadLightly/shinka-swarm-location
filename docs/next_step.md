# Current execution entry points

README.md is the current experiment specification. The development pipeline is
`prepare_search.py` → fixed references → native ShinkaEvolve. The operational
subscription entry point is `run_evo.py --run --subscription --codex-model MODEL
--docker-image sha256:...`, on the user's ChatGPT-authenticated Codex/Docker host.
It builds or resumes the unchanged full-size references before model requests.

`prepare_local_embeddings.py --download` retrieves pinned public CPU embedding
weights. Native Headless/Codex handles mutation, meta and novelty roles; the native
local-embedding interface retains semantic novelty without a paid embedding API.
`--resume-provider` is an explicit retry after a resolved provider pause; never
fall back to API billing. Keep provider credentials on the host and out of workers,
GitHub, and CI. Shared Codex instructions are not edited by the launcher.

The full program-search space, mathematical objective, development/assessment
families and standard/chapter-hour profiles remain in the current specification.
Execution status and measured results require actual host evidence. A passing
mock-CLI integration test is not a subscription-authenticated evolutionary run.
