#!/usr/bin/env python3
"""Exercise the documented immutable release update in a fictional adopter."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def git(repository: Path, *args: str, capture: bool = False) -> str:
    result = subprocess.run(
        ["git", "-C", str(repository), *args],
        check=True,
        stdout=subprocess.PIPE if capture else subprocess.DEVNULL,
        text=True,
    )
    return result.stdout.strip() if capture else ""


def configure(repository: Path) -> None:
    git(repository, "config", "user.name", "Release Test")
    git(repository, "config", "user.email", "release@example.invalid")


def fetch_recorded_release(repository: Path, tag: str) -> subprocess.CompletedProcess[str]:
    records = dict(
        line.split()
        for line in (repository / "TEMPLATE_RELEASE").read_text(encoding="utf-8").splitlines()
    )
    temporary_ref = "refs/tmp/template-tag-check"
    subprocess.run(["git", "-C", str(repository), "update-ref", "-d", temporary_ref], check=False)
    fetch = subprocess.run(
        ["git", "-C", str(repository), "fetch", "--no-tags", "template", f"refs/tags/{tag}:{temporary_ref}"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    if fetch.returncode:
        return fetch
    oid = git(repository, "rev-parse", temporary_ref, capture=True)
    if tag in records and records[tag] != oid:
        git(repository, "update-ref", "-d", temporary_ref)
        return subprocess.CompletedProcess(fetch.args, 1, "", f"template tag {tag} was rewritten upstream; refusing to use it")
    commit = git(repository, "rev-parse", f"{temporary_ref}^{{commit}}", capture=True)
    git(repository, "update-ref", "-d", temporary_ref)
    return subprocess.CompletedProcess(fetch.args, 0, f"{oid} {commit}", "")


class ReleaseUpdateTests(unittest.TestCase):
    def test_derived_repository_policy_suite_ignores_exact_core_identity(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            derived = Path(directory) / "derived"
            shutil.copytree(
                ROOT,
                derived,
                ignore=shutil.ignore_patterns(".git", "__pycache__", "*.pyc"),
            )
            config_path = derived / "fleet.json"
            config = json.loads(config_path.read_text(encoding="utf-8"))
            config["organization"]["slug"] = "derived-org"
            project = next(iter(config["projects"].values()))
            project["repository"] = "derived-org/derived-app"
            config["runner_pools"][project["ci_pool"]]["allowed_repositories"] = [project["repository"]]
            controller_name, controller = next(iter(config["controllers"].items()))
            for controller in config["controllers"].values():
                controller["engine_ref"] = "2" * 40
                controller["status_reporting"] = {
                    "enabled": True,
                    "config_file": "/etc/ci-fleet/monitoring.env",
                }
                controller["docker_network_policy"] = {
                    "networks_per_runner": 1,
                    "reserve_subnets": 1,
                    "default_address_pools": [{"base": "10.255.255.0/24", "size": 28}],
                }
            config_path.write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")
            evidence = {
                "schema_version": 1,
                "status_reporting_engine_capabilities": {
                    controller_name: {
                        "engine_ref": "2" * 40,
                        "status_reporting_config": True,
                        "required_status_reporting": True,
                        "docker_network_policy_config": True,
                    }
                },
            }
            (derived / "engine-rollout-evidence.json").write_text(
                json.dumps(evidence, indent=2) + "\n",
                encoding="utf-8",
            )
            multi_host_path = derived / "examples" / "multi-host" / "fleet.json"
            multi_host = json.loads(multi_host_path.read_text(encoding="utf-8"))
            for controller in multi_host["controllers"].values():
                controller["engine_ref"] = "2" * 40
            multi_host_path.write_text(json.dumps(multi_host, indent=2) + "\n", encoding="utf-8")
            (derived / "TEMPLATE_RELEASE").write_text("v1.0.0 " + "1" * 40 + "\n", encoding="utf-8")
            git(derived, "init", "-q")
            git(derived, "remote", "add", "origin", "https://github.com/derived-org/derived-config.git")

            result = subprocess.run(
                [sys.executable, str(derived / "scripts" / "test_policy.py")],
                cwd=derived,
                env={
                    **os.environ,
                    "HTTPS_PROXY": "http://127.0.0.1:9",
                    "https_proxy": "http://127.0.0.1:9",
                    "NO_PROXY": "",
                    "no_proxy": "",
                },
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )

        self.assertEqual(result.returncode, 0, result.stderr)

    def test_fictional_unrelated_adopter_update_preserves_config_and_detects_rewrite(self) -> None:
        release_notes = (ROOT / "docs" / "RELEASE.md").read_text(encoding="utf-8")
        for required in ("v1.0.0", "0aed0d7e85e10050028b7d11fb12b84b3619e638", "not published"):
            self.assertIn(required, release_notes)

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            template = root / "template"
            adopter = root / "adopter"
            shutil.copytree(
                ROOT,
                template,
                ignore=shutil.ignore_patterns(".git", "__pycache__", "*.pyc"),
            )
            git(template, "init", "-q")
            configure(template)
            git(template, "add", ".")
            git(template, "commit", "-qm", "template v1.0.0")
            git(template, "tag", "-a", "v1.0.0", "-m", "v1.0.0")
            release_oid = git(template, "rev-parse", "v1.0.0", capture=True)

            adopter.mkdir()
            git(adopter, "init", "-q")
            configure(adopter)
            subprocess.run(
                [
                    str(template / "scripts" / "init.sh"),
                    "--organization", "fictional-org",
                    "--project", "fictional-app",
                    "--engine-ref", "1" * 40,
                    "--output", str(adopter / "fleet.json"),
                ],
                check=True,
                stdout=subprocess.DEVNULL,
            )
            (adopter / "TEMPLATE_RELEASE").write_text(f"v1.0.0 {release_oid}\n", encoding="utf-8")
            staged_evidence = {
                "schema_version": 1,
                "status_reporting_engine_capabilities": {
                    "ci-01": {
                        "engine_ref": "1" * 40,
                        "status_reporting_config": True,
                        "required_status_reporting": False,
                        "docker_network_policy_config": True,
                    }
                },
            }
            (adopter / "engine-rollout-evidence.json").write_text(
                json.dumps(staged_evidence, indent=2) + "\n",
                encoding="utf-8",
            )
            git(adopter, "add", ".")
            git(adopter, "commit", "-qm", "adopter state")

            (template / "release-marker").write_text("v1.1.0\n", encoding="utf-8")
            git(template, "add", "release-marker")
            git(template, "commit", "-qm", "template v1.1.0")
            git(template, "tag", "-a", "v1.1.0", "-m", "v1.1.0")
            git(adopter, "remote", "add", "template", str(template))
            release = fetch_recorded_release(adopter, "v1.1.0")
            self.assertEqual(release.returncode, 0, release.stderr)
            new_oid, release_commit = release.stdout.split()
            adopter_head = git(adopter, "rev-parse", "HEAD", capture=True)
            expected_fleet = (adopter / "fleet.json").read_bytes()
            expected_evidence = (adopter / "engine-rollout-evidence.json").read_bytes()
            merge = subprocess.run(
                ["git", "-C", str(adopter), "merge", "--no-ff", "--no-commit", "--allow-unrelated-histories", release_commit],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            self.assertIn(merge.returncode, (0, 1))
            git(adopter, "restore", f"--source={adopter_head}", "--staged", "--worktree", "--", "fleet.json", "engine-rollout-evidence.json")
            self.assertEqual((adopter / "fleet.json").read_bytes(), expected_fleet)
            self.assertEqual((adopter / "engine-rollout-evidence.json").read_bytes(), expected_evidence)
            git(adopter, "add", ".")
            subprocess.run(
                [str(adopter / "scripts" / "validate.sh"), "--strict"],
                cwd=adopter,
                check=True,
                stdout=subprocess.DEVNULL,
            )
            with (adopter / "TEMPLATE_RELEASE").open("a", encoding="utf-8") as record:
                record.write(f"v1.1.0 {new_oid}\n")
            git(adopter, "add", "TEMPLATE_RELEASE")
            git(adopter, "commit", "-qm", "update to template v1.1.0")

            (template / "rewrite-marker").write_text("rewrite\n", encoding="utf-8")
            git(template, "add", "rewrite-marker")
            git(template, "commit", "-qm", "rewrite target")
            git(template, "tag", "-f", "-a", "v1.1.0", "-m", "rewritten")
            rewrite = fetch_recorded_release(adopter, "v1.1.0")
            self.assertNotEqual(rewrite.returncode, 0)
            self.assertIn("was rewritten upstream; refusing to use it", rewrite.stderr)


if __name__ == "__main__":
    unittest.main()
