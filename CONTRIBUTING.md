# Contributing

Universal AI Kit is licensed under **GPL-3.0-only**, including its SDKs and
examples. By submitting a contribution, you license it under those same terms
and confirm that you have the right to contribute it. Dependencies retain their
own licenses; do not copy code without checking its terms and provenance.

Discuss substantial features in an issue before implementing them. Include the
problem, a concrete use case and the smallest proposed change. Bug reports should
include the version, reproduction steps and redacted logs. Never attach `.env`,
API keys, customer documents or database backups.

## Development

Follow [the installation guide](docs/installation.md) and use an isolated branch.
Python requires 3.12+, Node 20+, PHP 8.2+; CI pins the tested toolchain in
`.github/workflows/test.yaml`. Tests requiring Docker use isolated fixture stacks,
not your production database.

```bash
python3 -m venv apps/runtime/.venv
apps/runtime/.venv/bin/pip install -r apps/runtime/requirements-dev.txt \
  packages/core packages/plugin-sdk packages/fastapi plugins/examples/hello
npm ci --prefix packages/sdk-typescript
npm ci --prefix packages/chat-widget
npm ci --prefix apps/console
composer install --working-dir=packages/sdk-php
PATH="$PWD/apps/runtime/.venv/bin:$PATH" make test
make build-packages
```

For release-tool changes, the smallest check is:

```bash
python3 -m unittest discover -s tests/release -p 'test_*.py'
python3 tests/release/check_release.py --source
```

Run the relevant tests first, then the documented full checks for changes that
span the platform. New behavior needs regression coverage, including ownership,
error paths and cancellation where applicable. If an optional service test did
not run, report it as skipped. Keep API contracts, SDKs, console and documentation
consistent. Avoid new services/dependencies when an existing owner can do the job.

Open pull requests against `main` with the problem, resulting behavior and exact
verification results. Keep unrelated work out of the diff. Maintainers review
licensing, compatibility, authorization and data-loss risks before merging.

## Security

Follow [SECURITY.md](SECURITY.md) for private vulnerability reporting. Do not
publish exploit details or real secrets in a public issue or pull request.
