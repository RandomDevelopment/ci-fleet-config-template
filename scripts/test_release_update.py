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
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
INITIAL_RELEASE_TAG_OID = "0e54aaa09d0565ce103035f213953639fc068a73"


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
    record_path = repository / "TEMPLATE_RELEASE"
    records = {}
    if record_path.exists():
        records = dict(
            line.split()
            for line in record_path.read_text(encoding="utf-8").splitlines()
        )
    prior_oid = INITIAL_RELEASE_TAG_OID if tag == "v1.0.0" else records.get(tag)
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
    if prior_oid and prior_oid != oid:
        git(repository, "update-ref", "-d", temporary_ref)
        return subprocess.CompletedProcess(fetch.args, 1, "", f"template tag {tag} was rewritten upstream; refusing to use it")
    commit = git(repository, "rev-parse", f"{temporary_ref}^{{commit}}", capture=True)
    git(repository, "update-ref", "-d", temporary_ref)
    return subprocess.CompletedProcess(fetch.args, 0, f"{oid} {commit}", "")


class ReleaseUpdateTests(unittest.TestCase):
    def test_workflow_runs_release_update_fixtures_only_upstream(self) -> None:
        workflow = (ROOT / ".github" / "workflows" / "validate.yml").read_text(encoding="utf-8")
        guarded_invocation = (
            'if [[ "$GITHUB_REPOSITORY" == RandomDevelopment/ci-fleet-config-template ]]; then\n'
            "            python3 scripts/test_release_update.py\n"
            "          fi"
        )
        self.assertIn(guarded_invocation, workflow)
        self.assertEqual(workflow.count("python3 scripts/test_release_update.py"), 1)

    def test_derived_repository_workflow_uses_strict_policy_without_exact_core_identity(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            derived = Path(directory) / "derived"
            shutil.copytree(
                ROOT,
                derived,
                ignore=shutil.ignore_patterns(".git", "__pycache__", "*.pyc"),
            )
            config_path = derived / "fleet.json"
            unchanged = subprocess.run(
                [str(derived / "scripts" / "validate.sh"), "--strict"],
                cwd=derived,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            self.assertNotEqual(unchanged.returncode, 0)
            self.assertTrue(
                "replace the example organization" in unchanged.stderr
                or "reviewed operational Docker pool CIDR" in unchanged.stderr,
                unchanged.stderr,
            )
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

            subprocess.run(
                [str(derived / "scripts" / "validate.sh"), "--strict"],
                cwd=derived,
                check=True,
                stdout=subprocess.DEVNULL,
            )

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
        workflow = (ROOT / ".github" / "workflows" / "validate.yml").read_text(encoding="utf-8")
        self.assertIn('if [[ "$GITHUB_REPOSITORY" != RandomDevelopment/ci-fleet-config-template ]]; then', workflow)
        self.assertIn("args+=(--strict)", workflow)

    def test_legacy_adopter_keeps_new_template_rollout_evidence(self) -> None:
        guide = (ROOT / "docs" / "UPDATING.md").read_text(encoding="utf-8")
        conditional_restore = 'if git cat-file -e "$ADOPTER_HEAD:engine-rollout-evidence.json" 2>/dev/null; then' in guide
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
            git(template, "commit", "-qm", "template release")
            release_commit = git(template, "rev-parse", "HEAD", capture=True)
            expected_evidence = (template / "engine-rollout-evidence.json").read_bytes()

            adopter.mkdir()
            git(adopter, "init", "-q")
            configure(adopter)
            subprocess.run(
                [
                    str(template / "scripts" / "init.sh"),
                    "--organization", "legacy-org",
                    "--project", "legacy-app",
                    "--engine-ref", "1" * 40,
                    "--output", str(adopter / "fleet.json"),
                ],
                check=True,
                stdout=subprocess.DEVNULL,
            )
            git(adopter, "add", "fleet.json")
            git(adopter, "commit", "-qm", "legacy adopter state")
            adopter_head = git(adopter, "rev-parse", "HEAD", capture=True)
            expected_fleet = (adopter / "fleet.json").read_bytes()
            git(adopter, "remote", "add", "template", str(template))
            git(adopter, "fetch", "template", release_commit)

            merge = subprocess.run(
                ["git", "-C", str(adopter), "merge", "--no-ff", "--no-commit", "--allow-unrelated-histories", release_commit],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            self.assertIn(merge.returncode, (0, 1))
            restore_paths = ["fleet.json"]
            if not conditional_restore:
                restore_paths.append("engine-rollout-evidence.json")
            git(adopter, "restore", f"--source={adopter_head}", "--staged", "--worktree", "--", *restore_paths)

            self.assertEqual((adopter / "fleet.json").read_bytes(), expected_fleet)
            self.assertEqual((adopter / "engine-rollout-evidence.json").read_bytes(), expected_evidence)
            git(adopter, "diff", "--cached", "--exit-code", adopter_head, "--", "fleet.json")
            git(adopter, "diff", "--cached", "--exit-code", release_commit, "--", "engine-rollout-evidence.json")
            git(adopter, "add", ".")
            subprocess.run(
                [str(adopter / "scripts" / "validate.sh"), "--strict"],
                cwd=adopter,
                check=True,
                stdout=subprocess.DEVNULL,
            )

    def test_published_release_evidence_preserves_historical_preparation(self) -> None:
        release_notes = (ROOT / "docs" / "RELEASE.md").read_text(encoding="utf-8")
        for required in (
            "0e54aaa09d0565ce103035f213953639fc068a73",
            "cf4a4d143540e0c70e1f301061038bbf95f04398",
            "0aed0d7e85e10050028b7d11fb12b84b3619e638",
            "Never retarget or recreate `v1.0.0`",
        ):
            self.assertIn(required, release_notes)
        for path in ("README.md", "docs/RELEASE.md", "docs/UPDATING.md"):
            document = (ROOT / path).read_text(encoding="utf-8")
            with self.subTest(path=path):
                self.assertIn("releases/tag/v1.0.0", document)
                self.assertIn("was published on September 2, 2026", document)
                self.assertIn("historical preparation state committed before publication", document)
                self.assertIn("released commit unchanged", document)
                self.assertNotIn("prepared but not published", document)
                self.assertNotIn("currently prepared, not published", document)
                self.assertNotIn("no tag or GitHub release", document)
        compatibility = json.loads((ROOT / "template-compatibility.json").read_text(encoding="utf-8"))
        self.assertEqual(
            compatibility["template_release"],
            {"planned_tag": "v1.0.0", "state": "prepared-not-published"},
        )
        guide = (ROOT / "docs" / "UPDATING.md").read_text(encoding="utf-8")
        self.assertIn(
            'if [ "$NEW_TAG" = v1.0.0 ]; then\n'
            f"     PRIOR_TAG_OID={INITIAL_RELEASE_TAG_OID}\n"
            "   fi",
            guide,
        )

    def test_first_import_verifies_published_initial_tag_without_record(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            template = Path(directory) / "template"
            adopter = Path(directory) / "adopter"
            template.mkdir()
            git(template, "init", "-q")
            configure(template)
            git(template, "commit", "--allow-empty", "-qm", "initial release")
            git(template, "tag", "-a", "v1.0.0", "-m", "published initial release")
            published_oid = git(template, "rev-parse", "v1.0.0", capture=True)
            published_commit = git(template, "rev-parse", "v1.0.0^{commit}", capture=True)
            adopter.mkdir()
            git(adopter, "init", "-q")
            git(adopter, "remote", "add", "template", str(template))

            with patch(__name__ + ".INITIAL_RELEASE_TAG_OID", published_oid):
                initial = fetch_recorded_release(adopter, "v1.0.0")
                self.assertEqual(initial.returncode, 0, initial.stderr)
                self.assertEqual(initial.stdout, f"{published_oid} {published_commit}")
                git(template, "tag", "-f", "-a", "v1.0.0", "-m", "rewritten initial release")
                rewritten = fetch_recorded_release(adopter, "v1.0.0")
                self.assertNotEqual(rewritten.returncode, 0)
                self.assertIn("was rewritten upstream; refusing to use it", rewritten.stderr)
            self.assertFalse((adopter / "TEMPLATE_RELEASE").exists())
            temporary_ref = subprocess.run(
                ["git", "-C", str(adopter), "rev-parse", "--verify", "refs/tmp/template-tag-check"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            self.assertNotEqual(temporary_ref.returncode, 0)

    def test_fictional_unrelated_adopter_update_preserves_config_and_detects_rewrite(self) -> None:
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
            next_evidence = json.loads(json.dumps(staged_evidence))
            next_evidence["status_reporting_engine_capabilities"]["ci-01"]["engine_ref"] = "2" * 40
            (adopter / "next-engine-rollout-evidence.json").write_text(
                json.dumps(next_evidence, indent=2) + "\n",
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
            expected_next_evidence = (adopter / "next-engine-rollout-evidence.json").read_bytes()
            merge = subprocess.run(
                ["git", "-C", str(adopter), "merge", "--no-ff", "--no-commit", "--allow-unrelated-histories", release_commit],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            self.assertIn(merge.returncode, (0, 1))
            git(
                adopter,
                "restore",
                f"--source={adopter_head}",
                "--staged",
                "--worktree",
                "--",
                "fleet.json",
                "engine-rollout-evidence.json",
                "next-engine-rollout-evidence.json",
            )
            self.assertEqual((adopter / "fleet.json").read_bytes(), expected_fleet)
            self.assertEqual((adopter / "engine-rollout-evidence.json").read_bytes(), expected_evidence)
            self.assertEqual(
                (adopter / "next-engine-rollout-evidence.json").read_bytes(),
                expected_next_evidence,
            )
            git(
                adopter,
                "diff",
                "--cached",
                "--exit-code",
                adopter_head,
                "--",
                "fleet.json",
                "engine-rollout-evidence.json",
                "next-engine-rollout-evidence.json",
            )
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

            git(template, "tag", "-f", "-a", "v1.1.0", "-m", "rewritten message")
            same_commit_rewrite = fetch_recorded_release(adopter, "v1.1.0")
            self.assertNotEqual(same_commit_rewrite.returncode, 0)
            self.assertIn("was rewritten upstream; refusing to use it", same_commit_rewrite.stderr)
            self.assertEqual(git(template, "rev-parse", "v1.1.0^{commit}", capture=True), release_commit)

            (template / "rewrite-marker").write_text("rewrite\n", encoding="utf-8")
            git(template, "add", "rewrite-marker")
            git(template, "commit", "-qm", "rewrite target")
            git(template, "tag", "-f", "-a", "v1.1.0", "-m", "rewritten")
            rewrite = fetch_recorded_release(adopter, "v1.1.0")
            self.assertNotEqual(rewrite.returncode, 0)
            self.assertIn("was rewritten upstream; refusing to use it", rewrite.stderr)


if __name__ == "__main__":
    unittest.main()
