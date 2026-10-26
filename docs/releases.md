# Release and packaging

The release is **reproducible and does not automatically publish** packages, images
or registry. The pipeline prepares a verifiable bundle; publication and deployment
they remain separate authorized actions.

## Versioning

`VERSION` is the authoritative source. The versions in `pyproject.toml`, `package.json`
and the image tags in `compose.yaml` must match. The version
follows SemVer (`MAJOR.MINOR.PATCH`) and the Git tag is `v<version>`.

```bash
make test-release
```

The check fails if a version diverges, if a Python requirement is not
pinned with `==`, if a lockfile is missing or if a Dockerfile uses a base image
floating.

## Release gate

Run in a clean runner:

```bash
make test # include contract, security, capacity and release source check
make build-packages # SDK, widgets, console, plugins
make release-dry-run # inventory, packages, images, manifests and verification
```

`make release-dry-run` produces in `release/`:

- `sbom.cdx.json` — CycloneDX 1.5 with transitive lockfile dependencies;
- `THIRD_PARTY_NOTICES.md` — notices per ecosystem, including dev dependencies;
- `packages/` — npm pack, Python wheel, Composer archive, Go source e
  project source archive;
- `images/` — OCI images saved as tar, with version tags and labels;
- `images.json` — tag, image ID, tar hash and OCI label;
- `manifest.json` + `SHA256SUMS` — version, commit (if available), hash of
  lockfile, contract hash, hash of each artifact;
- `release source/artifacts check` — no `.env`, key or secret in
  artifacts.

No command runs `npm publish`, `composer publish`, or `docker push`.

## Images

The images are constructed with:

- tag `uai-<component>:<VERSION>`;
- `org.opencontainers.image.version`, `.revision` and `.licenses`;
- local saving in tar and SHA-256 hash;
- image ID registered in `images.json` (local content digest).

The GitHub pipeline loads the artifacts as workflow attachments and generates
the provenance attestation with `actions/attest-build-provenance`. He's not coming
published a registry: distribution requires a separate phase that you push
the images and sign the digests with the chosen registry.

## SBOM, licenses and vulnerabilities

- The pipeline also generates SBOM with Syft for the repository and for each image.
- `tests/release/check_licenses.py` applies an SPDX allowlist to the CycloneDX
  generated; `NOASSERTION` fails and requires explicit review.
- Vulnerability scan uses Grype on SBOM and images, with `--fail-on high`
  and `--only-fixed`; the report is attached to the bundle.
- The table in [dependencies.md](dependencies.md) remains the human synthesis; the
  SBOM is machine-readable evidence. Model weight licenses are not
  in the software SBOM: they must be verified separately before distributing a
  model.
- The project is proprietary (`LicenseRef-Proprietary`): notices are not
  grant licenses to the project's code.

## Contract compatibility

Before packaging the pipeline compares `packages/api-contract/public.openapi.json`
with the previous tag. `tests/release/contract_diff.py` blocks:

- path or operations removed;
- parameters removed or become mandatory;
- request/response properties removed;
- enum type changes and restrictions;
- new mandatory request fields.

A breaking change requires a major version and a documented migration;
the local baseline is the previous Git tag, not a duplicate file in the repository.

## Publishing and rollback

The release candidate is a set of verifiable files. Publish SDK/images
requires a separate phase, with registry credentials and review of
licenses/vulnerabilities. For upgrade, rollback and two instances see
[upgrades.md](upgrades.md) and [deployment.md](deployment.md); for the final gate e
the release candidate see M6-09.