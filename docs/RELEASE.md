# Template releases

## Unreleased CI efficiency changes

Compatibility corpora reuse verified pinned downloads and retain independent
corruption fixtures. Hosted validation ignores description-only edits, checks
title-only edits separately, fetches selected histories without unrelated refs,
and installs ShellCheck only when absent. Full-suite coverage and its existing
budget remain unchanged. The updater checks its token before checkout.

These changes require a compatible independently reviewed standalone suite pin.
They publish no release and change no required checks or host acceptance policy.

## Unreleased v1.2.0 preparation

The development template targets ci-fleet commit
`840fb9be8a1c69404a5eebcf17855eff13c6c928` for portable ordinary-CI
configuration. The independent external staging-deployer and shared executor
pins remain `689c7c00deb0eebcb25f2284334a9f7168a25575`. The merged engine includes
PR157 maintenance and unused-pending preparation support. This template remains
unreleased, and an import does not deploy it. Fleet schema remains v3.
Fresh strict configurations require reviewed controller/runner image scalars by
engine revision and architecture. The initializer requires those inputs.
Image-free adopters need the separate manager bootstrap migration, retained
runtime evidence and later image-policy activation. Both bootstrap revisions
require previously integrated target-engine sidecar evidence even when optional
reporting/network blocks are absent. Prepare explicit incumbent and pending
evidence against actual predecessors, preserve it through bootstrap, and promote
only after runtime verification. Do not replace stale pending evidence without
the reviewed cancellation contract. Standalone network/type and disabled-storage
safety checks remain in force.
Maintenance sequencing, preserved legacy idle blockers, strict admitted accounting
and actual scheduled reclamation acceptance are part of the prepared handoff.
The updater treats changed image-identity semantics as manual migration. The
engine, actual template revision and adopter import must pass their own gates
before deployment; an issue or preparation commit is not adoption.

The updater treats a managed-image policy change as manual migration even
without a schema-version bump. Current examples use the new engine pin with
fictional image scalars and omit unstaged optional policies. APT-cache adoption is
host-local and optional. See [managed images](MANAGED-IMAGES.md),
[APT cache](APT-CACHE.md) and [updating](UPDATING.md).

The development suite uses `ci-fleet-config-standalone-v2` and the separately
pinned shared core systemd executor. Prepare a disposable Linux worker and use
a clean independently reviewed compatible suite, independently pinned engine
policy and exact committed source/base identities. See
[local validation](LOCAL-VALIDATION.md). Focused policy and regression results
alone are incomplete full-suite evidence.

`v1.2.0` is prepared, not published. Its final template commit, annotated tag
object, independent review and exact-source source/adopter complete-suite
results remain release gates. No release or operational acceptance is claimed.
The latest published release remains `v1.1.0`. All published identities and
historical preparation records below remain unchanged. Preserve adopter-owned
configuration, evidence, runtime pins and established required checks. Template
publication, private promotion, host activation and signed host acceptance are
separate operations.

## Published v1.1.0 release

The [`v1.1.0` release](https://github.com/RandomDevelopment/ci-fleet-config-template/releases/tag/v1.1.0)
was published on October 16, 2026, at `2026-10-16T21:36:49Z` as GitHub release
`415399985`. It is a stable, non-draft, non-prerelease release.

- Annotated tag object ID: `a963f867ca5f9a968d7cb57088870e7cd8f5824e`
- Template commit: `32db46f1247b184f267bdc6c401d63b69598fe6e`
- Reviewed ci-fleet commit: `aa9bbb27a4746fc80ce27d8932de68450b28364b`
- Reviewed deployer ci-fleet commit: `c67d18d24ceb5f22569d8887b94f7198a448ccde`

Independent GitHub API readback and a fresh Git fetch verified the raw annotated
tag, its direct and peeled template commit, annotation, tagger and published
notes. The notes contain the four immutable identities above. Published
`v1.0.0` retains its original tag object, target, release identity and notes.
Never retarget or recreate either published tag.

The actual release source and a fresh initialized adopter each passed all
11 local stages without skips or retries, in 223.333 and 216.172 seconds
respectively. The independent trusted suite was
`0e061d5ae1c6ab3052e8537f6aaa85b9ce571edf`. The source's actual first parent was
`970e8c75758abe413770da65578b85a18e0f7196` and its tree was
`181539f036e1a417bcf473e49764f35a28c70d42`. See
[release preparation PR #36](https://github.com/RandomDevelopment/ci-fleet-config-template/pull/36)
for the recorded exact-source evidence. These are unsigned local functional
results. Hosted validation was skipped; enabled hosted execution and setup
timing remain unverified.

The release includes complete standalone local validation, hosted validation
that defaults off, the weekly updater, staged Docker policies and deployment
boundary-v2 guidance. Adoption from `v1.0.0` requires
[manual compatibility review](UPDATING.md#deployment-boundary-v1-to-v2).
Preserve adopter-owned configuration, active/next-engine evidence and runtime
pins. Publication does not establish signed host acceptance or authorize
private promotion, host activation or operational policy migration.

The proposal, sections headed "Unpublished" and final weekly-updater
implementation note below retain their prepublication wording as historical
preparation records. The published identities above establish the release.
The future-release checklist remains applicable to later releases.

## Proposed v1.1.0 release

`v1.1.0` is proposed and unpublished. It gathers the accumulated changes after
published `v1.0.0`, including complete local validation, optional independently
pinned hosted validation, trusted regression inventories, the weekly updater,
staged Docker policies and deployment boundary v2. The local-validation
implementation merged in [PR #34](https://github.com/RandomDevelopment/ci-fleet-config-template/pull/34)
at `59476db12ac88d4e746931270129d95456264551`, from reviewed head
`41c6d50a82682bf8932b4c3fb1d1aa1697be71c6`. The follow-up in
[PR #35](https://github.com/RandomDevelopment/ci-fleet-config-template/pull/35)
merged at `970e8c75758abe413770da65578b85a18e0f7196`, from reviewed head
`5e8eeb95094b556319a7800ba7167d3f37e8c198`. It tests candidate harness
programs, verifies copied stages, and runs independent adopter checks together.
This documentation prepares the subsequent release. The final release commit,
annotated tag object and exact-commit release evidence remain pending.
Historical prepared `v1.0.1` notes and published release records below remain
unchanged. At preparation time, the latest published release was `v1.0.0`.

The pinned suite owns seven required inventories: policy, updater,
release-update, local-validation caller, supervisor, candidate runner and
workflow tests. They exercise candidate programs, workflows and upstream
setup/release documents in trusted fictional fixtures. The outer driver and
supervisor stay pinned. Candidate-added IDs are supplemental and cannot replace
required tests. Plans must have unique nonempty IDs, executed counts must match,
and actual skips fail. Adopters retain the complete public-fixture corpus plus
applicable candidate-mapped checks. Missing optional workflows receive the
pinned local-availability test and explicit applicability. Runner self-tests use
trusted workflow fixtures without restoring an absent candidate workflow.

Initial narrow fetches create source, engine-policy and trusted-suite seeds.
Effective origin/main metadata is fixed before their manifests are frozen.
Each stage uses independent copies that preserve modes and symlinks without
hardlinks or repeated fetches. The driver verifies seeds before copying, each
copy before execution, and seeds and stage copies afterward. Adopter policy,
updater and release-update stages run the public and candidate checks together
in separate fixture copies. Stages stay sequential, and both checks must pass.
The pinned supervisor finishes descendant cleanup before the driver assembles
both outputs and diagnostics into the authoritative stage log. Test corrections
wait for fixture readiness before cancellation or timeout assertions.

Hosted validation defaults off. Opt-in requires `CI_FLEET_HOSTED_VALIDATION=true`,
a reviewed engine SHA in `CI_FLEET_VALIDATOR_REVISION` and a compatible reviewed
public template suite SHA in `CI_FLEET_SUITE_REVISION`. Candidate, engine and
suite occupy separate sibling checkouts; execution uses the suite's absolute
entry point. PR jobs execute only while open, with PR and main-push concurrency
identities kept separate. The optional job retains its five-minute limit.
Local payload timings exclude hosted checkout/tool setup. Post-merge source
validation with both histories took 245.039 seconds, above the four-minute
expected payload target. Refreshed source and initialized-adopter proofs took
221.877 and 214.033 seconds. These results do not establish final release timing
or that an enabled hosted run fits its limit. Optional hosted validation was
skipped; no enabled hosted run or setup timing is claimed. A timed-out optional
run remains failed; it does not prevent the complete local command from running.

Fleet schema remains v3. The ordinary-CI compatibility baseline remains
`aa9bbb27a4746fc80ce27d8932de68450b28364b`, and the independently reviewed
staging deployer remains `c67d18d24ceb5f22569d8887b94f7198a448ccde`. Local-evidence
engine support merged at `67beabbddaad73c19f15bc3baa227779bc88dc96`.
These identities do not change controller pins, activate capabilities or grant
host authority.

Adoption from `v1.0.0` requires manual compatibility review because deployment
boundary v1 changes to v2. The updater produces a draft/manual report instead
of importing partial changes. Preserve adopter-owned fleet/delivery files,
active/next-engine evidence, runtime pins and immutable release history. Follow
[the import procedure](UPDATING.md#github-template-repositories-have-no-fork-ancestry)
and [boundary-v2 adoption](UPDATING.md#deployment-boundary-v1-to-v2). Existing
required checks and host policy need a deliberate
[coverage, recovery and policy migration](UPDATING.md#local-validation-and-hosted-cutover).
The updater retains its separate required-`validate` write gate; verified manual
imports support maintenance after local-only cutover.

The final release source/base/tree, independently reviewed suite/engine policy,
complete source and initialized-adopter results without actual skips, log
digests, applicable required checks and final independent review must be recorded
for the actual release commit. Implementation results cannot validate a later
release commit. Tag creation and publication require separate operator approval
of that concrete result under the
[immutable-release checklist](#historical-preparation-and-future-releases).
Repository implementation merge and tooling publication do not require signed
host cutover; signing authority, compatible-manager/checkpoint recovery, private
promotion and operational policy migration remain separately authorized work.

## Unpublished complete local validation

The standalone template adds one complete local validation entry point,
`scripts/local_validate.py`, with explicit Git identities, independently pinned
engine policy, separate trusted-suite identity, isolated temporary checkouts,
tool versions, per-check logs and digests. It preserves policy rejection cases,
updater safety, exact-core and external deployer compatibility, immutable
release-update fixtures, committed-history scanning, reference/multi-host
validation and initializer success/failure checks. Required regression
inventories always come from the pinned suite and test candidate programs,
optional workflows and upstream release/setup documents in trusted fictional
fixtures. Upstream runs keep every core probe. Adopters retain the full public
corpus plus candidate-mapped regressions and the three named upstream-only
probe applicability rules. Candidate-added IDs run after required tests. The
mapped runner requires nonempty unique plans and matching execution counts.
No actual skips are accepted. Removing an optional workflow uses a pinned local-availability
case, with honest report applicability.
Pinned caller, supervisor and candidate-runner inventories also exercise the
candidate harness programs once in upstream and adopter modes. The outer
driver/supervisor remains pinned. Runner self-test workflow content and
definitions stay trusted without restoring an absent candidate workflow.
Adopter policy, updater and release-update stages run the complete public and
candidate corpora concurrently in independent fixture copies through the pinned
runner. Stages remain sequential and both checks must pass. Combined stage logs
include both outputs through supervised cleanup before their final digests;
separate child logs remain diagnostic, including after cancellation or timeout.

Each stage uses fresh source, engine-policy and trusted-suite checkouts from
verified frozen seeds. Initial checkouts fetch only explicit commit SHAs and
their ancestry, without unrelated branches or tags. Effective origins and source
main refs are fixed before manifests. Stages restore independent copies,
preserving modes and symlinks without hardlinks or repeated Git fetches. The
same pre/post manifests, complete test inventories and cleanup remain in force.
Orchestration and stage environments filter
inherited or supplied `GIT_*` variables and apply fixed trusted controls.
Git identity checks read stored objects with replacement refs and grafts
disabled; trusted discovery advice settings keep Git diagnostics stable.
Nested updater fixtures retain
their private-index override. Direct manifests cover bytes, types, modes,
symlinks and Git metadata; changes fail before a stage can pass. Each command
has a separate Linux subreaper that owns descendants through cleanup, including
`setsid` and double-fork children. Missing supervisor results fail validation.
A successful command also fails if a live descendant requires `SIGKILL` after
the 60-second cleanup allowance. These checks prevent persistent substitution
between stages, but do not sandbox hostile root
or transient same-stage tampering. Independent review, supervised disposable
Linux execution with mounted `/proc`, subreaper and pidfd support, Python 3.11
or newer and a separate signing authority remain required. Kernel waits and
external hard kills retain the
[documented cleanup limits](LOCAL-VALIDATION.md#results-failures-and-cleanup).

Output must be a new external directory outside Git worktrees and Git storage,
including ignored artifact directories in source, suite or engine repositories.
Early host-admission or output-validation failures return nonzero with a stderr
diagnostic and create no output directory or report.

Hosted configuration validation becomes an explicit convenience, default off
through `CI_FLEET_HOSTED_VALIDATION`. Opting in requires independently reviewed
full engine and compatible standalone-suite SHAs in
`CI_FLEET_VALIDATOR_REVISION` and `CI_FLEET_SUITE_REVISION`.
The workflow runs the pinned suite from the fixed public
`RandomDevelopment/ci-fleet-config-template` repository. Candidate, suite and
engine checkouts are separate siblings, with read-only permissions and no
persisted credentials. Missing or malformed pins fail before checkout; the
candidate supplies only the source input. PR events run only while open, with
separate concurrency identities from main pushes.
The optional job and check context are `hosted-validation`, never `validate`.
Neither its result nor its skipped state satisfies an existing required
`validate` check or the updater's gate. The flag leaves application Actions
scheduling, self-hosted fleet workflows and the separately authorized
repository-writing updater unchanged. The updater
retains its existing classic-protection and required-`validate` gate; manual
verified imports remain the maintenance path without Actions.

The ordinary-CI compatibility baseline remains
`aa9bbb27a4746fc80ce27d8932de68450b28364b`; fleet schema, example controller
engine pins and published release identities are unchanged. The core signed
local-evidence contract merged through
[ci-fleet PR #137](https://github.com/RandomDevelopment/ci-fleet/pull/137) at
`67beabbddaad73c19f15bc3baa227779bc88dc96`, with
[complete engine validation outside Actions](https://github.com/RandomDevelopment/ci-fleet/issues/135#issuecomment-6200457374).
That result does not replace standalone validation or establish trusted host
acceptance. Independent suite review, an external signing authority, compatible
executing/candidate/checkpoint managers and tested recovery remain separate gates.
The merged engine does not change this template's compatibility pin or publish
a template release.

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
