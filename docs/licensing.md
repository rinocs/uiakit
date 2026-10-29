# Licensing and redistribution

Universal AI Kit first-party source, SDKs, plugins and examples use
**GPL-3.0-only**. The canonical license text is [LICENSE](https://github.com/rinocs/uiakit/blob/main/LICENSE).
Standalone packages contain the same text. No SDK exception or dual license is
currently offered. The project is provided without warranty under the license.

GPL allows commercial use, private modifications, redistribution and charging
for copies or services. When distributing covered modified/combined works,
preserve copyright/license notices, document changes, retain GPL rights and
provide the required corresponding source under GPL. Source includes the build
and installation material required by the license, not merely a link to an
unrelated version of the repository.

## Applications and SDKs

An independently written application communicating with the server over HTTP is
not automatically GPL merely because it uses that API. Incorporating GPL SDK or
plugin code into a distributed combined work may carry different obligations.
Check the actual combination and distribution model before embedding the SDK in
a proprietary application. The API can also be called with an independently
implemented HTTP client.

GPL does not impose AGPL's additional source-offer condition merely because
users interact remotely with a modified server. This project uses GPL, not AGPL.
A future license change does not retract rights already granted for released code.

## Dependencies and models

Dependencies retain their own terms; GPL on this repository does not relicense
third-party code or model weights. Generate the SBOM and notices with
`python3 scripts/release.py inventory --output release` in the clean release checkout, and review upstream
license texts and source obligations before distributing images or bundles.
The allowlist is a review gate, not a complete legal compatibility determination.

In particular, psycopg/psycopg-binary use LGPL terms, container base images include
additional system packages, and model weights require separate permission. Do
not bundle weights as GPL software. Record exact dependency versions, upstream
source locations, required notices, and any source/build offers for distributed
binaries. The initial public candidate can distribute first-party source without
redistributing third-party binaries; image/SDK publication is a separate gate.

## Release provenance

Distribute only the reviewed commit's sources, LICENSE, relevant notices, pinned
manifests and build/deployment instructions. Preserve the manifest/checksums and
make the exact corresponding source available alongside any reviewed binary
release. Never include credentials, customer data or local worktrees.

Contributions must be made by an authorized copyright holder and accepted under
the same GPL terms; see [contributing](https://github.com/rinocs/uiakit/blob/main/CONTRIBUTING.md).
