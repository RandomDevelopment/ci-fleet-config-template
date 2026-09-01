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

The initial `v1.0.0` release is currently prepared, not published. Do not use it until the repository has an immutable tag and GitHub release. If a published release is wrong, leave its tag object untouched, publish a new higher tag, and mark the old release as superseded. Never retarget or recreate an existing release tag.

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

   # The trusted baseline is the committed TEMPLATE_RELEASE file (shared
   # by every clone), not a local ref. Fetch into a temporary ref and
   # promote only after comparison, so a retargeted upstream tag never
   # becomes trusted.
   PRIOR_TAG_OID="$(awk -v t="$NEW_TAG" '$1 == t {print $2}' TEMPLATE_RELEASE 2>/dev/null || true)"
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

## Dependabot update PRs

Keep a `.github/dependabot.yml` in the private repository covering
GitHub Actions. When your workflows pin actions or reusable workflows to
commit SHAs, Dependabot still opens update PRs for them (it understands
SHA-pinned actions with version comments). Review each PR like any
engine update: confirm the new SHA is a reviewed upstream release, then
let the strict validator and CI run before merge.

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
