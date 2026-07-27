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

1. Add the template as a remote and fetch its tags:

   ```bash
   git remote add template https://github.com/RandomDevelopment/ci-fleet-config-template.git
   git fetch template --tags
   ```

2. Bring in the changes between your recorded release and the target
   release. The two repositories have unrelated roots, so either merge
   the target tag with the explicit unrelated-history flag (first time
   only):

   ```bash
   git merge --allow-unrelated-histories refs/tags/<new-tag>
   ```

   or apply the reviewed range as a patch series:

   ```bash
   git format-patch --stdout refs/tags/<old-tag>..refs/tags/<new-tag> -- . ':!fleet.json' | git am -3
   ```

   Resolve conflicts against your local `fleet.json` (which is yours and
   must never be overwritten by template examples). Do not cherry-pick a
   lone tag — that applies only its target commit and silently omits
   intermediate changes.
3. Run `./scripts/validate.sh --strict` before committing.

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
reviewed, mechanical transformation — not a hand edit:

1. Read the migration notes for the new schema version.
2. Run the migration tooling shipped with that engine/template release
   against a branch of the private repository.
3. Run `./scripts/validate.sh --strict` and review the diff.
4. Merge only when every controller in the fleet runs an engine that
   understands the new schema.

## Optional adopter registration, never telemetry

This project collects **no telemetry** and there is no phone-home of any
kind. If the community wants visibility into who operates a fleet, it is
strictly optional and opt-in: an `ADOPTERS.md` pull request or a
registration issue form on the public engine repository. Never a
requirement, never automatic.
