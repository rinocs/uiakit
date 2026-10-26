# ADR 0011 — SDK, widgets and administrative console

**Status:** proposed for future milestones. The explicit constraints of PROJECT_SPEC.md
remain mandatory; this document does not declare the proposed capabilities implemented.
**Date:** 2026-10-22.
**Related tasks:** M5-01…M5-10. Tabs and dependencies in [backlog](../TASKS.md).
**References:** [specification](../project-spec.md), [ADR 0001](0001-functional-core.md).

## Context

The platform must integrate into different applications without exporting administrative credentials to the browser. Consoles and chatbots have different privileges.

## Alternatives considered

Independent SDKs written without contracts diverge. UI with administrative key in JavaScript is excluded. Clients validated against OpenAPI and dedicated tokens separate the two flows.

## Proposed decision

SDK Order TypeScript, PHP/Laravel, Go; all validated on the public contract and shared SSE fixtures. Web Component widget with sanitized Markdown, whitelisted quotes, callback/theme/accessibility and scoped session token issued by trusted backend. Minimal SvelteKit console with administrative session and secrets kept server-side; API continues to apply RBAC. Console manages assistants/templates/directives, KB/documents, tools/plugins/approval, conversations/run/log and playground. No initial workflow editor.

## Consequences and limits

Console sessions and widget tokens have separate lifecycles and revocations; their cookies/tokens require CORS/CSRF consistent with the chosen transport. The SvelteKit choice is proposed in the set of technologies permitted by the specification; no frontend has already been implemented.

## Verification required

Contract matrix SDK, server-side Laravel example, broken SSE parser, XSS/unsafe URL, token expired or out of conversation, keyboard/screen reader test and mobile viewport. Bundles and network payloads do not contain admin keys.

## Subsequent changes

Update status and tasks with evidence when the decision is implemented. A change
incompatible requires a new ADR that replaces this one, without erasing its history.