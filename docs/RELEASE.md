# Initial template release preparation

The `v1.0.0` template release is prepared but not published. Creating the tag or GitHub release requires separate authorization after this change merges.

The candidate synchronizes the standalone schema-v3 contract with `templates/config-repository` at reviewed ci-fleet commit `0aed0d7e85e10050028b7d11fb12b84b3619e638`. It adds optional staged status-reporting and Docker network-policy support. Existing configurations that omit either field remain valid.

The fictional examples retain engine commit `8df97cc7575f47696fa82a179bbe39cd2874b1ca`. That older pin remains compatible only while the new optional fields are omitted. The examples use RFC 5737 Docker pools for documentation, so ordinary validation passes and strict validation deliberately fails until an adopter selects reviewed operational pool CIDRs.

When release is authorized:

1. Confirm the release commit passes every required check.
2. Create annotated tag `v1.0.0` at that exact commit.
3. Publish release notes that name the tag object ID, peeled template commit, and reviewed core commit above.
4. Never retarget the tag. Correct a bad release with a new higher tag and mark the old release as superseded.

The compatibility details are machine-readable in `template-compatibility.json`. No tag or GitHub release exists as part of this preparation change.
