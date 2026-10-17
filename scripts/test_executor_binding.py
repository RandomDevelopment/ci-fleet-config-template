#!/usr/bin/env python3
"""Verify the standalone driver uses only its reviewed installed core executor."""
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

import local_validate as local


class ExecutorBindingTests(unittest.TestCase):
    def test_selected_executor_has_the_fixed_installed_location_and_revision(self):
        self.assertEqual(local.EXECUTOR_PATH, Path("/usr/local/lib/ci-fleet-validation/executor.py"))
        self.assertRegex(local.EXECUTOR_REVISION, r"^[0-9a-f]{40}$")
        module = local.load_executor()
        self.assertEqual(Path(module.__file__), local.EXECUTOR_PATH)
        module.require_revision(local.EXECUTOR_REVISION)

    def test_driver_forwards_the_command_user_deadline_and_cleanup_grace(self):
        executor = Mock()
        root = Path("/unused")
        env = {"PATH": "/usr/bin:/bin", "CI_FLEET_STAGE_USER": "ci-fleet-validation"}
        with patch.object(local, "require_worker"), patch.object(local, "load_executor", return_value=executor):
            local.run(["true"], root, env, root / "log", 11)
        executor.run.assert_called_once_with(["true"], root, env, root / "log", 11,
                                             grace=local.CLEANUP_GRACE_SECONDS, user="ci-fleet-validation")

    def test_executor_failure_propagates_without_a_fallback(self):
        executor = Mock()
        executor.run.side_effect = RuntimeError("incomplete cgroup cleanup")
        with patch.object(local, "require_worker"), patch.object(local, "load_executor", return_value=executor), \
                patch.object(local.subprocess, "Popen") as launch:
            with self.assertRaisesRegex(RuntimeError, "incomplete cgroup cleanup"):
                local.run(["true"], Path("/"), {}, Path("/unused"), 1)
            launch.assert_not_called()

    def test_wrong_revision_refuses_before_starting_the_command(self):
        with patch.object(local, "EXECUTOR_REVISION", "0" * 40), patch.object(local.subprocess, "Popen") as launch:
            with self.assertRaisesRegex(RuntimeError, "exact reviewed"):
                local.run(["true"], Path("/"), {}, Path("/unused"), 1)
            launch.assert_not_called()

    def test_writable_or_missing_executor_is_never_imported(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "executor.py"
            path.write_text("raise AssertionError('untrusted executor imported')\n")
            path.chmod(0o666)
            with patch.object(local, "EXECUTOR_PATH", path), self.assertRaisesRegex(RuntimeError, "unsafe installed"):
                local.load_executor()
            path.unlink()
            with patch.object(local, "EXECUTOR_PATH", path), self.assertRaises(FileNotFoundError):
                local.load_executor()


if __name__ == "__main__":
    unittest.main()
