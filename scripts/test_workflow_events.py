#!/usr/bin/env python3
"""Exercise hosted event arguments using the workflow's actual shell block."""
from __future__ import annotations

import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
ZERO = "0" * 40


class WorkflowEventTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.source = self.root / "candidate"
        self.source.mkdir()
        self.workflow = (ROOT / ".github/workflows/validate.yml").read_text()
        lines = self.workflow.split("      - name: Run complete local validation\n", 1)[1]
        step = lines.split("      - name: ", 1)[0]
        environment, shell = step.split("        run: |\n", 1)
        self.environment = dict(line.strip().split(": ", 1) for line in environment.splitlines()
                                if line.startswith("          "))
        self.shell = "\n".join(line[10:] for line in shell.splitlines())
        bin_path = self.root / "bin"
        bin_path.mkdir()
        python = bin_path / "python3"
        python.write_text(f"#!{sys.executable}\n" +
                          "import json, os, sys\nfrom pathlib import Path\n"
                          "Path(os.environ['CAPTURE']).write_text(json.dumps(sys.argv[1:]))\n"
                          "raise SystemExit(int(os.environ.get('VALIDATOR_EXIT', '0')))\n")
        python.chmod(0o755)
        git = bin_path / "git"
        git.write_text('#!/bin/sh\nprintf "%s\\n" "$*" >> "$GIT_CALLED"\nexit 97\n')
        git.chmod(0o755)
        self.env = {"PATH": str(bin_path) + ":/usr/bin:/bin", "PWD": str(self.source),
                    "GITHUB_WORKSPACE": str(self.root),
                    "RUNNER_TEMP": str(self.root / "runner-temp"), "CAPTURE": str(self.root / "arguments.json"),
                    "GIT_CALLED": str(self.root / "git-called"), "SOURCE": "a" * 40, "BASE": "b" * 40,
                    "REPOSITORY": "fictional/config", "VALIDATOR": "c" * 40, "SUITE": "d" * 40,
                    "EVENT_NAME": "push", "PR_TITLE": "ci: unused push title"}

    def execute(self):
        process = subprocess.run(["bash", "-e", "-o", "pipefail", "-c", self.shell],
                                 cwd=self.source, env=self.env, capture_output=True, text=True)
        self.assertFalse(Path(self.env["GIT_CALLED"]).exists(), "workflow queried Git instead of preserving the event boundary")
        arguments = json.loads(Path(self.env["CAPTURE"]).read_text())
        self.assertEqual(arguments[:2], ["-I", str(self.root / ".ci-fleet-suite/scripts/local_validate.py")])
        return process, arguments

    def test_optional_job_has_a_distinct_context_and_read_only_permissions(self) -> None:
        jobs = self.workflow.split("jobs:\n", 1)[1]
        self.assertEqual(re.findall(r"^  ([A-Za-z0-9_-]+):", jobs, re.M), ["hosted-validation"])
        self.assertIn("    name: hosted-validation\n", jobs)
        self.assertIn("vars.CI_FLEET_HOSTED_VALIDATION == 'true'", jobs)
        self.assertIn("    timeout-minutes: 5\n", jobs)
        self.assertIn("permissions:\n  contents: read\n", self.workflow)
        self.assertNotIn("contents: write", self.workflow)

    def test_closed_pull_request_cannot_execute_or_cancel_main_validation(self) -> None:
        condition = re.search(r"^    if: \$\{\{ (.+) \}\}$", self.workflow, re.M).group(1)
        for flag, event, state, expected in (
            ("true", "pull_request", "open", True),
            ("true", "pull_request", "closed", False),
            ("true", "push", "", True),
            ("false", "pull_request", "open", False),
        ):
            with self.subTest(flag=flag, event=event, state=state):
                expression = condition.replace("vars.CI_FLEET_HOSTED_VALIDATION", repr(flag)).replace(
                    "github.event_name", repr(event)).replace("github.event.pull_request.state", repr(state))
                expression = expression.replace("&&", " and ").replace("||", " or ")
                self.assertEqual(eval(expression, {"__builtins__": {}}), expected)
        group = re.search(r"^  group: (.+)$", self.workflow, re.M).group(1)
        self.assertEqual(group, "config-validation-${{ github.event_name }}-"
                         "${{ github.event.pull_request.number || github.ref }}")
        closed_pr = group.replace("${{ github.event_name }}", "pull_request").replace(
            "${{ github.event.pull_request.number || github.ref }}", "34")
        main_push = group.replace("${{ github.event_name }}", "push").replace(
            "${{ github.event.pull_request.number || github.ref }}", "refs/heads/main")
        self.assertNotEqual(closed_pr, main_push)

    def test_suite_is_checked_out_from_a_fixed_independently_pinned_repository(self) -> None:
        step = self.workflow.split("      - name: Check out trusted suite\n", 1)[1].split("      - name: ", 1)[0]
        self.assertIn("repository: RandomDevelopment/ci-fleet-config-template\n", step)
        self.assertIn("ref: ${{ vars.CI_FLEET_SUITE_REVISION }}\n", step)
        self.assertIn("path: .ci-fleet-suite\n", step)
        self.assertIn("fetch-depth: 0\n", step)
        self.assertIn("persist-credentials: false\n", step)
        source = self.workflow.split("      - name: Check out exact source\n", 1)[1].split("      - name: ", 1)[0]
        self.assertIn("path: candidate\n", source)
        self.assertIn("persist-credentials: false\n", source)
        self.assertLess(self.workflow.index("      - name: Require independently pinned validator\n"),
                        self.workflow.index("      - name: Check out exact source\n"))

    def test_missing_or_malformed_pins_fail_before_candidate_execution(self) -> None:
        step = self.workflow.split("      - name: Require independently pinned validator\n", 1)[1].split("      - name: ", 1)[0]
        shell = "\n".join(line[10:] for line in step.split("        run: |\n", 1)[1].splitlines())
        self.assertEqual(subprocess.run(["bash", "-e", "-c", shell], env=self.env).returncode, 0)
        for variable in ("SUITE", "VALIDATOR"):
            for value in (None, "", "main", "v1.0.0", "d" * 39, "D" * 40, "d" * 40 + " ", ZERO):
                with self.subTest(variable=variable, value=value):
                    env = dict(self.env)
                    if value is None:
                        env.pop(variable)
                    else:
                        env[variable] = value
                    self.assertNotEqual(subprocess.run(["bash", "-e", "-c", shell], env=env).returncode, 0)
                    self.assertFalse(Path(self.env["CAPTURE"]).exists())
        self.assertIn("SUITE: ${{ vars.CI_FLEET_SUITE_REVISION }}", step)

    def test_candidate_entry_point_cannot_replace_the_trusted_driver(self) -> None:
        candidate = self.source / "scripts/local_validate.py"
        candidate.parent.mkdir()
        candidate_marker = self.root / "candidate-ran"
        candidate.write_text("from pathlib import Path\n" +
                             f"Path({str(candidate_marker)!r}).touch()\nraise SystemExit(0)\n")
        trusted = self.root / ".ci-fleet-suite/scripts/local_validate.py"
        trusted.parent.mkdir(parents=True)
        trusted_marker = self.root / "trusted-ran"
        trusted.write_text("import json, os, sys\nfrom pathlib import Path\n" +
                           f"Path({str(trusted_marker)!r}).touch()\n" +
                           "Path(os.environ['CAPTURE']).write_text(json.dumps(sys.argv[1:]))\n" +
                           "raise SystemExit(29)\n")
        env = {**self.env, "PATH": "/usr/bin:/bin"}
        process = subprocess.run(["bash", "-e", "-o", "pipefail", "-c", self.shell],
                                 cwd=self.source, env=env, capture_output=True, text=True)
        self.assertFalse(candidate_marker.exists(), "candidate replaced the trusted validation driver")
        self.assertTrue(trusted_marker.exists())
        self.assertEqual(process.returncode, 29, process.stderr)
        arguments = json.loads(Path(self.env["CAPTURE"]).read_text())
        self.assertEqual(arguments[arguments.index("--repository") + 1], str(self.source))
        self.assertEqual(arguments[arguments.index("--policy-repository") + 1], str(self.root / ".ci-fleet-validator"))

    def test_pull_request_edits_refresh_title_and_target_context(self) -> None:
        self.assertIn("  pull_request:\n    types: [opened, synchronize, reopened, edited]\n", self.workflow)

    def test_pull_request_passes_target_main_and_literal_title(self) -> None:
        self.assertEqual(self.environment["EVENT_NAME"], "${{ github.event_name }}")
        self.assertEqual(self.environment["PR_TITLE"], "${{ github.event.pull_request.title }}")
        self.assertEqual(self.environment["SOURCE"], "${{ github.event.pull_request.head.sha || github.sha }}")
        self.assertEqual(self.environment["BASE"], "${{ github.event.pull_request.base.sha || github.event.before }}")
        self.assertNotIn("${{", self.shell)
        sentinel = self.root / "title-was-executed"
        title = f'ci: preserve "$(touch {sentinel})"; `touch {sentinel}` $PATH\nsecond line'
        self.env.update(EVENT_NAME="pull_request", PR_TITLE=title)
        process, arguments = self.execute()
        self.assertEqual(process.returncode, 0, process.stderr)
        self.assertEqual(arguments[arguments.index("--main") + 1], self.env["BASE"])
        self.assertEqual(arguments[arguments.index("--base") + 1], self.env["BASE"])
        self.assertEqual(arguments[arguments.index("--source") + 1], self.env["SOURCE"])
        self.assertEqual(arguments[arguments.index("--pr-title") + 1], title)
        self.assertFalse(sentinel.exists())

    def test_push_uses_source_main_without_a_pull_request_title(self) -> None:
        process, arguments = self.execute()
        self.assertEqual(process.returncode, 0, process.stderr)
        self.assertEqual(arguments[arguments.index("--main") + 1], self.env["SOURCE"])
        self.assertEqual(arguments[arguments.index("--base") + 1], self.env["BASE"])
        self.assertNotIn("--pr-title", arguments)

    def test_imported_push_preserves_zero_base_even_with_a_source_parent(self) -> None:
        subprocess.run(["git", "init", "-q", str(self.source)], check=True)
        for value in ("initial", "child"):
            (self.source / "fixture").write_text(value + "\n")
            subprocess.run(["git", "-C", str(self.source), "add", "fixture"], check=True)
            subprocess.run(["git", "-C", str(self.source), "-c", "user.name=Fixture",
                            "-c", "user.email=fixture@example.invalid", "commit", "-qm", "test: " + value], check=True)
        self.env["SOURCE"] = subprocess.check_output(["git", "-C", str(self.source), "rev-parse", "HEAD"], text=True).strip()
        parent = subprocess.check_output(["git", "-C", str(self.source), "rev-parse", "HEAD^"], text=True).strip()
        self.assertNotEqual(self.env["SOURCE"], parent)
        for base in (ZERO, "", None):
            with self.subTest(base=base):
                if base is None:
                    self.env.pop("BASE", None)
                else:
                    self.env["BASE"] = base
                process, arguments = self.execute()
                self.assertEqual(process.returncode, 0, process.stderr)
                self.assertEqual(arguments[arguments.index("--base") + 1], ZERO)
                self.assertEqual(arguments[arguments.index("--main") + 1], self.env["SOURCE"])

    def test_validator_failure_is_not_masked(self) -> None:
        self.env.update(EVENT_NAME="pull_request", PR_TITLE="invalid title", VALIDATOR_EXIT="29")
        process, arguments = self.execute()
        self.assertEqual(process.returncode, 29)
        self.assertEqual(arguments[arguments.index("--pr-title") + 1], "invalid title")


class LocalAvailabilityTests(unittest.TestCase):
    def test_local_entry_point_remains_available_without_hosted_workflow(self) -> None:
        self.assertTrue((ROOT / "scripts/local_validate.py").is_file())


def load_tests(loader, tests, pattern):
    if (ROOT / ".github/workflows/validate.yml").exists():
        return tests
    return loader.loadTestsFromTestCase(LocalAvailabilityTests)


if __name__ == "__main__":
    unittest.main()
