# Managed controller and runner images

The development template implements the schema-v3 managed-image contract at
ci-fleet `689c7c00deb0eebcb25f2284334a9f7168a25575`. Published template `v1.1.0`
does not support this field. Review and import the complete compatible template
and trusted suite before using these commands. This guide changes no host.

## Fresh configuration

`managed_images` maps a full nonzero engine commit to `amd64` and/or `arm64`.
Each architecture declares different, nonzero `controller` and `runner` Docker
image IDs in `sha256:` format. Every controller's selected engine needs a map
entry. These are exact local image IDs, not mutable tags or registry names.
Public examples contain fictional IDs that strict validation rejects.

Obtain reviewed IDs through the pinned
[build and verification procedure](https://github.com/RandomDevelopment/ci-fleet/blob/689c7c00deb0eebcb25f2284334a9f7168a25575/docs/MANAGED-IMAGES.md#record-image-ids-for-an-engine-commit)
on a separately authorized isolated build host. It requires repeated clean
builds for each target architecture using the reviewed build inputs. Do not
invent IDs, use a revision label as identity proof, or build on a live daemon.

Initialize a private configuration with those reviewed values:

```bash
./scripts/init.sh \
  --organization your-org --project your-app \
  --engine-ref REVIEWED_ENGINE_COMMIT_SHA \
  --architecture amd64 \
  --controller-image-digest sha256:REVIEWED_CONTROLLER_IMAGE_ID \
  --runner-image-digest sha256:REVIEWED_RUNNER_IMAGE_ID
./scripts/validate.sh --strict
```

Replace every placeholder. Add other architectures to the same engine entry
only after separate verification. The initializer validates strict configuration
before atomically replacing its output. Missing inputs, unsupported architecture,
malformed, equal, zero or fixture IDs fail without replacing an existing file.
It still omits optional reporting, Docker network and storage policy.

Commit and independently review the source, then run the complete
[exact-source suite](LOCAL-VALIDATION.md) with a compatible reviewed suite and
independent current engine validator. A focused strict check alone is incomplete.

## Upgrade an image-free adopter

This is a semantic migration within schema v3. The updater leaves managed-image
policy changes for manual handling. Preserve adopter-owned fleet configuration,
active/next-engine evidence, private delivery configuration and release history.
Before importing the new contract, use the incumbent compatible validator and
reviewed suite to integrate target-engine evidence for every controller with
reporting or network policy. Keep engine A selected and record reviewed engine B
capabilities in `next-engine-rollout-evidence.json`. Include required-reporting
and default-bridge evidence when configured. The new image-free staging contract
permits only engine-ref changes and retains pending evidence, so it cannot add
that sidecar in a separate same-engine revision. Then import the complete
compatible schema, validator, initializer, tests and suite with the staging
revision; do not merge a mixed partial contract.

Follow the pinned
[manager bootstrap procedure](https://github.com/RandomDevelopment/ci-fleet/blob/689c7c00deb0eebcb25f2284334a9f7168a25575/docs/MANAGED-IMAGES.md#two-step-desired-state-rollout)
under separate host-specific authorization:

1. Remove storage-retention admission in an earlier integrated configuration and
   verify convergence before any engine change. Prepare and review target image
   IDs separately. Keep signing authority away from execution and build hosts.
2. Pause reconciliation on every activation target. Integrate a staging revision
   that changes only controller `engine_ref` values and omits `managed_images`.
   Keep every controller, other fleet value and incumbent capability record.
   Reporting and network policy require matching engine-B capability evidence
   from the previous integrated sidecar. Retain that sidecar unchanged.
   Validate against the complete actual previous configuration and evidence.
   Fresh installation cannot use image-free staging or an empty predecessor.
3. Apply staging with the reviewed candidate engine installer's `--upgrade` and
   the approved configuration SHA. The incumbent installer cannot bootstrap the
   newer manager. Require `MANAGER_STAGED` on every target. That result leaves
   the incumbent controller and image running and proves no runtime activation.
4. In a later integrated revision, add reviewed `managed_images` while retaining
   all staged controller settings and incumbent runtime capability evidence.
   Validation checks the target engine against the previous integrated sidecar
   again, even though the desired engine ref already changed during staging.
   Apply it through the staged manager. Only this revision may build and activate
   the new runtime. Do not change capacity, routing or controller state as part
   of manager staging or alter controller settings during image-policy introduction.
5. After actual runtime verification, update active capability evidence to that
   runtime in a follow-up revision. Resume reconciliation through the staged
   manager and verify health and a later timer cycle. Retire a promoted next-engine
   record when its new engine becomes the active runtime. Retain unchanged
   pending evidence through bootstrap rather than manufacturing new attestations.

Image-free staging cannot remove enforced image policy, add/remove controllers,
change unrelated settings or activate a runtime. Ordinary later engine upgrades
need the template's prior integrated next-engine sidecar for configured
reporting/network capabilities, as do both bootstrap revisions. Storage admission
must be absent across engine
changes and separately re-admitted after engine and exclusive-daemon verification.

## Failure, removal and rollback

An image map cannot be removed after enforcement. Missing or mismatched images
fail closed. The engine prepares and verifies candidate images before drain;
revision labels alone do not satisfy exact image identity. Keep the incumbent
runtime and protected checkpoints until separately authorized acceptance.

Rollback is the engine's protected checkpoint procedure, not deletion of
`managed_images`, release records or evidence. Retain legacy image objects;
pre-enforcement builds may be unreproducible. Lost legacy objects need verified
saved-image recovery or a separately authorized reinstall. Follow the pinned
[recovery contract](https://github.com/RandomDevelopment/ci-fleet/blob/689c7c00deb0eebcb25f2284334a9f7168a25575/docs/MANAGED-IMAGES.md).
Repository validation proves neither available host images nor live recovery.
