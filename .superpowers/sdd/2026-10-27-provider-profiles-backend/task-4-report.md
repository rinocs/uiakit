# Task 4 Report: Profile CRUD API and Provider Plane Push

## Status

Implemented the named provider profile CRUD API and internal provider-plane builder/push. The legacy provider handlers remain in place and the existing gateway scenarios continue to pass.

## TDD evidence

### RED

Command:

```text
cd apps/gateway && go test ./ -run TestProviderProfileCreatePushesPlaneRevision -count=1 -v
```

Observed failure:

```text
=== RUN   TestProviderProfileCreatePushesPlaneRevision
... status=502: {"error":"provider_pending"}
--- FAIL: TestProviderProfileCreatePushesPlaneRevision
FAIL
```

This was expected: the new route sent the profile-plane payload while the test runtime still decoded only the legacy singleton `providerRuntimeConfig`, so the plane could not be applied successfully.

### GREEN

Focused regression tests:

```text
cd apps/gateway && go test ./ -run 'TestProviderProfile|TestRuntimePlaneDecrypts' -count=1
```

Result:

```text
ok github.com/universal-ai-kit/gateway 0.011s
```

Full gateway suite and vet:

```text
cd apps/gateway && go test ./ -count=1 && go vet ./...
```

Result:

```text
ok github.com/universal-ai-kit/gateway 0.174s
```

Race suite:

```text
cd apps/gateway && go test -race ./ -count=1
```

Result:

```text
ok github.com/universal-ai-kit/gateway 1.901s
```

The repository root has no Go module; the required Go commands were therefore run from `apps/gateway`, where the module lives.

## Implementation

- Added public profile view/input/list types and validation for profile IDs, names, URLs, token limits, model limits, model IDs, duplicate models, capability rules, and namespaced model-length limits.
- Added `GET /v1/providers`, `POST /v1/providers`, and `GET|PUT|DELETE /v1/providers/{id}` with the existing scope enforcement and ETag/If-Match conventions.
- Added credential-free public views exposing only `secret_source`, `secret_configured`, and `secret_readable`; stored values and cipher material are not serialized.
- Added internal `providerRuntimePlane`/`providerRuntimeProfile` payload construction, stored-secret decryption through the existing `secretBox`, environment-reference propagation, runtime apply, model synchronization, and applied-revision marking.
- Added in-use model checks for profile deletion and pending-write handling that leaves the saved row intact when runtime apply fails.
- Updated gateway test fakes to understand the profile plane and global profile config sequences while preserving legacy test behavior.
- Added focused profile API, validation, plane, secret isolation, delete protection, and pending-write regression tests.

## Changed files

- `apps/gateway/provider.go`
- `apps/gateway/provider_test.go`
- `apps/gateway/provider_profiles_task4_test.go`
- `.superpowers/sdd/2026-10-27-provider-profiles-backend/task-4-report.md`

## Self-review findings

- Public profile responses contain no stored secret, cipher, nonce, or environment-reference value beyond the intended source/configured/readable flags.
- Stored credentials are decrypted only by `runtimePlane` using the existing `secretBox`; crypto was not reimplemented.
- Delete checks each profile/model namespaced key and returns `profile_in_use` before deleting an in-use profile.
- Runtime apply failures return `provider_pending` after the profile row has already been saved.
- The legacy handlers, routes, fake runtime behavior, and existing tests remain passing.
- Plane model IDs remain bare profile model IDs; no profile prefix is added by the gateway payload builder.
- No unrelated tracked source file was changed; the generated `apps/gateway/gateway` binary was restored and is not part of the change.

## Concerns

No known functional concerns remain for Task 4. The root-level `go test ./ -count=1` form is not runnable because this repository has no root Go module; the equivalent required suite was run from `apps/gateway`.
