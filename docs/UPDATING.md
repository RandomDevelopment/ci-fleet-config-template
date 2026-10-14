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
   NEW_TAG=<new-tag>
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

   Do not cherry-pick or format-patch a tag range: either can omit
   intermediate or merge-result changes.

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
schema/validator from the matching template release in the same change
(per the update procedure above) so validation actually exercises the
pinned contract. Releases that introduce a new `schema_version` are the
exception: import the new schema/validator in phase 2 of the two-phase
rollout below, after every deployed controller runs the new engine.

Migration programs use `scripts/migrate-v<old>-to-v<new>.py`. Release notes name the exact path. If a release changes `schema_version` but does not ship that named program, stop the update.

## Optional host-enforced configuration approval

The reviewed
[configuration approval contract](https://github.com/RandomDevelopment/ci-fleet/blob/fd1aa69daae8fa71f84e34cc112de1adf3156f09/docs/CONFIGURATION-APPROVAL.md)
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
[fictional policy example](https://github.com/RandomDevelopment/ci-fleet/blob/fd1aa69daae8fa71f84e34cc112de1adf3156f09/host/config-review-policy.json.example)
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
- An allowed reviewer other than the PR author must submit a formal
  `APPROVED` review on the full final head SHA, after any base retargeting.
  Latest reviewer decisions apply. Stale or dismissed approvals do not count;
  an outstanding trusted `CHANGES_REQUESTED` decision blocks acceptance.
  Comments, reactions, and a Codex completion summary do not grant approval.
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
2. Import the reviewed compatibility record, documentation and tests through the
   manual update procedure above. Preserve adopter-owned `fleet.json`, active
   and next-engine evidence, controller pins and delivery files. The schema,
   initializer and validator require no migration. Run policy/updater tests and
   `./scripts/validate.sh --strict`; require final-head CI and review. This step
   changes repository support only.
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
controller pins merely to adopt the deployer. Any separate controller upgrade
with active optional fields must still follow the existing two integrated
commits for next-engine evidence and promotion.

### Roll back boundary adoption

Before any host activation, restore the previously reviewed v1 template files
and compatibility record in a reviewed repository change. Preserve fleet
configuration, delivery files, rollout evidence and historical release records.
Run strict validation and final-head CI/review again. No host rollback is needed
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
let the strict validator and CI run before merge.

## Weekly template update PRs

`.github/workflows/template-update.yml` checks every Monday and supports manual dispatch. It uses the highest newer stable published release and opens or refreshes one PR on the reserved `automation/template-update` branch. The public template skips this job. Adopters opt in by configuring `TEMPLATE_UPDATER_TOKEN`; without it, scheduled and manual runs exit successfully without invoking the updater. No adopter registration is needed.

The updater checks every tag recorded in `TEMPLATE_RELEASE`, plus any pending PR's release identity, against the published release notes and fetched annotated tag object. It verifies the peeled template commit and its reviewed core compatibility record. A missing release, rewritten tag, ambiguous identity, or malformed baseline stops the job before it pushes changes. New release identities become a shared baseline only after a maintainer reviews and merges the PR. These checks detect rewrites; they do not replace release review or prove authorship through a signature.

Updates use a three-way merge of the recorded template snapshot, the current adopter default branch, and the target snapshot. Fork ancestry is unnecessary. Adopter-only files and nonconflicting local edits survive. `fleet.json`, `engine-rollout-evidence.json`, and `next-engine-rollout-evidence.json` remain byte-for-byte unchanged, including their absence. This preserves fleet settings, engine pins, and the delivery inventory/policy inside `fleet.json`.

For delivery policy or other adopter-owned files outside those paths, commit `.github/template-updater.json` before enabling the job:

```json
{
  "preserve": ["delivery", "docs/LOCAL_POLICY.md"]
}
```

Entries are repository-relative file or directory paths, without trailing slashes or globs. This settings file is itself adopter-owned. Do not preserve template validators or schema files unless you intend to maintain them yourself.

A conflict, fleet schema migration, or change to the release's deployment policy boundary produces a draft PR containing only `.github/template-update-status.json`, with the verified identities and manual-handling reasons. It imports no partial update. Follow the manual update and migration procedures above, then validate and review the result before marking the PR ready. The next run rebuilds the reserved branch from the current default branch, so copy manual work to a separate branch or disable the updater while resolving it. Never use the reserved branch for other work. Ref updates use a lease to reject concurrent changes.

The updater never runs fetched scripts, migrations, or validators with its write token. Normal `pull_request` validation runs after the push with the validation workflow's read-only token and hosted runner. The updater neither merges nor enables auto-merge. Engine-pin changes and their two-commit evidence rollout remain separate work.

### Setup for new adopters

1. Create your repository from the template and initialize/review `fleet.json` as described in the README. Review the source revision you copy. Commit `TEMPLATE_RELEASE` with the last reviewed published tag and raw annotated tag object ID. For the initial published baseline:

   ```text
   v1.0.0 0e54aaa09d0565ce103035f213953639fc068a73
   ```

   Use the verification procedure above first. A checkout of template `main` may include unpublished changes; record the published baseline and expect local edits to require review. Do not invent a release identity for `main`.
2. List any extra adopter-owned delivery files in `.github/template-updater.json`.
3. Configure the review/check gate and bot token below, then enable Actions. Scheduled jobs run from the default branch. Run **Update template** manually once to verify setup. Until a newer release is published, it reports no update.

### Setup for existing adopters

Copy the reviewed `scripts/update_template.py`, `scripts/test_template_updater.py`, and `.github/workflows/template-update.yml` into your repository. Add the updater test command to your normal validation workflow, retaining its `pull_request` trigger, read-only permissions, five-minute timeout, and `validate` job name. Review and commit these files without replacing your fleet configuration or delivery workflow. Keep the existing `TEMPLATE_RELEASE` history; if it is missing, establish and verify your baseline through the manual procedure above. Then follow steps 2 and 3 for new adopters.

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

GitHub-hosted Ubuntu supplies Python 3, GitHub CLI, and Git with `merge-tree --merge-base` support. Local runs need those tools, a clean checkout, `GITHUB_REPOSITORY=owner/repository`, authenticated GitHub CLI/Git, and Git 2.40 or newer. Local runs can push a PR and require the same review gate. Neither setup changes hosts, deploys infrastructure, or grants deployment authority.

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
   - Phase 1 (old schema): merge a configuration commit that only
     advances each controller's `engine_ref` to the new reviewed engine
     commit, still expressed in the old `schema_version`, and let every
     deployed controller upgrade.
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
