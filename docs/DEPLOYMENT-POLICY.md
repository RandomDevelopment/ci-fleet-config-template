# Deployment policy boundary v2

Boundary v2 supports the standalone staging deployer introduced by
[ci-fleet PR #69](https://github.com/RandomDevelopment/ci-fleet/pull/69).
The minimum core revision reviewed here for verified-stop rollback is
`461a707a688dd4cd03ddbc15a0bad69ff34b6635`, the merged commit of
[ci-fleet PR #186](https://github.com/RandomDevelopment/ci-fleet/pull/186).
The deployer reads protected host-local policy with `SCHEMA_VERSION=1`.
`fleet.json` remains schema-v3 logical inventory. The initializer produces
inventory only, so fresh and existing adopters use the same external policy path.
The [optional ordinary-CI Docker policies](UPDATING.md#optional-docker-network-and-storage-policy) do not
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

For a separately authorized first staging deployment, start with the
[pinned first staging quickstart](https://github.com/RandomDevelopment/ci-fleet/blob/587dee67c792aa51526f4059829fef9f6c3ca932/docs/STAGING-QUICKSTART.md).
The reviewed [deployer runbook](https://github.com/RandomDevelopment/ci-fleet/blob/461a707a688dd4cd03ddbc15a0bad69ff34b6635/docs/DEPLOYER-HOST.md)
defines the actual policy keys, evidence formats, adapter interface and installer
commands. For the application-to-host handoff, see the
[deployment path diagram](https://github.com/RandomDevelopment/ci-fleet/blob/fd4b75e374ae4da2230ff7bbbf708520969f3089/docs/ARCHITECTURE.md#application-deployment-path).
The policy is `/etc/ci-fleet-deployer/deployer.conf`, a root-owned
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

## Verified-stop rollback for exclusive services

The three optional `ROLLBACK_*` settings belong only in protected host-local
`deployer.conf`. Fleet validation rejects them as unknown inventory fields.
The examples below use fictional service names and contain only policy values.

| Host policy key | Accepted values | Fictional example |
| --- | --- | --- |
| `ROLLBACK_EXCLUSIVE_SERVICES` | A comma-separated list of 1 to 32 unique identifiers matching `^[a-z0-9][a-z0-9._-]{0,63}$`, without spaces. Each generated `ci-fleet-deploy-<DEPLOYER_IDENTITY>-<service>` name must fit within 128 characters. Omit the key if there are no exclusive services. | `scheduler` |
| `ROLLBACK_STOP_TIMEOUT_SECONDS` | An integer from 1 to 600. The effective default is 120 seconds. | `90` |
| `ROLLBACK_STOP_SIGNAL` | One of `SIGTERM`, `SIGINT`, `SIGQUIT`, `SIGHUP`, `SIGUSR1`, `SIGUSR2` or `SIGWINCH`. If omitted in both policies, core uses the container's supported `StopSignal` or defaults to `SIGTERM` when it is empty. Core rejects unsupported signals before signaling. | `SIGTERM` |

Timeout and signal each require an exclusive service list in the same policy.
Core merges the active and retained last-known-good service lists. The union
can contain at most 32 services. Its size multiplied by the effective timeout
must be at most 1,800 seconds. An explicit active timeout or signal takes
precedence over the corresponding retained value. If either policy declares
exclusive services, both must name the same dedicated rootless daemon through
the same `DOCKER_SOCKET` value. The policies must also agree on environment,
target and deployer identity.

Core looks up containers by the target's ownership labels and the
`io.randomdevelopment.ci-fleet.service` label. If the service label is absent,
core uses the generated container name. Before invoking the retained adapter's
`rollback`, core validates the adapter, disables restart for each running or
restartable exclusive container and verifies exit through Docker. The container
must have no running, restarting or paused state, a zero PID and restart
disabled. Ambiguous ownership or multiple active or restartable matches block
the stop. An unverified stop after signaling retains recovery state and blocks
adapter dispatch. `SIGKILL` is invalid in policy. A separately authorized
rollback with `--force-stop-timeout` can escalate after an eligible graceful
timeout. Core still verifies exit.

The adapter's `rollback` must tolerate exclusive containers that core has
already stopped. It must restore one running replacement for each exclusive
service declared by the retained policy without overlapping instances. The
broker permits starting containers only with the approved artifact during
rollback. The adapter verifies application health and writes the private
`CI_FLEET_DEPLOYER_ROLLBACK_COMMIT` marker atomically as its last successful step
before exiting zero. On failure, the adapter must restore its pre-call
application state. Core verifies each replacement's image ID and requires
`healthy` when Docker health checks are configured. Core waits up to 30 seconds
for a starting health check. If readiness remains unverified and the journal
confirms broker completion, retrying rollback checks readiness without running
the adapter's `rollback` again. If broker completion is uncertain, core blocks
for operator recovery. After commit, core runs the adapter's read-only `health`
before publishing the deployed snapshot. Preserve the protected journal and
follow the pinned runbook if recovery is needed.

## Host-local HTTP ingress

An exclusive staging HTTP service can stay on its internal Docker bridge
without publishing ports. The host-local reverse proxy reaches it over a
pathname Unix socket in a dedicated, labelled local named volume with no
driver options. The application also checks HTTP through the socket in its
Docker health check. Follow the
[reviewed engine runbook](https://github.com/RandomDevelopment/ci-fleet/blob/3848226bb5a7ee5d8ba8b47d9e4b581e0c507ff8/docs/DEPLOYER-HOST.md#host-local-http-ingress).

- Give only the exclusive service a writable mount of the volume. In the
  approved image, give the empty mount directory mode `0755` and ownership
  by the service's non-root numeric UID and GID. Use the same IDs, volume
  and socket path in the candidate and last-known-good artifacts. Verify
  ownership after volume initialization using the actual rootless daemon's
  `uid_map` and `gid_map`. In the matching row, add the container ID's offset
  within the row to the outside start ID. Keep the volume through deploy,
  rollback and routine adapter cleanup.
- Verify that Docker's canonical `Mountpoint` matches
  `<data-root>/volumes/<scoped-volume>/_data` under the dedicated daemon's
  approved data root. A protected ancestor, such as a daemon-owned mode-`0700`
  directory without access ACLs, must prevent the proxy worker and unrelated
  host accounts from traversing the original path.
- Make the route private before attaching the volume. Use the runbook's
  helper to bind only that volume directory with private propagation and
  `ro,nosuid,nodev,noexec,nosymfollow`. Keep the route ancestors root-owned
  and limit search access to the dedicated unprivileged proxy group. Keep
  the proxy worker outside the daemon group. Start the proxy after the
  mount verifies and stop it before unmounting or replacing the volume.
  Use a loopback listener and apply proxy or application authentication if
  other local callers lack authorization.

During deployment, the adapter stops the incumbent and verifies exit before the
candidate can remove a stale socket entry or bind that pathname. If the
incumbent has a restart policy, the adapter removes the stopped container
through the broker and retains the volume. For rollback, declare the socket
owner in `ROLLBACK_EXCLUSIVE_SERVICES`. Core verifies the stop before it
dispatches the retained adapter. Expect an interruption while the socket
owner changes. See the [staging upgrade steps](UPDATING.md#host-local-http-ingress-for-staging).

Keep the volume, mount, proxy and rollback settings in protected host-local
configuration. Ingress uses the existing broker contract and requires no
template schema field, initializer setting or automation credential.

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
for a v1 baseline or [the verified-stop update](UPDATING.md#verified-stop-rollback-for-staging)
for an existing v2 adopter. A repository merge or template import cannot provision a
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
