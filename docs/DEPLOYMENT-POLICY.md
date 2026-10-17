# Deployment policy boundary v2

Boundary v2 supports adoption of the standalone staging deployer in ci-fleet
commit `689c7c00deb0eebcb25f2284334a9f7168a25575`, including the staging implementation from
[PR #69](https://github.com/RandomDevelopment/ci-fleet/pull/69) and subsequent
role-admission and durable-recovery fixes. It does not make
`fleet.json` executable deployment policy. Boundary v2 itself needs no fleet
schema migration, initializer change or controller engine upgrade because the
deployer consumes a separate protected host-local schema-version-1 policy.
The optional ordinary-CI Docker policies documented in the README do not
authorize deployment or cleanup on an application daemon. Public fleet examples
continue to omit those optional policies and retain their reviewed engine pins.

`template-compatibility.json` records both contracts. Its top-level
`reviewed_core` pins the embedded ordinary-CI template. The nested
`deployment_policy_boundary.standalone_deployer.reviewed_core` pins the deployer.
Neither pin silently upgrades a controller or grants deployment authority.
This development pin supersedes the deployer baseline in published `v1.1.0`;
the published release identity remains unchanged.

| Role | Boundary v2 support | Authority |
| --- | --- | --- |
| Ordinary CI | Existing schema-v3 configuration | Trusted private repositories, isolated runner pools and infrastructure-owned capacity |
| Standalone staging deployer | External host-policy adoption | Dedicated host, independently approved source/artifact and target-scoped credentials |
| Production deployer | Operations disabled in the reviewed core | Separate future decision and authorization, even when production inventory exists |
| Deploy-ref writer | Excluded | Separate identity and reviewed contract, never the deployer or ordinary CI |
| Persistent tester and image builder | Excluded | Separate reviewed contracts, not implied by deployer adoption |

Boundary v1 remains the historical ordinary-CI-only contract. V2 adds an explicit
external staging adoption path without relabeling v1 or changing released tags.
Inventory validation still cannot verify host policy, approval, credentials,
checkpoint recoverability, application compatibility, or live deployment.

## Logical inventory and protected host policy

The following fictional mapping describes operator review. It is not a rendered
configuration or a renderer specification. Keep actual host inventory and all
runtime files outside public and private configuration Git.

| Logical inventory or reviewed input | Host-local interpretation | Required independent check |
| --- | --- | --- |
| Project `example-app`, repository `example-org/example-app` | Select the application-owned adapter and exact `SOURCE_COMMIT` | Source is a reviewed full lowercase commit SHA |
| Project `image` repository | Select one `ARTIFACT_IMAGE` ending in `@sha256:<64 lowercase hex>` | Approval binds that exact image digest and source, without rebuilding for production |
| Environment `example-staging`, group `example-staging-apps` of class `staging` | Operator chooses `ENVIRONMENT=staging`, a logical `TARGET_ID` and dedicated `DEPLOYER_IDENTITY` | Environment, target, identity and daemon are isolated from CI and production |
| `automatic` and `requires_approval` | Intended inventory policy only | Neither value creates an approval or permits automatic request submission |
| `required_secret_names` | Operator provisions a target-scoped protected credential file | Names are not credentials, and a secret store is not approval |
| Reviewed deployer core and application adapter | `CORE_REF`, `ADAPTER_PATH` and `ADAPTER_SHA256` | Core is the exact reviewed checkout; adapter bytes match SHA-256 at an immutable digest-suffixed path |
| Independent deployment approval | `APPROVAL_PROVIDER` and `APPROVAL_EVIDENCE_PATH` | Approval binds environment, target, source, artifact, approver, policy, stable approval ID and UTC time |
| Recoverable checkpoint | `CHECKPOINT_EVIDENCE_PATH` | Operator creates and verifies a recovery procedure; core does not operate infrastructure or prove recovery |

The reviewed [deployer runbook](https://github.com/RandomDevelopment/ci-fleet/blob/689c7c00deb0eebcb25f2284334a9f7168a25575/docs/DEPLOYER-HOST.md)
defines the actual policy keys, evidence formats, adapter interface and installer
commands. The policy is `/etc/ci-fleet-deployer/deployer.conf`, a root-owned
regular file with mode `0600` under a protected mode-`0700` directory. Adapters,
credentials and evidence use the runbook's protected directories. Do not commit
policy copies, credential paths, requests or approval/checkpoint records here.
The template does not generate or execute those files.

The adapter must implement `validate`, `health`, `deploy`, `rollback` and scoped
`cleanup`. Its source belongs to the application repository; its installed bytes
and runtime configuration remain host-local. It runs in a bounded DynamicUser
service with a private network, read-only filesystem, no capabilities and a
constrained broker. The broker permits only the approved artifact and labelled
resources for the exact deployer identity, environment and target on a dedicated
rootless daemon. It rejects host networking, arbitrary bind mounts, Docker exec,
unrestricted Compose, builds and global prune. Private artifacts require
separately authorized provisioning; the broker rejects registry auth headers.

## Approval and routing restrictions

The host accepts `manual-exact-head` or `external-exact-head` protected evidence,
or `github-environment` with separate exact-head capability evidence for that
installation. A GitHub plan name, CI output or the presence of an Environment
does not prove protected approval. Use only a plan and repository visibility
that actually support required reviewers. Every provider must approve the exact
source and artifact outside the requesting CI identity.

The host consumes a stable approval ID before adapter dispatch. Replayed,
mismatched or missing approval fails closed. Failed attempts need a new approval
ID. Retain the durable replay ledger, audit records, deployed policy,
last-known-good state, adapter bytes and credential sources across restart,
rotation and rollback. Uncertain or interrupted operations require protected
journal reconciliation, not deletion of guards or evidence to force progress.

Never register the deployer as a GitHub runner, accept PR jobs on it, share a CI
Docker daemon, or use ordinary-CI runner groups or routing labels to dispatch
privileged work. `public_repositories: false`, one pool per runner group,
capacity budgets, task/shard isolation and five-minute ordinary-CI job limits
remain unchanged. Deployment service bounds come from the separate core
contract and do not extend ordinary-CI jobs. The deployer receives no deploy-ref
write credential. Any future writer must use a separate reviewed authority.

The fleet schema and validator reject deployer roles, runner groups and routing
labels declared on deployment host groups, plus host-policy fields and approval
declarations in inventory. Ordinary-CI pool identifiers are adopter-owned names;
their spelling cannot register or authorize the standalone deployer. The host
runtime rejects ordinary GitHub runner state regardless of group or label names.
The current deployer also checks unit paths, unit-file inventory and loaded
units, including vendor, runtime and transient units. Mixed controller, tester,
status-receiver or runner roles and unavailable inventories fail admission.
Uncertain operations retain protected guards and journals for operator recovery.
These engine protections require prepared-host verification before adoption.
Controller engines
and reusable workflows still require full immutable SHAs. Mutable deployment
artifacts are rejected by the pinned host runtime, not by the inventory's image
repository field. Production inventory still requires `automatic: false` and
`requires_approval: true`. The reviewed runtime rejects production deployment
and cleanup, and the installer rejects production rollback even with additional
production authorization evidence. V2 does not enable those operations.

## Migration, rollback and acceptance

Follow [the staged v1-to-v2 migration](UPDATING.md#deployment-boundary-v1-to-v2)
before host adoption. A repository merge or template import cannot provision a
host, deliver credentials or authorize cutover. Keep existing application
deployment paths available until separately authorized cutover and rollback
decisions are complete.

Application compatibility work remains in
[MMPriceFeed #126](https://github.com/RandomDevelopment/mmrss/issues/126) and
[TF2 Recommendation Engine #373](https://github.com/RandomDevelopment/TF2-Recommendation-Engine/issues/373).
They must resolve data persistence, database/migration compatibility, ingress,
source egress and credential delivery within the broker restrictions. This
template does not certify either adapter or edit those applications.

Repository acceptance requires policy/updater tests, exact pinned-contract
verification, strict validation of initialized fictional adopters, required CI
and review on the final PR head. No prepared-host end-to-end exercise is a
template merge gate. Provisioning, credential use, deployment, failure exercises,
checkpoint restoration and production remain separately authorized operations.
Local tests do not establish any of those operational results.
