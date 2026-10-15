# Keeping a private configuration repository up to date

A private configuration repository is created from this public template
and then lives its own life. This guide explains how it stays current.

## Two different version numbers

- **`schema_version`** (inside `fleet.json`) is the version of the
  *data contract* — the fields the engine and validator understand. It
  changes rarely and only through an explicit migration (see below).
- **Template version** is the version of the *starting content* — the
  scripts, validators, examples, and documentation you copied from this
  template. It is tracked by the template's tagged releases, not by
  anything inside `fleet.json`.

Bumping one never bumps the other. A new template release can ship
validator fixes with an unchanged `schema_version`, but a schema
migration always arrives as part of a template/engine release — never as
an adopter-local edit.

## Template releases are versioned

This template publishes tagged releases. Record the release you started
from **in versioned repository data** — a `TEMPLATE_RELEASE` file at the
repository root containing the tag name and its reviewed 40-hex object
ID, one per line — and review release notes when updating. Keeping the
reviewed object ID in Git means every clone and every maintainer shares
the same rewrite-detection baseline; a local-only ref cannot do that.
Treat template files as vendored code: update them deliberately, not
casually.

The initial [`v1.0.0` release](https://github.com/RandomDevelopment/ci-fleet-config-template/releases/tag/v1.0.0) was published on September 2, 2026. Its annotated tag object is `0e54aaa09d0565ce103035f213953639fc068a73`, peeling to template commit `cf4a4d143540e0c70e1f301061038bbf95f04398`. See [release evidence and the historical preparation record](RELEASE.md). `template-compatibility.json` records the historical preparation state committed before publication. Keep that record and the released commit unchanged. Verify the tag object using the procedure below before adopting it.

If a published release is wrong, leave its tag object untouched, publish a new higher tag, and mark the old release as superseded. Never retarget or recreate an existing release tag.

## GitHub template repositories have no fork ancestry

A repository created with GitHub's "Use this template" button is **not**
a fork: it has no git ancestry link to the template, so
`git pull upstream` does not work and GitHub will never offer sync PRs.
Updating is an explicit operation:

1. Start from a clean tree — no uncommitted or unstaged changes,
   especially to `fleet.json`, `engine-rollout-evidence.json`, or the optional
   `next-engine-rollout-evidence.json`; the
   procedure restores adopter-owned files from the recorded pre-merge
   commit and would silently discard an uncommitted edit. Then add the
   template as a remote and fetch its tags into that remote's tracking
   namespace. `--no-tags` prevents Git from also creating adopter-visible
   tags. A retargeted upstream tag
   updates a `refs/remotes/*` ref silently, so verify the reviewed
   object ID yourself before using any previously fetched tag ref:

   ```bash
   # Hard stop on any uncommitted state; a dirty tree would be silently
   # overwritten by the adopter-owned state restore below.
   test -z "$(git status --porcelain)" || { echo "clean the tree first" >&2; exit 1; }
   # one-time setup; on later runs require the existing remote to be the
   # template, not an unrelated remote that happens to share the name:
   if ! git remote get-url template 2>/dev/null; then
     git remote add template https://github.com/RandomDevelopment/ci-fleet-config-template.git
   fi
   test "$(git remote get-url template)" = \
     "https://github.com/RandomDevelopment/ci-fleet-config-template.git" || \
     { echo "remote 'template' points elsewhere; refusing to continue" >&2; exit 1; }

   # Capture the tag as data and constrain its format. Never interpolate
   # an unvalidated tag into shell commands: Git permits metacharacters
   # in tag names, which would execute before the release is reviewed.
   # Replace this placeholder with the reviewed release tag, such as v1.0.0.
   NEW_TAG=REPLACE_WITH_REVIEWED_TAG
   [[ "$NEW_TAG" =~ ^[0-9A-Za-z][0-9A-Za-z._/-]{0,127}$ ]] || exit 1

   # The trusted baseline is the committed TEMPLATE_RELEASE file, shared
   # by every clone. For v1.0.0, always use the published object ID above,
   # including on a first import with no TEMPLATE_RELEASE file. Fetch
   # into a temporary ref and compare before trusting it.
   PRIOR_TAG_OID="$(awk -v t="$NEW_TAG" '$1 == t {print $2}' TEMPLATE_RELEASE 2>/dev/null || true)"
   if [ "$NEW_TAG" = v1.0.0 ]; then
     PRIOR_TAG_OID=0e54aaa09d0565ce103035f213953639fc068a73
   fi
   git update-ref -d refs/tmp/template-tag-check 2>/dev/null || true
   if ! git fetch --no-tags template "refs/tags/$NEW_TAG:refs/tmp/template-tag-check"; then
     echo "tag $NEW_TAG not found upstream" >&2; exit 1
   fi
   # Compare the raw tag object (catches re-signing/message rewrites of
   # annotated tags that still point at the same commit); peel separately
   # for the merge source, which must be a commit.
   NEW_TAG_OID="$(git rev-parse refs/tmp/template-tag-check)"
   MERGE_SOURCE="$(git rev-parse 'refs/tmp/template-tag-check^{commit}')"
   if [ -n "$PRIOR_TAG_OID" ] && [ "$NEW_TAG_OID" != "$PRIOR_TAG_OID" ]; then
     # Fail closed: do not promote the rewritten tag; stop and review upstream.
     git update-ref -d refs/tmp/template-tag-check
     echo "template tag $NEW_TAG was rewritten upstream; refusing to use it" >&2
     exit 1
   fi
   git update-ref -d refs/tmp/template-tag-check
   ```

2. Record the adopter commit, then merge the target template release
   without committing. The explicit unrelated-history flag is required
   on the first update and harmless after the first merge establishes
   common ancestry:

   ```bash
   ADOPTER_HEAD="$(git rev-parse HEAD)"
   git merge --no-ff --no-commit --allow-unrelated-histories \
     "$MERGE_SOURCE"
   ```

   If Git reports conflicts, leave the merge in progress and continue.
   Whether or not it conflicted, restore the adopter-owned configuration
   from the recorded pre-merge commit. Preserve rollout evidence from that
   commit when it exists; otherwise keep the evidence introduced by the new
   template release. Then resolve and stage every other conflict:

   ```bash
   git restore --source="$ADOPTER_HEAD" --staged --worktree -- fleet.json
   if git cat-file -e "$ADOPTER_HEAD:engine-rollout-evidence.json" 2>/dev/null; then
     git restore --source="$ADOPTER_HEAD" --staged --worktree -- engine-rollout-evidence.json
   fi
   if git cat-file -e "$ADOPTER_HEAD:next-engine-rollout-evidence.json" 2>/dev/null; then
     git restore --source="$ADOPTER_HEAD" --staged --worktree -- next-engine-rollout-evidence.json
   fi
   git status --short
   ```

   If the release keeps the same `schema_version`, prove the adopter-owned
   configuration and rollout evidence still have no staged changes:

   ```bash
   git diff --cached --exit-code "$ADOPTER_HEAD" -- fleet.json
   if git cat-file -e "$ADOPTER_HEAD:engine-rollout-evidence.json" 2>/dev/null; then
     git diff --cached --exit-code "$ADOPTER_HEAD" -- engine-rollout-evidence.json
   else
     git diff --cached --exit-code "$MERGE_SOURCE" -- engine-rollout-evidence.json
   fi
   if git cat-file -e "$ADOPTER_HEAD:next-engine-rollout-evidence.json" 2>/dev/null; then
     git diff --cached --exit-code "$ADOPTER_HEAD" -- next-engine-rollout-evidence.json
   fi
   ```

3. Review the complete staged result — including any changes the merge
   brings to `scripts/validate.sh`, the validator, or migration sources —
   **before** executing anything the merge introduced. An erroneous or
   compromised release must never run code in your environment
   unreviewed:

   ```bash
   git diff --cached
   git status --short
   ```

   If the release changes `schema_version`, run the now-reviewed target
   release's migration tooling while this template merge is still
   pending, then stage and review the mechanical `fleet.json` migration.
4. Validate, record the reviewed release in `TEMPLATE_RELEASE` (the
   verified tag and object ID), and commit:

   ```bash
   ./scripts/validate.sh --strict
   printf '%s %s\n' "$NEW_TAG" "$NEW_TAG_OID" >> TEMPLATE_RELEASE
   git add TEMPLATE_RELEASE
   git commit
   ```

   Run the [complete local suite](LOCAL-VALIDATION.md) against the committed
   result, using the recorded pre-merge adopter commit as the base. Include the
   original reviewed head when validating an applied merge or squash commit.
   The focused strict check above does not replace this exact-source result.
   Preserve existing required checks until the deliberate cutover below.

   Do not cherry-pick or format-patch a tag range: either can omit
   intermediate or merge-result changes.

### Import an unpublished reviewed revision

Some support documented here has merged after the latest published release.
The tag procedure above cannot import those changes until publication. To
adopt them earlier, review a full immutable template commit and its complete
diff against your existing vendored files. Record that source SHA and the
documentation impact in the adopter PR. Preserve `TEMPLATE_RELEASE` exactly;
an unpublished commit is not a new release identity and the weekly updater
continues to use the last reviewed published baseline.

Use Bash from a clean adopter checkout. Configure and verify the `template`
remote as in step 1 above. Replace the placeholder with the reviewed full SHA:

```bash
test -z "$(git status --porcelain)" || { echo "clean the tree first" >&2; exit 1; }
REVIEWED_TEMPLATE_COMMIT=REPLACE_WITH_REVIEWED_FULL_TEMPLATE_SHA
[[ "$REVIEWED_TEMPLATE_COMMIT" =~ ^[0-9a-f]{40}$ ]] || exit 1
test "$(git remote get-url template)" = \
  "https://github.com/RandomDevelopment/ci-fleet-config-template.git" || exit 1
git fetch --no-tags template "$REVIEWED_TEMPLATE_COMMIT" || exit 1
MERGE_SOURCE="$(git rev-parse 'FETCH_HEAD^{commit}')"
test "$MERGE_SOURCE" = "$REVIEWED_TEMPLATE_COMMIT" || exit 1
ADOPTER_HEAD="$(git rev-parse HEAD)"
git merge --no-ff --no-commit --allow-unrelated-histories "$MERGE_SOURCE"
```

Continue only after a successful merge or ordinary merge conflicts. Stop on
other Git errors. Preserve these adopter-owned paths, including their absence.
Add your extra owned delivery files and customized workflows to the array
before running it. Use the same ownership list as `.github/template-updater.json`
when that file exists; do not replace application delivery workflows with the
template's workflows.

```bash
ADOPTER_PATHS=(fleet.json engine-rollout-evidence.json next-engine-rollout-evidence.json
  TEMPLATE_RELEASE .github/template-updater.json)
for path in "${ADOPTER_PATHS[@]}"; do
  if git cat-file -e "$ADOPTER_HEAD:$path" 2>/dev/null; then
    git restore --source="$ADOPTER_HEAD" --staged --worktree -- "$path" || exit 1
  else
    git rm -r -f --ignore-unmatch -- "$path" || exit 1
  fi
done
git diff --cached --exit-code "$ADOPTER_HEAD" -- "${ADOPTER_PATHS[@]}" || exit 1
git diff --cached
git status --short
```

Resolve and stage every remaining conflict. Review all imported scripts,
workflows, schema and compatibility changes before executing them. An older
adopter with no active evidence file may need a separately reviewed empty
schema-version-1 evidence record before validation. Do not copy capability
attestations from another controller. Run the reviewed policy/updater tests,
`./scripts/validate.sh --strict`, and
`python3 scripts/test_core_compatibility.py`, then commit the reviewed merge:

```bash
git status --short
git commit
```

Open an adopter PR recording the reviewed template SHA and documentation impact.
Require a complete exact-head local result, independent review and every check
still required by the current policy before merging. This import changes
repository support only; engine selection, host activation and production
approval remain separate steps.

## Local validation and hosted cutover

Complete local validation needs no GitHub Actions execution or hosted allowance.
Use the [complete command](LOCAL-VALIDATION.md) from a clean independently
reviewed template checkout with a separately pinned engine validator. Commit
the reviewed update first, then validate the exact source/base identities. Keep
the full logs and result outside Git. Changing a source, base, reviewed head,
suite or engine-policy identity requires another run.
Run under operator supervision on a disposable Linux execution machine with
mounted `/proc`, child subreaper and pidfd support, and Python 3.11 or newer.
The suite verifies its seeds and fresh source, engine-policy and trusted-suite
checkouts for each stage. Explicit SHA-only fetches include the selected
ancestry without unrelated branches or tags. Each command's separate subreaper
owns descendants through cleanup, including `setsid` and double-fork children.
Missing supervisor results and forced cleanup after the 60-second grace fail
validation. See [cleanup limits](LOCAL-VALIDATION.md#results-failures-and-cleanup)
for kernel waits and hard kills. This prevents persistent substitution between
stages; it does not contain hostile root or transient tampering within a stage.

The ordinary-CI compatibility pin remains
`aa9bbb27a4746fc80ce27d8932de68450b28364b`; fictional example engine pins and
immutable release records remain unchanged. The local-evidence contract in
[ci-fleet PR #137](https://github.com/RandomDevelopment/ci-fleet/pull/137),
reviewed proposed reference `a1451c024e0be642ecb60715980515da1868e85c`, is pending merge.
Do not adopt that unmerged proposal as a released engine or claim host
acceptance from template tests.

For an existing repository, migrate in this order:

1. Inventory required branch checks and host approval policy, including any
   dependency on the required `validate` context. Keep that path operating while
   importing and reviewing the complete local suite. Application workflows and
   self-hosted fleet routing stay unchanged. The optional job reports only
   `hosted-validation`; it cannot replace or satisfy `validate`. If the old
   producer is removed before an authorized policy migration, the existing
   required `validate` check must continue blocking the merge.
2. Compare complete local coverage and exact identities with the existing
   path. Exercise an unconfigured hosted flag, `true`, then `false`, removal
   of the optional workflow, and Actions unavailable or quota-blocked. Every
   state must retain complete local validation. A failed or skipped hosted run
   remains failed or skipped; it is not local proof.
3. Wait for a merged supporting engine and independent review of the complete
   standalone suite before proposing trusted host acceptance. Stage compatible
   executing, candidate and checkpoint managers advertising
   `configuration_local_validation`. Preserve optional-capability staging and
   any separate image-enforcement bootstrap requirements.
4. With separate operator authorization, configure the independent signing
   authority and policy-v2 required suite/checks. Verify the approved suite
   revision/tree as well as the pinned engine, repository/PR/head/base/tree,
   report completeness, expiry and log digests. Independently verify actual
   suite and engine identities; a report alone does not establish them. Keep
   signing keys off execution machines. Prove rejection of forged, stale,
   mismatched, tampered or incomplete evidence, and prove compatible recovery
   with Actions unavailable.
5. Only after coverage and recovery acceptance, deliberately migrate the
   applicable branch-protection and host policies. Remove the old hosted
   requirement explicitly if choosing local-only acceptance. Do not wait for a
   missing or skipped required check to pass, and do not bypass a still-active
   gate. Opting into hosted convenience alone creates no required check.

Repository Actions variables control only the optional configuration workflow.
Set `CI_FLEET_HOSTED_VALIDATION=true` and independently pin
`CI_FLEET_VALIDATOR_REVISION` to opt in. Set the flag to `false`, delete it, or
remove `.github/workflows/validate.yml` to stop hosted execution after any
necessary policy migration. A repository may explicitly retain hosted evidence
as an additional requirement. Existing policy-v1 hosts continue needing Actions
until an authorized compatible policy-v2 migration.

Before cutover, retain the reviewed workflow, validator/suite identities,
host-local policy and checkpoint or documented reinstall procedure appropriate
to the host's failure boundary. Test the intended rollback without Actions.
If local validation fails, fix the failure and rerun; do not remove checks to
make the report pass. If recovery requires restoring the prior hosted-required
policy, restore a compatible manager and the reviewed workflow/variables before
relying on it, and confirm hosted execution is actually available. A hosted
outage can leave that old path blocked. Keep the host on its last accepted
configuration until the reviewed recovery procedure succeeds.

The updater has a separate unchanged write gate. Its current automatic and CLI
paths require classic branch protection with a required `validate` status. A
passing or skipped `hosted-validation` job cannot satisfy it. A local-only
cutover can therefore stop the updater. Use the verified manual
release import in this guide instead; do not weaken the updater's protections
to force it to run. This migration changes no settings, keys, private pins or
live host by itself.

## Validation is pinned to immutable releases

Controller `engine_ref` values and any reusable workflow references must
be full reviewed commit SHAs, not moving tags or branches. When you
update the pinned engine, resolve the exact merge commit on the engine's
default branch, review it, and pin that 40-hex SHA.

One limitation to understand: `./scripts/validate.sh --strict` runs the
validator **vendored in your repository**, so it verifies that
`engine_ref` is a well-formed 40-hex SHA but does not fetch that commit
or check it against the engine's actual contract. When you adopt a new
engine release whose `schema_version` is unchanged, update the vendored
schema/validator from the matching reviewed template release or immutable
template revision in the same change so validation actually exercises the
pinned contract. Releases that introduce a new `schema_version` are the
exception: import the new schema/validator in phase 2 of the two-phase
rollout below, after every deployed controller runs the new engine.

The complete local suite adds an independent pinned engine-policy check and a
trusted template validator with the standalone safety rules. Its explicit
policy revision does not change controller `engine_ref`, establish engine
activation or make an unmerged engine a released compatibility baseline.

Migration programs use `scripts/migrate-v<old>-to-v<new>.py`. Release notes name the exact path. If a release changes `schema_version` but does not ship that named program, stop the update.

## Engine manager upgrades and recovery outcomes

An engine revision selected in `fleet.json`, an installed manager, and the
running controller can differ during an upgrade. Selecting a new engine does
not replace the manager already executing reconciliation. Read the selected
engine's immutable runbook and verify that this adopter has matching schema,
validator and evidence support before changing a pin.
Remove and converge any storage-retention admission before the pin change,
then preserve the staging rules for remaining reporting/network capabilities.

The reviewed [upgrade and reconciliation contract](https://github.com/RandomDevelopment/ci-fleet/blob/ad5fd55c68fdc269332e187eef329ae881cb9b27/docs/DESIRED-STATE.md)
documents the installer and result handling. Ordinary upgrades use the reviewed
installer's `--upgrade` with the exact configuration SHA. Upgrades introducing
managed image enforcement require the separate
[manager bootstrap procedure](https://github.com/RandomDevelopment/ci-fleet/blob/ad5fd55c68fdc269332e187eef329ae881cb9b27/docs/MANAGED-IMAGES.md#two-step-desired-state-rollout):

1. Obtain host-specific authorization and pause reconciliation before publishing
   staging. The incumbent installer cannot bootstrap the newer manager.
2. Apply the reviewed staging configuration with the candidate checkout's
   `scripts/install-worker-controller.sh --upgrade`, the approved full config
   SHA and controller ID. The upstream procedure preserves controller settings
   and incumbent runtime capability evidence, omits `managed_images`, and must
   report `MANAGER_STAGED` without activating the new runtime.
3. Only after every target has staged its manager, follow that contract's
   reviewed image-ID activation and subsequent runtime-evidence steps. Resume
   reconciliation with the compatible manager and verify runtime health and a
   later timer cycle. Manager staging alone does not prove runtime activation.

This template's reviewed ordinary-CI baseline supports Docker bridge and storage
policy, but does not add `managed_images`. Adopters needing that newer contract
must first import compatible reviewed schema/validator support. Do not add
unsupported fields, substitute the ordinary two-commit evidence procedure for
the image bootstrap contract, or treat these instructions as fixing the legacy
dependency transition tracked in [ci-fleet #113](https://github.com/RandomDevelopment/ci-fleet/issues/113).

The reviewed [rejection and recovery runbook](https://github.com/RandomDevelopment/ci-fleet/blob/ad5fd55c68fdc269332e187eef329ae881cb9b27/docs/DESIRED-STATE.md#rejected-upgrades-and-uncertain-recovery)
distinguishes these outcomes:

- An explicit rejection during initial read-only admission emits `REJECTED`.
  Reconciliation retains the installed/applied commit, records `status=failed`
  and `transaction_phase=pre_transaction`, and leaves health `unknown`. Disk
  use at or above 80% records `failure_reason=docker_disk_capacity`; other
  explicit initial preconditions use `installer_precondition`. These are
  controlled fields, not copied installer stderr.
- A transaction failure with verified checkpoint restoration reports verified
  rollback only after the existing prior-runtime health check succeeds.
- Unverified rollback reports `ROLLBACK_UNVERIFIED`. Preserve its checkpoint
  and inspect the protected recovery state before an authorized recovery.
- Missing, empty, malformed, contradictory or unsupported results are unknown.
  Interruption and failures after initial admission cannot claim an early
  rejection, even if they ultimately changed nothing. Empty phase/reason fields
  do not prove that no transaction ran. Reconciliation does not attempt outer
  recovery from an uncertain installer outcome.

Early-rejection eligibility ends before lock creation, adoption writes,
configuration work, manager preparation or checkpoint repair. Both the executing
installer and reconciler must support this result contract. An older installer's
missing result stays unknown until the compatible manager is adopted.

Rejection and uncertain recovery retain exit code 3, which systemd accepts so
the five-minute timer can retry. A successful unit result or unchanged applied
SHA therefore proves neither health nor convergence. Inspect the host-local
`/var/lib/ci-fleet/reconcile/state.json` status, desired/applied commits, health,
phase and reason together with its service journal. The 80% disk admission gate
and retry behavior remain unchanged. These observations authorize no cleanup
or gate bypass. Engine merge, template publication, private engine promotion
and separately authorized host acceptance are distinct milestones.

## Optional Docker network and storage policy

The reviewed ordinary-CI compatibility baseline is
`aa9bbb27a4746fc80ce27d8932de68450b28364b`. These optional schema-v3 fields do
not change an existing configuration that omits them. The default initializer
and public fleet examples leave them absent. Full fleet examples retain their
old engine pins. Review fragments illustrate syntax without attesting host support.
See the [review-only network-policy fragment](../examples/docker-network-policy.json).

### Address pools and the default bridge

The [reviewed network contract](https://github.com/RandomDevelopment/ci-fleet/blob/aa9bbb27a4746fc80ce27d8932de68450b28364b/docs/DESIRED-STATE.md#schema-v3)
permits `docker_network_policy.default_bridge_cidr`, an IPv4 interface CIDR
with a usable bridge gateway. Its subnet must not overlap an address pool.
After network, broadcast and gateway addresses, it must provide at least
`max_runners + reserve_subnets` container addresses. Address-pool capacity has
its separate `max_runners * networks_per_runner + reserve_subnets + 1`
calculation. The reviewed engine must advertise `docker_network_policy_config`
and `docker_network_policy_adapter`, plus `docker_default_bridge_cidr_config`
when the bridge field is present.

For first activation, integrate these separately reviewed changes:

1. Select and activate the compatible engine while leaving new policy fields
   absent. First remove existing storage-retention admission and verify
   convergence. Existing active reporting or network fields still require the
   two integrated next-engine staging/promotion commits described in the README.
2. After verifying the exact engine is active, record its per-controller
   `docker_network_policy_config: true` and, for a bridge,
   `docker_default_bridge_cidr_config: true` in active rollout evidence.
3. In a later integrated commit, add the reviewed policy without changing the
   engine or capability evidence. Adding a bridge to an existing policy needs
   the same prior-integrated bridge evidence. A new controller must establish
   its configuration and evidence before introducing network policy.

Retained fields require matching current evidence. When upgrading an engine
with active network policy, stage all required engine B evidence in the
next-engine sidecar first, then promote it with the pin change. Remove an
unsupported bridge or network policy in a reviewed earlier change before
selecting an older engine, and remove stale evidence when changing controllers.

The optional initializer flag `--default-bridge-cidr 192.0.2.1/24` validates the
requested bridge and prints a review-only network-policy fragment. It does not
insert network policy into the generated fleet. Its single RFC 5737 pool supports
up to 30 runners, with the subnet size chosen for the requested maximum. For
larger fleets, initialize without the flag and review a larger network design
separately. Replace RFC 5737 pool and bridge
values with operational policy in private Git before strict validation and
activation. This narrow address exception does not admit host addresses,
service endpoints, VM identifiers or rendered Docker configuration.

The engine applies only reviewed Docker keys through its drain, checkpoint,
restart, effective-network verification and health procedure. A Git revert
does not itself restore a host's Docker configuration. Authorized host rollback
must use the compatible retained checkpoint and verify restored Docker network
state and controller health. Retain recovery evidence if rollback fails.

### Disposable image and build-cache retention

The [reviewed maintenance contract](https://github.com/RandomDevelopment/ci-fleet/blob/aa9bbb27a4746fc80ce27d8932de68450b28364b/docs/HOST-MAINTENANCE.md#docker-storage-retention)
requires activation of an engine advertising `docker_storage_retention` before
adding this admission in a separate reviewed configuration change:

```json
"docker_storage_retention": {"exclusive_fleet_daemon": true}
```

The object accepts exactly that true-valued key. It has no new rollout-evidence
flag, and the initializer never emits it. Existing reporting/network evidence
rules still apply to any engine upgrade. Before admission, inventory the whole
daemon and establish exclusive disposable ordinary-CI ownership, the compatible
credential-free socket proxy, and absence of independent Docker writers.
Shared application daemons, persistent workloads, remote builders and
asynchronous orchestrators do not qualify. Unknown or persistent images must
leave the daemon or carry `io.randomdevelopment.ci-fleet.retention=keep`.
A project name, age or Docker's reclaimable estimate cannot prove ownership.

With the previous integrated configuration supplied, transition validation
rejects retention on a new controller or when the predecessor is not `active`
or `drained`. This applies to retained admission too. The schema and validator
also reject retention on a currently `disabled` controller. Remove admission
when disabling. A disabled declaration must first be enabled without
admission in an earlier integrated change, then its engine and inventory
verified before a later admission change. An `engine_ref` change requires
retention admission to be absent from both the previous and current configuration. CI
supplies that predecessor context. A supplied predecessor must contain a
`controllers` object. These ordering checks do not prove that the engine is
active or that daemon inventory is complete; operators must verify both before
admission.

Before any engine change, remove retention admission in an earlier integrated
same-engine change and verify convergence. Upgrade with admission absent,
preserving the two-commit evidence procedure for any reporting or network
capabilities that remain active. A next-engine record cannot authorize retaining
storage admission across the pin change because the reviewed evidence format
has no storage-capability field. After the new engine is active and support,
exclusive ownership and inventory are verified, re-admit retention in a later
same-engine change. The host's engine-capability check remains required.

The hourly service starts reclamation at 70% measured Docker filesystem use
and targets 65%, below the unchanged 80% installer gate. Each storage pass is
limited to 50 unreferenced images, at least seven days old, and two minutes.
Referenced images, running work, installed images, retained checkpoint images,
keep-labelled resources and uncertain protection state remain protected.
Default-builder cache uses Engine's unused-cache selection with `until=168h`
and a 10 GiB reserve; unknown last-use evidence defers removal. Custom Buildx
volumes are outside this admission. Cleanup uses shared locks, idle checks and
uncertainty guards. It never forces removals or performs global Docker prune.

For separately authorized activation, follow the linked systemd dry-run, review
its candidates, retain a sanitized applying-service journal, measure actual
headroom, observe the next scheduled pass, and verify later reconciliation
passes disk admission. Prove running and unknown-owned leftovers survive.
Repository checks do not satisfy this live acceptance gate in
[ci-fleet #111](https://github.com/RandomDevelopment/ci-fleet/issues/111).
An engine already blocked by 80% disk use cannot bootstrap this feature through
that blocked upgrade. Initial scoped recovery requires operator authorization.

To stop retention, remove the admission and converge that reviewed change before
an unsupported engine downgrade. Do not edit rendered environment variables or
delete uncertainty markers. Removing policy cannot restore deleted images or
cache. Controller rollback relies on its protected retained images and verified
checkpoint, and requires separate authorized host verification.

## Optional host-enforced configuration approval

The reviewed
[configuration approval contract](https://github.com/RandomDevelopment/ci-fleet/blob/f5d3c45dd4eb09ac9cefe16bde7a457673fff678/docs/CONFIGURATION-APPROVAL.md)
adds the opt-in engine capability `configuration_approval_gate`, with no new
`fleet.json` field. Review and adopt a compatible immutable engine SHA under
the existing capability-rollout rules. Importing template documentation or
merging engine code does not activate host enforcement.

After bootstrap, a separately authorized root operator must verify the
installed manager supports that capability and review its trusted installed
configuration baseline, last-known-good record, and compatible recovery
checkpoint. Do not enable the gate before a first installation or while an
older manager is installed. Give the existing host-side GitHub App read-only
Contents, Pull requests, and Actions permissions on the configuration
repository. It needs no approval or write authority.

The operator provisions `/etc/ci-fleet/config-review-policy.json` and
`/etc/ci-fleet/config-review-required`, which contains exactly `1` followed by
a newline. Both must be root-owned regular files with mode `0600`, in
root-owned directories that reject group and other writes. Follow the reviewed
[fictional policy example](https://github.com/RandomDevelopment/ci-fleet/blob/f5d3c45dd4eb09ac9cefe16bde7a457673fff678/host/config-review-policy.json.example)
for the numeric repository, workflow, and allowed reviewer IDs, trusted branch,
and required job names. Keep the policy, marker, credentials, rendered runtime
configuration, and approval evidence host-local, outside public and private
Git configuration. Candidate configuration cannot disable the gate. Either
file's presence requires verification; a remaining marker with missing policy
fails closed. With neither present, existing installations retain their
previous behavior.

Before reconciliation, drift repair, forward installation/adoption/upgrade,
or policy-adapter resume, the trusted installed verifier requires:

- The exact applied SHA must result from one merged PR to the trusted
  repository and branch. It must preserve the installed baseline's ancestry.
  Every first-parent commit since that baseline must independently pass the
  review and check rules, within the contract's twenty-commit and evidence
  limits. A reviewed PR cannot carry an unreviewed direct-pushed base.
- The applied tree must equal the final reviewed PR head's tree and preserve
  the required parent relationships. Reconcile with the final base and repeat
  review before merging; approval of stale content does not permit deleting
  later branch changes.
- By default, an allowed reviewer other than the PR author must submit a formal
  `APPROVED` review on the full final head SHA, after any base retargeting.
  Latest reviewer decisions apply. Stale or dismissed approvals do not count;
  an outstanding trusted `CHANGES_REQUESTED` decision blocks acceptance.
  The explicit Codex opt-in below can accept its narrow verified clean response.
  Other comments, reactions and generic completion summaries do not grant approval.
- The latest push run of the pinned workflow on the exact applied SHA must
  complete successfully for the trusted repository and branch. Every required
  named job must succeed in that same run attempt. Successful PR merge-ref
  checks alone are insufficient; queued, missing, skipped, cancelled, or failed
  checks are rejected.

Direct pushes, unavailable or incomplete evidence, missing permissions, and
API/network failures reject a candidate. The running controller and its
last-known-good state remain in place, and the timer may retry when evidence
becomes available. Unchanged commits and check-only runs also verify evidence.
Revoked evidence prevents further convergence without automatically stopping
an already running controller.

Rollback preserves the policy and marker and can restore a trusted compatible
root-owned checkpoint without GitHub availability. It rejects checkpoints
whose older manager would remove enforcement. Remote last-known-good recovery
accepts only the exact repository, commit, and controller in the trusted
root-owned record, and still requires an approval-capable engine. Historical
baselines are not retroactively attested. Incompatible recovery requires a
separately authorized root-operator procedure rather than an automatic
downgrade. Follow the engine contract for recovery, and verify real permissions,
reviewer provisioning, systemd execution, and unattended bypass rejection in a
separately authorized live exercise.

The weekly updater's branch-protection requirements remain unchanged. Those
checks govern the bot's PR writes; this host gate governs applying a merged
configuration and needs no paid branch-protection feature. Neither grants
production deployment approval or privileged-role authority. Boundary v2 staging
adoption still uses separate host-local deployment approval. Fleet inventory
validation remains logical only.

### Opt into verified Codex clean reviews

Formal reviews remain the default. The newer engine contract allows an operator
to add `"codex_reviewer_ids": [202]` to the protected host-local policy. The ID
is fictional. Independently verify the actual bot's numeric GitHub ID and also
include it in `reviewer_ids`. The bot must differ from the PR author. A copied
summary or renamed account does not substitute that identity.

Before adding the field, including an empty list, install an engine and
executing manager advertising `configuration_codex_reviews`. Review checkpoint
managers and last-known-good recovery for that capability too. Follow the
[manager upgrade procedure](#engine-manager-upgrades-and-recovery-outcomes),
matching template support and any existing next-engine evidence gates before
provisioning policy. Active-policy admission and rollback reject incompatible
targets before mutation or restoration. Omitting the field or using an empty
list keeps formal-only behavior; older engines reject the field even when
empty. Remove it before any separately authorized formal-only downgrade.

The accepted decision is an unedited issue comment beginning exactly
`Codex Review: Didn't find any major issues.` with the standard `Reviewed commit`
field. Only the linked verifier's recognized optional follow-up and integration
help footer are accepted. The commit must resolve through GitHub to the full
current PR head. An abbreviated textual match is insufficient. Format changes,
extra findings or warnings fail closed until reviewed verifier support exists.

The clean result must follow any base retargeting, and all review threads must
be resolved. Newer comments or formal reviews from any pinned Codex identity,
pending bot reviews, or later `@codex review` and `@codex security review`
requests invalidate it. Any later comment deletion or an edit that could erase
a request also needs a fresh clean result. GitHub deletion history must be
available and completely paginated. Edited decision responses cannot approve;
editing an older decision after the clean result also invalidates that result.
Same-second conflicts reject acceptance. Outstanding trusted formal change
requests continue to block it.

The separate activity dashboard cannot approve. A later refresh is allowed only
in the exact recognized format, with the `codex-pull-request-review-summary`
HTML marker, the `Codex Review Summary` heading, its known prose/footer, and a
table whose columns are `Review`, `Status`, `Commit`, and `Review trigger`.
Its only row must be the recognized completed code review on the same resolved
head, timestamped at or after the separate clean response, with `Manual request`
or `PR opened` as trigger. The relative-time label must exactly match its
`datetime`; running, failed, stale, additional or unrecognized rows reject it.
Follow the immutable contract's complete formatting rather than constructing
a dashboard manually.

When present, the optional `codex-review-state:v1` HTML marker, including an
indented marker, must contain exactly the `code_review` and `security_review`
objects. Each contains exactly `commit_sha`, `status`, `has_any_findings`, and
`has_unresolved_findings`. Code review must name the full head, have status
`completed`, and both finding flags false. All four security-review values must
be null. Unknown versions, extra fields, security activity or inconsistent
visible/state evidence fail closed.

Tree equality, ancestry, independent identity, successful exact-applied-SHA push
workflow/jobs, trusted baselines, recovery enforcement and API failure behavior
remain required. PR CI, a merge, comment, reaction or template release alone
does not prove host acceptance. After separately authorized activation, verify
real permissions, accepted/rejected reviews, compatible upgrade/recovery and
a later timer cycle. This grants no deployment or privileged-role authority.

## Deployment boundary v1 to v2

Boundary v2 adds a reviewed external staging-deployer adoption path. It requires
manual compatibility review even though `fleet.json` remains schema v3. The
weekly updater detects the changed `deployment_policy_boundary` and creates a
draft report without importing partial changes. This includes future changes to
the nested deployer core pin. Do not bypass that report by changing its version.

1. Review [boundary v2](DEPLOYMENT-POLICY.md) and ci-fleet commit
   `c67d18d24ceb5f22569d8887b94f7198a448ccde`, including its installer, runtime,
   broker and application adapter restrictions. Record the reviewed template
   revision. This change is not a published release; keep existing
   `TEMPLATE_RELEASE` identities until a new immutable release is published and
   verified. Do not invent a release tag for template `main`.
2. Import the reviewed compatibility record, documentation and tests through
   [the unpublished immutable-revision procedure](#import-an-unpublished-reviewed-revision),
   or use the tag procedure after a matching release is published. Preserve adopter-owned `fleet.json`, active
   and next-engine evidence, controller pins and delivery files. The schema,
   initializer and validator require no migration for boundary v2 itself. Other
   changes in the selected template commit still need review. Run policy/updater tests and
   `./scripts/validate.sh --strict`, then `python3 scripts/test_core_compatibility.py`;
   require the complete exact-head local suite, independent review and all
   checks still required by the current policy. The compatibility command verifies the
   independently pinned deployer in derived repositories too; only embedded
   ordinary-CI byte comparisons are upstream-only. Network or digest failures
   reject verification. This step changes repository support only.
3. Review the application-owned adapter and immutable image separately. Resolve
   its data, migration, network, ingress, credentials and rollback requirements
   against the constrained broker before selecting it. Retain the existing
   deployment path. Track application work in
   [MMPriceFeed #126](https://github.com/RandomDevelopment/mmrss/issues/126) and
   [TF2 Recommendation Engine #373](https://github.com/RandomDevelopment/TF2-Recommendation-Engine/issues/373).
4. Before host work, obtain separate operator authorization for the isolated
   staging target, rootless daemon, protected credential/artifact provisioning,
   independent exact-source/exact-artifact approval, checkpoint creation and
   permitted deployment or recovery exercises. Follow the pinned
   [deployer runbook](https://github.com/RandomDevelopment/ci-fleet/blob/c67d18d24ceb5f22569d8887b94f7198a448ccde/docs/DEPLOYER-HOST.md).
   Keep policy, runtime state and evidence outside configuration Git. Every
   installer mode, including `--check`, requires root. Check runs bounded
   transient health verification and can retain a recovery guard if interrupted.
5. Cut over only under that authorization after application acceptance. Record
   core/source SHAs, adapter/image digests and redacted results in the adopter
   issue. Production remains disabled; inventory or additional evidence cannot
   enable deployment, cleanup or rollback in the reviewed core.

The deployer core pin is independent of controller `engine_ref`. Do not advance
controller pins merely to adopt the deployer. Before any separate controller
upgrade, remove and converge storage-retention admission. Any remaining active
reporting or network fields still require the two integrated commits for
next-engine evidence and promotion.

### Roll back boundary adoption

Before any host activation, restore the previously reviewed v1 template files
and compatibility record in a reviewed repository change. Preserve fleet
configuration, delivery files, rollout evidence and historical release records.
Run strict validation, the complete exact-head local suite, independent review
and all checks still required by the current policy again. No host rollback is needed
when adoption never activated a host.

After authorized staging activation, reverting Git does not undo host policy or
an application deployment. An authorized operator must resolve any active or
uncertain operation through protected journals, drain the deployer, and use
the pinned installer's `--rollback` for its retained compatible last-known-good
policy. Restore the prior reviewed host policy, approval and checkpoint evidence
through the protected operator process, then run `--check`. Retain immutable
adapter paths, credential sources, replay ledger, audit history and recovery
state. Never downgrade by deleting those records.

If application data is incompatible with rollback or no recovery point exists,
follow the separately reviewed checkpoint restoration procedure. The template
cannot prove recovery. Keep the legacy deployment path available until its
operator-reviewed restoration is safe. Uninstall removes managed activation
but deliberately retains policy, credentials, evidence, releases and audits;
retirement and credential revocation need their own authorized procedure.

## Optional capacity telemetry

The reviewed ci-fleet `capacity_telemetry` capability requires no new
`fleet.json` field. Adopt it only with a compatible engine release whose
implementation and commit SHA have been reviewed. The public fixture and its
engine pin remain unchanged, and copying this template does not activate the
capability on a host.

After an authorized operator has installed that engine, review the preceding
seven days on each controller with:

```bash
sudo /opt/ci-fleet/current/scripts/health.py capacity-report
```

The read-only JSON report groups data by logical pool and reports nearest-rank
p50 and p95 values for observed host and runner metrics, along with sample and
anonymous runner-observation counts. An empty report means no managed runner
was observed. Sampling runs on the host, keeps bounded history there, and does
not add data to heartbeat or outbound status-report payloads. The reviewed
[capacity telemetry contract](https://github.com/RandomDevelopment/ci-fleet/blob/09cfc64044dfc72e6edb9269090286b4a20fd0a3/docs/CAPACITY-TELEMETRY.md)
defines the retention and data boundaries. The sampler discards records older
than eight days and compacts history at its reviewed 26,000/24,000-record
thresholds.

Keep telemetry samples, reports, and host details out of the configuration
repository.

Use this evidence when reviewing `max_runners`, per-runner resources, and pool
capacity budgets. Any adjustment requires its own reviewed private
configuration change. Workflows still submit independent jobs and do not use
`strategy.max-parallel` to encode fleet capacity. This host-local report is
separate from the weekly template updater, which remains opt-in and sends no
telemetry.

## Dependabot update PRs

Keep a `.github/dependabot.yml` in the private repository covering
GitHub Actions. When your workflows pin actions or reusable workflows to
commit SHAs, Dependabot still opens update PRs for them (it understands
SHA-pinned actions with version comments). Review each PR like any
engine update: confirm the new SHA is a reviewed upstream release, then
run the complete exact-head local suite and review before merge, along with
every check still required by the current policy.

## Weekly template update PRs

`.github/workflows/template-update.yml` checks every Monday and supports manual dispatch. It uses the highest newer stable published release and opens or refreshes one PR on the reserved `automation/template-update` branch. The public template skips this job. Adopters opt in by configuring `TEMPLATE_UPDATER_TOKEN`; without it, scheduled and manual runs exit successfully without invoking the updater. No adopter registration is needed.

The updater checks every tag recorded in `TEMPLATE_RELEASE`, plus any pending PR's release identity, against the published release notes and fetched annotated tag object. It verifies the peeled template commit and its reviewed core compatibility record. Boundary-v2 releases also require a distinct `Reviewed deployer ci-fleet commit` line matching the nested deployer core pin; historical boundary-v1 releases retain their original identity contract. A missing release, rewritten tag, ambiguous identity, or malformed baseline stops the job before it pushes changes. New release identities become a shared baseline only after a maintainer reviews and merges the PR. These checks detect rewrites; they do not replace release review or prove authorship through a signature.

Updates use a three-way merge of the recorded template snapshot, the current adopter default branch, and the target snapshot. Fork ancestry is unnecessary. Adopter-only files and nonconflicting local edits survive. `fleet.json`, `engine-rollout-evidence.json`, and `next-engine-rollout-evidence.json` remain byte-for-byte unchanged, including their absence. This preserves fleet settings, engine pins, and the delivery inventory/policy inside `fleet.json`.

For delivery policy or other adopter-owned files outside those paths, commit `.github/template-updater.json` before enabling the job:

```json
{
  "preserve": ["delivery", "docs/LOCAL_POLICY.md"]
}
```

Entries are repository-relative file or directory paths, without trailing slashes or globs. This settings file is itself adopter-owned. Do not preserve template validators or schema files unless you intend to maintain them yourself.

A conflict, fleet schema migration, or change to the release's deployment policy boundary produces a draft PR containing only `.github/template-update-status.json`, with the verified identities and manual-handling reasons. It imports no partial update. Follow the manual update and migration procedures above, then validate and review the result before marking the PR ready. The next run rebuilds the reserved branch from the current default branch, so copy manual work to a separate branch or disable the updater while resolving it. Never use the reserved branch for other work. Ref updates use a lease to reject concurrent changes.

The updater never runs fetched scripts, migrations, or validators with its write token. Maintainers run the complete local suite against its proposed commit. If the separate hosted-validation flag is enabled, `pull_request` convenience validation also runs with the validation workflow's read-only token and hosted runner. A disabled or missing convenience job does not fulfill the updater's unchanged required-check gate. The updater neither merges nor enables auto-merge. Engine-pin changes and their two-commit evidence rollout remain separate work.

### Setup for new adopters

1. Create your repository from the template and initialize/review `fleet.json` as described in the README. Review the source revision you copy. Commit `TEMPLATE_RELEASE` with the last reviewed published tag and raw annotated tag object ID. For the initial published baseline:

   ```text
   v1.0.0 0e54aaa09d0565ce103035f213953639fc068a73
   ```

   Use the verification procedure above first. A checkout of template `main` may include unpublished changes; record the published baseline and expect local edits to require review. Do not invent a release identity for `main`.
2. List any extra adopter-owned delivery files in `.github/template-updater.json`.
3. For scheduled updater use, configure the review/check gate and bot token below, then enable Actions. Scheduled jobs run from the default branch. Run **Update template** manually once to verify setup. Until a newer release is published, it reports no update. This separate opt-in can use hosted execution even when configuration validation is disabled. For maintenance without Actions, use the verified manual import procedure above.

### Setup for existing adopters

Copy the reviewed `scripts/update_template.py`, `scripts/test_template_updater.py`, and `.github/workflows/template-update.yml` into your repository. The complete local suite includes the updater safety tests; copying only `scripts/validate.sh` does not. Review and commit the reviewed suite files without replacing fleet configuration or application delivery workflows. Preserve any existing required validation path until a deliberate policy migration. Keep the existing `TEMPLATE_RELEASE` history; if it is missing, establish and verify your baseline through the manual procedure above. Then follow steps 2 and 3 for new adopters.

### GitHub permissions and review gate

Use a dedicated bot account's fine-grained personal access token, or a separately managed GitHub App installation token, as the repository Actions secret `TEMPLATE_UPDATER_TOKEN`. Token provisioning/rotation is an operator task. Grant access only to the adopter repository, with these repository permissions:

| Permission | Access | Why |
|---|---|---|
| Contents | Read and write | Fetch the adopter and push the reserved branch |
| Pull requests | Read and write | Find, create, edit, and mark update PRs draft |
| Workflows | Read and write | Releases may update vendored workflow files |
| Administration | Read | Verify the default branch's protection |
| Metadata | Read | Read repository/default-branch metadata |

The sample workflow expects a token already stored in the secret. GitHub App tokens expire; an adopter using an App must mint its installation token in a trusted step before invoking the script. Keep token creation on the default branch and do not expose it to PR jobs. The workflow's built-in `GITHUB_TOKEN` has only `contents: read` and cannot be used for the updater. Events created with `GITHUB_TOKEN` generally do not start normal PR workflows; the separate bot token does.

Protect the default branch with at least one required approving review, stale-approval dismissal, enforcement for administrators, no review bypass allowances, and the required `validate` status check with "Require branches to be up to date". Give the bot no bypass role. The updater checks this classic branch-protection configuration before writing. Ruleset-only configurations are not supported by this version. If the repository's GitHub plan does not support these protections, or the token cannot read them, the updater stops. Do not weaken the gate to work around that limit.

This unchanged updater gate is stricter than the default local-validation
choice. Enabling `CI_FLEET_HOSTED_VALIDATION` alone does not create branch
protection, and its `hosted-validation` context does not satisfy the required
`validate` check. While that protection remains configured, the updater may
propose PRs, but a missing `validate` producer leaves those PRs blocked from
merging. Removing `validate` from protection during a local-only migration
makes the updater reject writes because its required configuration is absent.
Use manual verified imports after the authorized migration instead of bypassing
the gate. An updater policy redesign is separate work.

GitHub-hosted Ubuntu supplies Python 3, GitHub CLI, and Git with `merge-tree --merge-base` support. Local updater runs need those tools, a clean checkout, `GITHUB_REPOSITORY=owner/repository`, separately authorized authenticated GitHub CLI/Git, and Git 2.40 or newer. The explicit CLI entry point is `GITHUB_REPOSITORY=owner/repository python3 scripts/update_template.py`. It can push a branch and create or update a PR; it is not part of read-only local validation. It requires the same unchanged review/check gate and network access, but no Actions scheduler. Neither setup changes hosts, deploys infrastructure, or grants deployment authority.

## Schema migrations are explicit tooling

When the engine introduces a new `schema_version`, the migration is a
reviewed, mechanical transformation — not a hand edit. Apply it inside
the pending template merge above so the new schema, validator, migration,
and migrated private configuration are validated and committed together:

1. Read the migration notes for the new schema version.
2. Start the template merge, restore the adopter's pre-merge
   `fleet.json`, and run the migration tooling shipped with that target
   engine/template release before committing the merge.
3. Run `./scripts/validate.sh --strict` and review the diff.
4. Roll out in two phases when controllers run the older engine. The
   vendored validator understands one schema version, so importing the
   new schema/validator and migrating `fleet.json` in the same change
   would reject the configuration still needed by un-upgraded hosts:
   - Phase 1 (old schema): advance each controller to the new reviewed
     engine while retaining the old `schema_version`. First remove and converge
     storage-retention admission. With remaining active reporting or network
     capabilities, first integrate next-engine evidence, then promote the
     matching active evidence with `engine_ref` in a second integrated commit.
     Without those active capabilities, the pin change can be one commit.
     Follow any separate engine-specific manager/bootstrap requirements and
     verify every deployed controller actually runs the new engine.
   - Phase 2 (new schema): once every still-deployed `active` or
     `drained` controller runs the new engine, merge the template update
     that imports the matching schema/validator and run the migration
     above.
   Retained `disabled` declarations have no running host and gate
   neither phase.

## Optional adopter registration, never telemetry

This project collects **no telemetry** and there is no phone-home of any
kind. If the community wants visibility into who operates a fleet, it is
strictly optional and opt-in: an `ADOPTERS.md` pull request or a
registration issue form on the public engine repository. Never a
requirement, never automatic.
