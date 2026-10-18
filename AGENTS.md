# Agent instructions

## Purpose

This repository maps projects to CI pools, Git-authored controller desired state, deployment environments, logical host groups, and container images. It never stores secret values or host-local infrastructure details.

## Required verification

Before committing configuration changes, run the focused strict policy check:

```bash
./scripts/validate.sh --strict
```

That command alone is incomplete suite evidence. After committing, run the
complete exact-source suite from a clean, independently reviewed template
checkout, with an independently pinned engine validator:

```bash
sudo python3 -I /trusted/template/scripts/local_validate.py \
  --repository /work/config --repository-name OWNER/REPOSITORY \
  --source SOURCE_SHA --base BASE_SHA --main MAIN_SHA \
  --policy-repository /trusted/ci-fleet --policy REVIEWED_ENGINE_VALIDATOR_SHA \
  --output /results/new-dir
```

The output directory must be new and outside every Git worktree and Git storage
path. Ignored artifact directories inside source, suite or engine repositories
are rejected; subdirectories and symlink aliases do not bypass this boundary.

Use full available commit identities, except the explicit all-zero `--base`
sentinel when no prior integrated state exists. See
[local validation](docs/LOCAL-VALIDATION.md) for prerequisites, reviewed-head
handling, expected skips and results. Public fictional fixtures use non-strict
validation; initialized adopters must pass strict policy. Re-run after any
source, base, reviewed-head, suite or policy change. Missing tools, unexpected
skips, missing results and nonzero exits are incomplete or failed validation.

Hosted configuration validation is optional and defaults off. Enabling it
requires independently reviewed full engine and standalone-suite SHAs in
`CI_FLEET_VALIDATOR_REVISION` and `CI_FLEET_SUITE_REVISION`. The workflow runs
the pinned public standalone suite with the separate candidate checkout only
as its source input. Description-only PR edits start no validation job. Title-only
edits run the pinned engine title validator in the separate five-minute
`hosted-title-validation` job and produce no complete-suite evidence. Base-branch
edits retain complete validation. Keep job-level concurrency so ignored edits and
title checks cannot cancel a full run. Use a compatible independently reviewed
suite pin when adopting this workflow contract.
Neither enabling it nor a local developer result changes
required checks or trusted host policy. The optional full-suite job has a
documented 20-minute developer-acceptance budget because complete validation
exceeds five minutes. Restore five minutes only after setup and complete
coverage reliably fit a four-minute payload. Ordinary task jobs keep five minutes.
Preserve existing required checks until an authorized policy migration and
tested recovery are complete. Core local-evidence support merged at
`67beabbddaad73c19f15bc3baa227779bc88dc96`; template release, compatible-manager
staging and signed operational acceptance remain separate gates. Keep signing
keys off execution machines and follow the documented independent-authority
boundary.

Required regression inventories come from the pinned suite for both upstream
and adopter validation. Candidate programs, optional workflows and upstream
release/setup documents supply inputs, never replacement required tests.
Candidate-added IDs run only after the required corpus. The mapped runner
requires unique planned IDs and matching execution counts. Its standard-library
process worker must return a normal integer result; zero-status process exit
cannot substitute for test completion. Systemd owns deadlines and cleanup.
No actual skips are accepted. Keep the trusted public fixtures and derived upstream-probe applicability intact.
Run the pinned caller, executor-binding and candidate-runner definitions against the
candidate harness programs once in both upstream and adopter modes. Keep the
outer driver and core executor pinned and runner self-test workflow inputs trusted;
those fixture inputs must not restore an absent candidate workflow.
In adopter policy, updater and release-update stages, run the complete public
and candidate-mapped corpora concurrently through the pinned runner in separate
fixture copies. Keep stages sequential. Wait for both checks, require both child
logs on success, and assemble their ordered output only after supervised cleanup,
including failures, cancellation and timeout. The combined stage log is authoritative.

Fresh verified source, engine-policy and trusted-suite checkouts for each stage
prevent persistent cross-stage substitution. Initial narrow Git fetches build
the seeds. Freeze their effective origin/main metadata before manifests, then
restore independent stage copies with symlinks and modes preserved, without
hardlinks or repeated fetches. Symlinks must resolve inside their own worktree
and outside `.git`; reject trusted-sibling and external targets, including
dangling ones, before candidate stages. Check seeds before restoration, require each
copied target to match that frozen seed manifest before candidate execution,
and check both seeds and stage trees afterward. All orchestrator Git calls and
stage environments must filter inherited and supplied `GIT_*` variables and
apply the fixed trusted controls, including disabling replacement refs and
grafts. Preserve trusted fixture overrides such as the updater's private index.
These checks are not a sandbox against hostile root or same-stage transient
tampering. Independently review candidate
programs and the harness, and supervise execution on a disposable Linux machine
with systemd 255 or newer, cgroup v2 and Python 3.11 or newer.
Prepare the shared core executor from the independently reviewed revision named
by `EXECUTOR_REVISION`. Require its protected installed revision/hash manifest;
never load an executor supplied by the candidate or add a fallback supervisor.
The root launcher gives ordinary stages a locked unprivileged account, read-only
trusted inputs and separate writable source/home/scratch paths. Harness fixtures
that exercise the root launcher remain disposable-machine-only. The system
manager must confirm cgroup cleanup; missing receipts and forced termination
fail. Lost-worker runs are incomplete. Export one complete verified result
bundle outside the worker before disposal. Signing authority remains separate.
Preflight rejects standard installed fleet and signing-role markers, including
broken symlinks. Platform and host admission happen before Git inspection,
output-directory creation, tool probes or candidate execution. Installed-executor
revision, permission and host admission also precedes Git output discovery. Early admission
failures or invalid output locations return nonzero with a diagnostic on stderr
and create no output directory or report. Verify custom installations and the
execution machine's role separately, and keep the signing authority elsewhere.

## Hard rules

- Never add real `.env` files, credentials, tokens, private keys, cookies, or passwords.
- Never add addresses, VM IDs, storage identifiers, backup identifiers, SSH details, or rendered runtime configuration. Reviewed Docker `default_address_pools[].base` and `default_bridge_cidr` CIDRs are the only address exceptions after the corresponding engine capabilities are staged. Public review fragments use RFC 5737 ranges and must never activate policy in a newly initialized controller.
- Do not weaken `public_repositories: false` for Docker-socket runner pools.
- Infrastructure configuration owns capacity. Application workflows submit all independent jobs and do not use `max-parallel` to model fleet size.
- Each GitHub runner group belongs to exactly one runner pool; do not create ambiguous cross-pool assignments.
- The sum of active and drained controller maxima must not exceed the pool capacity budget.
- Controller engine revisions and reusable workflows must be pinned to full reviewed commit SHAs.
- Upgrade an engine with active optional capabilities in two integrated commits: first keep engine A active and stage reviewed engine B evidence in optional adopter-owned `next-engine-rollout-evidence.json`; then change `engine_ref` to engine B, promote the matching sidecar record to active evidence, and remove the sidecar when empty.
- Admit `docker_storage_retention` only in a separate reviewed change after activating a supporting engine and inventorying an exclusive ordinary-CI daemon. Adding or retaining admission requires current and previous controller states to be `active` or `drained`. Disabled declarations must omit admission; enable a disabled controller without admission in an earlier change before re-admitting it. Remove admission in an earlier integrated change and verify convergence before changing `engine_ref`; the reviewed contract has no storage-capability evidence field. Keep admission absent by default, protect active, persistent and uncertain resources, and never use global Docker prune. Repository validation does not establish live cleanup safety or scheduled headroom proof.
- Production inventory must require approval and must not deploy automatically. Deployment policy boundary v2 supports separately authorized standalone staging adoption through protected host-local policy only. Production operations, testers, image builders, and deploy-ref writers remain excluded. Inventory validation never proves deployment approval.
- Keep deployer policy, adapters, credential references, requests, approval/capability evidence, and checkpoint records outside public and private configuration Git. Pin the deployer core separately from ordinary-CI controller engines; never route privileged work through CI runner pools or labels.
- CI runner hosts and application deployment hosts are separate roles.
- Image promotion uses immutable digests; do not rebuild separately for production.
- Keep ordinary task jobs at a five-minute hard ceiling and expected shard payload at four minutes or less.
- Preserve deterministic task/shard isolation; Compose identity must include task and shard as well as run identity.
- Update schema, initializer, validator, tests, examples, and documentation together.


## Documentation impact

- Always assess documentation impact when working on an issue, preparing a commit, or creating, updating, or reviewing a PR. Repeat the assessment if the scope changes.
- Check whether the change affects documented behavior, usage, setup, configuration, APIs, architecture, deployment, or operations. Read the relevant documentation and compare it with the implementation.
- When implementing a change, update affected documentation in the same commit or PR. Follow the repository's documentation and changelog conventions. Preserve historical release notes and immutable records.
- When reviewing, report missing or inaccurate documentation as a finding.
- Before declaring the work complete, check updated examples, commands, links, and configuration names. Run applicable documentation checks.
- When creating or updating a PR, state the documentation impact in its description. In all cases, include the assessment in the completion summary. List updated documents, or explain why no documentation changes are needed. Report any remaining gaps.
