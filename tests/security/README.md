# Security regression matrix

`matrix.json` is the permanent contract for security regressions. Every trust
boundary names at least one **deny** and one **allow** test. The checker verifies
that each referenced test still exists and that every referenced E2E script is
scheduled by `tests/e2e/run.sh` (directly or through the runtime fixture mount in
`tests/e2e/compose.yaml`).

```bash
make test-security                                       # static config + matrix + referenced tests
python3 tests/security/check_matrix.py                   # validate references only
python3 tests/security/check_matrix.py --run             # execute referenced Go/Python/TS tests
```

Boundaries:

| Boundary | Unit evidence | E2E evidence |
|---|---|---|
| credentials and bootstrap | Go auth/server tests | `check_auth.py` |
| scopes | Go assistants/documents/approvals tests | `check_auth.py` |
| ownership | Go KB/documents tests | `check_auth.py`, `check_documents.py`, `check_knowledge_bases.py`, `check_versions.py` |
| widget tokens and CORS | Go widget tests | `check_integrations.py` |
| internal runtime auth | Python runtime/hooks tests | – |
| prompt injection and retrieval | Python tool/rag/directive tests | `check_directives.py` |
| SSRF, DNS pinning, redirects | Python HTTP tool tests | `check_tools.py` |
| upload, parser and path limits | Go documents, Python storage/parser/skills tests | `check_documents.py`, `check_ingestion.py` |
| XSS | chat-widget Markdown/URL tests | `make test-widget` |
| plugin boundary | Go plugin, Python isolated tests | `check_plugins.py`, `check_plugin_admin.py`, `check_isolated_plugin.py` |
| approval/replay/idempotency | Go approvals/server, Python approval tests | `check_approvals.py`, `check_tool_executions.py`, `check_versions.py` |
| log and audit redaction | Go audit, Python audit/hooks tests | `check_approvals.py`, `check_observability.py` |
| secrets never plaintext | Go credential, Python secret tests | `check_auth.py` |
| rate limit and egress storage | Go limiter, Python egress tests | `make test-security` |
| knowledge-base isolation | Go KB, Python RAG tests | `check_knowledge_bases.py`, `check_rag.py` |

The matrix is deliberately backed by existing focused tests: it adds a
regression contract and execution gate without duplicating the suites. New trust
boundaries must be added to `required` and to `boundaries` with both cases.
