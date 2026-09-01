#!/usr/bin/env python3
"""Exercise the documented immutable release update in a fictional adopter."""

from __future__ import annotations

import json
import shutil
import subprocess
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


class ReleaseUpdateTests(unittest.TestCase):
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
            git(template, "commit", "-qm", "template release")
            git(template, "tag", "-a", "v1.0.0", "-m", "v1.0.0")
            release_oid = git(template, "rev-parse", "v1.0.0", capture=True)
            release_commit = git(template, "rev-parse", "v1.0.0^{commit}", capture=True)

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
            fleet = json.loads((adopter / "fleet.json").read_text(encoding="utf-8"))
            next(iter(fleet["controllers"].values()))["docker_network_policy"]["default_address_pools"][0]["base"] = "198.18.0.0/24"
            (adopter / "fleet.json").write_text(json.dumps(fleet, indent=2) + "\n", encoding="utf-8")
            (adopter / "TEMPLATE_RELEASE").write_text(f"v1.0.0 {release_oid}\n", encoding="utf-8")
            git(adopter, "add", ".")
            git(adopter, "commit", "-qm", "adopter state")
            adopter_head = git(adopter, "rev-parse", "HEAD", capture=True)
            expected_fleet = (adopter / "fleet.json").read_bytes()

            git(adopter, "remote", "add", "template", str(template))
            git(adopter, "fetch", "--no-tags", "template", release_commit)
            merge = subprocess.run(
                ["git", "-C", str(adopter), "merge", "--no-ff", "--no-commit", "--allow-unrelated-histories", "FETCH_HEAD"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            self.assertIn(merge.returncode, (0, 1))
            git(adopter, "restore", f"--source={adopter_head}", "--staged", "--worktree", "--", "fleet.json")
            self.assertEqual((adopter / "fleet.json").read_bytes(), expected_fleet)
            subprocess.run(
                [str(adopter / "scripts" / "validate.sh"), "--strict"],
                cwd=adopter,
                check=True,
                stdout=subprocess.DEVNULL,
            )

            (template / "rewrite-marker").write_text("rewrite\n", encoding="utf-8")
            git(template, "add", "rewrite-marker")
            git(template, "commit", "-qm", "rewrite target")
            git(template, "tag", "-f", "-a", "v1.0.0", "-m", "rewritten")
            rewritten_oid = git(template, "rev-parse", "v1.0.0", capture=True)
            self.assertNotEqual(rewritten_oid, release_oid)


if __name__ == "__main__":
    unittest.main()
