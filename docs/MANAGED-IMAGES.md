# Managed controller and runner images

This development specification follows merged ci-fleet
`840fb9be8a1c69404a5eebcf17855eff13c6c928`, including portable-image,
PR157 maintenance and unused-pending preparation support. Validate and review
the actual template revision, import and accept it in the adopter, then perform
the authorized rollout. Published template
`v1.1.0` does not provide this contract. This guide changes no host.

## Image identity

`managed_images` keeps the schema-v3 engine, architecture and role scalar map.
Each full nonzero engine commit maps `amd64` and/or `arm64` to distinct nonzero
`controller` and `runner` values in `sha256:` form.

The selected runtime source determines their meaning. If that exact source
advertises `portable_managed_image_ids`, the scalars are original image config
digests. Older sources retain exact opaque local Docker IDs. Do not infer the
meaning from digest syntax, storage backend or the manager executing the update.
Do not rewrite historical catalogs. The root installer binds portable config
digests to immutable runtime IDs and protects the binding proof outside Git.
Derived runtime IDs, rendered environments and host proof do not belong in
`managed_images` or rollout evidence.

Follow the reviewed engine's
[build and verification procedure](https://github.com/RandomDevelopment/ci-fleet/blob/840fb9be8a1c69404a5eebcf17855eff13c6c928/docs/MANAGED-IMAGES.md#record-image-ids-for-an-engine-commit)
on an authorized isolated build host. Build the same actual reviewed merged
engine twice from clean state for each target architecture. Portable builds
must match their original config digests. Native import, export, launch,
resource limits and deadline acceptance remain separate evidence. A revision
label or a build of an unmerged head cannot substitute for that proof. Do not
build candidate engines on live workers.

The reviewed transport lets Docker prepare the first export until
the remaining shared 180-second pair deadline. Connections, metadata responses
and gaps after streaming begins retain 30-second inactivity limits. Starting the
second role does not reset the pair budget. This adds no capability or evidence
field. Follow the pinned engine procedure above when recording build evidence.

## Fresh configuration

Initialize with the reviewed scalar appropriate to the selected source:

```bash
./scripts/init.sh \
  --organization your-org --project your-app \
  --engine-ref REVIEWED_ENGINE_COMMIT_SHA \
  --architecture amd64 \
  --controller-image-digest sha256:REVIEWED_CONTROLLER_SCALAR \
  --runner-image-digest sha256:REVIEWED_RUNNER_SCALAR
./scripts/validate.sh --strict
```

Replace every placeholder. The initializer requires architecture and both
scalars, validates before atomically replacing its output, and rejects equal,
zero, malformed or fixture values. It omits optional reporting, network and
storage policy. An explicit bridge input prints a review-only fragment rather
than enabling it in `fleet.json`.

Review and integrate the initial configuration with an empty active evidence
map and no optional policies. After installing that exact configuration,
require `--check` to report `CHECK_OK`. Review capabilities at the selected
source and observed runtime activation, then integrate active evidence in an
evidence-only commit. Add optional policy only in a later reviewed change.
`CHECK_STAGED` proves an incumbent during manager staging, not a fresh install.

Run the complete committed [exact-source suite](LOCAL-VALIDATION.md) using a
compatible independently reviewed suite and engine validator. A focused strict
check alone is incomplete acceptance.

## Upgrade an image-free adopter

This is a semantic migration within schema v3. The updater requires manual
handling when managed-image requirements or identity semantics change. Import
the complete reviewed specification while preserving private policy, tests,
workflow and release history through the [ownership procedure](UPDATING.md#import-ownership-for-engine-specification-updates).
Do not replace a customized adopter harness with the public upstream suite.
For an established image-free predecessor with unchanged fleet and active
evidence, the import may include only the explicitly reviewed pending preparation
transition described there. Unchanged fleet and evidence do not qualify as
manager staging.

Use actual immediate predecessors throughout the migration:

1. Remove retention admission in an earlier integrated same-engine change and
   verify convergence. Keep every other fleet setting. Obtain and review the
   actual merged target engine's image scalars separately.
2. For an established image-free fleet, integrate missing incumbent active
   records in an evidence-only commit. They describe already observed runtime
   and exact source capabilities, including explicit all-false records where
   appropriate. Preserve all existing active and pending records.
3. In a later evidence-only commit, add the target's reviewed pending records.
   Keep the entire fleet and active evidence unchanged. Every controller needs
   a matching previously integrated pending record, including controllers with
   no optional status/network blocks. `portable_managed_image_ids`, when present
   in active or pending evidence, must be a boolean. Source review does not
   attest runtime activation.
4. After the repository and isolated rehearsal gates pass, pause reconciliation
   on the authorized activation targets. Integrate an image-free manager-staging
   revision changing only controller `engine_ref` values. Keep every incumbent
   active and target pending record. Apply it through the reviewed candidate
   installer and require `MANAGER_STAGED`. The incumbent runtime remains active.
5. Introduce reviewed `managed_images` in a later integrated revision while
   retaining all other fleet settings and both evidence files. Apply through
   the staged manager. This is the runtime activation step. Neither capacity
   nor routing may change as part of image-policy introduction.
6. After actual runtime verification, promote the matching pending records
   unchanged into active evidence in a fleet-unchanged revision. Remove promoted
   pending entries and the sidecar when empty. Resume approved reconciliation,
   verify health and retain a later automatic cycle.

Ordinary image-enforced upgrades also require previously integrated matching
pending evidence, even with no optional policy. Selection promotes that exact
record into active evidence and removes it from the pending map. Staging and
selection cannot share one commit. A true no-op cannot serve as image-free
manager staging. Image policy cannot be removed after enforcement.

### Cancel or replace an unused pending target

The selected merged engine supports this preparation. Use a compatible reviewed
template and independently pinned supporting trusted policy. Before manager
selection, a separate evidence-only transition may cancel or replace
unused pending records only when the complete image-free fleet and every active
record remain unchanged. Every controller must have explicit active evidence
matching its selected engine. Validate the actual immediate predecessor and
review the replacement target's capabilities normally. Remove the sidecar when
canceling its last entry; an empty sidecar is invalid.
The independently pinned trusted validator and executing manager must support
this route; candidate-local acceptance cannot override an older trusted policy.

Integrate a replacement before selecting it. Missing incumbent evidence,
manager/runtime mismatch, image introduction, simultaneous selection and
unrelated changes do not qualify. Do not change the base, reinitialize the
adopter, infer activation from a source declaration or rewrite active evidence
to make a stale pending target disappear.

## Failure, removal and rollback

An installed portable image binding and an approved runtime do not update an
older last-known-good configuration automatically. The separately gated
[installed-baseline acceptance guidance](UPDATING.md#accepting-a-verified-installed-recovery-baseline)
preserves the old recovery evidence while verifying the installed policy. Follow
its final supporting source and delivery order before use; it authorizes no
image deletion, workload retirement or storage admission.

The selected runtime source and the executing manager can differ. Preserve
trusted incumbent-compatible source before checkpoint capture, preflight,
drain and restoration. A portable candidate cannot supply an older runtime's
identity semantics or Compose context. Missing compatible source fails before
drain. For opaque sources, validate candidate Compose before checkpoint capture;
for portable sources, validate only after both role bindings are verified.
Failed Compose must not drain or publish canonical image tags.

Keep exact old image catalogs, raw checkpoint IDs, original absence and retained
objects. A rebuild cannot recover a lost legacy opaque image. Recovery needs
verified retained-object import or separately authorized reinstall. Maintenance
must authenticate historical `release-target` context, including retained
manager source when the canonical release never existed. Source normalization
does not reconstruct an old image object. Portable cleanup still requires valid
binding proof, and unresolved opaque rollback identities defer removal.

Use the engine's protected checkpoint procedure rather than deleting image
policy, checkpoints or evidence. See the reviewed
[recovery requirements](https://github.com/RandomDevelopment/ci-fleet/blob/840fb9be8a1c69404a5eebcf17855eff13c6c928/docs/MANAGED-IMAGES.md#recovery-and-retained-images).
Repository checks, a published template and source availability do not prove
native image availability, resource admission, runtime activation or rollback.
