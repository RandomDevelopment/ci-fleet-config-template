#!/usr/bin/env python3
"""Run complete standalone validation against explicit Git commits without Actions."""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import signal
import stat
import subprocess
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = Path(__file__).resolve().with_name("local_validation_supervisor.py")
SPEC = importlib.util.spec_from_file_location("local_validation_supervisor", MODULE_PATH)
supervisor = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(supervisor)
SHA = re.compile(r"[0-9a-f]{40}")
NO_PRIOR_STATE = "0" * 40
SUITE = "ci-fleet-config-standalone-v1"
CHECKS = ("commits", "history-secrets", "syntax", "engine-policy", "configuration",
          "core-compatibility", "initializer", "policy", "updater", "release-update", "harness")
UPSTREAM = "https://github.com/RandomDevelopment/ci-fleet-config-template"
CLEANUP_GRACE_SECONDS = 60
PAIRED_CHECKS_PROGRAM = '''import json, subprocess, sys
processes = []
status = 0
for command, path in json.loads(sys.argv[1]):
    try:
        with open(path, "xb") as output:
            processes.append(subprocess.Popen(command, stdout=output, stderr=subprocess.STDOUT))
    except OSError as error:
        print("paired check launch failed: " + str(error), file=sys.stderr, flush=True)
        status = 1
for process in processes:
    code = process.wait()
    if code:
        print("paired check exited " + str(code), file=sys.stderr, flush=True)
        status = 1
sys.exit(status)
'''


def git_environment(values: dict | None = None) -> dict:
    env = {key: value for key, value in (os.environ if values is None else values).items()
           if not key.startswith("GIT_")}
    env.update(GIT_NO_REPLACE_OBJECTS="1", GIT_GRAFT_FILE="/dev/null",
               GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_GLOBAL="/dev/null",
               GIT_OPTIONAL_LOCKS="0", GIT_TERMINAL_PROMPT="0",
               GIT_CONFIG_COUNT="1", GIT_CONFIG_KEY_0="advice.graftFileDeprecated", GIT_CONFIG_VALUE_0="false")
    return env


def git(repository: Path, *args: str) -> str:
    return subprocess.check_output(["git", "-C", str(repository), *args], env=git_environment(), text=True).strip()


def require_commit(repository: Path, value: str) -> None:
    if not SHA.fullmatch(value) or git(repository, "rev-parse", value + "^{commit}") != value:
        raise ValueError("identities must be full available commit SHAs")
    if git(repository, "rev-parse", "--is-shallow-repository") != "false":
        raise ValueError("complete Git history is required")


def clone(repository: Path, revision: str, target: Path, identities: list[str]) -> None:
    if any(not SHA.fullmatch(value) or value == NO_PRIOR_STATE for value in identities):
        raise ValueError("checkout identities must be full nonzero commit SHAs")
    target.mkdir()
    subprocess.run(["git", "init", "--quiet", str(target)], env=git_environment(), check=True)
    subprocess.run(["git", "-C", str(target), "config", "remote.origin.url", str(repository)], env=git_environment(), check=True)
    subprocess.run(["git", "-C", str(target), "fetch", "--quiet", "--no-tags", "origin", *identities], env=git_environment(), check=True)
    subprocess.run(["git", "-C", str(target), "checkout", "--quiet", "--detach", revision], env=git_environment(), check=True)


def checkout_manifest(root: Path) -> dict:
    if root.is_symlink() or not root.is_dir():
        raise RuntimeError("checkout changed: " + str(root))
    entries = {}
    for path in [root, *root.rglob("*")]:
        mode = path.lstat().st_mode
        if stat.S_ISREG(mode):
            with path.open("rb") as handle:
                value = hashlib.file_digest(handle, "sha256").hexdigest()
        elif stat.S_ISLNK(mode):
            value = os.readlink(path)
        elif stat.S_ISDIR(mode):
            value = None
        else:
            raise RuntimeError("unsupported checkout entry: " + str(path))
        entries[str(path.relative_to(root))] = (stat.S_IFMT(mode), stat.S_IMODE(mode), value)
    return entries


def verify_checkout(root: Path, expected: dict, *, allow_generated: bool = False) -> None:
    actual = checkout_manifest(root)
    changes = []
    for name, previous in expected.items():
        current = actual.get(name)
        if current != previous:
            kind = {stat.S_IFREG: "file", stat.S_IFDIR: "directory", stat.S_IFLNK: "symlink"}[previous[0]]
            reason = "removed" if current is None else "type changed" if current[0] != previous[0] else \
                     "mode changed" if current[1] != previous[1] else "content changed"
            changes.append(f"{name!r} ({kind} {reason})")
            if len(changes) == 3:
                break
    if changes:
        raise RuntimeError("checkout changed: " + str(root) + ": " + ", ".join(changes))
    for name in actual.keys() - expected.keys():
        path = Path(name)
        generated = ("__pycache__" in path.parts or path.suffix == ".pyc") and path.parts[0] != ".git"
        if not allow_generated or not generated or actual[name][0] not in {stat.S_IFDIR, stat.S_IFREG}:
            raise RuntimeError("checkout changed: unexpected " + str(root / path))


def require_proc() -> None:
    if sys.platform != "linux" or not Path("/proc/self/stat").is_file():
        raise RuntimeError("validation requires Linux with mounted /proc")


def require_execution_host() -> None:
    installed = ("ci-fleet", "ci-fleet-tester", "ci-fleet-deployer", "ci-fleet-status", "ci-fleet-signing")
    markers = [Path(parent, role) for parent in ("/etc", "/var/lib", "/opt") for role in installed]
    markers.extend((Path("/var/lib/ci-fleet-status-installer"),
                    Path("/var/lib/ci-fleet-deployer-container-credentials"),
                    Path("/srv/ci-fleet-signing")))
    for parent in ("/etc/systemd/system", "/run/systemd/system", "/usr/lib/systemd/system"):
        for pattern in ("ci-fleet-*", "actions.runner*"):
            markers.extend(Path(parent).rglob(pattern))
    if any(path.exists() or path.is_symlink() for path in markers):
        raise ValueError("validation refuses an installed fleet host or signing authority")


def output_directory(path: Path, *repositories: Path) -> Path:
    output = path.resolve()
    ancestor = output
    while not ancestor.exists():
        ancestor = ancestor.parent
    if not ancestor.is_dir():
        ancestor = ancestor.parent
    message = "--output must be outside Git worktrees and repositories"
    env = git_environment()
    env.update(LC_ALL="C", GIT_DISCOVERY_ACROSS_FILESYSTEM="1")
    for repository in dict.fromkeys((*repositories, Path(__file__).resolve().parent, ancestor)):
        for location in ("--show-toplevel", "--absolute-git-dir"):
            result = subprocess.run(["git", "-C", str(repository), "rev-parse", location],
                                    capture_output=True, env=env)
            if result.returncode == 0:
                root = Path(os.fsdecode(result.stdout.removesuffix(b"\n")))
                if not root.is_absolute():
                    raise ValueError(message + "; invalid Git location")
                if output.is_relative_to(root.resolve()):
                    raise ValueError(message)
                continue
            if result.stderr.startswith(b"fatal: not a git repository (or any"):
                break
            if location != "--show-toplevel" or result.stderr != b"fatal: this operation must be run in a work tree\n":
                raise ValueError(message + "; cannot determine Git location")
    # A broken Git marker must not make a checkout safe for private logs.
    if any((parent / ".git").exists() or (parent / ".git").is_symlink()
           for parent in (output, *output.parents)):
        raise ValueError(message)
    return output


def run(command: list[str], cwd: Path, env: dict, log: Path, timeout: int) -> None:
    require_proc()
    supervisor.run(command, cwd, env, log, timeout, grace=CLEANUP_GRACE_SECONDS)


def check_log(raw: bytes) -> None:
    if re.search(rb"(?:skipped=[1-9][0-9]*|\.\.\. skipped |^SKIP(?:PED)?(?:[ :]|$))", raw, re.I | re.M):
        raise RuntimeError("unexpected skipped check; see check log")


def execute(args: argparse.Namespace) -> int:
    require_proc()
    require_execution_host()
    output = output_directory(args.output, args.repository, args.policy_repository)
    output.mkdir(mode=0o700, parents=True, exist_ok=False)
    report = {"schema_version": 1, "suite": SUITE, "profile": "full", "status": "incomplete",
              "source": args.source, "reviewed_head": args.reviewed_head or args.source,
              "base": args.base, "prior_state_absent": args.base == NO_PRIOR_STATE,
              "main": args.main, "policy": args.policy,
              "repository": args.repository_name, "pr_title": args.pr_title, "expected_skips": [], "tools": {},
              "results": [{"name": name, "status": "incomplete", "log": name + ".log"} for name in CHECKS],
              "started_at": int(time.time())}
    try:
        repository, policy_repository = args.repository.resolve(), args.policy_repository.resolve()
        if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", args.repository_name):
            raise ValueError("repository-name must be owner/repository")
        suite_revision = git(ROOT, "rev-parse", "HEAD")
        require_commit(ROOT, suite_revision)
        # Bind the caller and its process supervisor to the same committed suite.
        for path in (Path(__file__), MODULE_PATH):
            committed = subprocess.check_output(["git", "-C", str(ROOT), "show", suite_revision + ":scripts/" + path.name],
                                                env=git_environment())
            if committed != path.read_bytes():
                raise ValueError("commit the reviewed validation component before running it: " + path.name)
        source_identities = list(dict.fromkeys((args.source, report["reviewed_head"], args.main)))
        if not report["prior_state_absent"]:
            source_identities.append(args.base)
        for revision in source_identities:
            require_commit(repository, revision)
        require_commit(policy_repository, args.policy)
        if not report["prior_state_absent"]:
            for head in set((args.source, report["reviewed_head"])):
                subprocess.run(["git", "-C", str(repository), "merge-base", "--is-ancestor", args.base, head],
                               env=git_environment(), check=True)
        report["tree"] = git(repository, "rev-parse", args.source + "^{tree}")
        if report["tree"] != git(repository, "rev-parse", report["reviewed_head"] + "^{tree}"):
            raise ValueError("integrated and reviewed source trees differ")
        report.update(suite_revision=suite_revision, suite_tree=git(ROOT, "rev-parse", suite_revision + "^{tree}"))
        # The explicit operator identity controls fictional fixtures; candidate origin does not.
        upstream = args.repository_name == "RandomDevelopment/ci-fleet-config-template"
        report["fixture_mode"] = "template" if upstream else "strict-adopter"
        report["applicability"] = {"source-exact-core": upstream, "standalone-fixture-tests": True,
                                   "hosted-workflow-present": bool(git(repository, "ls-tree", args.source, "--", ".github/workflows/validate.yml")),
                                   "candidate-regressions": True,
                                   "upstream-probes-covered-by-trusted-fixtures": not upstream}
        with tempfile.TemporaryDirectory(prefix="ci-fleet-config-validation-") as temporary:
            root = Path(temporary)
            root.chmod(0o700)
            source, policy, suite = (root / name for name in ("source", "policy", "suite"))
            clone(repository, args.source, source, source_identities)
            clone(policy_repository, args.policy, policy, [args.policy])
            clone(ROOT, suite_revision, suite, [suite_revision])
            git(source, "update-ref", "refs/remotes/origin/main", args.main)
            # Preserve only the public fixture identity used by the existing tests.
            git(suite, "remote", "set-url", "origin", UPSTREAM)
            if upstream:
                git(source, "remote", "set-url", "origin", UPSTREAM)
            home, fixtures = root / "home", root / "tmp"
            home.mkdir()
            fixtures.mkdir()
            env = git_environment({"PATH": "/usr/sbin:/usr/bin:/sbin:/bin", "HOME": str(home), "LANG": "C.UTF-8",
                   "TMPDIR": str(fixtures), "PYTHONNOUSERSITE": "1",
                   "CI_FLEET_VALIDATION_ROOT": str(source),
                   "CI_FLEET_VALIDATION_BASE": args.base, "CI_FLEET_TEMPLATE_FIXTURES": str(upstream).lower()})
            for name, command in {"bash": ["bash", "--version"], "git": ["git", "--version"],
                                  "python": ["python3", "--version"], "shellcheck": ["shellcheck", "--version"],
                                  "openssl": ["openssl", "version"], "stat": ["stat", "--version"]}.items():
                report["tools"][name] = subprocess.check_output(command, env=env, text=True, stderr=subprocess.STDOUT).strip()
            report["run_id"] = root.name
            trusted_template = policy / "templates/config-repository"
            for path in (policy / "scripts/validate_commits.py", policy / "scripts/scan_committed_secrets.py",
                         trusted_template / "scripts/validate.py", trusted_template / "fleet.schema.json"):
                if not path.is_file():
                    raise ValueError("pinned engine is missing required validator files")
            heads = list(dict.fromkeys((args.source, report["reviewed_head"])))
            commits = []
            for head in heads:
                commits.extend(git(source, "rev-list", "--reverse", args.base + ".." + head if not report["prior_state_absent"] else head).splitlines())
                commits.append(head)
            report["scanned_commits"] = list(dict.fromkeys(commits))
            py = ["python3"]
            plans = {
                "commits": [[*py, "-I", str(policy / "scripts/validate_commits.py"), "--base", "" if report["prior_state_absent"] else args.base,
                             "--head", head] for head in (report["scanned_commits"] if report["prior_state_absent"] else heads)],
                "history-secrets": [[*py, "-I", str(policy / "scripts/scan_committed_secrets.py"), "--repository", str(source), "--commit", commit] for commit in report["scanned_commits"]],
                "syntax": [["bash", "-n", *[str(p) for p in sorted((source / "scripts").glob("*.sh"))]],
                           ["shellcheck", *[str(p) for p in sorted((source / "scripts").glob("*.sh"))]],
                           [*py, "-I", "-m", "py_compile", *[str(p) for p in sorted((source / "scripts").glob("*.py"))]]],
                "engine-policy": [["bash", str(suite / "scripts/validate-local-configuration.sh")]],
                "configuration": [["bash", str(suite / "scripts/validate-local-configuration.sh")]],
                "core-compatibility": [[*py, str(suite / "scripts/test_core_compatibility.py"), "--standalone-root", str(source), *([] if upstream else ["--derived"])]],
                "initializer": [["bash", str(suite / "scripts/validate-local-configuration.sh")]],
                "harness": [[*py, "-I", *(["-W", "error::ResourceWarning"] if module == "test_local_validation_supervisor" else []),
                             str(suite / "scripts/run_candidate_tests.py"), "--repository", str(source), "--test", module,
                             *([] if upstream else ["--derived"])]
                            for module in ("test_local_validation", "test_local_validation_supervisor", "test_candidate_runner")],
            }
            paired_logs = {}
            for name, module in (("policy", "test_policy"), ("updater", "test_template_updater"),
                                 ("release-update", "test_release_update"), ("harness", "test_workflow_events")):
                if name != "harness":
                    plans[name] = []
                candidate = [*py, "-I", str(suite / "scripts/run_candidate_tests.py"),
                             "--repository", str(source), "--test", module, *([] if upstream else ["--derived"])]
                if not upstream and name != "harness":
                    public = [*py, "-I", str(suite / "scripts/run_candidate_tests.py"),
                              "--repository", str(suite), "--test", module]
                    paired_logs[name] = [(public, output / (name + "-public.log")),
                                         (candidate, output / (name + "-candidate.log"))]
                    plans[name].append([*py, "-I", "-c", PAIRED_CHECKS_PROGRAM,
                                        json.dumps([(command, str(path)) for command, path in paired_logs[name]])])
                elif not upstream:
                    plans[name].append([*py, str(suite / "scripts" / (module + ".py"))])
                    plans[name].append(candidate)
                else:
                    plans[name].append(candidate)
            if args.pr_title is not None:
                plans["commits"].append([*py, "-I", str(policy / "scripts/validate_commits.py"), "--pr-title", args.pr_title])
            # Seeds and the entire plan are frozen before any candidate program executes.
            seeds = []
            for target in (source, policy, suite):
                seed = root / (target.name + "-seed")
                target.rename(seed)
                git(seed, "remote", "set-url", "origin",
                    UPSTREAM if target == suite or (upstream and target == source) else str(seed))
                seeds.append((seed, checkout_manifest(seed), target))
            for entry in report["results"]:
                name = entry["name"]
                entry["started_at"] = int(time.time())
                print("Running " + name, flush=True)
                stage_env = dict(env)
                stage_env["CI_FLEET_VALIDATOR_ROOT"] = str(trusted_template if name == "engine-policy" else suite)
                stage_env["CI_FLEET_STATIC_ENGINE_POLICY"] = str(name == "engine-policy").lower()
                stage_env["CI_FLEET_CONFIG_ONLY"] = str(name in {"engine-policy", "configuration"}).lower()
                stage_env["CI_FLEET_INITIALIZER_ONLY"] = str(name == "initializer").lower()
                try:
                    for seed, expected, target in seeds:
                        verify_checkout(seed, expected)
                        shutil.copytree(seed, target, symlinks=True)
                        verify_checkout(target, expected)
                    stage_trees = [(target, expected) for _, expected, target in seeds]
                    with (output / entry["log"]).open("wb") as log:
                        for command in plans[name]:
                            label = "Paired driver command: " if name in paired_logs else "$ "
                            log.write((label + json.dumps(command) + "\n").encode())
                            log.flush()
                            command_log = root / "command.log"
                            try:
                                run(command, source, stage_env, command_log, args.timeout)
                                if any(not path.is_file() for _, path in paired_logs.get(name, [])):
                                    raise RuntimeError("paired check did not produce both child logs")
                            finally:
                                # The supervisor finishes descendant cleanup before log assembly.
                                for child_command, child_log in paired_logs.get(name, []):
                                    log.write(("$ " + json.dumps(child_command) + "\n").encode())
                                    if child_log.exists():
                                        with child_log.open("rb") as child_output:
                                            shutil.copyfileobj(child_output, log)
                                    else:
                                        log.write(b"Missing paired child output.\n")
                                if name in paired_logs:
                                    log.write(b"Paired driver diagnostics:\n")
                                if command_log.exists():
                                    with command_log.open("rb") as command_output:
                                        shutil.copyfileobj(command_output, log)
                                    command_log.unlink()
                    for target, expected in stage_trees:
                        verify_checkout(target, expected, allow_generated=True)
                    for seed, expected, _ in seeds:
                        verify_checkout(seed, expected)
                    check_log((output / entry["log"]).read_bytes())
                    entry["status"] = "passed"
                except (Exception, KeyboardInterrupt):
                    entry["status"] = "failed"
                    if (output / entry["log"]).exists():
                        print((output / entry["log"]).read_text(errors="replace")[-8000:], file=sys.stderr)
                    raise
                finally:
                    entry["finished_at"] = int(time.time())
                    if (output / entry["log"]).exists():
                        entry["sha256"] = hashlib.sha256((output / entry["log"]).read_bytes()).hexdigest()
                    for _, _, target in seeds:
                        if target.is_symlink():
                            target.unlink()
                        elif target.exists():
                            shutil.rmtree(target)
            report["status"] = "passed"
    except (Exception, KeyboardInterrupt) as error:
        report.update(status="failed", error=str(error))
        print(str(error), file=sys.stderr)
    finally:
        report["finished_at"] = int(time.time())
        (output / "result.json").write_text(json.dumps(report, indent=2) + "\n")
    return 0 if report["status"] == "passed" else 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository", type=Path, default=Path.cwd())
    parser.add_argument("--repository-name", required=True, help="operator-selected owner/repository; only the public template uses fictional fixtures")
    parser.add_argument("--policy-repository", type=Path, required=True)
    for name in ("source", "base", "main", "policy"):
        parser.add_argument("--" + name, required=True,
                            help="full commit SHA; base also accepts 40 zeroes for no prior integrated state" if name == "base" else None)
    parser.add_argument("--reviewed-head")
    parser.add_argument("--pr-title")
    parser.add_argument("--timeout", type=int, default=180)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.timeout <= 0:
        parser.error("timeout must be positive")
    signal.signal(signal.SIGTERM, lambda *_: (_ for _ in ()).throw(KeyboardInterrupt()))
    try:
        return execute(args)
    except (OSError, ValueError, RuntimeError) as error:
        print(str(error), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
