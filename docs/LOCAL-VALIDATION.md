# Complete local configuration validation

The complete suite runs without GitHub Actions, an Actions API, hosted minutes
or account billing. It validates Git commits rather than working-tree edits.
`./scripts/validate.sh --strict` remains useful while editing an initialized
adopter, but runs only the focused policy check.

## Prerequisites and trusted inputs

Use a separate disposable Linux execution worker with systemd 255 or newer as
PID 1 and cgroup v2. Use Bash 4+, Git 2.40+, Python 3.11+, OpenSSL, ShellCheck
and GNU stat. Updater fixtures need Git's `merge-tree --merge-base` support.
The trusted launcher runs as root; ordinary configuration stages use a locked
unprivileged account and read-only trusted inputs. Writable paths are limited to
that stage's source, home and scratch. Root-launcher regression fixtures run as
root only on this disposable worker. No Docker daemon, runner registration or
fleet credential is needed. There is no custom process-tracking fallback.

From a clean core checkout at the exact revision in the trusted suite's
`EXECUTOR_REVISION`, prepare each fresh worker once:

```bash
sudo python3 -I /trusted/executor/scripts/local_validation_executor.py \
  --prepare --disposable-host
```

Preparation installs the shared executor and a revision/hash manifest under
`/usr/local/lib/ci-fleet-validation` and creates a locked execution account and
protected workspace parent. It adds no daemon, timer or unique fleet state.
Use a Linux VM or remote prepared worker from macOS or Windows. Shared executor support merged in core [PR #144](https://github.com/RandomDevelopment/ci-fleet/pull/144)
at `689c7c00deb0eebcb25f2284334a9f7168a25575`. The ordinary-CI
configuration-policy baseline is `840fb9be8a1c69404a5eebcf17855eff13c6c928`.
The executor remains independently pinned to the reviewed
`689c7c00deb0eebcb25f2284334a9f7168a25575` implementation. Engine merge,
template acceptance and host activation remain separate.
Executor and policy pins are independent inputs. Pinning an executor
alone does not adopt the managed-image contract or activate a runtime.

Never execute candidate scripts on an active fleet host or a machine holding
the evidence-signing private key. Source programs are proposed code and need
independent review before execution.

Platform and host admission run before Git inspection, output-directory creation,
tool probes or candidate execution. The harness rejects standard installed
fleet or signing-role markers. It checks `ci-fleet`, `ci-fleet-tester`,
`ci-fleet-deployer`, `ci-fleet-status` and `ci-fleet-signing` under `/etc`,
`/var/lib` and `/opt`, plus installer and credential metadata directories,
`/srv/ci-fleet-signing` and standard systemd role/runner markers. An existing
marker or a symlink, including a broken symlink, fails admission. The check
reads no signing-key contents and performs no credential scan. Operators must
identify custom installations separately and still supervise execution on a
disposable machine with a separate signing authority.

Prepare a clean committed checkout of the reviewed standalone template at
`/trusted/template` and an independent engine checkout at `/trusted/ci-fleet`.
Review the complete template harness as well as the engine validator. The
harness records its actual `suite_revision` and `suite_tree`; a caller cannot
supply a suite revision to relabel another program. Engine policy is selected
independently through `--policy`, never from candidate configuration.
The harness binds its caller and candidate-test runner to the committed suite.
It loads only the protected installed core executor, requires its exact revision
and records `executor_revision`. Identity and committed-byte checks disable Git
replacement refs and grafts. Candidate-local modules cannot select the executor.
An independent signing authority must check that recorded executor revision
against the reviewed suite pin before accepting the bundle.

Fetch the required commits and fresh engine history before running. Source,
main, reviewed head, engine policy and any nonzero base must be full lowercase
40-hex available commit SHAs. Source, policy and suite histories must not be
shallow. A nonzero base must be an ancestor of the source and any original
reviewed head. Select the actual integrated first-parent base for host-acceptance
work when a prior integrated state exists. The all-zero base has the separate
meaning below. A syntactically valid engine SHA does not establish that it is
reviewed or compatible.

Local does not mean air-gapped. Fetching history and the exact-core and external
deployer compatibility checks can contact public GitHub repositories. A network
failure fails the affected check. Each compatibility corpus downloads its pinned
core and deployer inputs once, checks their reviewed hashes, and supplies local
inputs to its success and rejection subprocesses. Corruption tests use separate
copies. Stages and public/candidate corpora retain independent fixtures. Repeated
core-file reads within a process reuse the downloaded bytes; explicit local
inputs are always read again so corruption remains observable.
The suite needs no GitHub Actions event, scheduler or authenticated Actions API.
Keep credentials and reports outside
configuration Git.

## Run the complete suite

Replace all SHA placeholders and use a new external output directory:

```bash
sudo python3 -I /trusted/template/scripts/local_validate.py \
  --repository /work/config --repository-name OWNER/REPOSITORY \
  --source SOURCE_SHA --base BASE_SHA --main MAIN_SHA \
  --policy-repository /trusted/ci-fleet --policy REVIEWED_ENGINE_VALIDATOR_SHA \
  --output /results/new-dir
```

`--output` must name a new directory outside every Git worktree and Git storage
path, including the source, trusted template suite and engine-policy repositories.
An ignored artifact directory inside any of these repositories is rejected.
Subdirectories and symlink aliases do not bypass this boundary. Bare input
repositories are allowed, but output must remain outside their storage too.

After host admission, preflight resolves the output path and inspects the
explicit source and policy repositories, the executing suite and the nearest
existing output ancestor. It checks both Git worktree roots and Git storage
locations using the shared hardened Git environment described below. Discovery
also fixes `LC_ALL=C` and `GIT_DISCOVERY_ACROSS_FILESYSTEM=1` and preserves path
bytes.
Unexpected Git errors, indeterminate locations and broken `.git` markers fail
preflight. This inspection finishes before directory or report creation.

`--repository-name` is the actual operator-selected owner/repository identity,
not a value inferred from candidate files or its remote. Only
`RandomDevelopment/ci-fleet-config-template` selects fictional upstream
fixtures. Never supply that identity for an adopter. The suite preserves the
public fixture's origin identity in isolated checkouts so upstream-only tests
do not silently disappear after cloning from a local path. Fictional upstream
reference configurations run non-strict checks. Managed-image migration ordering
applies to strict adopters; fictional upstream pin/image changes are not host
migrations. Both modes retain optional-capability predecessor and evidence checks. Initialized adopters must pass
strict validation, including transition checks against committed prior fleet,
active evidence and next-engine evidence when a prior integrated state exists.

If no prior integrated state exists, explicitly pass
`--base 0000000000000000000000000000000000000000`. This assertion applies even
when an imported source commit has parents. The report records
`prior_state_absent: true`. Conventional-commit and committed-secret checks
cover the complete source and original reviewed histories. The configuration
adapter uses an empty prior controller set and supplies no previous active or
next-engine evidence; current-state and current-evidence checks still run.
Do not use this sentinel to omit an existing integrated state or its evidence.
Every nonzero base retains the usual ancestry and transition checks.

When validating an applied merge or squash commit, add
`--reviewed-head ORIGINAL_PR_HEAD_SHA`. Set `--source` to the applied commit
and, when prior integrated state exists, `--base` to its first parent.
The reviewed and applied trees must match. Both histories are scanned,
including secrets added and then removed before a
squash. A result for the original PR head alone does not validate the applied
commit. `--main` identifies the mainline context explicitly. For a PR run, use
the actual target/base commit, including when the source comes from a fork.
For a main-branch push, use the source commit. To validate a PR title locally,
pass `--pr-title "$PR_TITLE"` as one quoted argument.

The suite runs these named stages:

| Check | Coverage |
|---|---|
| `commits` | Independently pinned engine commit policy |
| `history-secrets` | Pinned scanner across source and original reviewed histories |
| `syntax` | Shell and Python syntax |
| `engine-policy` | Current state against the independent engine validator and schema |
| `configuration` | Stricter trusted template policy, prior fleet and active/next evidence, reference and multi-host fixtures |
| `core-compatibility` | Exact reviewed-core comparisons where applicable and mandatory candidate external deployer verification |
| `initializer` | Initializer success and rejection cases, generated strict configuration and RFC 5737 rejection |
| `policy` | Standalone forbidden-configuration regressions |
| `updater` | Updater safety and immutable-release handling |
| `release-update` | Immutable-release import and fictional adopter fixtures |
| `harness` | Local execution, failure, identity and optional-workflow regressions |

The pinned engine checks current state. The independently committed template
validator enforces the reviewed standalone transition rules and active/next
evidence, including the standalone next-engine, network and storage safety checks.
Both checks finish before any candidate initializer or test program executes.
Fresh initialized adopters need reviewed managed image scalars. Image-free adopter
staging needs its complete committed predecessor and retained active/next-engine
evidence; the all-zero no-prior-state sentinel cannot authorize that migration.
Use a suite that supports [managed-image migration](MANAGED-IMAGES.md), not the
published `v1.1.0` suite. Required inventories change only through a reviewed
suite revision; an older trusted corpus is not silently replaced by candidate tests.
A newer engine with an incompatible fleet contract fails validation; this
entry point does not waive its schema or promote its revision.

Required policy, updater, release-update, harness and workflow test definitions come
from the pinned suite for upstream and adopter runs. Upstream runs execute each
corpus once against candidate programs and workflow inputs in trusted fictional
fixtures. They also test the candidate's README, AGENTS and LOCAL-VALIDATION,
UPDATING, RELEASE and DEPLOYMENT-POLICY documents. Public fleet/example fixtures
remain trusted inputs.

Adopter runs retain the complete trusted public-fixture regressions and the
candidate-mapped policy, updater, release and workflow checks. The candidate
policy run excludes only its three upstream-only byte-comparison probes; the
complete trusted public run covers them. The runner names those probes and
rejects any actual skipped test. Adopter configuration and customized documents
do not replace the trusted fictional configuration or public release fixtures.

The workflow corpus reads the candidate workflow. If that optional file is
absent, a pinned availability test checks the local entry point and the report
records `hosted-workflow-present: false`. This applicability does not use a
runtime skip. Adopter runs still execute the full trusted public workflow corpus.

The pinned local-validation, executor-binding and candidate-runner test inventories
run once against candidate harness programs in both upstream and adopter modes.
The outer runner comes from the selected trusted suite; the executor is the
independently selected installed core revision. Candidate harness files are programs under test, never the outer driver.
Runner self-tests read their workflow content and definitions from the trusted
fixture root. Those fixture resources do not restore a missing candidate
workflow or change its availability result.

Adopter policy, updater and release-update stages each run two checks concurrently
in independent fixture copies. One uses the trusted public suite as its input;
the other uses candidate programs in derived mode. Both use the pinned runner's
required test plans and execution counts. The other stages remain sequential,
and the system manager owns both checks and their descendants.
Either failure fails the stage. The driver waits for both checks, including after
a child launch failure, and success requires both named child logs to exist.

The trusted parent freezes command vectors and invocation-private scratch child-log paths
before candidate execution. After the system manager finishes cleanup, the parent
assembles command headers, public output, candidate output and driver diagnostics
in that order, including after failure, cancellation or timeout. Late descendant
output therefore precedes the final stage-log digest. The combined stage log
listed in `result.json` is authoritative; child logs are temporary inputs discarded with the worker scratch space.
Each checkout symlink must resolve within its own worktree and outside `.git`.
Links into trusted sibling checkouts, external paths or Git metadata fail before
candidate stages run, even when dangling. Internal worktree links remain valid.
Complete installed-executor revision, permission and host admission precedes
Git output discovery and creation. Refusal creates no result directory or report.

Both checks share the existing command timeout. The optional hosted full-suite
job has the separate budget documented below.

The trusted parent runs candidate-mapped tests in a standard-library process
worker and requires its normal integer result. An abrupt zero-status exit,
including `os._exit(0)`, or `SystemExit(0)` fails validation. Systemd continues
to own command deadlines and descendant cleanup.

Each candidate-mapped required corpus records its planned test IDs. IDs must
be nonempty and unique, the executed count must match the plan, and actual
skips fail. After
the required corpus passes, a differing candidate test file can add test IDs
as supplemental coverage. Existing IDs keep the pinned definitions. Identical
test files add no duplicate run. Candidate tests cannot remove the required
inventory by deleting or neutralizing their own files.
Ordinary-CI byte comparisons are upstream-only; verification of the candidate's
external deployer metadata remains mandatory in derived repositories. The
report's applicability records identify that distinction. Every named stage
still runs and `expected_skips` remains empty. Missing tools and skipped tests
fail the suite. Check the exact report before using it as evidence.

The independent engine validator checks current state without applying the
standalone transition extensions. The independently pinned trusted template
validator checks transitions against the base, including current and prior
active evidence and next-engine sidecars. Missing transition support in that
template validator fails the suite; keep the evidence intact. Trusted engine,
stricter template and candidate deployer-metadata checks run before any
candidate initializer or test program. Trusted host acceptance remains gated
on a supporting merged engine and the separate signing and recovery checks.

## Results, failures and cleanup

Early platform or host-admission failures, and invalid output locations, produce
a nonzero exit and a diagnostic on stderr without creating an output directory
or report. After admission and output validation succeed, the new output
directory contains `result.json` and per-check logs. Preserve the whole directory.
The report records source, original reviewed head, tree,
base, whether prior integrated state is absent, main, engine-policy revision,
suite revision/tree, tool versions, timestamps, results, expected skips and
log SHA-256 digests. The suite ID is
`ci-fleet-config-standalone-v2`; the profile is `full`.

Only a completed report with `status: passed` and a successful process exit is
a completed developer result. Nonzero exits, missing or incomplete reports,
missing tools, timeouts and unexpected skips are failures or incomplete work.
Do not infer success from the last visible test line. A change to source,
reviewed head, tree, base, main, PR title, engine policy or suite invalidates prior
results. Re-run against the new identities.

Before running candidate programs, the harness freezes identities, the stage
plan and report provenance. It creates separate verified seed checkouts for
source, engine policy and trusted suite. The orchestrator keeps direct manifests
of these seeds in memory, including digests of file bytes, entry types and modes,
symlink targets and `.git` metadata. Git status or index checks alone cannot detect all
changes, such as assume-unchanged files or edits to `.git/config`.

Initial seeds start as empty Git repositories. Source fetches use
`--no-tags` and explicit source, original reviewed head, main and nonzero base
SHAs with their complete ancestry. Engine-policy and trusted-suite fetches
include only their selected commit and its ancestry. Checkouts inherit no
unrelated branches or tags, and the standalone suite needs no inherited release
refs. Updater and release-update tests still use their isolated release fixtures.

Before freezing a seed manifest, the harness records the intended source main
ref and normalizes origins. Suite and public-template source origins name the
public template; policy and derived-source origins name their own seed paths.
Each named stage receives independent copies of all three verified seeds,
including detached HEADs, the declared histories and normalized metadata.
Copying preserves symlinks and modes without hardlinking files, Git objects or
indexes to the seed. An existing stage target is rejected. Seeds are verified
before copying, and each copied target must match the same frozen manifest
before a candidate command runs. Seeds are never fetched or modified after freezing. This avoids
repeated Git setup while retaining fresh stages. Metadata such as `FETCH_HEAD`
may differ from the former repeated-clone implementation; effective selected
identities, main ref and origins remain fixed.
Before the stage can pass, the harness checks the seeds and stage checkouts
against their manifests. Generated regular files under `__pycache__` or with a
`.pyc` suffix, and their cache directories, may appear only in stage checkouts;
the harness discards them with that stage. Seed changes fail validation.
All orchestrator Git calls and stage environments remove every inherited or
supplied `GIT_*` variable before adding nine fixed controls.
`GIT_NO_REPLACE_OBJECTS=1` and `GIT_GRAFT_FILE=/dev/null` disable replacement refs
and grafts. `GIT_CONFIG_NOSYSTEM=1` and `GIT_CONFIG_GLOBAL=/dev/null` disable
system and global configuration. `GIT_OPTIONAL_LOCKS=0` prevents optional index
cache writes, and `GIT_TERMINAL_PROMPT=0` disables interactive credential prompts.
The trusted one-entry override uses `GIT_CONFIG_COUNT=1`,
`GIT_CONFIG_KEY_0=advice.graftFileDeprecated` and `GIT_CONFIG_VALUE_0=false`.
It suppresses graft-deprecation advice so that advice cannot alter the stderr
diagnostics used by output discovery.

Nested trusted policy, scanner, updater and release checks inherit this
environment. Their deliberate scoped overrides remain intact, including the
updater's private merge index in `GIT_INDEX_FILE`. Stage environments also
exclude inherited credentials and Python configuration. Tests use
invocation-specific temporary resources.

Each command has a default 180-second timeout, adjustable with `--timeout`.
The shared executor starts a unique system-manager transient service per command.
PID 1 tracks the entire cgroup, including detached and double-fork children, and
enforces the deadline. When the command's recorded main process exits, the
trusted client asks the manager to stop its cgroup. Cgroup lifetime keeps
cleanup helpers alive through the 60-second stop grace, even if a shell exits
before its child. Forced termination fails the check.

Success requires a protected manager receipt, a successful command result and
an empty cgroup before another stage begins. Missing receipts, cancellation,
timeout and incomplete cleanup fail validation. There are no Python process-tree
walks, pidfds or child subreapers in this repository. Manager failure or uncertain
cleanup requires discarding the worker. Killing the launcher leaves PID 1's
deadline in place, but cannot produce accepted completion evidence.

Export the one complete result directory once to durable storage outside the
worker, verify its report and every recorded log hash there, and use that bundle
for review and signing. Interrupted execution or export cannot authorize host
application. GitHub artifact uploads are optional. Rebuild a lost worker from
its reviewed prerequisites and rerun the exact pinned inputs. No machine backup
or persistent validator service is required. This suite creates no Docker
resources and does not use global pruning.

Fresh stage checkouts prevent a stage from persistently substituting source or
pinned scripts for later stages. These checks are not a sandbox against a
hostile root user or transient tampering that a program restores within its own
stage. Independently review candidate code and the complete harness, supervise
execution on the disposable machine, and keep the signing authority separate.
The authority must independently verify the actual suite revision/tree and
engine identity before signing.

## Optional hosted convenience

The repository variable `CI_FLEET_HOSTED_VALIDATION` defaults to absent, which
disables `.github/workflows/validate.yml`. Two independently chosen variables
pin its trusted tools. `CI_FLEET_VALIDATOR_REVISION` selects the engine
validator. `CI_FLEET_SUITE_REVISION` selects a compatible reviewed standalone
suite from the fixed public `RandomDevelopment/ci-fleet-config-template`
repository. Both must be nonzero full lowercase 40-hex commit SHAs. Missing or
malformed pins fail before checkout; an unavailable commit fails its checkout.
The full-suite job and its check context are named `hosted-validation`, never
`validate`. Description-only PR edits start no validation job. An edit that
changes only the title runs the pinned engine's title validator under the
separate `hosted-title-validation` context and a five-minute limit. It checks
only the title and produces no complete-suite report. A base-branch edit runs
the complete suite, including when the title changes too. Other existing PR
and main-push triggers retain complete validation.

Concurrency applies to each job. A description edit or title check cannot cancel
an active full-suite run, and main-push validation remains separate from PR runs.
A skipped or completed convenience job cannot satisfy an existing required
`validate` check or the updater's unchanged gate. Updating the workflow requires
an independently reviewed compatible suite pin; older suites enforce the older
workflow contract.

1. Independently review a standalone suite commit from that public repository
   and a compatible engine validator commit.
2. In repository Settings, Secrets and variables, Actions, Variables, set
   `CI_FLEET_SUITE_REVISION` to the reviewed standalone commit,
   `CI_FLEET_VALIDATOR_REVISION` to the reviewed engine commit, and
   `CI_FLEET_HOSTED_VALIDATION` to the literal `true`.
3. Inspect the exact-source result from a new open PR or main push. The workflow
   checks out candidate, trusted suite and engine into separate sibling paths,
   without persisted credentials. Initial checkouts are shallow. A subsequent fetch
   requests only the selected source/base, engine and suite commits with complete
   ancestry and no tags or unrelated branch refs. The executor checkout needs only
   its exact committed program. Fetches use the job's read-only token through a
   command-scoped GitHub CLI credential helper; they persist no checkout credential.
   ShellCheck is installed only when absent. Executor preparation still runs on
   every fresh hosted worker. The workflow runs the trusted suite's absolute entry
   point with only the candidate path as `--repository`. The report records
   the actual pinned suite revision/tree and independent engine policy.
   Permissions remain `contents: read`. The public template receives no
   private self-hosted runner access.

For PR events the workflow uses the actual target/base commit for `--main`.
For pushes to main it uses the source commit. It passes the PR title through
an environment variable as one quoted argument for commit-policy validation;
the title is never shell source.
When enabled, title edits refresh the separate title check. Target-branch
changes refresh the full report's title, base and main context.
Closed PRs cannot run either job. PR and main-push concurrency identities remain
separate, so edits to a closed PR cannot cancel main validation.

The optional complete developer-acceptance job has a 20-minute limit. This is
a slower class than ordinary task-matrix CI. Complete source validation measured
314 seconds on the disposable worker before hosted setup, and root-launcher
fixtures in the private adopter alone exceeded 300 seconds. Enabling the job
can consume up to 20 hosted minutes per run. Return it to five minutes only
after setup and complete coverage reliably fit the four-minute payload budget.
Ordinary task jobs retain their five-minute ceiling.

Use your available hosted allowance or paid capacity if desired. Hosted
availability and billing never determine whether the local command can run.
Set the flag to `false`, remove it, or delete the optional validation workflow
to stop hosted runs. Do not delete application workflows or the separate
updater workflow as part of this choice. Local execution remains complete when
hosted validation is enabled, disabled again, removed, quota-blocked or
unavailable.

The hosted workflow runs the independently pinned suite as a developer
convenience. Replacing the candidate's entry point cannot change that driver.
Its result is not independently trusted signed evidence. Enabling it does not
create a required check. Existing branch protections and host
policies continue to apply until the separately authorized
[cutover and rollback](UPDATING.md#local-validation-and-hosted-cutover).
A skipped, failed or unavailable hosted job must never be relabeled as passing.

The flag does not change ordinary application Actions scheduling, fleet task
matrices, capacity, routing or self-hosted CI. It also does not enable, disable
or authorize the repository-writing template updater. See its
[separate requirements](UPDATING.md#weekly-template-update-prs).

## Developer results and trusted host acceptance

The core local-evidence contract merged through
[ci-fleet PR #137](https://github.com/RandomDevelopment/ci-fleet/pull/137) at
`67beabbddaad73c19f15bc3baa227779bc88dc96`. The
[complete engine run 6](https://github.com/RandomDevelopment/ci-fleet/issues/135#issuecomment-6200457374)
passed all eight stages outside Actions on reviewed source and policy
`a8552da5c902c54c0d78b19e6f093e2e96482f62`, with `expected_skips: []`.
That engine result does not replace this complete standalone suite.
The development ordinary-CI compatibility baseline is
`689c7c00deb0eebcb25f2284334a9f7168a25575`. The historical Git/output helpers retain their reviewed implementation provenance at
`96f277b3a75f3d2bef3c04ceb7b3c8778b8998c2`.
Core availability and functional suite results establish no template release,
private engine promotion or signed operational acceptance.

After independent review of the complete standalone suite, policy-v2 host
acceptance still needs a separate operator signing authority. That authority
must verify the approved suite revision/tree,
independent engine validator, complete required-check set, identities and logs
before signing. Candidate code cannot waive the independently selected policy.
Do not turn an arbitrary candidate-produced report into trusted evidence merely
by signing it. Keep private signing keys off execution machines.

The signed contract binds repository and PR identity, original reviewed head,
applied source, base, tree, policy digest, required checks, expiry and log
digests. The authority must match the report's repository identity to the real
target, require strict-adopter fixture mode for an adopter, and retain the
independently checked suite identity.
Policy-v2 adoption requires the `configuration_local_validation` capability in
the executing manager, candidate engine and checkpoint manager. Review their
compatibility and test recovery with Actions unavailable before activation.
Existing policy-v1 hosts continue requiring their Actions evidence. Adding
hosted requirements to policy v2 is a separate explicit operator choice.

This documentation provisions no keys, credentials, policies or settings. Host
acceptance, recovery testing, release publication and private-adopter rollout
remain separately authorized steps.
