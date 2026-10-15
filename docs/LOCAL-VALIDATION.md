# Complete local configuration validation

The complete suite runs without GitHub Actions, an Actions API, hosted minutes
or account billing. It validates Git commits rather than working-tree edits.
`./scripts/validate.sh --strict` remains useful while editing an initialized
adopter, but runs only the focused policy check.

## Prerequisites and trusted inputs

Use a separate disposable Linux execution machine under operator supervision,
with `/proc` mounted and kernel support for child subreapers and pidfds.
Use Bash 4 or newer, Git 2.40 or newer, Python 3.11 or newer,
OpenSSL, ShellCheck and GNU `stat` available on the standard system path.
The harness rejects other operating systems or an unavailable `/proc`, and the
supervisor checks subreaper and pidfd support before launching a command.
The updater fixtures need Git's
`merge-tree --merge-base` support. No Docker daemon, root account, runner
registration or fleet credential is needed.
Never execute candidate scripts on an active fleet host or a machine holding
the evidence-signing private key. Source programs are proposed code and need
independent review before execution.

Before tool probes or candidate execution, the harness rejects standard installed
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
The harness binds both `scripts/local_validate.py` and its
`scripts/local_validation_supervisor.py` helper to that same committed suite.
The helper captures its source once at import, before candidate execution.
Every child supervisor runs that frozen code through Python `-I -c`, so replacing
the original helper path cannot change the supervisor used by later commands.

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
failure fails the affected check. The suite needs no GitHub Actions event,
scheduler or authenticated Actions API. Keep credentials and reports outside
configuration Git.

## Run the complete suite

Replace all SHA placeholders and use a new output directory outside Git:

```bash
python3 -I /trusted/template/scripts/local_validate.py \
  --repository /work/config --repository-name OWNER/REPOSITORY \
  --source SOURCE_SHA --base BASE_SHA --main MAIN_SHA \
  --policy-repository /trusted/ci-fleet --policy REVIEWED_ENGINE_VALIDATOR_SHA \
  --output /results/new-dir
```

`--repository-name` is the actual operator-selected owner/repository identity,
not a value inferred from candidate files or its remote. Only
`RandomDevelopment/ci-fleet-config-template` selects fictional upstream
fixtures. Never supply that identity for an adopter. The suite preserves the
public fixture's origin identity in isolated checkouts so upstream-only tests
do not silently disappear after cloning from a local path. Fictional upstream
reference configurations run non-strict checks. Initialized adopters must pass
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
evidence, including stricter deltas absent from the older engine baseline.
Both checks finish before any candidate initializer or test program executes.
A newer engine with an incompatible fleet contract fails validation; this
entry point does not waive its schema or promote its revision.

Adopter runs execute both the trusted suite's public-fixture regressions and
trusted policy, updater and release-update regressions against the
candidate programs in isolated fictional fixtures. The candidate policy run excludes only its three
upstream-only byte-comparison probes; the complete trusted fixture run still
covers those probes. The runner reports those names and fails on any actual
skipped test. Adopter configuration is not substituted for the trusted
suite's fictional fixture.
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

The new output directory contains `result.json` and per-check logs. Preserve
the whole directory. The report records source, original reviewed head, tree,
base, whether prior integrated state is absent, main, engine-policy revision,
suite revision/tree, tool versions, timestamps, results, expected skips and
log SHA-256 digests. The suite ID is
`ci-fleet-config-standalone-v1`; the profile is `full`.

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

Seeds and stage checkouts start as empty Git repositories. Source fetches use
`--no-tags` and explicit source, original reviewed head, main and nonzero base
SHAs with their complete ancestry. Engine-policy and trusted-suite fetches
include only their selected commit and its ancestry. Checkouts inherit no
unrelated branches or tags, and the standalone suite needs no inherited release
refs. Updater and release-update tests still use their isolated release fixtures.

Each named stage receives fresh detached checkouts of all three verified seeds
through the same explicit SHA fetches. Before the stage can pass, the harness
checks the seeds and stage checkouts
against their manifests. Generated regular files under `__pycache__` or with a
`.pyc` suffix, and their cache directories, may appear only in stage checkouts;
the harness discards them with that stage. Seed changes fail validation.
`GIT_OPTIONAL_LOCKS=0`
prevents optional Git index-cache writes from changing a checkout during reads.
Check environments exclude inherited credentials and Git/Python configuration.
Tests use invocation-specific temporary resources.

Each command has a default 180-second timeout, adjustable with `--timeout`.
A dedicated supervisor becomes a Linux child subreaper for that command; the
calling orchestrator does not. The supervisor adopts orphaned descendants,
including programs that use `setsid` or double-fork to leave the command's
process group. It tracks descendants through `/proc` and signals them through
pidfds to avoid signalling a different process after PID reuse.

After command completion, failure, timeout or handled cancellation, the
supervisor sends one initial `SIGTERM` sweep to remaining descendants and allows
60 seconds for cleanup before sending `SIGKILL`. During that grace period it
sends further `SIGTERM` only to newly adopted direct orphans. Cleanup helpers
under a still-living, already signalled parent can run until the same grace
deadline. The supervisor reaps exited children and returns only after `waitpid`
reports `ECHILD`, confirming no children remain. The orchestrator
requires a valid structured supervisor result with complete cleanup; a missing
or malformed result fails validation. A successful command leader still fails
its stage if a descendant requires `SIGKILL`. Graceful descendant cleanup does
not turn success into failure. Failed, timed-out and cancelled commands remain
failed or cancelled after cleanup. Temporary checkouts are removed; logs remain
in the output directory.

A task stuck in an uninterruptible kernel wait can delay return beyond the
command timeout and cleanup grace. The supervisor keeps waiting for the kernel
to confirm that every descendant has exited and been reaped. A hard kill or
machine loss can prevent final reporting and temporary-resource cleanup.
Killing the supervisor can also leave descendants behind. Inspect that run's
processes and temporary resources before removal. This suite creates no Docker
resources and does not require global pruning.

Fresh stage checkouts prevent a stage from persistently substituting source or
pinned scripts for later stages. These checks are not a sandbox against a
hostile root user or transient tampering that a program restores within its own
stage. Independently review candidate code and the complete harness, supervise
execution on the disposable machine, and keep the signing authority separate.
The authority must independently verify the actual suite revision/tree and
engine identity before signing.

## Optional hosted convenience

The repository variable `CI_FLEET_HOSTED_VALIDATION` defaults to absent, which
disables `.github/workflows/validate.yml`. A separately chosen variable,
`CI_FLEET_VALIDATOR_REVISION`, pins the independent engine validator.
The optional job and its check context are named `hosted-validation`, never
`validate`. A skipped or completed convenience job cannot satisfy an existing
required `validate` check or the updater's unchanged gate.

1. Review the harness and a supporting full engine SHA.
2. In repository Settings, Secrets and variables, Actions, Variables, set
   `CI_FLEET_VALIDATOR_REVISION` to that SHA and
   `CI_FLEET_HOSTED_VALIDATION` to the literal `true`.
3. Inspect the exact-source result from a new PR or main push. The workflow uses
   a public hosted runner, existing `contents: read` permissions and the same
   complete entry point. The public template receives no private self-hosted
   runner access.

For PR events the workflow uses the actual target/base commit for `--main`.
For pushes to main it uses the source commit. It passes the PR title through
an environment variable as one quoted argument for commit-policy validation;
the title is never shell source.
When enabled, the workflow also handles PR edits so retitles and target-branch
changes refresh the recorded title, base and main context.

Use your available hosted allowance or paid capacity if desired. Hosted
availability and billing never determine whether the local command can run.
Set the flag to `false`, remove it, or delete the optional validation workflow
to stop hosted runs. Do not delete application workflows or the separate
updater workflow as part of this choice. Local execution remains complete when
hosted validation is enabled, disabled again, removed, quota-blocked or
unavailable.

The hosted workflow runs the candidate checkout's harness as a developer
convenience. Its result is not independently trusted signed evidence. Enabling
it does not create a required check. Existing branch protections and host
policies continue to apply until the separately authorized
[cutover and rollback](UPDATING.md#local-validation-and-hosted-cutover).
A skipped, failed or unavailable hosted job must never be relabeled as passing.

The flag does not change ordinary application Actions scheduling, fleet task
matrices, capacity, routing or self-hosted CI. It also does not enable, disable
or authorize the repository-writing template updater. See its
[separate requirements](UPDATING.md#weekly-template-update-prs).

## Developer results and trusted host acceptance

The core local-evidence contract is pending
[ci-fleet PR #137](https://github.com/RandomDevelopment/ci-fleet/pull/137).
The reviewed proposed reference `cb9727197d6b8c1fb66f913bfd6d62e30ba89739` is
unmerged, not a merged or released baseline. The standalone ordinary-CI
compatibility baseline remains `aa9bbb27a4746fc80ce27d8932de68450b28364b`.
No compatibility, template release, private engine promotion or host activation
is established by implementing this harness.

After a supporting core has merged and the complete standalone suite has been
independently reviewed, policy-v2 host acceptance needs a separate operator
signing authority. That authority must verify the approved suite revision/tree,
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
