# Template releases

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

1. Confirm the release commit passes every required check.
2. Create a new, higher SemVer annotated tag at that exact commit.
3. Publish release notes that name the new tag object ID, peeled template commit, and the core commit reviewed for that release.
4. Never retarget the tag. Correct a bad release with a new higher tag and mark the old release as superseded.

Use the [adopter update guide](UPDATING.md) to record and verify the reviewed tag object before importing a release. Never retarget or recreate `v1.0.0`.
