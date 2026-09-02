# Initial template release preparation

The `v1.0.0` template release is prepared but not published. Creating the tag or GitHub release requires separate authorization after this change merges.

The candidate synchronizes the standalone schema-v3 contract with `templates/config-repository` at reviewed ci-fleet commit `0aed0d7e85e10050028b7d11fb12b84b3619e638`. It adds optional staged status-reporting and Docker network-policy support. Existing configurations that omit either field remain valid.

The fictional examples retain engine commit `8df97cc7575f47696fa82a179bbe39cd2874b1ca` and omit both optional fields. Network-policy validation fixtures use RFC 5737 ranges only. A private adopter may add a reviewed operational `default_address_pools[].base` CIDR only after the compatible engine and capability evidence have existed in prior integrated states.

When release is authorized:

1. Confirm the release commit passes every required check.
2. Create annotated tag `v1.0.0` at that exact commit.
3. Publish release notes that name the tag object ID, peeled template commit, and reviewed core commit above.
4. Never retarget the tag. Correct a bad release with a new higher tag and mark the old release as superseded.

The compatibility details are machine-readable in `template-compatibility.json`. No tag or GitHub release exists as part of this preparation change.
