#!/usr/bin/env python3
"""Exercise identity, isolation, failure and complete-result handling."""
from __future__ import annotations

import argparse
import contextlib
import io
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import signal
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

import local_validate as local

HOST_MARKERS = tuple(Path(root) / role for root in ("/etc", "/var/lib", "/opt")
                     for role in ("ci-fleet", "ci-fleet-tester", "ci-fleet-deployer", "ci-fleet-status", "ci-fleet-signing")) + (
    Path("/var/lib/ci-fleet-status-installer"), Path("/var/lib/ci-fleet-deployer-container-credentials"),
    Path("/srv/ci-fleet-signing"),
)
SYSTEMD_ROOTS = tuple(map(Path, ("/etc/systemd/system", "/run/systemd/system", "/usr/lib/systemd/system")))
HOST_REFUSAL = "validation refuses an installed fleet host or signing authority"


class LocalValidationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.repository = self.root / "repository"
        self.repository.mkdir()
        self.git("init", "-q")
        self.git("config", "user.name", "Fixture")
        self.git("config", "user.email", "fixture@example.invalid")
        for relative in ("scripts/local_validate.py", "scripts/local_validation_supervisor.py",
                         "scripts/validate_commits.py", "scripts/scan_committed_secrets.py",
                         "templates/config-repository/scripts/validate.py", "templates/config-repository/fleet.schema.json"):
            path = self.repository / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(Path(local.__file__).with_name(path.name).read_bytes()
                             if path.name in {"local_validate.py", "local_validation_supervisor.py"} else b"fixture\n")
        self.git("add", ".")
        self.git("commit", "-qm", "test: initial fixture")
        self.base = self.git("rev-parse", "HEAD")
        (self.repository / "marker").write_text("candidate\n")
        self.git("add", ".")
        self.git("commit", "-qm", "test: candidate")
        self.source = self.git("rev-parse", "HEAD")
        self.args = argparse.Namespace(repository=self.repository, repository_name="fictional/config",
                                       source=self.source, reviewed_head=None, base=self.base, main=self.source,
                                       policy_repository=self.repository, policy=self.base,
                                       output=self.root / "results", timeout=5, pr_title=None)

    def git(self, *args: str) -> str:
        return subprocess.check_output(["git", "-C", str(self.repository), *args], text=True).strip()

    def execute(self, action=None):
        commands = []
        def run(command, cwd, env, log, timeout):
            commands.append((command, cwd, dict(env)))
            log.write_bytes(f"fixture executed {len(commands)}\n".encode())
            if action:
                action(command, env, log)
        with patch.object(local, "ROOT", self.repository), patch.object(local, "run", run), \
                contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            code = local.execute(self.args)
        return code, json.loads((self.args.output / "result.json").read_text()), commands

    def test_full_report_binds_identities_and_independent_policy(self) -> None:
        code, result, commands = self.execute()
        self.assertEqual(code, 0, result)
        self.assertEqual(result["source"], self.source)
        self.assertEqual(result["base"], self.base)
        self.assertEqual(result["tree"], self.git("rev-parse", "HEAD^{tree}"))
        self.assertEqual(result["suite_revision"], self.source)
        self.assertEqual(result["expected_skips"], [])
        self.assertEqual(len(local.CHECKS), 11)
        self.assertEqual(len(local.CHECKS), len(set(local.CHECKS)))
        self.assertEqual([check["name"] for check in result["results"]], list(local.CHECKS))
        combined = ""
        for check in result["results"]:
            self.assertEqual(check["status"], "passed")
            log = (self.args.output / check["log"]).read_bytes()
            self.assertEqual(check["sha256"], hashlib.sha256(log).hexdigest())
            self.assertEqual(log.count(b"$ ["), log.count(b"fixture executed "))
            combined += log.decode()
        for number in range(1, len(commands) + 1):
            self.assertEqual(combined.count(f"fixture executed {number}\n"), 1)
        self.assertTrue(all(command[1] == "-I" for command, _, _ in commands if "validate_commits.py" in " ".join(command)))
        self.assertTrue(all("GITHUB_TOKEN" not in env and "GITHUB_EVENT_PATH" not in env for _, _, env in commands))
        self.assertTrue(any("/policy/scripts/scan_committed_secrets.py" in " ".join(c) for c, _, _ in commands))
        self.assertFalse(any(cwd.exists() for _, cwd, _ in commands))

    def test_failed_stage_leaves_remaining_coverage_incomplete(self) -> None:
        def fail(command, env, log):
            raise RuntimeError("deliberate check failure")
        code, result, _ = self.execute(fail)
        self.assertEqual(code, 1)
        self.assertEqual(result["results"][0]["status"], "failed")
        self.assertTrue(all(check["status"] == "incomplete" for check in result["results"][1:]))
        log = (self.args.output / result["results"][0]["log"]).read_bytes()
        self.assertIn(b"fixture executed 1\n", log)
        self.assertEqual(result["results"][0]["sha256"], hashlib.sha256(log).hexdigest())

    def test_installed_role_markers_and_dangling_symlinks_reject(self) -> None:
        for marker in HOST_MARKERS:
            for dangling in (False, True):
                with self.subTest(marker=marker, dangling=dangling), \
                        patch.object(local.Path, "exists", lambda path: path == marker and not dangling), \
                        patch.object(local.Path, "is_symlink", lambda path: path == marker and dangling), \
                        patch.object(local.Path, "rglob", lambda path, pattern: iter(())):
                    with self.assertRaisesRegex(ValueError, HOST_REFUSAL):
                        local.require_execution_host()

    def test_installed_systemd_units_and_dangling_symlinks_reject(self) -> None:
        for root in SYSTEMD_ROOTS:
            for pattern, name in (("ci-fleet-*", "ci-fleet-fixture.service"),
                                  ("actions.runner*", "actions.runner.fixture.service")):
                marker = root / name
                for dangling in (False, True):
                    with self.subTest(marker=marker, dangling=dangling), \
                            patch.object(local.Path, "exists", lambda path: path == marker and not dangling), \
                            patch.object(local.Path, "is_symlink", lambda path: path == marker and dangling), \
                            patch.object(local.Path, "rglob", lambda path, glob: iter((marker,)) if (path, glob) == (root, pattern) else iter(())):
                        with self.assertRaisesRegex(ValueError, HOST_REFUSAL):
                            local.require_execution_host()

    def test_signing_host_rejection_precedes_git_tools_and_candidate_execution(self) -> None:
        markers = [path for path in HOST_MARKERS if path.name == "ci-fleet-signing"]
        self.assertEqual(len(markers), 4)
        for number, marker in enumerate(markers):
            for dangling in (False, True):
                self.args.output = self.root / f"signing-host-{number}-{dangling}"
                with self.subTest(marker=marker, dangling=dangling), \
                        patch.object(local.Path, "exists", lambda path: path == marker and not dangling), \
                        patch.object(local.Path, "is_symlink", lambda path: path == marker and dangling), \
                        patch.object(local.Path, "rglob", lambda path, pattern: iter(())), \
                        patch.object(local, "git") as git, \
                        patch.object(local.subprocess, "check_output") as tools:
                    code, report, commands = self.execute()
                    self.assertEqual(code, 1, report)
                    self.assertEqual(report["status"], "failed")
                    self.assertEqual(report["error"], HOST_REFUSAL)
                    self.assertEqual(report["tools"], {})
                    self.assertEqual(commands, [])
                    self.assertEqual(len(report["results"]), 11)
                    self.assertTrue(all(check["status"] == "incomplete" for check in report["results"]), report)
                    git.assert_not_called()
                    tools.assert_not_called()

    def test_clean_execution_host_uses_only_scoped_marker_queries(self) -> None:
        exists, symlinks, scans = set(), set(), set()

        def missing(path):
            exists.add(path)
            return False

        def not_symlink(path):
            symlinks.add(path)
            return False

        def empty(path, pattern):
            scans.add((path, pattern))
            return iter(())

        with patch.object(local.Path, "exists", missing), \
                patch.object(local.Path, "is_symlink", not_symlink), \
                patch.object(local.Path, "rglob", empty):
            local.require_execution_host()
        self.assertEqual(exists, set(HOST_MARKERS))
        self.assertEqual(symlinks, set(HOST_MARKERS))
        self.assertEqual(scans, {(root, pattern) for root in SYSTEMD_ROOTS for pattern in ("ci-fleet-*", "actions.runner*")})

    def test_checkout_substitution_fails_before_the_next_stage(self) -> None:
        cases = [(name, "content") for name in
                 ("source", "policy", "suite", "source-seed", "policy-seed", "suite-seed")]
        cases += [("source", kind) for kind in
                  ("assume-unchanged", "index", "git-config", "mode", "symlink", "cache-symlink", "git-cache")]
        cases.append(("source-seed", "cache"))
        for checkout, kind in cases:
            with self.subTest(checkout=checkout, kind=kind):
                self.args.output = self.root / (checkout + "-" + kind)

                def tamper(command, env, log):
                    root = Path(env["CI_FLEET_VALIDATION_ROOT"]).parent / checkout
                    target = root / "scripts/local_validate.py"
                    if kind == "assume-unchanged":
                        subprocess.run(["git", "-C", str(root), "update-index", "--assume-unchanged",
                                        "scripts/local_validate.py"], check=True, env=env)
                        target.write_text("candidate replacement\n")
                        self.assertEqual(local.git(root, "status", "--porcelain"), "")
                    elif kind == "index":
                        subprocess.run(["git", "-C", str(root), "update-index", "--assume-unchanged",
                                        "scripts/local_validate.py"], check=True, env=env)
                    elif kind == "git-config":
                        subprocess.run(["git", "-C", str(root), "config", "core.hooksPath", "/dev/null"],
                                       check=True, env=env)
                    elif kind == "mode":
                        target.chmod(target.stat().st_mode ^ 0o100)
                    elif kind == "symlink":
                        target.unlink()
                        target.symlink_to("validate_commits.py")
                    elif kind in {"cache", "cache-symlink", "git-cache"}:
                        cache = root / (".git" if kind == "git-cache" else "scripts") / "__pycache__/fixture.pyc"
                        cache.parent.mkdir()
                        if kind == "cache-symlink":
                            cache.symlink_to(target)
                        else:
                            cache.write_bytes(b"generated")
                    else:
                        target.write_text("candidate replacement\n")

                code, result, commands = self.execute(tamper)
                self.assertEqual(code, 1, result)
                self.assertEqual(result["results"][0]["status"], "failed", result)
                self.assertTrue(all(check["status"] == "incomplete" for check in result["results"][1:]), result)
                self.assertEqual(len(commands), 1)
                self.assertEqual(result["tree"], self.git("rev-parse", self.source + "^{tree}"))

    def test_generated_stage_caches_are_discarded_before_the_next_stage(self) -> None:
        observed = []

        def cache(command, env, log):
            source = Path(env["CI_FLEET_VALIDATION_ROOT"])
            root = source.parent
            paths = [root / name / "scripts/__pycache__/fixture.pyc" for name in ("source", "policy", "suite")]
            if "validate_commits.py" in " ".join(command):
                self.assertEqual(env["GIT_OPTIONAL_LOCKS"], "0")
                for path in paths:
                    path.parent.mkdir()
                    path.write_bytes(b"generated bytecode")
                (source / "fixture.pyc").write_bytes(b"generated bytecode")
            elif "scan_committed_secrets.py" in " ".join(command):
                self.assertTrue(all(not path.exists() for path in paths))
                self.assertFalse((source / "fixture.pyc").exists())
                observed.append(True)

        code, result, _ = self.execute(cache)
        self.assertEqual(code, 0, result)
        self.assertTrue(observed)

    def test_only_explicit_histories_reach_all_seeds_and_stage_checkouts(self) -> None:
        self.git("checkout", "-q", "--detach", self.base)
        (self.repository / "marker").write_text("reviewed intermediate state\n")
        self.git("add", ".")
        self.git("commit", "-qm", "test: reviewed intermediate")
        intermediate = self.git("rev-parse", "HEAD")
        (self.repository / "marker").write_text("candidate\n")
        self.git("add", ".")
        self.git("commit", "-qm", "test: reviewed source")
        self.args.reviewed_head = self.git("rev-parse", "HEAD")
        self.git("checkout", "-q", "--detach", self.base)
        (self.repository / "main-marker").write_text("independent main context\n")
        self.git("add", ".")
        self.git("commit", "-qm", "test: main context")
        self.args.main = self.git("rev-parse", "HEAD")
        blob = subprocess.check_output(["git", "-C", str(self.repository), "hash-object", "-w", "--stdin"],
                                       input=b"unrelated private fixture bytes\n").decode().strip()
        tree = subprocess.check_output(["git", "-C", str(self.repository), "mktree"],
                                       input=f"100644 blob {blob}\tunrelated\n".encode()).decode().strip()
        unrelated = self.git("commit-tree", tree, "-m", "test: unrelated local history")
        self.git("branch", "unrelated-local", unrelated)
        self.git("tag", "-a", "unrelated-local", unrelated, "-m", "test: unrelated local tag")
        tag = self.git("rev-parse", "refs/tags/unrelated-local")
        inspected = []

        def inspect(command, env, log):
            if inspected:
                return
            root = Path(env["CI_FLEET_VALIDATION_ROOT"]).parent
            for name in ("source", "policy", "suite", "source-seed", "policy-seed", "suite-seed"):
                checkout = root / name
                refs = local.git(checkout, "for-each-ref", "--format=%(refname)")
                self.assertNotIn("unrelated-local", refs, name)
                for identity in (blob, tree, unrelated, tag):
                    result = subprocess.run(["git", "-C", str(checkout), "cat-file", "-e", identity],
                                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env=env)
                    self.assertNotEqual(result.returncode, 0, (name, identity))
            source = root / "source"
            for identity in (self.args.source, self.args.reviewed_head, self.args.main, self.base, intermediate):
                self.assertEqual(local.git(source, "rev-parse", identity + "^{commit}"), identity)
            for head in (self.args.source, self.args.reviewed_head):
                subprocess.run(["git", "-C", str(source), "merge-base", "--is-ancestor", self.base, head],
                               check=True, env=env)
            self.assertEqual(local.git(source, "rev-parse", "HEAD"), self.args.source)
            self.assertEqual(local.git(source, "rev-parse", "refs/remotes/origin/main"), self.args.main)
            inspected.append(True)

        code, result, _ = self.execute(inspect)
        self.assertEqual(code, 0, result)
        self.assertTrue(inspected)
        self.assertIn(intermediate, result["scanned_commits"])

    def test_clone_rejects_zero_identity_before_fetch(self) -> None:
        target = self.root / "invalid-checkout"
        with patch.object(local.subprocess, "run") as run:
            with self.assertRaises(ValueError):
                local.clone(self.repository, self.source, target, [self.source, local.NO_PRIOR_STATE])
            run.assert_not_called()
        self.assertFalse(target.exists())

    def test_committed_supervisor_drift_fails_before_commands(self) -> None:
        helper = self.repository / "scripts/local_validation_supervisor.py"
        helper.write_bytes(helper.read_bytes() + b"\n# unreviewed supervisor drift\n")
        self.git("add", ".")
        self.git("commit", "-qm", "test: changed supervisor fixture")
        code, result, commands = self.execute()
        self.assertEqual(code, 1, result)
        self.assertEqual(commands, [])
        self.assertTrue(all(check["status"] == "incomplete" for check in result["results"]), result)

    def test_isolated_entrypoint_loads_its_absolute_trusted_helper(self) -> None:
        for name in ("subprocess.py", "local_validation_supervisor.py"):
            (self.repository / name).write_text("raise RuntimeError('candidate import executed')\n")
        result = subprocess.run([sys.executable, "-I", str(Path(local.__file__).resolve()), "--help"],
                                cwd=self.repository, env={"PATH": "/usr/bin:/bin", "PYTHONPATH": str(self.repository)},
                                text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("--repository", result.stdout)
        self.assertNotIn("candidate import executed", result.stderr)

    def test_loaded_supervisor_does_not_reload_mutated_helper_path(self) -> None:
        trusted = self.root / "trusted-caller"
        trusted.mkdir()
        caller = trusted / "local_validate.py"
        caller.write_bytes(Path(local.__file__).read_bytes())
        helper = trusted / "local_validation_supervisor.py"
        helper.write_bytes(local.MODULE_PATH.read_bytes())
        spec = importlib.util.spec_from_file_location("trusted_local_fixture", caller)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        helper.write_text("raise RuntimeError('replacement helper executed')\n")
        log = self.root / "frozen-helper.log"
        module.run([sys.executable, "-I", "-c", "print('original supervisor executed')"],
                   self.root, {"PATH": "/usr/bin:/bin"}, log, 5)
        self.assertEqual(log.read_text(), "original supervisor executed\n")

    def test_skip_word_in_valid_title_does_not_invalidate_log(self) -> None:
        local.check_log(b'$ ["--pr-title", "ci: skip optional hosted execution"]\nOK\n')
        with self.assertRaises(RuntimeError):
            local.check_log(b'SKIP missing tool\n')

    def test_unexpected_skip_fails_instead_of_claiming_full_coverage(self) -> None:
        def skip(command, env, log):
            with log.open("ab") as output:
                output.write(b"OK (skipped=1)\n")
        code, result, _ = self.execute(skip)
        self.assertEqual(code, 1)
        self.assertIn("unexpected skipped", result["error"])

    def test_wrong_integrated_tree_and_missing_identities_fail(self) -> None:
        self.args.reviewed_head = self.base
        code, result, commands = self.execute()
        self.assertEqual(code, 1)
        self.assertIn("trees differ", result["error"])
        self.assertEqual(commands, [])
        self.args.output = self.root / "missing-results"
        self.args.source = "f" * 40
        code, result, _ = self.execute()
        self.assertEqual(code, 1)
        self.assertEqual(result["status"], "failed")

    def test_original_reviewed_history_is_included_after_squash(self) -> None:
        reviewed = self.source
        self.git("checkout", "-q", "--detach", self.base)
        (self.repository / "marker").write_text("removed intermediate secret\n")
        self.git("add", ".")
        self.git("commit", "-qm", "test: removed intermediate state")
        intermediate = self.git("rev-parse", "HEAD")
        (self.repository / "marker").write_text("candidate\n")
        self.git("add", ".")
        self.git("commit", "-qm", "test: identical final tree")
        self.args.reviewed_head = self.git("rev-parse", "HEAD")
        self.args.source = reviewed
        code, result, _ = self.execute()
        self.assertEqual(code, 0, result)
        self.assertIn(intermediate, result["scanned_commits"])
        self.assertIn(reviewed, result["scanned_commits"])

    def test_zero_base_scans_removed_secret_and_all_commit_policy(self) -> None:
        scanner = self.repository / "scripts/scan_committed_secrets.py"
        scanner.write_bytes(Path(__file__).with_name("scan_committed_secrets.py").read_bytes())
        self.git("add", ".")
        self.git("commit", "-qm", "test: install independent scanner")
        self.args.policy = self.git("rev-parse", "HEAD")
        (self.repository / ".env").write_text("EXAMPLE=fictional\n")
        self.git("add", ".")
        self.git("commit", "-qm", "test: add later removed secret file")
        removed = self.git("rev-parse", "HEAD")
        self.git("rm", "-q", ".env")
        self.git("commit", "-qm", "test: remove secret file")
        self.args.source = self.git("rev-parse", "HEAD")
        self.args.main = self.args.source
        self.args.base = local.NO_PRIOR_STATE
        expected = self.git("rev-list", "--reverse", self.args.source).splitlines()
        real_run = local.run

        def scan(command, env, log):
            if "scan_committed_secrets.py" in " ".join(command):
                real_run(command, Path(env["CI_FLEET_VALIDATION_ROOT"]), env, log, 5)

        with patch.object(local, "clone", wraps=local.clone) as clone:
            code, result, commands = self.execute(scan)
        self.assertTrue(clone.call_args_list)
        for call in clone.call_args_list:
            self.assertNotIn(local.NO_PRIOR_STATE, call.args[-1])
        self.assertEqual(code, 1, result)
        self.assertTrue(result["prior_state_absent"])
        self.assertEqual(result["base"], local.NO_PRIOR_STATE)
        self.assertEqual(result["scanned_commits"], expected)
        self.assertIn(removed, result["scanned_commits"])
        checked = [command[command.index("--head") + 1] for command, _, _ in commands
                   if "validate_commits.py" in " ".join(command)]
        self.assertEqual(checked, expected)
        for command, _, _ in commands:
            if "validate_commits.py" in " ".join(command):
                self.assertEqual(command[command.index("--base") + 1], "")
        self.assertEqual(result["results"][0]["status"], "passed")
        self.assertEqual(result["results"][1]["status"], "failed")

    def test_zero_base_does_not_admit_root_controller_network_policy(self) -> None:
        trusted = Path(__file__).resolve().parents[1]
        source = self.root / "initial-config"
        (source / "examples/multi-host").mkdir(parents=True)
        shutil.copy2(trusted / "examples/multi-host/fleet.json", source / "examples/multi-host/fleet.json")
        config = json.loads((trusted / "fleet.json").read_text())
        name, controller = next(iter(config["controllers"].items()))
        controller["docker_network_policy"] = {"networks_per_runner": 1, "reserve_subnets": 1,
            "default_address_pools": [{"base": "198.51.100.0/24", "size": 28}]}
        (source / "fleet.json").write_text(json.dumps(config))
        (source / "engine-rollout-evidence.json").write_text(json.dumps({"schema_version": 1,
            "status_reporting_engine_capabilities": {name: {"engine_ref": controller["engine_ref"],
                "status_reporting_config": False, "required_status_reporting": False,
                "docker_network_policy_config": True}}}))
        for args in (("init", "-q"), ("add", "."),
                     ("-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid", "commit", "-qm", "test: initial network policy")):
            subprocess.run(["git", "-C", str(source), *args], check=True, stdout=subprocess.DEVNULL)
        result = subprocess.run(["bash", str(trusted / "scripts/validate-local-configuration.sh")], cwd=source,
            env={"PATH": "/usr/bin:/bin", "CI_FLEET_VALIDATION_ROOT": str(source),
                 "CI_FLEET_VALIDATION_BASE": local.NO_PRIOR_STATE, "CI_FLEET_VALIDATOR_ROOT": str(trusted),
                 "CI_FLEET_TEMPLATE_FIXTURES": "true", "CI_FLEET_CONFIG_ONLY": "true"},
            text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn("must be omitted from a new controller", result.stdout)

    def test_trusted_python_does_not_import_candidate_subprocess(self) -> None:
        (self.repository / "subprocess.py").write_text("raise RuntimeError('candidate import executed')\n")
        validator = self.root / "trusted.py"
        validator.write_text("import subprocess; print(subprocess.__file__)\n")
        log_path = self.root / "isolation.log"
        local.run(["python3", "-I", str(validator)], self.repository,
                  {"PATH": "/usr/bin:/bin"}, log_path, 5)
        self.assertNotIn("candidate import executed", log_path.read_text())

    def descendant_command(self, *, graceful=False, status=0):
        ready = self.root / ("descendant-ready-" + str(time.monotonic_ns()))
        cleaned = ready.with_suffix(".cleaned")
        handler = (f"def cleanup(*_):\n Path({str(cleaned)!r}).write_text('cleaned\\n')\n raise SystemExit(0)\n"
                   "signal.signal(signal.SIGTERM, cleanup)\n") if graceful else "signal.signal(signal.SIGTERM, signal.SIG_IGN)\n"
        child = ("import os, signal, time\nfrom pathlib import Path\n" + handler +
                 f"Path({str(ready)!r}).write_text(str(os.getpid()) + ' ' + str(os.getpgrp()))\n"
                 "while True: time.sleep(0.05)\n")
        leader = ("import subprocess, sys, time\nfrom pathlib import Path\n"
                  f"child = subprocess.Popen([sys.executable, '-c', {child!r}])\n"
                  "deadline = time.monotonic() + 5\n"
                  f"while not Path({str(ready)!r}).exists():\n"
                  " if child.poll() is not None or time.monotonic() > deadline: raise RuntimeError('child did not start')\n"
                  " time.sleep(0.01)\n" +
                  ("time.sleep(30)\n" if status is None else f"sys.exit({status})\n"))

        def cleanup():
            if ready.exists():
                pid, _ = map(int, ready.read_text().split())
                try:
                    os.kill(pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass

        self.addCleanup(cleanup)
        return [sys.executable, "-c", leader], ready, cleaned

    def assert_descendant_stopped(self, ready):
        for pid in map(int, ready.read_text().split()):
            self.assertFalse(Path(f"/proc/{pid}").exists(), "a child was not reaped before the supervisor returned")

    def test_missing_proc_fails_before_starting_a_command(self) -> None:
        with patch.object(local.Path, "is_file", return_value=False), \
                patch.object(local.subprocess, "Popen") as popen:
            with self.assertRaises(RuntimeError):
                local.run([sys.executable, "-c", "pass"], self.root, {}, self.root / "missing-proc.log", 5)
            popen.assert_not_called()
            code, result, commands = self.execute()
        self.assertEqual(code, 1, result)
        self.assertEqual(commands, [])
        self.assertTrue(all(check["status"] == "incomplete" for check in result["results"]), result)

    def test_successful_leader_fails_when_descendant_requires_sigkill(self) -> None:
        command, ready, _ = self.descendant_command()
        with patch.object(local, "CLEANUP_GRACE_SECONDS", 0.2):
            with self.assertRaises(RuntimeError):
                local.run(command, self.root, {"PATH": "/usr/bin:/bin"}, self.root / "forced-cleanup.log", 5)
        self.assert_descendant_stopped(ready)

    def test_graceful_descendant_cleanup_preserves_success(self) -> None:
        command, ready, cleaned = self.descendant_command(graceful=True)
        with patch.object(local, "CLEANUP_GRACE_SECONDS", 2):
            local.run(command, self.root, {"PATH": "/usr/bin:/bin"}, self.root / "graceful-cleanup.log", 5)
        self.assertEqual(cleaned.read_text(), "cleaned\n")
        self.assert_descendant_stopped(ready)

    def test_forced_cleanup_preserves_original_failure_or_timeout(self) -> None:
        for status in (3, None):
            with self.subTest(status=status):
                command, ready, _ = self.descendant_command(status=status)
                log = self.root / ("failure-" + str(status) + ".log")
                with patch.object(local, "CLEANUP_GRACE_SECONDS", 0.2):
                    if status is None:
                        with self.assertRaises(subprocess.TimeoutExpired):
                            local.run(command, self.root, {"PATH": "/usr/bin:/bin"}, log, 1)
                    else:
                        with self.assertRaisesRegex(RuntimeError, "check exited 3"):
                            local.run(command, self.root, {"PATH": "/usr/bin:/bin"}, log, 5)
                self.assert_descendant_stopped(ready)
                ready.unlink()

    def test_actions_states_do_not_change_local_plan(self) -> None:
        for flag in (None, "true", "false"):
            self.args.output = self.root / ("result-" + str(flag))
            variables = {"CI_FLEET_HOSTED_VALIDATION": flag} if flag else {}
            with patch.dict(os.environ, variables, clear=True):
                code, report, _ = self.execute()
            self.assertEqual(code, 0, report)
            self.assertEqual([r["name"] for r in report["results"]], list(local.CHECKS))
        self.assertFalse((self.repository / ".github/workflows/validate.yml").exists())

    def test_missing_tool_keeps_all_checks_incomplete(self) -> None:
        original = subprocess.check_output
        def output(command, **kwargs):
            if command == ["shellcheck", "--version"]:
                raise FileNotFoundError("shellcheck is required")
            return original(command, **kwargs)
        with patch.object(local.subprocess, "check_output", output):
            code, result, commands = self.execute()
        self.assertEqual(code, 1)
        self.assertIn("shellcheck", result["error"])
        self.assertEqual(commands, [])
        self.assertTrue(all(r["status"] == "incomplete" for r in result["results"]))

    def test_trusted_checks_precede_candidate_initializer(self) -> None:
        self.assertLess(local.CHECKS.index("engine-policy"), local.CHECKS.index("initializer"))
        self.assertLess(local.CHECKS.index("configuration"), local.CHECKS.index("initializer"))
        self.assertLess(local.CHECKS.index("core-compatibility"), local.CHECKS.index("initializer"))
        _, _, commands = self.execute()
        adapters = [env for c, _, env in commands if "validate-local-configuration.sh" in " ".join(c)]
        self.assertEqual([env["CI_FLEET_CONFIG_ONLY"] for env in adapters], ["true", "true", "false"])
        self.assertEqual([env["CI_FLEET_INITIALIZER_ONLY"] for env in adapters], ["false", "false", "true"])

    def test_workflow_requires_opt_in_and_calls_same_suite(self) -> None:
        workflow_path = Path(__file__).resolve().parents[1] / ".github/workflows/validate.yml"
        if not workflow_path.exists():
            self.assertTrue((workflow_path.parents[2] / "scripts/local_validate.py").is_file())
            return
        workflow = workflow_path.read_text()
        self.assertIn("vars.CI_FLEET_HOSTED_VALIDATION == 'true'", workflow)
        self.assertIn("vars.CI_FLEET_VALIDATOR_REVISION", workflow)
        self.assertIn("python3 -I scripts/local_validate.py", workflow)
        self.assertIn("contents: read", workflow)
        self.assertNotIn("self-hosted", workflow)
        self.assertNotIn("contents: write", workflow)


if __name__ == "__main__":
    unittest.main()
