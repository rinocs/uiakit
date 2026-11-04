# GitHub release readiness and competitor review

Reviewed on 2026-10-29. This is a proposal and repository assessment, not a
release approval or a full security/legal audit. The user prefers GPL; the plan
therefore targets GPLv3. The baseline findings below were recorded before
implementation; see the implementation update at the end. Repository visibility
and publication settings have not been changed.

## Recommended product direction

Publish a useful, documented developer platform before pursuing full Cheshire
Cat parity. Target developers adding a self-hosted assistant to an existing
application: versioned HTTP/SSE API, TypeScript/Go/PHP SDKs, embeddable widget,
RAG with provenance, explicit authorization and recoverable execution.

These are capabilities already present, not claims of superiority. Validate the
positioning with working integration examples and user feedback. Avoid claiming
HA, arbitrary plugin installation, autonomous write agents, or full MCP support.

Three approaches were considered:

| Approach | Benefit | Cost | Recommendation |
|---|---|---|---|
| Publish the current developer kit after release blockers | Delivers something useful without expanding the architecture | Must state feature limits plainly | First milestone |
| Complete Cheshire Cat parity first | Familiar feature checklist | Delays release for memory, forms, plugins and transport differences | Select individual features after launch |
| Build a visual automation platform | Competes directly with Dify/Flowise | New workflow product, editor and execution semantics | Outside the initial scope |

This recommendation is the author's proposal, not an approved product strategy.

## Competitors verified online

The sources below are upstream READMEs and license files retrieved during this
review. Features are upstream declarations, not independently benchmarked.
Branches and licenses can change; recheck at release. This is a focused market
comparison, not an exhaustive list. Hosted tiers may have different terms.

| Product | Overlap with Universal AI Kit | Implication | License evidence |
|---|---|---|---|
| [Cheshire Cat](https://github.com/cheshire-cat-ai/core/blob/1.9.2/README.md) | API-first agents, RAG, plugins, tools, forms, admin UI | Closest conceptual reference; v1.9.2 is a fixed comparison baseline | [GPLv3](https://github.com/cheshire-cat-ai/core/blob/1.9.2/LICENSE) |
| [Dify](https://github.com/langgenius/dify/blob/main/README.md) | LLM applications, visual workflows, RAG, agents, model management, API | Competing on breadth would require a much larger product | [Modified Apache-based license](https://github.com/langgenius/dify/blob/main/LICENSE), including multi-tenant-service and branding conditions |
| [Flowise](https://github.com/FlowiseAI/Flowise/blob/main/README.md) | Visual agent construction, integrations, APIs, self-hosting | Differentiate through code/API integration rather than a new canvas | [Apache-2.0 with commercial exceptions](https://github.com/FlowiseAI/Flowise/blob/main/LICENSE.md) for enterprise paths and designated files |
| [Langflow](https://github.com/langflow-ai/langflow/blob/main/README.md) | Visual workflows, Python components, agents, API/MCP deployment | Strong alternative when visual composition is the primary need | [MIT](https://github.com/langflow-ai/langflow/blob/main/LICENSE) |
| [AnythingLLM](https://github.com/Mintplex-Labs/anything-llm/blob/master/README.md) | Local document chat, agents, API, widget, memories, MCP | Onboarding and a working document-to-chat demo are essential | [MIT](https://github.com/Mintplex-Labs/anything-llm/blob/master/LICENSE) |
| [RAGFlow](https://github.com/infiniflow/ragflow/blob/main/README.md) | Document ingestion, retrieval, citations, agents | Advanced parsing/retrieval is an established specialty; do not promise parity | [Apache-2.0](https://github.com/infiniflow/ragflow/blob/main/LICENSE) |
| [Open WebUI](https://github.com/open-webui/open-webui/blob/main/README.md) | Self-hosted model UI, RAG, tools, memories, integrations | End-user chat alone is not a sufficient differentiator | [Custom license](https://github.com/open-webui/open-webui/blob/main/LICENSE) with branding restrictions and stated exceptions |

Cheshire Cat's current [main README](https://github.com/cheshire-cat-ai/core/blob/main/README.md)
warns that v2 is unstable alpha. V1 and v2 must not be combined into an alleged
single stable feature set. No star counts, pricing or performance rankings were
used in this assessment.

## What exists and what is needed

| Area | Repository evidence | Decision |
|---|---|---|
| Chat/history/SSE, assistants, SDKs/widget/console | Gateway routes, SDK packages and console already exist | Reuse; WebSocket parity is not a launch requirement |
| RAG/file ingestion | Worker, parsing, embeddings, Qdrant, KB versions and citations exist | Demonstrate end to end; keep Qdrant optional |
| Safe public source distribution | `scripts/release.py:source_archive` walks the working directory instead of tracked release sources | Block public bundles until corrected |
| License | No root LICENSE; README says proprietary, npm says UNLICENSED, PHP says proprietary, image labels and SBOM say proprietary | Implement GPLv3 consistently after verifying rights and dependency obligations |
| Community support | No tracked root CONTRIBUTING/SECURITY documents or issue/PR templates found | Add a small usable contribution and vulnerability-reporting path |
| First-run experience | Setup guide exists but clone URL is a placeholder; its bootstrap omits RustFS credentials still required by Compose interpolation | One safe bootstrap path, clean-clone proof and two integration demos |
| Isolated plugin tools | Registered and independently executable, but `_available_tools` in `tool_loop.py` admits only builtin/http executors | Connect existing isolated tools to the agent before adding another protocol |
| URL ingestion | `WebLoader` is a protocol; current parsers only consume bytes | First new RAG feature; reuse jobs, storage and parsing |
| Skills | SDK loader/registrar exist; Go and Python assistant validators reject nonempty skills | Connect existing implementation after core release |
| MCP | Executor enum exists; no implemented MCP adapter found | Add a bounded remote read-only client after existing extension paths work |
| Semantic conversation memory | Explicitly rejected by assistant validators | Later, opt-in with isolation, provenance and deletion |
| Write agents | Approvals and durable effect journal exist separately; model loop is read-only | Later, complete persistence/resume and human review before enabling writes |
| Conversational forms | No CatForm-equivalent execution found | Later, schema-driven state over existing conversation/run persistence |
| Provider breadth | One active provider configuration, OpenAI-compatible/native Ollama | Document compatible proxies first; add native adapters only for demonstrated demand |

## Release blocker: packaging local state

Observed implementation: `source_archive()` uses `ROOT.rglob('*')` and a directory
denylist. `.env`, `.bootstrap-admin-key`, `.aws`, `.codex` and `.worktrees` are not
excluded by that list. A temporary synthetic repository fixture confirmed that
all five can enter the generated source tarball. No real secret values were read
or placed into an archive during this review.

The later artifact checker rejects a member named `.env`, but that does not make
archive creation safe: the archive already exists, and plain bootstrap tokens or
other credential files are not reliably covered by its narrow patterns. The
checker also skips members larger than 5 MiB. Fix selection at the source and
retain scanning as defense in depth.

A filename-only check found none of `.env`, `.bootstrap-admin-key`, `.aws`,
`.codex`, `.agents` or `.worktrees` tracked in the current checkout; a history
path query found no occurrences for those exact paths. This does **not** prove
that history, renamed files or artifacts are secret-free. Neither gitleaks nor
trufflehog was available on PATH. Run a redacted full-history scan before release.

Do not distribute the current working-tree source bundle. Export the reviewed
commit, build from that same clean checkout, and check bundle membership against
the export manifest. Inspect any previously generated artifacts before reuse.
Extend `.dockerignore` as well: its current rules exclude `.env` but do not
explicitly exclude the other credential/agent/worktree paths identified above.

## Release blocker: clean-template Compose setup

With `.env.example` and synthetic values for the three secrets generated by the
README, `docker compose --env-file .env.example config --quiet` fails because
`RUSTFS_ACCESS_KEY` and `RUSTFS_SECRET_KEY` are required by interpolation even
without the S3 profile. The unified bootstrap must produce all required Compose
credentials, including these two, or optional-service configuration must be
separated without weakening validation when enabled. No containers were started.

## GPL decision

The user's direction is GPL. The proposed precise SPDX identifier is
`GPL-3.0-only`; `GPL-3.0-or-later` is an alternative requiring an explicit choice.
The approved implementation now applies `GPL-3.0-only` to first-party code.

- GPL permits commercial use, redistribution for a fee and private modification.
- Distribution of covered modified/combined works must satisfy GPL obligations,
  including the required corresponding source; recipients retain GPL rights.
- Running a modified server for remote users alone is not the AGPL network-source
  trigger. Choose AGPL only if that additional obligation is wanted.
- An independently implemented app calling HTTP endpoints is not automatically
  GPL merely because the server is GPL. Incorporating/distributing GPL SDK code
  can create different obligations; document the boundary accurately.
- The default proposal is one GPLv3 license for first-party code. If proprietary
  SDK adoption is important, consider an explicit SDK exception or permissive SDK
  license as a separate owner decision; do not silently add one.
- Verify ownership/contributor rights before relicensing. Preserve third-party
  licenses and notices; inspect LGPL psycopg/binary distribution and container
  components separately. A license allowlist is not a legal compatibility proof.
- The current `tests/release/test_release_checks.py` explicitly expects
  `GPL-3.0-only` to be rejected. The release gate, SBOM, image labels, manifests
  and documentation must all change together.

Reference: [GitHub's GPLv3 guide and license text](https://github.com/github/choosealicense.com/blob/gh-pages/_licenses/gpl-3.0.txt).

Free source does not mean free model inference, hosting, storage or managed
support. Offer a local Ollama path and an external-provider path, with their
resource/cost requirements stated. Do not bundle model weights under the code's
license.

## Release scope and validation

The first public release can ship with read-only agents and no semantic memory
if these limits are visible in README, console and examples. Full Cheshire Cat
parity is not a prerequisite. Keep one gateway/runtime per database as the
supported topology until leases/rate limits are designed for replication.

In this planning turn, packaging behavior was reproduced with synthetic data
and clean-template Compose interpolation was checked with synthetic credentials.
Metadata/source paths were inspected. No full security audit, dependency
compatibility determination, production load test, GitHub CI run or public
publication was performed. The earlier turn's 72 targeted test passes are
historical evidence, not a fresh full-suite result.

Fresh checks: all 8 existing release unit tests passed, the source metadata gate
passed for 0.1.0, and the new documents' local links/navigation registrations were
checked. These checks do not prove safe archive contents or GPL readiness.
The MkDocs strict build could not run because `mkdocs` is not installed in the
active Python environment; no documentation dependencies were installed.

## Implementation update

The user approved proceeding with the GPL direction. First-party code, standalone
packages and OCI metadata now use GPL-3.0-only. Source export and package/image
builds use the verified commit; local-state paths and unsupported links fail
closed. The bootstrap generates all required Compose credentials with exclusive
0600 file creation and refuses to overwrite an installation.

The implementation adds narrow historical Gitleaks suppression for one reviewed
synthetic Idempotency-Key fixture; all-ref history scanning otherwise reports no
findings. Full tests, package builds, strict MkDocs (using a temporary docs
environment), 25 browser tests, Docker E2E, upgrade and restore checks passed.
Three real-service opt-in runtime tests remain skipped. Independent review found
two release-provenance issues; regression tests reproduced both before fixes.

These local results do not themselves authorize publication. The exact clean
candidate still needs its source/package/image artifacts and corresponding-source
obligations checked before distribution. Private vulnerability reporting must be
verified/enabled on GitHub at the public-release gate. Later capabilities remain
separate milestones.

See the [implementation plan](superpowers/plans/2026-10-29-github-release-and-capabilities.md)
for ordered work, owners, acceptance gates and deferred features.
