#!/usr/bin/env python3
"""Prove trusted candidate tests execute changed programs without hiding omissions."""
from __future__ import annotations

from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import textwrap
import unittest


RUNNER = Path(__file__).with_name("run_candidate_tests.py")
PROBES = (
    "test_exact_core_drift_check_is_pinned_and_runnable",
    "test_exact_core_drift_check_rejects_required_tree_and_allowlisted_hash_drift",
    "test_exact_core_drift_check_rejects_corrupt_allowlisted_core_bytes",
)
MODULES = ("test_policy", "test_template_updater", "test_release_update")
IMPLEMENTATIONS = (
    "scripts/validate.py", "scripts/validate.sh", "scripts/init.py", "scripts/init.sh",
    "scripts/scan_committed_secrets.py", "scripts/update_template.py", "scripts/local_validate.py",
    "scripts/local_validation_supervisor.py",
    "scripts/validate-local-configuration.sh", "fleet.schema.json", "template-compatibility.json",
)


class CandidateRunnerTests(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.repository = self.root / "candidate"
        self.trusted = self.root / "trusted"
        (self.trusted / "scripts").mkdir(parents=True)
        shutil.copy2(RUNNER, self.trusted / "scripts/run_candidate_tests.py")
        for relative in IMPLEMENTATIONS:
            for repository in (self.repository, self.trusted):
                path = repository / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("# unused fixture program\n")
        for repository in (self.repository, self.trusted):
            (repository / "scripts/update_template.py").write_text('def candidate_value():\n    return "candidate dependency"\n')
        (self.trusted / "fleet.json").write_text('"trusted fictional configuration"\n')
        (self.repository / "fleet.json").write_text('"adopter configuration must not replace fixtures"\n')
        (self.trusted / ".github/workflows").mkdir(parents=True)
        (self.trusted / ".github/workflows/validate.yml").write_text("trusted workflow\n")

    def run_module(self, name: str, body: str, *, derived: bool = False):
        (self.trusted / "scripts" / (name + ".py")).write_text(textwrap.dedent(body))
        command = [sys.executable, "-I", str(self.trusted / "scripts/run_candidate_tests.py"),
                   "--repository", str(self.repository), "--test", name]
        if derived:
            command.append("--derived")
        return subprocess.run(command, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=10)

    def policy_fixture(self, *, probes=PROBES, extra: str = "") -> str:
        methods = "".join(f"    def {name}(self):\n        self.fail('upstream probe executed')\n" for name in probes)
        return "import unittest\nclass PolicyTests(unittest.TestCase):\n" + methods + (
            "    def test_candidate_behavior(self):\n        self.assertEqual(2 + 2, 4)\n" + extra
        )

    def test_trusted_suites_import_candidate_implementation(self) -> None:
        for module in MODULES:
            with self.subTest(module=module):
                result = self.run_module(module, '''
                    import unittest
                    from update_template import candidate_value
                    class CandidateTests(unittest.TestCase):
                        def test_candidate_import(self):
                            self.assertEqual(candidate_value(), "candidate dependency")
                ''')
                self.assertEqual(result.returncode, 0, result.stdout)
                self.assertIn("Ran 1 test", result.stdout)

    def test_candidate_functional_failures_cannot_replace_trusted_tests(self) -> None:
        (self.repository / "scripts/update_template.py").write_text('def candidate_value():\n    return "candidate regression"\n')
        for module in MODULES:
            with self.subTest(module=module):
                (self.repository / "scripts" / (module + ".py")).write_text("raise SystemExit(0)\n")
                result = self.run_module(module, '''
                    import unittest
                    from update_template import candidate_value
                    class CandidateTests(unittest.TestCase):
                        def test_candidate_behavior(self):
                            self.assertEqual(candidate_value(), "candidate dependency")
                ''')
                self.assertEqual(result.returncode, 1, result.stdout)
                self.assertIn("candidate regression", result.stdout)

    def test_candidate_import_cannot_exit_successfully_before_tests(self) -> None:
        (self.repository / "scripts/update_template.py").write_text("raise SystemExit(0)\n")
        result = self.run_module("test_template_updater", "import update_template\n")
        self.assertEqual(result.returncode, 2, result.stdout)
        self.assertIn("candidate test execution failed", result.stdout)

    def test_fictional_configuration_is_preserved_and_workflow_absence_is_actual(self) -> None:
        result = self.run_module("test_template_updater", '''
            from pathlib import Path
            import unittest
            class CandidateTests(unittest.TestCase):
                def test_fixture_configuration(self):
                    root = Path(__file__).resolve().parents[1]
                    self.assertEqual((root / "fleet.json").read_text(), '"trusted fictional configuration"\\n')
                    self.assertFalse((root / ".github/workflows/validate.yml").exists())
        ''')
        self.assertEqual(result.returncode, 0, result.stdout)

    def test_actual_omission_fails_even_when_unittest_reports_success(self) -> None:
        result = self.run_module("test_template_updater", '''
            import unittest
            class CandidateTests(unittest.TestCase):
                @unittest.skip("unexpected omitted behavior")
                def test_candidate_behavior(self):
                    pass
        ''')
        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn("unexpected omissions", result.stdout)

    def test_derived_policy_omits_only_named_upstream_probes(self) -> None:
        result = self.run_module("test_policy", self.policy_fixture(), derived=True)
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn("upstream probes covered by trusted fixtures", result.stdout)
        for name in PROBES:
            self.assertIn(name, result.stdout)
        self.assertIn("Ran 1 test", result.stdout)
        self.assertNotIn("skipped", result.stdout.lower())

    def test_derived_policy_additional_omission_fails(self) -> None:
        fixture = self.policy_fixture(extra=(
            "    @unittest.skip('unexpected omitted behavior')\n"
            "    def test_additional_behavior(self):\n        pass\n"
        ))
        result = self.run_module("test_policy", fixture, derived=True)
        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn("unexpected omissions", result.stdout)

    def test_derived_policy_missing_expected_probe_fails(self) -> None:
        result = self.run_module("test_policy", self.policy_fixture(probes=PROBES[:-1]), derived=True)
        self.assertEqual(result.returncode, 2, result.stdout)
        self.assertIn("required upstream probe must occur exactly once", result.stdout)
        self.assertIn(PROBES[-1], result.stdout)

    def test_derived_updater_and_release_suites_are_not_filtered(self) -> None:
        for module in MODULES[1:]:
            with self.subTest(module=module):
                result = self.run_module(module, self.policy_fixture(), derived=True)
                self.assertEqual(result.returncode, 1, result.stdout)
                self.assertIn("Ran 4 tests", result.stdout)
                self.assertNotIn("upstream probes covered by trusted fixtures", result.stdout)

    def test_upstream_policy_probes_are_not_filtered(self) -> None:
        result = self.run_module("test_policy", self.policy_fixture())
        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn("Ran 4 tests", result.stdout)


if __name__ == "__main__":
    unittest.main()
