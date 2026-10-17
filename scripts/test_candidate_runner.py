#!/usr/bin/env python3
"""Prove trusted candidate tests execute changed programs without hiding omissions."""
from __future__ import annotations

from pathlib import Path
import os
import shutil
import subprocess
import sys
import tempfile
import textwrap
import unittest


RUNNER = Path(__file__).with_name("run_candidate_tests.py")
TRUSTED_FIXTURE_ROOT = globals().get("TRUSTED_FIXTURE_ROOT", RUNNER.parents[1])
PROBES = (
    "test_exact_core_drift_check_is_pinned_and_runnable",
    "test_exact_core_drift_check_rejects_required_tree_and_allowlisted_hash_drift",
    "test_exact_core_drift_check_rejects_corrupt_allowlisted_core_bytes",
)
MODULES = ("test_policy", "test_template_updater", "test_release_update", "test_workflow_events",
           "test_local_validation", "test_executor_binding", "test_candidate_runner")
UPSTREAM_INPUTS = (
    "README.md", "AGENTS.md", "docs/LOCAL-VALIDATION.md", "docs/UPDATING.md",
    "docs/RELEASE.md", "docs/DEPLOYMENT-POLICY.md",
)
IMPLEMENTATIONS = (
    "scripts/validate.py", "scripts/validate.sh", "scripts/init.py", "scripts/init.sh",
    "scripts/scan_committed_secrets.py", "scripts/update_template.py", "scripts/local_validate.py",
    "scripts/run_candidate_tests.py",
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
        for relative in IMPLEMENTATIONS:
            for repository in (self.repository, self.trusted):
                path = repository / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("# unused fixture program\n")
        for repository in (self.repository, self.trusted):
            shutil.copy2(RUNNER, repository / "scripts/run_candidate_tests.py")
        for repository in (self.repository, self.trusted):
            for relative in UPSTREAM_INPUTS:
                path = repository / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("reviewed fixture documentation\n")
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
        return subprocess.run(command, env={**os.environ, "TMPDIR": str(self.root)},
                              text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=10)

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

    def test_exit_zero_during_import_test_or_addition_cannot_complete_the_worker(self) -> None:
        for location in ("import", "test", "addition"):
            with self.subTest(location=location):
                (self.repository / "scripts/update_template.py").write_text(
                    "import os; os._exit(0)\n" if location == "import" else "# fixture\n")
                addition = self.repository / "scripts/test_policy.py"
                if location == "addition":
                    addition.write_text("import os; os._exit(0)\n")
                else:
                    addition.unlink(missing_ok=True)
                action = "os._exit(0)" if location == "test" else "pass"
                result = self.run_module("test_policy", "import unittest, os, update_template\n"
                                         "class ExitTests(unittest.TestCase):\n"
                                         f"    def test_candidate(self): {action}\n")
                self.assertNotEqual(result.returncode, 0, result.stdout)

    def test_harness_corpora_exercise_candidate_programs_with_pinned_definitions(self) -> None:
        for name, program in (("test_local_validation", "local_validate"),
                              ("test_executor_binding", "local_validate"),
                              ("test_candidate_runner", "run_candidate_tests")):
            corpus = f'''import unittest
from {program} import candidate_value
class HarnessProgramTests(unittest.TestCase):
    def test_candidate_behavior(self):
        self.assertEqual(candidate_value(), "reviewed harness behavior")
'''
            (self.repository / "scripts" / (name + ".py")).write_text("# candidate removed all required tests\n")
            path = self.repository / "scripts" / (program + ".py")
            for derived in (False, True):
                with self.subTest(program=program, derived=derived):
                    path.write_text('def candidate_value(): return "reviewed harness behavior"\n')
                    result = self.run_module(name, corpus, derived=derived)
                    self.assertEqual(result.returncode, 0, result.stdout)
                    path.write_text('def candidate_value(): return "broken candidate harness"\n')
                    result = self.run_module(name, corpus, derived=derived)
                    self.assertEqual(result.returncode, 1, result.stdout)
                    self.assertIn("broken candidate harness", result.stdout)

    def test_pinned_workflow_input_does_not_restore_an_absent_candidate_workflow(self) -> None:
        result = self.run_module("test_candidate_runner", '''
            from pathlib import Path
            import unittest
            class PinnedFixtureTests(unittest.TestCase):
                def test_fixture_provenance(self):
                    self.assertEqual((TRUSTED_FIXTURE_ROOT / ".github/workflows/validate.yml").read_text(), "trusted workflow\\n")
                    self.assertFalse((Path(__file__).resolve().parents[1] / ".github/workflows/validate.yml").exists())
        ''', derived=True)
        self.assertEqual(result.returncode, 0, result.stdout)

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

    def test_required_inventory_rejects_duplicate_ids_and_incomplete_execution(self) -> None:
        duplicate = """
            import unittest
            class Required(unittest.TestCase):
                def test_required(self):
                    pass
            def load_tests(loader, tests, pattern):
                test = Required('test_required')
                return unittest.TestSuite([test, test])
        """
        result = self.run_module("test_template_updater", duplicate)
        self.assertEqual(result.returncode, 2, result.stdout)
        self.assertIn("unique identities", result.stdout)
        result = self.run_module("test_template_updater", """
            import unittest
            class Required(unittest.TestCase):
                def test_required(self):
                    self.fail('must be counted')
                def run(self, result=None):
                    return result
        """)
        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn("planned count", result.stdout)

    def test_candidate_additions_follow_required_tests_without_replacing_them(self) -> None:
        (self.repository / "scripts/test_template_updater.py").write_text(textwrap.dedent("""
            import unittest
            class Required(unittest.TestCase):
                def test_required(self):
                    self.fail('replacement must not run')
                def test_added_regression(self):
                    self.fail('candidate-added regression executed')
        """))
        result = self.run_module("test_template_updater", """
            import unittest
            class Required(unittest.TestCase):
                def test_required(self):
                    pass
        """)
        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn('"corpus": "trusted"', result.stdout)
        self.assertIn('"corpus": "candidate additions"', result.stdout)
        self.assertIn("candidate-added regression executed", result.stdout)
        self.assertNotIn("replacement must not run", result.stdout)

    def test_neutralized_candidate_tests_cannot_hide_program_or_release_failures(self) -> None:
        cases = (
            ("test_policy", "scripts/validate.py",
             "class Validation:\n    def __init__(self): self.errors=[]\ndef validate_config(value, result, strict): result.errors.append('invalid')\n",
             "class Validation:\n    def __init__(self): self.errors=[]\ndef validate_config(value, result, strict): pass\n",
             "from validate import Validation, validate_config\nimport unittest\nclass Required(unittest.TestCase):\n    def test_rejects_invalid_configuration(self):\n        result=Validation()\n        validate_config({}, result, False)\n        self.assertTrue(result.errors)\n"),
            ("test_template_updater", "scripts/update_template.py",
             "def records(raw): raise ValueError('malformed release record')\n", "def records(raw): return {}\n",
             "from update_template import records\nimport unittest\nclass Required(unittest.TestCase):\n    def test_rejects_malformed_release_record(self):\n        with self.assertRaises(ValueError): records('bad')\n"),
            ("test_release_update", "docs/RELEASE.md",
             "0e54aaa09d0565ce103035f213953639fc068a73\n", "rewritten published record\n",
             "from pathlib import Path\nimport unittest\nclass Required(unittest.TestCase):\n    def test_published_tag_identity(self):\n        self.assertIn('0e54aaa09d0565ce103035f213953639fc068a73', (Path(__file__).resolve().parents[1]/'docs/RELEASE.md').read_text())\n"),
        )
        for name, relative, good, broken, corpus in cases:
            with self.subTest(module=name):
                (self.trusted / relative).write_text(good)
                (self.repository / relative).write_text(broken)
                (self.repository / "scripts" / (name + ".py")).write_text("# candidate removed all regressions\n")
                result = self.run_module(name, corpus)
                self.assertEqual(result.returncode, 1, result.stdout)
                self.assertIn("Ran 1 test", result.stdout)

    def test_trusted_workflow_corpus_rejects_candidate_guards_and_masked_failures(self) -> None:
        original = (TRUSTED_FIXTURE_ROOT / ".github/workflows/validate.yml").read_text()
        corpus = (TRUSTED_FIXTURE_ROOT / "scripts/test_workflow_events.py").read_text()
        candidate = self.repository / ".github/workflows/validate.yml"
        candidate.parent.mkdir(parents=True)
        (self.repository / "scripts/test_workflow_events.py").write_text("# candidate removed all workflow tests\n")
        changes = (
            ('[[ "$SUITE" =~ ^[0-9a-f]{40}$ && "$SUITE" != 0000000000000000000000000000000000000000 ]]', 'true'),
            (" && (github.event_name != 'pull_request' || github.event.pull_request.state == 'open')", ""),
            ('"${title_args[@]}"\n', '"${title_args[@]}" || true\n'),
        )
        for before, after in changes:
            with self.subTest(bypass=before):
                self.assertEqual(original.count(before), 1)
                candidate.write_text(original.replace(before, after))
                result = self.run_module("test_workflow_events", corpus)
                self.assertEqual(result.returncode, 1, result.stdout)
                self.assertIn("Ran 11 tests", result.stdout)

    def test_missing_candidate_workflow_uses_trusted_availability_case_without_skips(self) -> None:
        result = self.run_module("test_workflow_events", (TRUSTED_FIXTURE_ROOT / "scripts/test_workflow_events.py").read_text(), derived=True)
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn("LocalAvailabilityTests.test_local_entry_point_remains_available_without_hosted_workflow", result.stdout)
        self.assertIn("Ran 1 test", result.stdout)
        self.assertNotIn("skipped", result.stdout.lower())

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

    def test_non_policy_derived_suites_are_not_filtered(self) -> None:
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
