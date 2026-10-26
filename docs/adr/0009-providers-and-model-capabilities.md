# ADR 0009 — Provider, capability and budget model

**Status:** proposed for future milestones. The explicit constraints of PROJECT_SPEC.md
remain mandatory; this document does not declare the proposed capabilities implemented.
**Date:** 2026-10-22.
**Related tasks:** M1-03, M2-03, M3-07, M4-06, M4-07, P-03, P-08, P-09. Tabs and dependencies in [backlog](../TASKS.md).
**References:** [specification](../project-spec.md), [ADR 0001](0001-functional-core.md).

## Context

An OpenAI-compatible endpoint does not guarantee tool calling, usage, embeddings or structured output. The M1 character limit is not a complete measure of the context window.

## Alternatives considered

A mandatory universal library introduces dependencies and hides differences. Small adapters with explicit capabilities maintain replaceable providers and verifiable limits.

## Proposed decision

Extend the existing ModelProvider, without duplicating it in a new framework. Operator-configured template catalog with actual chat/streaming/tool_calling/structured_output/embeddings/reranking/vision, context windows, and secret references. OpenAI-compatible adapter and explicit Ollama; LiteLLM optional. Separate EmbeddingProvider/Reranker from chat streams. Tokenizer/counter consistent with provider and input/output/run budget; unknown use remains unknown, cost calculated only with declared rates. Normalized timeouts and errors; limited retry for transient errors only before output and without duplicating effects. No retry after delta.

## Consequences and limits

The model can reject a capability even if configured: normalized runtime error and administrative diagnosis. We do not simulate structured output or vision support with non-validated text. M1 continues with conservative limits until the token-aware budget arrives.

## Verification required

Contract suite for providers with immediate delta, malformed frame, truncation, usage, partial tool args and missing capability. Embedding change requires new index version. No cloud calls in unit tests.

## Subsequent changes

Update status and tasks with evidence when the decision is implemented. A change
incompatible requires a new ADR that replaces this one, without erasing its history.

## Implementation M2-03

Authenticated and public-safe catalog implemented for the OpenAI-compatible adapter,
chat/streaming capability, model snapshots in runs and preflight validation.
Context window unknown remains null; additional provider/capability and budget tokens
remain in future tasks. See [ADR 0013](0013-assistant-version-snapshots.md).