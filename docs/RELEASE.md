# Initial template release

The [`v1.0.0` template release](https://github.com/RandomDevelopment/ci-fleet-config-template/releases/tag/v1.0.0) was published on September 2, 2026. It is a non-draft, non-prerelease release with the following reviewed identities:

- Annotated tag object: `0e54aaa09d0565ce103035f213953639fc068a73`
- Peeled template commit: `cf4a4d143540e0c70e1f301061038bbf95f04398`
- Reviewed ci-fleet commit: `0aed0d7e85e10050028b7d11fb12b84b3619e638`

Publication is recorded in [issue #12](https://github.com/RandomDevelopment/ci-fleet-config-template/issues/12#issuecomment-5515033394), with [passing post-merge validation](https://github.com/RandomDevelopment/ci-fleet-config-template/actions/runs/33671685334). This release did not deploy infrastructure or activate private configuration.

The release synchronizes the standalone schema-v3 contract with `templates/config-repository` at the reviewed ci-fleet commit above. It adds optional staged status-reporting and Docker network-policy support. Existing configurations that omit either field remain valid.

The fictional examples retain engine commit `8df97cc7575f47696fa82a179bbe39cd2874b1ca` and omit both optional fields. Network-policy validation fixtures use RFC 5737 ranges only. A private adopter may add a reviewed operational `default_address_pools[].base` CIDR only after the compatible engine and capability evidence have existed in prior integrated states.

## Historical preparation and future releases

The `template_release.state: prepared-not-published` value in `template-compatibility.json` records the preparation state committed before publication; it is not the current GitHub release status. Its compatibility details still describe the reviewed contract. The release and tag evidence above establish publication; do not rewrite the released commit to change its preparation record.

For a future, separately authorized release:

1. Confirm the release commit passes every required check.
2. Create a new, higher SemVer annotated tag at that exact commit.
3. Publish release notes that name the new tag object ID, peeled template commit, and the core commit reviewed for that release.
4. Never retarget the tag. Correct a bad release with a new higher tag and mark the old release as superseded.

Use the [adopter update guide](UPDATING.md) to record and verify the reviewed tag object before importing a release. Never retarget or recreate `v1.0.0`.
