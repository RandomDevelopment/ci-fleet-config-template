# Template releases

## Unpublished complete local validation

The standalone template adds one complete local validation entry point,
`scripts/local_validate.py`, with explicit Git identities, independently pinned
engine policy, separate trusted-suite identity, isolated temporary checkouts,
tool versions, per-check logs and digests. It preserves policy rejection cases,
updater safety, exact-core and external deployer compatibility, immutable
release-update fixtures, committed-history scanning, reference/multi-host
validation and initializer success/failure checks.

Each stage uses fresh source, engine-policy and trusted-suite checkouts from
verified seeds. Direct manifests cover bytes, types, modes, symlinks and Git
metadata; changes fail before a stage can pass. A successful command also fails
if a live descendant requires `SIGKILL` after its cleanup allowance. These checks
prevent persistent substitution between stages, but do not sandbox hostile root
or transient same-stage tampering. Independent review, supervised disposable
Linux execution and a separate signing authority remain required.

Hosted configuration validation becomes an explicit convenience, default off
through `CI_FLEET_HOSTED_VALIDATION`. Opting in also requires the independently
reviewed full engine SHA in `CI_FLEET_VALIDATOR_REVISION`. The workflow calls
the same complete local entry point with existing read-only permissions. The
optional job and check context are `hosted-validation`, never `validate`.
Neither its result nor its skipped state satisfies an existing required
`validate` check or the updater's gate. The flag leaves application Actions
scheduling, self-hosted fleet workflows and the separately authorized
repository-writing updater unchanged. The updater
retains its existing classic-protection and required-`validate` gate; manual
verified imports remain the maintenance path without Actions.

The ordinary-CI compatibility baseline remains
`aa9bbb27a4746fc80ce27d8932de68450b28364b`; fleet schema, example controller
engine pins and published release identities are unchanged. The core signed
local-evidence contract is pending
[ci-fleet PR #137](https://github.com/RandomDevelopment/ci-fleet/pull/137),
current proposed head `a1451c024e0be642ecb60715980515da1868e85c`. That proposal is
unmerged and is not a merged or released compatibility baseline. A developer
result does not establish trusted host acceptance. A supporting merged engine,
independently reviewed suite, external signing authority, compatible
executing/candidate/checkpoint managers and tested recovery are separate gates.

See [the complete command and evidence boundaries](LOCAL-VALIDATION.md),
[migration and rollback](UPDATING.md#local-validation-and-hosted-cutover), and
the [setup guide](../README.md). Existing required checks remain in force until
deliberately migrated after coverage and recovery proof. A future release
must record exact final-commit results and documentation impact without
rewriting the historical sections below. This change publishes no release,
promotes no private engine and activates no host or policy.

## Unpublished Docker policies and operator guidance

The current template reviews the ordinary-CI schema-v3 contract at ci-fleet
commit `aa9bbb27a4746fc80ce27d8932de68450b28364b`. It adds optional staged
`docker_network_policy.default_bridge_cidr` and opt-in
`docker_storage_retention` support. Existing configurations that omit them keep
their behavior. Full public fleet examples retain engine
`8df97cc7575f47696fa82a179bbe39cd2874b1ca` and omit optional fields. The new
`examples/docker-network-policy.json` is a review-only RFC 5737 fragment, not
an installable controller declaration.

The initializer still writes a configuration without optional fields. Its
explicit `--default-bridge-cidr` option prints a proposed policy fragment for
review. Adopters must choose operational CIDRs and complete the documented
engine/capability staging before adding the fragment. Storage retention stays
absent until a separate reviewed change admits an exclusive ordinary-CI daemon
on a supporting engine. Transition validation rejects admission on a new
controller and any pin change while retention admission is present in either
the previous or current configuration. Remove admission in an earlier change,
upgrade with it absent, then separately verify the new engine and daemon before
re-admission. It adds no rollout-evidence flag. These checks do not prove live
engine activation or daemon inventory.

The schema and validator also limit retention declarations to `active` or
`drained` controllers. Admission requires an `active` or `drained` predecessor,
including when admission is retained. Remove admission when disabling, and
enable a disabled declaration without admission before a later verified
admission change.

Operator guidance also covers rejected upgrades and uncertain recovery against
merged engine `ad5fd55c68fdc269332e187eef329ae881cb9b27`, and optional verified
Codex reviews against `f5d3c45dd4eb09ac9cefe16bde7a457673fff678`. Those host
contracts have their own adoption prerequisites. They do not change the
ordinary-CI compatibility pin, activate a host gate or prove recovery.

See the [configuration and setup guide](../README.md),
[adoption procedures](UPDATING.md), and independent
[deployment boundary](DEPLOYMENT-POLICY.md). These changes are unpublished.
They do not publish the prepared v1.0.1 release, change an existing release
identity, promote an adopter engine or authorize host activation. A future
release must use a new immutable identity and pass the checklist below.

## Unpublished deployment boundary v2

The boundary-v2 change added external staging-deployer adoption,
pinned independently to merged ci-fleet commit
`c67d18d24ceb5f22569d8887b94f7198a448ccde`. That change left fleet schema v3,
the ordinary-CI compatibility baseline, initializer, validator, examples and
controller engine pins unchanged. The subsequent ordinary-CI additions are
recorded above. Production operations, testers, image builders and deploy-ref
writers remain excluded.

See [deployment policy](DEPLOYMENT-POLICY.md) and
[migration and rollback](UPDATING.md#deployment-boundary-v1-to-v2). This changes
the deployment compatibility boundary, so the weekly updater requires manual
handling. No release or host activation occurs with this implementation. A
future release must record the deployer pin as well as the ordinary-CI reviewed
core, pass final-commit checks and follow the immutable-tag checklist below.
The historical prepared v1.0.1 notes and published v1.0.0 identities remain
unchanged.

## Prepared v1.0.1 release

`v1.0.1` is a proposed patch release, not a published release. The reviewed
changes are those merged after `v1.0.0` through template commit
`04f98d29c589994bd52012521585c5a9b98fb58b`, plus these release notes.

### Release notes

- Malformed host-group objects and non-string controller and host-group enum
  values now produce validation errors instead of Python tracebacks.
- Deployment policy boundary v1 explicitly limits executable support to
  ordinary CI. Deployment inventory and secret names do not establish approval
  or authorize deployment. Persistent tester, image builder, deployer, and
  deploy-ref-writer roles remain excluded.
- The adopter update guide verifies the published `v1.0.0` tag object on a
  first import, including when the adopter has no `TEMPLATE_RELEASE` record.
  Regression coverage also rejects an annotated tag rewritten to point to the
  same commit.
- Documentation records the published initial release and distinguishes it
  from the historical preparation state in `template-compatibility.json`.

### Compatibility and adoption

No schema migration or engine upgrade is required. The fleet schema remains
version 3. The schema, initializer, example configurations, active rollout
evidence, and CI workflow are unchanged from `v1.0.0`. The reviewed core remains
`0aed0d7e85e10050028b7d11fb12b84b3619e638`, and the example engine remains
`8df97cc7575f47696fa82a179bbe39cd2874b1ca`.

The validator changes reject malformed input without changing the accepted
schema-v3 contract. Approval fields and privileged role extensions were already
unsupported in `v1.0.0`; this release documents that boundary and adds regression
coverage. Follow [the adopter update procedure](UPDATING.md) once the new release
is published. Preserve adopter-owned configuration and rollout evidence.

### Readiness evidence

The review of the merged baseline found no blocker to preparing a patch release:

- [Baseline CI passed](https://github.com/RandomDevelopment/ci-fleet-config-template/actions/runs/38117423528)
  on `04f98d29c589994bd52012521585c5a9b98fb58b`.
- Local policy tests passed, 81 tests. Exact core compatibility passed, including
  the three repository-identity tests and staged capability checks. All six
  release-update tests passed.
- Reference configuration validation passed. An initialized fictional adopter
  passed `./scripts/validate.sh --strict --config <initialized-fleet.json>` with
  repository path scanning enabled.
- `./scripts/validate.sh --strict` against the public placeholder configuration
  returned the two expected errors requiring replacement of the example
  organization and repository. Public fixtures must remain fictional.
- GitHub still reports the initial annotated tag object as
  `0e54aaa09d0565ce103035f213953639fc068a73`, peeling to
  `cf4a4d143540e0c70e1f301061038bbf95f04398`.

Publication still requires review and passing CI on the final release commit,
an explicitly authorized new annotated tag, and release notes recording that
tag object and peeled commit. These baseline checks do not establish validation
of a future release commit. No adopter configuration or host was changed.

## Published v1.0.0 release

The [`v1.0.0` template release](https://github.com/RandomDevelopment/ci-fleet-config-template/releases/tag/v1.0.0) was published on September 2, 2026. It is a non-draft, non-prerelease release with the following reviewed identities:

- Annotated tag object: `0e54aaa09d0565ce103035f213953639fc068a73`
- Peeled template commit: `cf4a4d143540e0c70e1f301061038bbf95f04398`
- Reviewed ci-fleet commit: `0aed0d7e85e10050028b7d11fb12b84b3619e638`

Publication is recorded in [issue #12](https://github.com/RandomDevelopment/ci-fleet-config-template/issues/12#issuecomment-5515033394), with [passing post-merge validation](https://github.com/RandomDevelopment/ci-fleet-config-template/actions/runs/33671685334). This release did not deploy infrastructure or activate private configuration.

The release synchronizes the standalone schema-v3 contract with `templates/config-repository` at the reviewed ci-fleet commit above. It adds optional staged status-reporting and Docker network-policy support. Existing configurations that omit either field remain valid.

The fictional examples retain engine commit `8df97cc7575f47696fa82a179bbe39cd2874b1ca` and omit both optional fields. Network-policy validation fixtures use RFC 5737 ranges only. A private adopter may add a reviewed operational `default_address_pools[].base` CIDR only after the compatible engine and capability evidence have existed in prior integrated states.

## Historical preparation and future releases

The `template_release.state: prepared-not-published` value in `template-compatibility.json` records the historical preparation state committed before publication. Its compatibility details still describe the reviewed contract. The release and tag evidence above establish publication. Keep the preparation record and released commit unchanged.

For a future, separately authorized release:

1. Confirm the exact release commit passes the complete local suite and every
   check still required by the deliberate acceptance policy. Preserve its
   source/base/tree, trusted suite/engine identities, logs and independent
   review. Missing, skipped or unavailable hosted checks are not passing
   evidence. Do not use an unmerged engine proposal as the release's merged
   compatibility baseline.
2. Create a new, higher SemVer annotated tag at that exact commit.
3. Publish release notes that name the new tag object ID, peeled template commit, and the core commit reviewed for that release. Include exactly one of each of the following lines, with full lowercase 40-hex IDs, so the adopter updater can verify them:

   ```text
   - Annotated tag object ID: `<tag-object-id>`
   - Template commit: `<peeled-template-commit>`
   - Reviewed ci-fleet commit: `<reviewed-core-commit>`
   ```

   For boundary v2 or later, also include exactly one deployer identity line:

   ```text
   - Reviewed deployer ci-fleet commit: `<reviewed-deployer-core-commit>`
   ```

   The ordinary-CI core commit must match top-level `reviewed_core` in
   `template-compatibility.json` at the release commit. The deployer line must
   match `deployment_policy_boundary.standalone_deployer.reviewed_core` and
   use a full lowercase 40-hex commit. The updater rejects missing, duplicate,
   malformed or mismatched deployer identities. Published boundary-v1 releases
   retain their original three identity lines and require no new field.
   The tag must directly name the template commit, rather than another tag.
   Stable tags use `vMAJOR.MINOR.PATCH` with no leading zeroes. The updater
   ignores draft releases and prereleases.
4. Never retarget the tag. Correct a bad release with a new higher tag and mark the old release as superseded.

Use the [adopter update guide](UPDATING.md) to record and verify the reviewed tag object before importing a release. Never retarget or recreate `v1.0.0`.

The weekly updater is a standalone template tool. It changes no fleet schema, initializer, validator, example engine pin, or reviewed core contract. It adds a workflow and tests beyond the prepared patch-release baseline above. Shipping it requires a future release under the checklist above; this implementation does not publish one or alter `v1.0.0`.
