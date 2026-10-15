#!/usr/bin/env python3
"""Run trusted regression tests against candidate programs and reject omissions."""
from __future__ import annotations

import argparse
import importlib.util
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
IMPLEMENTATIONS = (
    "scripts/validate.py", "scripts/validate.sh", "scripts/init.py", "scripts/init.sh",
    "scripts/scan_committed_secrets.py", "scripts/update_template.py", "scripts/local_validate.py",
    "scripts/validate-local-configuration.sh", "fleet.schema.json", "template-compatibility.json",
)
OPTIONAL_WORKFLOWS = (".github/workflows/validate.yml", ".github/workflows/template-update.yml")
UPSTREAM_PROBES = (
    "test_exact_core_drift_check_is_pinned_and_runnable",
    "test_exact_core_drift_check_rejects_required_tree_and_allowlisted_hash_drift",
    "test_exact_core_drift_check_rejects_corrupt_allowlisted_core_bytes",
)


def flatten(suite):
    for test in suite:
        if isinstance(test, unittest.TestSuite):
            yield from flatten(test)
        else:
            yield test


def run_tests(fixture: Path, name: str, derived: bool) -> int:
    sys.path.insert(0, str(fixture / "scripts"))
    os.chdir(fixture)
    spec = importlib.util.spec_from_file_location(name, fixture / "scripts" / (name + ".py"))
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    tests = list(flatten(unittest.defaultTestLoader.loadTestsFromModule(module)))
    if derived and name == "test_policy":
        expected = {f"{name}.PolicyTests.{probe}" for probe in UPSTREAM_PROBES}
        for probe in sorted(expected):
            if sum(test.id() == probe for test in tests) != 1:
                raise ValueError("required upstream probe must occur exactly once: " + probe)
        tests = [test for test in tests if test.id() not in expected]
        print("upstream probes covered by trusted fixtures: " + ", ".join(UPSTREAM_PROBES), flush=True)
    if not tests:
        raise ValueError("candidate regression suite contains no applicable tests")
    result = unittest.TextTestRunner(verbosity=2).run(unittest.TestSuite(tests))
    if result.skipped:
        print("candidate regression tests contain unexpected omissions", file=sys.stderr)
        return 1
    return 0 if result.wasSuccessful() else 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository", type=Path, required=True)
    parser.add_argument("--test", choices=("test_policy", "test_template_updater", "test_release_update"), required=True)
    parser.add_argument("--derived", action="store_true")
    args = parser.parse_args()
    try:
        repository = args.repository.resolve(strict=True)
        with tempfile.TemporaryDirectory(prefix="ci-fleet-candidate-tests-") as temporary:
            fixture = Path(temporary) / "fixture"
            shutil.copytree(ROOT, fixture, ignore=shutil.ignore_patterns(".git", "__pycache__", "*.pyc"))
            for relative in IMPLEMENTATIONS:
                shutil.copy2(repository / relative, fixture / relative)
            for relative in OPTIONAL_WORKFLOWS:
                target = fixture / relative
                if (repository / relative).is_file():
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(repository / relative, target)
                else:
                    target.unlink(missing_ok=True)
            origin = "fictional/derived-config" if args.derived else "RandomDevelopment/ci-fleet-config-template"
            for command in (
                ["init", "-q"], ["remote", "add", "origin", "https://github.com/" + origin], ["add", "."],
                ["-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid", "commit", "-qm", "test: candidate programs"],
            ):
                subprocess.run(["git", "-C", str(fixture), *command], check=True, stdout=subprocess.DEVNULL)
            return run_tests(fixture, args.test, args.derived)
    except (Exception, SystemExit) as error:
        print("candidate test execution failed: " + str(error), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
