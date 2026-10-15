#!/usr/bin/env python3
"""Run complete standalone validation against explicit Git commits without Actions."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import signal
import subprocess
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
SHA = re.compile(r"[0-9a-f]{40}")
SUITE = "ci-fleet-config-standalone-v1"
CHECKS = ("commits", "history-secrets", "syntax", "engine-policy", "configuration",
          "core-compatibility", "initializer", "policy", "updater", "release-update", "harness")
UPSTREAM = "https://github.com/RandomDevelopment/ci-fleet-config-template"


def git(repository: Path, *args: str) -> str:
    return subprocess.check_output(["git", "-C", str(repository), *args], text=True).strip()


def require_commit(repository: Path, value: str) -> None:
    if not SHA.fullmatch(value) or git(repository, "rev-parse", value + "^{commit}") != value:
        raise ValueError("identities must be full available commit SHAs")
    if git(repository, "rev-parse", "--is-shallow-repository") != "false":
        raise ValueError("complete Git history and tags are required")


def clone(repository: Path, revision: str, target: Path, identities: list[str]) -> None:
    subprocess.run(["git", "clone", "--quiet", "--no-local", "--no-checkout", str(repository), str(target)], check=True)
    subprocess.run(["git", "-C", str(target), "fetch", "--quiet", "--no-tags", "origin", *identities], check=True)
    subprocess.run(["git", "-C", str(target), "checkout", "--quiet", "--detach", revision], check=True)


def run(command: list[str], cwd: Path, env: dict, log, timeout: int) -> None:
    log.write(("$ " + json.dumps(command) + "\n").encode())
    log.flush()
    process = subprocess.Popen(command, cwd=cwd, env=env, stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
    try:
        if process.wait(timeout=timeout):
            raise RuntimeError("command failed; see check log")
    finally:
        try:
            os.killpg(process.pid, signal.SIGTERM)
            deadline = time.monotonic() + 5
            while time.monotonic() < deadline:
                process.poll()
                os.killpg(process.pid, 0)
                time.sleep(0.05)
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        process.wait()


def check_log(raw: bytes) -> None:
    if re.search(rb"(?:skipped=[1-9][0-9]*|\.\.\. skipped |^SKIP(?:PED)?(?:[ :]|$))", raw, re.I | re.M):
        raise RuntimeError("unexpected skipped check; see check log")


def execute(args: argparse.Namespace) -> int:
    output = args.output.resolve()
    output.mkdir(mode=0o700, parents=True, exist_ok=False)
    report = {"schema_version": 1, "suite": SUITE, "profile": "full", "status": "incomplete",
              "source": args.source, "reviewed_head": args.reviewed_head or args.source,
              "base": args.base, "main": args.main, "policy": args.policy,
              "repository": args.repository_name, "pr_title": args.pr_title, "expected_skips": [], "tools": {},
              "results": [{"name": name, "status": "incomplete", "log": name + ".log"} for name in CHECKS],
              "started_at": int(time.time())}
    try:
        repository, policy_repository = args.repository.resolve(), args.policy_repository.resolve()
        if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", args.repository_name):
            raise ValueError("repository-name must be owner/repository")
        suite_revision = git(ROOT, "rev-parse", "HEAD")
        require_commit(ROOT, suite_revision)
        # Execute only the committed orchestrator. All other suite files come from its clone.
        committed = subprocess.check_output(["git", "-C", str(ROOT), "show", suite_revision + ":scripts/local_validate.py"])
        if committed != Path(__file__).read_bytes():
            raise ValueError("commit the reviewed validation entry point before running it")
        for revision in (args.source, report["reviewed_head"], args.base, args.main):
            require_commit(repository, revision)
        require_commit(policy_repository, args.policy)
        for head in set((args.source, report["reviewed_head"])):
            subprocess.run(["git", "-C", str(repository), "merge-base", "--is-ancestor", args.base, head], check=True)
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
            clone(repository, args.source, source, [args.source, report["reviewed_head"], args.base, args.main])
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
            env = {"PATH": "/usr/sbin:/usr/bin:/sbin:/bin", "HOME": str(home), "LANG": "C.UTF-8",
                   "TMPDIR": str(fixtures), "PYTHONNOUSERSITE": "1", "GIT_CONFIG_NOSYSTEM": "1",
                   "GIT_CONFIG_GLOBAL": "/dev/null", "CI_FLEET_VALIDATION_ROOT": str(source),
                   "CI_FLEET_VALIDATION_BASE": args.base, "CI_FLEET_TEMPLATE_FIXTURES": str(upstream).lower()}
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
                commits.extend(git(source, "rev-list", "--reverse", args.base + ".." + head).splitlines())
                commits.append(head)
            report["scanned_commits"] = list(dict.fromkeys(commits))
            fixture_source = source if upstream else suite
            py = ["python3"]
            plans = {
                "commits": [[*py, "-I", str(policy / "scripts/validate_commits.py"), "--base", args.base, "--head", head] for head in heads],
                "history-secrets": [[*py, "-I", str(policy / "scripts/scan_committed_secrets.py"), "--repository", str(source), "--commit", commit] for commit in report["scanned_commits"]],
                "syntax": [["bash", "-n", *[str(p) for p in sorted((source / "scripts").glob("*.sh"))]],
                           ["shellcheck", *[str(p) for p in sorted((source / "scripts").glob("*.sh"))]],
                           [*py, "-I", "-m", "py_compile", *[str(p) for p in sorted((source / "scripts").glob("*.py"))]]],
                "engine-policy": [["bash", str(suite / "scripts/validate-local-configuration.sh")]],
                "configuration": [["bash", str(suite / "scripts/validate-local-configuration.sh")]],
                "policy": [[*py, str(fixture_source / "scripts/test_policy.py")]],
                "updater": [[*py, str(fixture_source / "scripts/test_template_updater.py")]],
                "core-compatibility": [[*py, str(suite / "scripts/test_core_compatibility.py"), "--standalone-root", str(source), *([] if upstream else ["--derived"])]],
                "initializer": [["bash", str(suite / "scripts/validate-local-configuration.sh")]],
                "release-update": [[*py, str(fixture_source / "scripts/test_release_update.py")]],
                "harness": [[*py, str(suite / "scripts/test_local_validation.py")],
                            [*py, str(suite / "scripts/test_candidate_runner.py")]],
            }
            if not upstream:
                for name, module in (("policy", "test_policy"), ("updater", "test_template_updater"),
                                     ("release-update", "test_release_update")):
                    plans[name].append([*py, "-I", str(suite / "scripts/run_candidate_tests.py"),
                                        "--repository", str(source), "--test", module, "--derived"])
            if args.pr_title:
                plans["commits"].append([*py, "-I", str(policy / "scripts/validate_commits.py"), "--pr-title", args.pr_title])
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
                    with (output / entry["log"]).open("wb") as log:
                        for command in plans[name]:
                            run(command, source, stage_env, log, args.timeout)
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
        parser.add_argument("--" + name, required=True)
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
    except OSError as error:
        print(str(error), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
