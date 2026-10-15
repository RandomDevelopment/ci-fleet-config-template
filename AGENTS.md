# Agent instructions

## Purpose

This repository maps projects to CI pools, Git-authored controller desired state, deployment environments, logical host groups, and container images. It never stores secret values or host-local infrastructure details.

## Required verification

Before committing configuration changes, run:

```bash
./scripts/validate.sh --strict
```

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
