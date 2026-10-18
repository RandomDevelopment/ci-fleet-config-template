#!/usr/bin/env python3
"""Focused updater tests using fictional releases and unrelated adopters."""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
import textwrap
import unittest
from pathlib import Path
from unittest.mock import patch

import update_template as updater

ROOT = Path(__file__).resolve().parents[1]


class WorkflowTests(unittest.TestCase):
    def test_absent_token_skips_and_configured_token_runs_updater(self) -> None:
        workflow = (ROOT / ".github/workflows/template-update.yml").read_text()
        opt_in = workflow.split("      - name: Check updater opt-in\n", 1)[1].split("      - name: ", 1)[0]
        admission = textwrap.dedent(opt_in.split("        run: |\n", 1)[1])
        checkout = workflow.split("      - name: Check out the adopter's default branch\n", 1)[1].split("      - name: ", 1)[0]
        proposal = workflow.split("      - name: Propose a template release update\n", 1)[1]
        for step in (checkout, proposal):
            self.assertIn("if: steps.opt-in.outputs.enabled == 'true'", step)
        script = textwrap.dedent(proposal.split("        run: |\n", 1)[1])
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            marker = root / "calls"
            for name in ("gh", "git", "python3"):
                stub = root / name
                stub.write_text(f"#!/bin/sh\nprintf '%s\\n' {name} >> '{marker}'\n")
                stub.chmod(0o755)
            for token, expected in (("", []), ("configured", ["gh", "git", "git", "python3"])):
                with self.subTest(configured=bool(token)):
                    marker.unlink(missing_ok=True)
                    output = root / "outputs"
                    output.unlink(missing_ok=True)
                    env = {**os.environ, "GH_TOKEN": token, "PATH": f"{root}:{os.environ['PATH']}", "GITHUB_OUTPUT": str(output)}
                    result = subprocess.run(["bash", "-e", "-c", admission], env=env, capture_output=True, text=True)
                    self.assertEqual(result.returncode, 0, result.stderr)
                    self.assertEqual(output.read_text(), "enabled=" + ("true" if token else "false") + "\n")
                    self.assertFalse(marker.exists(), "opt-in check invoked a checkout or updater tool")
                    if token:
                        result = subprocess.run(["bash", "-e", "-c", script], env=env, capture_output=True, text=True)
                        self.assertEqual(result.returncode, 0, result.stderr)
                    calls = marker.read_text().splitlines() if marker.exists() else []
                    self.assertEqual(calls, expected)
                    if not token:
                        self.assertIn("Template updates are disabled", result.stdout)


class UpdaterTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.directory = Path(self.temporary.name)
        self.template = self.directory / "template"
        self.adopter = self.directory / "adopter"
        self.original_cwd = Path.cwd()
        self.addCleanup(os.chdir, self.original_cwd)
        for repository in (self.template, self.adopter):
            repository.mkdir()
            os.chdir(repository)
            updater.git("init", "-q", "-b", "main")
            updater.git("config", "user.name", "Updater test")
            updater.git("config", "user.email", "updater@example.invalid")
        self.compatibility = json.loads((ROOT / "template-compatibility.json").read_text())
        self.write(self.template, "template-compatibility.json", self.compatibility)
        self.write(self.template, "fleet.json", {
            "schema_version": 3,
            "organization": {"slug": "fictional-template"},
            "controllers": {"ci": {"engine_ref": "2" * 40}},
            "environments": {"production": {"automatic": False, "requires_approval": True,
                                            "required_secret_names": ["DEPLOY_AUTH"]}},
        })
        self.write(self.template, "engine-rollout-evidence.json", {"template": True})
        self.write(self.template, "validator.txt", "original\n")
        self.write(self.template, "delivery/policy.json", {"automatic": False})
        self.baseline = self.release("v1.2.0")
        for path in self.template.rglob("*"):
            if path.is_file() and ".git" not in path.parts:
                relative = path.relative_to(self.template)
                self.write(self.adopter, str(relative), path.read_text())
        fleet = json.loads((self.adopter / "fleet.json").read_text())
        fleet["organization"]["slug"] = "fictional-adopter"
        next(iter(fleet["controllers"].values()))["engine_ref"] = "1" * 40
        fleet["environments"]["production"]["required_secret_names"] = ["CUSTOM_DEPLOY_AUTH"]
        self.write(self.adopter, "fleet.json", fleet)
        self.write(self.adopter, "engine-rollout-evidence.json", {"adopter": "active"})
        self.write(self.adopter, "next-engine-rollout-evidence.json", {"adopter": "next"})
        self.write(self.adopter, "delivery/policy.json", {"automatic": False, "owner": "adopter"})
        self.write(self.adopter, updater.SETTINGS, {"preserve": ["delivery"]})
        self.write(self.adopter, "TEMPLATE_RELEASE", f"v1.2.0 {self.baseline['oid']}\n")
        self.write(self.adopter, "adopter-only.txt", "keep me\n")
        os.chdir(self.adopter)
        updater.git("add", ".")
        updater.git("commit", "-qm", "unrelated adopter")
        self.head = updater.git("rev-parse", "HEAD")

    def write(self, root: Path, name: str, value) -> None:
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(value if isinstance(value, str) else json.dumps(value) + "\n")

    def release(self, tag: str) -> dict:
        os.chdir(self.template)
        updater.git("add", ".")
        updater.git("commit", "--allow-empty", "-qm", tag)
        updater.git("tag", "-a", tag, "-m", tag)
        commit = updater.git("rev-parse", "HEAD")
        oid = updater.git("rev-parse", tag)
        os.chdir(self.adopter)
        updater.git("fetch", "--no-tags", str(self.template), f"refs/tags/{tag}")
        return {"tag": tag, "commit": commit, "oid": oid,
                "core": self.compatibility["reviewed_core"]["commit"],
                "compatibility": json.loads(json.dumps(self.compatibility))}

    def metadata(self, release: dict) -> dict:
        metadata = {"tag_name": release["tag"], "draft": False, "prerelease": False,
                "published_at": "2026-10-11T00:00:00Z", "body":
                f"- Annotated tag object ID: `{release['oid']}`\n"
                f"- Template commit: `{release['commit']}`\n"
                f"- Reviewed ci-fleet commit: `{release['core']}`\n"}
        boundary = release["compatibility"]["deployment_policy_boundary"]
        if boundary["version"] >= 2:
            deployer_core = boundary["standalone_deployer"]["reviewed_core"]["commit"]
            metadata["body"] += f"- Reviewed deployer ci-fleet commit: `{deployer_core}`\n"
        return metadata

    def test_update_preserves_fleet_policy_evidence_and_extra_files_without_ancestry(self) -> None:
        self.write(self.template, "validator.txt", "updated\n")
        self.write(self.template, "fleet.json", {"schema_version": 3, "controllers": {"template": {}}})
        (self.template / "engine-rollout-evidence.json").unlink()
        self.write(self.template, "next-engine-rollout-evidence.json", {"template": "replace"})
        self.write(self.template, "delivery/policy.json", {"automatic": True})
        self.write(self.template, "new-script.txt", "new\n")
        sentinel = self.directory / "imported-code-ran"
        self.write(self.template, "scripts/validate.sh", f"#!/bin/sh\ntouch '{sentinel}'\n")
        target = self.release("v1.3.0")
        proposed, reasons = updater.prepare_tree(self.head, self.baseline, target)
        self.assertEqual(reasons, [])
        for path in updater.PRESERVED | {"delivery/policy.json", "adopter-only.txt"}:
            self.assertEqual(updater.read_file(proposed, path), updater.read_file(self.head, path), path)
        self.assertEqual(updater.read_file(proposed, "validator.txt"), "updated")
        self.assertEqual(updater.read_file(proposed, "new-script.txt"), "new")
        self.assertEqual(updater.records(updater.read_file(proposed, "TEMPLATE_RELEASE")),
                         {"v1.2.0": self.baseline["oid"], "v1.3.0": target["oid"]})
        self.assertEqual(updater.git("status", "--porcelain"), "")
        self.assertEqual((self.adopter / "validator.txt").read_text(), "original\n")
        self.assertFalse(sentinel.exists())

    def test_managed_image_contract_change_requires_manual_migration_with_schema_v3(self) -> None:
        self.compatibility["template_contract"].pop("managed_images")
        self.write(self.template, "template-compatibility.json", self.compatibility)
        baseline = self.release("v1.3.0")
        self.compatibility["template_contract"]["managed_images"] = "required-for-fresh-strict-configurations"
        self.write(self.template, "template-compatibility.json", self.compatibility)
        self.write(self.template, "validator.txt", "must not import a partial migration\n")
        target = self.release("v1.4.0")
        proposed, reasons = updater.prepare_tree(self.head, baseline, target)
        self.assertTrue(any("Managed-image policy changed" in reason for reason in reasons), reasons)
        self.assertEqual(updater.read_file(proposed, "validator.txt"), "original")
        self.assertEqual(updater.read_file(proposed, "fleet.json"), updater.read_file(self.head, "fleet.json"))
        self.assertEqual(updater.read_file(proposed, "TEMPLATE_RELEASE"), updater.read_file(self.head, "TEMPLATE_RELEASE"))

    def test_three_way_merge_keeps_nonconflicting_local_edits_and_template_deletions(self) -> None:
        self.write(self.template, "shared.txt", "first\nmiddle\nlast\n")
        self.write(self.template, "removed.txt", "remove in next release\n")
        baseline = self.release("v1.3.0")
        self.write(self.adopter, "shared.txt", "local\nmiddle\nlast\n")
        self.write(self.adopter, "removed.txt", "remove in next release\n")
        self.write(self.adopter, "TEMPLATE_RELEASE", f"v1.2.0 {self.baseline['oid']}\nv1.3.0 {baseline['oid']}\n")
        updater.git("add", ".")
        updater.git("commit", "-qm", "local changes")
        head = updater.git("rev-parse", "HEAD")
        self.write(self.template, "shared.txt", "first\nmiddle\nupstream\n")
        (self.template / "removed.txt").unlink()
        target = self.release("v1.4.0")
        proposed, reasons = updater.prepare_tree(head, baseline, target)
        self.assertFalse(reasons)
        self.assertEqual(updater.read_file(proposed, "shared.txt"), "local\nmiddle\nupstream")
        self.assertNotIn("removed.txt", updater.tree(proposed))

    def test_absent_owned_evidence_stays_absent(self) -> None:
        (self.adopter / "next-engine-rollout-evidence.json").unlink()
        updater.git("add", ".")
        updater.git("commit", "-qm", "no staged evidence")
        head = updater.git("rev-parse", "HEAD")
        self.write(self.template, "next-engine-rollout-evidence.json", {"template": True})
        target = self.release("v1.3.0")
        proposed, reasons = updater.prepare_tree(head, self.baseline, target)
        self.assertFalse(reasons)
        self.assertNotIn("next-engine-rollout-evidence.json", updater.tree(proposed))

    def test_conflict_creates_only_manual_report_without_partial_update(self) -> None:
        self.write(self.adopter, "validator.txt", "adopter override\n")
        updater.git("add", ".")
        updater.git("commit", "-qm", "custom validator")
        head = updater.git("rev-parse", "HEAD")
        self.write(self.template, "validator.txt", "upstream change\n")
        self.write(self.template, "new-script.txt", "must not import\n")
        target = self.release("v1.3.0")
        proposed, reasons = updater.prepare_tree(head, self.baseline, target)
        self.assertEqual(reasons, ["Merge conflict in validator.txt"])
        self.assertEqual(updater.tree(proposed).keys() - updater.tree(head).keys(), {updater.STATUS})
        for path, entry in updater.tree(head).items():
            self.assertEqual(updater.tree(proposed)[path], entry)

    def test_schema_and_policy_changes_require_manual_handling(self) -> None:
        target = self.release("v1.3.0")
        for change in ("schema", "policy"):
            with self.subTest(change=change):
                compatibility = json.loads(json.dumps(self.compatibility))
                if change == "schema":
                    compatibility["template_contract"]["fleet_schema_version"] = 4
                else:
                    compatibility["deployment_policy_boundary"]["version"] += 1
                proposed, reasons = updater.prepare_tree(self.head, self.baseline,
                                                        {**target, "compatibility": compatibility})
                self.assertEqual(len(reasons), 1)
                self.assertEqual(updater.read_file(proposed, "TEMPLATE_RELEASE"),
                                 updater.read_file(self.head, "TEMPLATE_RELEASE"))
                self.assertIn("manual_handling", json.loads(updater.read_file(proposed, updater.STATUS)))

    def test_v1_to_v2_and_deployer_pin_changes_import_only_manual_report(self) -> None:
        target = self.release("v1.3.0")
        for change in ("v1-to-v2", "deployer-pin"):
            with self.subTest(change=change):
                baseline = json.loads(json.dumps(self.baseline))
                candidate = json.loads(json.dumps(target))
                if change == "v1-to-v2":
                    baseline["compatibility"]["deployment_policy_boundary"] = {
                        "version": 1, "status": "logical-inventory-only",
                        "supported_executable_roles": ["ordinary-ci"], "approval_validation": False,
                    }
                else:
                    candidate["compatibility"]["deployment_policy_boundary"]["standalone_deployer"]["reviewed_core"]["commit"] = "f" * 40
                proposed, reasons = updater.prepare_tree(self.head, baseline, candidate)
                self.assertEqual(reasons, ["Deployment policy compatibility changed; review the new boundary manually."])
                self.assertEqual(updater.tree(proposed).keys() - updater.tree(self.head).keys(), {updater.STATUS})
                for path, entry in updater.tree(self.head).items():
                    self.assertEqual(updater.tree(proposed)[path], entry, path)

    def test_tag_verification_detects_message_rewrite_and_wrong_identities(self) -> None:
        target = self.release("v1.3.0")
        metadata = self.metadata(target)
        with patch.object(updater, "SOURCE", str(self.template)):
            self.assertEqual(updater.verify_release(metadata, target["oid"])["commit"], target["commit"])
            for key in ("oid", "commit", "core"):
                with self.subTest(key=key), self.assertRaises(ValueError):
                    updater.verify_release(self.metadata({**target, key: "f" * 40}), target["oid"])
            os.chdir(self.template)
            updater.git("tag", "-f", "-a", target["tag"], "-m", "rewritten message")
            changed_oid = updater.git("rev-parse", target["tag"])
            os.chdir(self.adopter)
            with self.assertRaisesRegex(ValueError, "tag object"):
                updater.verify_release(metadata, target["oid"])
            with self.assertRaisesRegex(ValueError, "rewritten"):
                updater.verify_release(self.metadata({**target, "oid": changed_oid}), target["oid"])
        self.assertEqual(updater.git("for-each-ref", "refs/template-updater/"), "")

    def test_lightweight_unpublished_and_ambiguous_release_notes_are_rejected(self) -> None:
        target = self.release("v1.3.0")
        with patch.object(updater, "SOURCE", str(self.template)):
            for field in ("draft", "prerelease"):
                with self.subTest(field=field), self.assertRaises(ValueError):
                    updater.verify_release({**self.metadata(target), field: True})
            duplicate = self.metadata(target)
            duplicate["body"] += f"- Template commit: `{target['commit']}`\n"
            with self.assertRaises(ValueError):
                updater.verify_release(duplicate)
            os.chdir(self.template)
            updater.git("tag", "-f", target["tag"], target["commit"])
            os.chdir(self.adopter)
            with self.assertRaisesRegex(ValueError, "annotated tag"):
                updater.verify_release(self.metadata({**target, "oid": target["commit"]}))

    def test_v2_release_requires_exact_deployer_identity_and_v1_still_verifies(self) -> None:
        target = self.release("v1.3.0")
        metadata = self.metadata(target)
        line = metadata["body"].splitlines(keepends=True)[-1]
        deployer_core = self.compatibility["deployment_policy_boundary"]["standalone_deployer"]["reviewed_core"]["commit"]
        with patch.object(updater, "SOURCE", str(self.template)):
            verified = updater.verify_release(metadata)
            self.assertEqual(verified["deployer_core"], deployer_core)
            for body in (
                metadata["body"].replace(line, ""),
                metadata["body"] + line,
                metadata["body"] + line.replace(deployer_core, "main"),
                metadata["body"].replace(line, line.replace(deployer_core, "f" * 40)),
                metadata["body"].replace(line, line.replace(deployer_core, "main")),
            ):
                with self.subTest(body=body), self.assertRaisesRegex(ValueError, "deployer"):
                    updater.verify_release({**metadata, "body": body})
            compatibility = json.loads(json.dumps(self.compatibility))
            compatibility["deployment_policy_boundary"] = {
                "version": 1, "status": "logical-inventory-only", "approval_validation": False,
            }
            self.write(self.template, "template-compatibility.json", compatibility)
            legacy = self.release("v1.4.0")
            legacy["compatibility"] = compatibility
            self.assertNotIn("deployer_core", updater.verify_release(self.metadata(legacy)))

    def test_review_gate_fails_closed(self) -> None:
        protection = {"required_pull_request_reviews": {"required_approving_review_count": 1,
                       "dismiss_stale_reviews": True}, "enforce_admins": {"enabled": True},
                      "required_status_checks": {"strict": True, "checks": [{"context": "validate"}]}}
        with patch.object(updater, "api", return_value=protection):
            updater.require_review("fictional/config", "main")
        for key in protection:
            with self.subTest(key=key), patch.object(updater, "api", return_value={
                    k: v for k, v in protection.items() if k != key}), self.assertRaises(ValueError):
                updater.require_review("fictional/config", "main")
        protection["required_pull_request_reviews"]["bypass_pull_request_allowances"] = {"apps": ["bot"]}
        with patch.object(updater, "api", return_value=protection), self.assertRaises(ValueError):
            updater.require_review("fictional/config", "main")

    def test_weekly_refresh_uses_one_pr_latest_stable_and_checks_pending_identity(self) -> None:
        remote = self.directory / "origin.git"
        subprocess.run(["git", "init", "--bare", "-q", str(remote)], check=True)
        updater.git("remote", "add", "origin", str(remote))
        updater.git("push", "-q", "origin", "HEAD:main")
        self.write(self.template, "validator.txt", "updated\n")
        target = self.release("v1.3.0")
        releases = [self.metadata(self.baseline), self.metadata(target),
                    {**self.metadata(target), "tag_name": "v9.0.0", "prerelease": True}]
        calls = []
        real_run = updater.run
        pr = None

        def fake_run(*args, **kwargs):
            if args[0] != "gh":
                return real_run(*args, **kwargs)
            calls.append(args)
            if args[1:3] == ("api", f"repos/{updater.UPSTREAM}/releases?per_page=100"):
                return json.dumps([releases]).encode()
            if args[1:3] == ("pr", "list"):
                return json.dumps([pr] if pr else []).encode()
            return b"https://github.com/fictional/config/pull/1\n"

        with patch.object(updater, "run", side_effect=fake_run), patch.object(updater, "api", return_value={
                "default_branch": "main"}), patch.object(updater, "require_review"), patch.object(
                updater, "SOURCE", str(self.template)), patch.dict(os.environ, {"GITHUB_REPOSITORY": "fictional/config"}):
            updater.main()
            first = updater.git("ls-remote", "--heads", "origin", f"refs/heads/{updater.BRANCH}").split()[0]
            pr = {"number": 1, "isDraft": False, "isCrossRepository": False}
            updater.main()
            second = updater.git("ls-remote", "--heads", "origin", f"refs/heads/{updater.BRANCH}").split()[0]
            self.assertEqual(first, second)
            self.assertEqual(sum(call[1:3] == ("pr", "create") for call in calls), 1)
            self.assertEqual(sum(call[1:3] == ("pr", "edit") for call in calls), 1)
            original_oid = target["oid"]
            target["oid"] = "f" * 40
            releases[1] = self.metadata(target)
            with self.assertRaisesRegex(ValueError, "rewritten"):
                updater.main()
            target["oid"] = original_oid
            releases[1] = self.metadata(target)
            # Once merged, a weekly run must not create another PR for the same release.
            updater.git("push", "origin", f"{first}:refs/heads/main")
            pr = None
            updater.main()
            self.assertEqual(sum(call[1:3] in (("pr", "create"), ("pr", "edit")) for call in calls), 2)

    def test_manual_pr_is_draft_and_existing_pr_is_converted_to_draft(self) -> None:
        target = self.release("v1.3.0")
        with patch.object(updater, "run", return_value=b"PR") as command, patch.object(
                updater, "git", return_value="commit"):
            updater.publish("fictional/config", "main", self.head, None, "tree", target, ["conflict"], None)
            self.assertIn("--draft", command.call_args.args)
            updater.publish("fictional/config", "main", self.head, None, "tree", target, ["conflict"],
                            {"number": 1, "isDraft": False})
            self.assertTrue(any(call.args[1:3] == ("pr", "ready") and "--undo" in call.args
                                for call in command.call_args_list))

    def test_invalid_records_and_preserve_paths_fail_closed(self) -> None:
        for raw in ("", "v1.0.0 " + "f" * 40, "v1.2.0 bad", "v1.2.0 " + "f" * 40 + "\nv1.1.0 " + "f" * 40):
            with self.subTest(raw=raw), self.assertRaises(ValueError):
                updater.records(raw)
        for path in ("/tmp/file", "../fleet.json", ".git/config", "delivery/", 1):
            self.write(self.adopter, updater.SETTINGS, {"preserve": [path]})
            updater.git("add", ".")
            updater.git("commit", "-qm", "invalid settings")
            with self.subTest(path=path), self.assertRaises(ValueError):
                updater.preserved_paths(updater.git("rev-parse", "HEAD"))


if __name__ == "__main__":
    unittest.main()
