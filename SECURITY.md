# Security policy

## Supported versions

The project is currently a 0.1.0 release candidate. Only the latest reviewed
release receives fixes; no long-term-support policy or response-time SLA is
promised. Do not expose the runtime, PostgreSQL or Qdrant directly to the internet.
See [security operations](docs/security-operations.md) for deployment guidance.

## Reporting a vulnerability

Use [GitHub private vulnerability reporting](https://github.com/rinocs/uiakit/security/advisories/new)
if the repository's Security page offers **Report a vulnerability**. Availability
must be verified by maintainers before the first public release.

If private reporting is unavailable, open an issue containing only a request for
a private security contact, without vulnerability details, credentials, payloads
or affected customer data. Maintainers must establish a private channel before
accepting sensitive details. Do not treat a public issue as a private report.

A private report should include the affected version/commit, prerequisites,
reproduction using synthetic data, expected/actual behavior and impact. Redact all
secrets. Coordinate public disclosure with maintainers after a fix is available.

## Release checks

Source exports must come from a clean reviewed Git commit. Local credentials,
agent state, worktrees, backups and runtime data are forbidden in distributions.
Secret scanning is an additional control, not permission to distribute a working
directory. If a credential was exposed, revoke it; deleting a Git file or an
artifact alone does not revoke it.
