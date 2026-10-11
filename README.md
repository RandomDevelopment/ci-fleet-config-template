# ci-fleet configuration template

This is the public, secret-free starting point for an organization's private `ci-fleet` configuration repository. It records which trusted projects may use each CI pool, the reviewed desired state for controller machines, infrastructure capacity budgets, logical deployment environments, and the standardized commands every project must expose.

It does **not** contain runner registration tokens, deploy credentials, private keys, host addresses, VM IDs, storage names, backup identifiers, or `.env` files. The sole address exception is a reviewed Docker `default_address_pools[].base` CIDR after an adopter has staged engine support. It is fleet capacity policy, not a host or service address. Public examples and fixtures use RFC 5737 ranges only.

```mermaid
flowchart LR
  E[Public ci-fleet engine] -->|pinned engine commit| C[Private configuration]
  C -->|pool policy and capacity budget| A[Controller at site A]
  C -->|pool policy and capacity budget| B[Controller at site B]
  P[Authorized project repositories] -->|all independent jobs| G[GitHub runner group]
  A --> G
  B --> G
  G --> R[Ephemeral Docker workers]

  classDef public fill:#dff4ff,stroke:#1570a6,color:#102a43
  classDef private fill:#fff3cd,stroke:#9a6700,color:#3d2b00
  class E public
  class C,A,B,P,G,R private
```

## Start a private organization configuration

1. Create a **private** repository from this public template.
2. Clone it and initialize the first project and controller:

   ```bash
   ./scripts/init.sh \
     --organization your-org \
     --project your-app \
     --controller ci-01 \
     --location primary-site \
     --capacity-budget 1 \
     --max-runners 1 \
     --engine-ref <reviewed-ci-fleet-commit>
   ```

3. Edit `fleet.json` to add the organization's real logical mappings.
4. Run the strict policy check:

   ```bash
   ./scripts/validate.sh --strict
   ```

5. Keep secret values outside Git. GitHub Free private repositories cannot use Environments or Environment secrets. Team supports private Environment secrets, but required reviewers for private repositories require Enterprise. Root-owned host files and external secret managers are alternatives for secret storage. A secret store does not supply deployment approval.

The initializer refuses to replace a configured file unless `--force` is explicit. Run `./scripts/init.sh --help` for repository, registry, runner-group, controller, location, capacity, resource, and output options.

## Reviewed compatibility and release state

`template-compatibility.json` pins the reviewed embedded template to ci-fleet commit `0aed0d7e85e10050028b7d11fb12b84b3619e638`. It records schema and validator/initializer support, optional staged capabilities, the standalone new-controller safety check, and the unchanged fictional example engine pin. `engine-rollout-evidence.json` records active per-controller capability evidence in the shape consumed by that pinned core. New status-reporting or Docker network-policy fields require prior-state evidence. Upgrade an engine with active optional capabilities in exactly two integrated commits:

1. Keep `fleet.json` and `engine-rollout-evidence.json` on engine A. Add reviewed engine B capability evidence to optional adopter-owned `next-engine-rollout-evidence.json`, using the same schema-version-1 record shape.
2. Change `engine_ref` to engine B, promote the matching sidecar record to `engine-rollout-evidence.json`, and remove the sidecar when it has no remaining staged records.

The committed examples and initializer omit both optional fields because their engine capability has not been staged. When a private adopter later stages `docker_network_policy`, it must replace the RFC 5737 review fixture with a reviewed operational pool before strict validation passes. Initial release preparation and exclusions are in `docs/RELEASE.md`; no tag or GitHub release is published by this repository change.

## Deployment policy boundary v1

This release supports ordinary CI controller configuration. `host_groups`, `environments`, project `deployments`, and `required_secret_names` are logical inventory only. `automatic` and `requires_approval` record intended policy. Passing schema or strict validation does not prove an approval occurred, authorize a deployment, or grant a host credentials or network access. The initializer and both fictional examples retain these inventory objects for schema-v3 compatibility.

`template-compatibility.json` records boundary version 1 and its safe exclusion under issue #11. Executable persistent tester, image builder, development deployer, production deployer, and optional deploy-ref-writer roles are unsupported. The template defines no runner groups, labels, credentials, or authority for those roles. Do not route privileged work through ordinary CI or give ordinary CI production credentials, production network access, or deployment-ref write authority. Public pull-request CI remains unprivileged; privileged delivery belongs in a separate private repository.

The reviewed core validator at `0aed0d7e85e10050028b7d11fb12b84b3619e638` rejects `organization.github_plan`, environment `approval_mechanism` and `approval_evidence`, and the `persistent-testing` and `image-build` host-group roles. This template rejects the same declarations in every validation mode. Its two exact-hash safety deltas preserve staged Docker network-policy enforcement and report malformed host groups and enum values without a traceback. The compatibility record names each core gap. It does not infer an approval mechanism from omitted fields. No configuration in this version can claim a validated protected-Environment gate or manual-external approval record.

Before enabling deployment through a future versioned contract, an operator must establish a real approval outside the requesting CI identity. A protected GitHub Environment requires a plan that supplies required reviewers for the repository's visibility. The manual/external fallback must approve the exact reviewed commit before an isolated privileged identity receives immutable image digests. CI run output, moving refs or tags, mutable artifact references, and secret stores are not approval evidence. Keep approval records outside this inventory contract until core support is reviewed.

Core [#22](https://github.com/RandomDevelopment/ci-fleet/issues/22) and [#23](https://github.com/RandomDevelopment/ci-fleet/issues/23) own the deployer and tester contracts. A future contract must distinguish each privileged role, reject reuse of ordinary-CI runner groups and routing labels, isolate credentials and network authority, and keep the optional ref writer separate. It must ship reviewed core support, schema, initializer, validator, tests, and migration guidance together. Boundary v1 explicitly excludes those guarantees.

## Schema v3: Git-authored controller desired state

`fleet.json` is the reviewed authority for logical controller state. Each entry in `controllers` has a unique ID and declares:

- its runner pool and logical location;
- whether it is `active`, `drained`, or `disabled`;
- its unique GitHub scale-set name;
- an `experimental`, `stable`, or `retiring` lifecycle;
- the full reviewed ci-fleet commit SHA it runs;
- a zero managed minimum and reviewed maximum runner capacity;
- CPU and memory available to each ephemeral runner.

The controller ID is how a target host selects its declaration. A location is a non-sensitive logical slug such as `primary-site` or `remote-site`, never an address. Runtime-generated configuration and credentials remain host-local.

### Pool capacity is infrastructure policy

Each runner pool has a `capacity_budget` and a runner group that must not be assigned to any other pool. Unique runner-group assignment keeps routing and repository authorization unambiguous. The semantic validator enforces this cross-object rule because JSON Schema cannot compare values stored in separate object properties.

The validator totals the maximum capacity of every active or drained controller assigned to the pool and rejects overcommit. Drained capacity remains reserved so an undrain cannot silently exceed the reviewed budget. Disabled controllers do not reserve capacity.

Application repositories do not encode the number of available workers. They submit all independent tasks and shards. Do not use GitHub Actions `strategy.max-parallel` to model fleet size; controllers and the private configuration decide how many jobs run simultaneously. An application may limit concurrency only for a separately documented external-system constraint, not worker availability.

This separation lets one infrastructure change add, remove, drain, or resize controllers without editing every project workflow.

## Target-host installation and adoption

The public ci-fleet engine owns the host installer. Its intended interface consumes one logical controller from a pinned private configuration revision:

```bash
sudo ./scripts/install-worker-controller.sh \
  --config-repo example-org/example-fleet-config \
  --controller example-ci-01 \
  --ref <reviewed-config-commit> \
  --install
```

Use `--adopt` instead of `--install` to bring an existing controller under Git-authored desired state. The engine contract also provides `--check`, `--upgrade`, `--rollback`, and `--uninstall` modes.

The command runs on the target Linux Docker machine. It validates the pinned configuration, renders host-local runtime state, preserves root-owned secrets, drains before disruptive changes, verifies a recoverable checkpoint, installs maintenance services, checks health, and reports drift without exposing credentials. OpenClaw or another agent may invoke it, but no agent is required.

The engine-side implementation is `scripts/install-worker-controller.sh` in the parent ci-fleet repository. Its accepted scope is isolated ordinary-CI fleet hosts under reviewed schema-v3 desired state; this configuration repository never installs a controller by itself.

## Drain, retire, and delete a controller host

Host retirement is an explicit reviewed transition:

1. Change the controller state to `drained` and merge the private configuration change.
2. Converge the host and verify that it accepts no new work and has no active runner.
3. Remove only fleet-owned residue and verify replacement capacity.
4. Unregister its scale set and revoke that host's credentials.
5. Change the declaration to `disabled` or remove it in a later reviewed change.
6. Delete or repurpose the machine according to the installation's declared infrastructure policy.

Deleting one generic controller must not require application workflow changes. Legacy project-specific hosts should remain only until CI, promotion, and deployment no longer reference them.

## Hard rules

- Public repositories never receive direct access to the trusted self-hosted runner pool.
- Every project publishes `scripts/ci/plan.json` and implements `./scripts/ci/run.sh <task> --shard INDEX/TOTAL` in its own Docker-defined test environment.
- `./scripts/ci/run.sh fast` and `full` remain aggregate developer commands; fleet scheduling expands their named tasks across available workers.
- Every matrix job has a five-minute hard timeout, while expected test payload targets four minutes or less to reserve startup and reporting time.
- Application workflows submit all independent jobs; infrastructure configuration alone controls worker capacity.
- A GitHub runner group is assigned to exactly one runner pool.
- CI runner pools execute ordinary CI only. Deployment host groups are logical inventory, with executable privileged roles excluded by deployment policy boundary v1.
- Production inventory requires approval and prohibits automatic deployment. The actual gate must be available for the repository plan and visibility, and established outside this inventory contract before deployment.
- Controller engine revisions, reusable workflows, and third-party actions are pinned to immutable commits.
- Configuration contains logical identifiers only. Secret values, private host details, and credentials never enter Git.
- Promoted artifacts are container image digests; production does not rebuild a different image.

`fleet.schema.json` provides editor completion and structural documentation. `scripts/validate.py` is the authoritative dependency-free policy check, including cross-object relationships JSON Schema cannot express clearly.

## Five-minute parallelism contract

Projects divide their total test-minutes into independent named tasks and deterministic shards. Forty-five test-minutes require at least nine perfectly balanced five-minute jobs in theory. In practice, projects should create additional shards targeting four minutes of test payload so checkout, image preparation, and reporting remain inside the five-minute job ceiling.

```mermaid
flowchart LR
  P[plan.json] --> M[GitHub matrix]
  M --> A[lint]
  M --> B[unit 1 of 4]
  M --> C[unit 2 of 4]
  M --> D[integration 1 of 3]
  M --> E[other independent shards]
```

Adding workers reduces wall-clock time only while independent shards remain queued. A genuinely indivisible test longer than five minutes must be optimized, split, or moved into an explicitly slower scheduled class outside ordinary CI.

## Repository map

| Path | Purpose |
|---|---|
| `fleet.json` | Fictional, valid schema-v3 configuration with one controller |
| `fleet.schema.json` | JSON Schema draft 2020-12 editor contract |
| `template-compatibility.json` | Exact reviewed core/template compatibility and prepared release state |
| `engine-rollout-evidence.json` | Active optional-capability evidence, empty in the public template |
| `next-engine-rollout-evidence.json` | Optional adopter-owned next-engine evidence sidecar; not committed by this public template |
| `scripts/init.sh` | Safe first-project and first-controller initializer |
| `scripts/validate.sh` | Structural, relational, capacity, and secret-boundary validation |
| `scripts/test_policy.py` | Regression tests proving unsafe configurations fail closed |
| `examples/multi-host/fleet.json` | Fictional two-project, two-location controller topology |
| `SECURITY.md` | Secret handling and vulnerability reporting |
| `AGENTS.md` | Non-negotiable rules for humans and coding agents |
| `docs/UPDATING.md` | Keeping a derived private repository current: schema vs template versions, releases, migrations, Dependabot |
| `docs/RELEASE.md` | Prepared initial release notes and immutable-tag publication checklist |

## Public and private boundary

| Safe in this public template | Belongs in the private config repo | Belongs only outside Git |
|---|---|---|
| Schema, validator, fictional examples | Real repository names and runner-group policy | Tokens, passwords, private keys |
| Standard CI entrypoint names | Logical controller IDs and locations | Host addresses, VM IDs, SSH material |
| Controller state and lifecycle vocabulary | Capacity budgets and per-runner limits | Rendered runtime configuration |
| Reusable engine interface | Required secret **names** | Secret values and application credentials |

The public engine and this template use the [Unlicense](LICENSE). See [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) before copying third-party material into a derived repository.
