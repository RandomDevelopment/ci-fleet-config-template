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
validator fixes with an unchanged `schema_version`; a schema migration
can happen without any other template change.

## Template releases are versioned

This template publishes tagged releases. Record the release you started
from in your private repository (for example in its README), and review
release notes when updating. Treat template files as vendored code:
update them deliberately, not casually.

## GitHub template repositories have no fork ancestry

A repository created with GitHub's "Use this template" button is **not**
a fork: it has no git ancestry link to the template, so
`git pull upstream` does not work and GitHub will never offer sync PRs.
Updating is an explicit operation:

1. Start from a clean tree — no uncommitted or unstaged changes,
   especially to `fleet.json`; the procedure restores `fleet.json` from
   the recorded pre-merge commit and would silently discard an
   uncommitted edit. Then add the template as a remote and fetch its
   tags into that remote's tracking namespace. `--no-tags` prevents Git
   from also creating adopter-visible tags. A retargeted upstream tag
   updates a `refs/remotes/*` ref silently, so verify the reviewed
   object ID yourself before using any previously fetched tag ref:

   ```bash
   git status --porcelain   # must be empty
   # one-time setup; skip if `git remote` already lists `template`:
   git remote add template https://github.com/RandomDevelopment/ci-fleet-config-template.git
   git fetch --no-tags template 'refs/tags/*:refs/remotes/template/tags/*'
   # If you fetched this tag before, require the object to be unchanged:
   # test "$(git rev-parse refs/remotes/template/tags/<new-tag>)" = \
   #   "$(git ls-remote template refs/tags/<new-tag> | awk '{print $1}')"
   ```

2. Record the adopter commit, then merge the target template release
   without committing. The explicit unrelated-history flag is required
   on the first update and harmless after the first merge establishes
   common ancestry:

   ```bash
   ADOPTER_HEAD="$(git rev-parse HEAD)"
   git merge --no-ff --no-commit --allow-unrelated-histories \
     refs/remotes/template/tags/<new-tag>
   ```

   If Git reports conflicts, leave the merge in progress and continue.
   Whether or not it conflicted, restore the adopter-owned configuration
   from the recorded pre-merge commit, then resolve and stage every other
   conflict:

   ```bash
   git restore --source="$ADOPTER_HEAD" --staged --worktree -- fleet.json
   git status --short
   ```

   If the release keeps the same `schema_version`, prove `fleet.json`
   still has no staged change:

   ```bash
   git diff --cached --exit-code -- fleet.json
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
4. Validate and commit:

   ```bash
   ./scripts/validate.sh --strict
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
engine release, update the vendored schema/validator from the matching
template release in the same change (per the update procedure above) so
validation actually exercises the pinned contract.

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
4. Merge only when every still-deployed `active` or `drained` controller
   runs an engine that understands the new schema. Retained `disabled`
   declarations have no running host and do not gate the migration.

## Optional adopter registration, never telemetry

This project collects **no telemetry** and there is no phone-home of any
kind. If the community wants visibility into who operates a fleet, it is
strictly optional and opt-in: an `ADOPTERS.md` pull request or a
registration issue form on the public engine repository. Never a
requirement, never automatic.
