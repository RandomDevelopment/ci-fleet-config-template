#!/usr/bin/env python3
"""Exercise identity, isolation, failure and complete-result handling."""
from __future__ import annotations

import argparse
import contextlib
import io
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import local_validate as local


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
        for relative in ("scripts/local_validate.py", "scripts/validate_commits.py", "scripts/scan_committed_secrets.py",
                         "templates/config-repository/scripts/validate.py", "templates/config-repository/fleet.schema.json"):
            path = self.repository / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(Path(local.__file__).read_bytes() if relative == "scripts/local_validate.py" else b"fixture\n")
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
            log.write(b"fixture executed\n")
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
        self.assertEqual([check["name"] for check in result["results"]], list(local.CHECKS))
        for check in result["results"]:
            self.assertEqual(check["status"], "passed")
            self.assertEqual(check["sha256"], hashlib.sha256((self.args.output / check["log"]).read_bytes()).hexdigest())
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

    def test_unexpected_skip_fails_instead_of_claiming_full_coverage(self) -> None:
        def skip(command, env, log):
            log.write(b"OK (skipped=1)\n")
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

    def test_trusted_python_does_not_import_candidate_subprocess(self) -> None:
        (self.repository / "subprocess.py").write_text("raise RuntimeError('candidate import executed')\n")
        validator = self.root / "trusted.py"
        validator.write_text("import subprocess; print(subprocess.__file__)\n")
        log_path = self.root / "isolation.log"
        with log_path.open("wb") as log:
            local.run(["python3", "-I", str(validator)], self.repository,
                      {"PATH": "/usr/bin:/bin"}, log, 5)
        self.assertNotIn("candidate import executed", log_path.read_text())

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
