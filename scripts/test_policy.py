#!/usr/bin/env python3
"""Regression tests for ci-fleet's non-negotiable configuration policies."""

from __future__ import annotations

import copy
import json
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from validate import Validation, load_json, scan_secret_material, scan_tree_path_list, validate_config


ROOT = Path(__file__).resolve().parents[1]


def reference_config() -> dict:
    return json.loads((ROOT / "fleet.json").read_text(encoding="utf-8"))


def contract_schema() -> dict:
    return json.loads((ROOT / "fleet.schema.json").read_text(encoding="utf-8"))


def schema_accepts_engine_ref(value: str) -> bool:
    pattern = contract_schema()["$defs"]["controller"]["properties"]["engine_ref"]["pattern"]
    return re.fullmatch(pattern, value) is not None


def schema_accepts_delivery_engine(value: str) -> bool:
    contract = contract_schema()["properties"]["organization"]["properties"]["delivery_engine"]
    return contract.get("const") == value


def errors_for(config: dict, *, strict: bool = False) -> list[str]:
    validation = Validation()
    scan_secret_material(config, validation)
    validate_config(config, validation, strict)
    return validation.errors


def first_project(config: dict) -> dict:
    return next(iter(config["projects"].values()))


def first_controller(config: dict) -> dict:
    return next(iter(config["controllers"].values()))


# Vendored schema-v3 fixture (pre-change e483998:fleet.json). Pinned as a
# string so the regression test cannot depend on upstream repository history;
# adopter repos created via "Use this template" have no e483998 ancestry
# (Codex finding, PR #14 round 7: vendor the legacy fixture instead of reading
# repository history).
LEGACY_V3_FLEET_JSON = """{
  "$schema": "./fleet.schema.json",
  "schema_version": 3,
  "organization": {
    "slug": "example-org",
    "registry": "ghcr.io/example-org",
    "delivery_engine": "RandomDevelopment/ci-fleet",
    "workflow_ref_policy": "immutable-commit"
  },
  "runner_pools": {
    "trusted-ci": {
      "runner_group": "example-trusted-ci",
      "routing_labels": ["docker-ci"],
      "allowed_repositories": ["example-org/example-app"],
      "public_repositories": false,
      "capacity_budget": 1,
      "job_submission_policy": "all-independent-jobs"
    }
  },
  "controllers": {
    "example-ci-01": {
      "pool": "trusted-ci",
      "location": "example-site-a",
      "state": "active",
      "scale_set_name": "example-ci-01",
      "lifecycle": "experimental",
      "engine_ref": "8df97cc7575f47696fa82a179bbe39cd2874b1ca",
      "min_runners": 0,
      "max_runners": 1,
      "runner_resources": {
        "cpu_cores": 2,
        "memory_mib": 4096
      }
    }
  },
  "host_groups": {
    "development-apps": {
      "role": "deployment",
      "environment_class": "development"
    },
    "production-apps": {
      "role": "deployment",
      "environment_class": "production"
    }
  },
  "environments": {
    "development": {
      "host_group": "development-apps",
      "automatic": true,
      "requires_approval": false,
      "required_secret_names": ["DEPLOY_AUTH"]
    },
    "production": {
      "host_group": "production-apps",
      "automatic": false,
      "requires_approval": true,
      "required_secret_names": ["DEPLOY_AUTH"]
    }
  },
  "projects": {
    "example-app": {
      "repository": "example-org/example-app",
      "image": "ghcr.io/example-org/example-app",
      "ci_pool": "trusted-ci",
      "ci_contract": {
        "runner_entrypoint": "./scripts/ci/run.sh",
        "task_plan": "./scripts/ci/plan.json",
        "aggregate_entrypoints": {
          "fast": "./scripts/ci/run.sh fast",
          "full": "./scripts/ci/run.sh full"
        },
        "target_wall_clock_minutes": 5,
        "max_job_minutes": 5,
        "shard_target_minutes": 4
      },
      "deployments": ["development", "production"]
    }
  }
}"""


class PolicyTests(unittest.TestCase):
    def assert_rejected(self, config: dict, expected: str, *, strict: bool = False) -> None:
        errors = errors_for(config, strict=strict)
        self.assertTrue(any(expected in error for error in errors), errors)

    def assert_engine_ref_contract(self, value: str, accepted: bool) -> None:
        config = copy.deepcopy(reference_config())
        first_controller(config)["engine_ref"] = value
        self.assertEqual(schema_accepts_engine_ref(value), accepted)
        self.assertEqual(errors_for(config) == [], accepted)

    def assert_delivery_engine_contract(self, value: str, accepted: bool) -> None:
        config = copy.deepcopy(reference_config())
        config["organization"]["delivery_engine"] = value
        self.assertEqual(schema_accepts_delivery_engine(value), accepted)
        self.assertEqual(errors_for(config) == [], accepted)

    def test_reference_configuration_is_valid(self) -> None:
        self.assertEqual(errors_for(reference_config()), [])

    def test_multi_host_multi_location_configuration_is_valid(self) -> None:
        config = json.loads((ROOT / "examples" / "multi-host" / "fleet.json").read_text(encoding="utf-8"))
        self.assertEqual(errors_for(config), [])

    def test_schema_version_two_is_rejected(self) -> None:
        config = copy.deepcopy(reference_config())
        config["schema_version"] = 2
        self.assert_rejected(config, "must equal 3")

    def test_public_repository_access_is_rejected(self) -> None:
        config = copy.deepcopy(reference_config())
        config["runner_pools"]["trusted-ci"]["public_repositories"] = True
        self.assert_rejected(config, "trusted private repositories")

    def test_duplicate_runner_group_is_rejected(self) -> None:
        config = copy.deepcopy(reference_config())
        duplicate = copy.deepcopy(config["runner_pools"]["trusted-ci"])
        duplicate["routing_labels"] = ["other-ci"]
        config["runner_pools"]["other-ci"] = duplicate
        self.assert_rejected(config, "runner_group: must be unique")

    def test_capacity_overcommit_is_rejected(self) -> None:
        config = copy.deepcopy(reference_config())
        overcommit = config["runner_pools"]["trusted-ci"]["capacity_budget"] + 1
        first_controller(config)["max_runners"] = overcommit
        self.assert_rejected(config, f"must cover {overcommit} runners")

    def test_drained_capacity_remains_reserved(self) -> None:
        config = copy.deepcopy(reference_config())
        overcommit = config["runner_pools"]["trusted-ci"]["capacity_budget"] + 1
        first_controller(config)["state"] = "drained"
        first_controller(config)["max_runners"] = overcommit
        self.assert_rejected(config, f"must cover {overcommit} runners")

    def test_disabled_capacity_is_not_reserved(self) -> None:
        config = copy.deepcopy(reference_config())
        first_controller(config)["state"] = "disabled"
        first_controller(config)["max_runners"] = 100
        self.assertEqual(errors_for(config), [])

    def test_duplicate_scale_set_is_rejected(self) -> None:
        config = copy.deepcopy(reference_config())
        duplicate = copy.deepcopy(first_controller(config))
        duplicate["location"] = "example-site-b"
        config["controllers"]["example-ci-02"] = duplicate
        config["runner_pools"]["trusted-ci"]["capacity_budget"] = 2
        self.assert_rejected(config, "scale_set_name: must be unique")

    def test_scale_set_must_include_controller_id(self) -> None:
        config = copy.deepcopy(reference_config())
        first_controller(config)["scale_set_name"] = "other-scale"
        self.assert_rejected(config, "must include the controller ID")

    def test_routing_label_must_not_equal_scale_set(self) -> None:
        config = copy.deepcopy(reference_config())
        config["runner_pools"]["trusted-ci"]["routing_labels"] = [first_controller(config)["scale_set_name"]]
        self.assert_rejected(config, "must not equal a controller scale-set name")

    def test_controller_pool_must_exist(self) -> None:
        config = copy.deepcopy(reference_config())
        first_controller(config)["pool"] = "missing"
        self.assert_rejected(config, "must reference a declared runner pool")

    def test_controller_pool_must_be_a_string(self) -> None:
        config = copy.deepcopy(reference_config())
        first_controller(config)["pool"] = ["trusted-ci"]
        self.assert_rejected(config, "must reference a declared runner pool")

    def test_delivery_engine_repository_is_fixed_in_schema_and_semantics(self) -> None:
        self.assert_delivery_engine_contract("RandomDevelopment/ci-fleet", True)

    def test_delivery_engine_rejects_another_repository(self) -> None:
        self.assert_delivery_engine_contract("attacker/engine", False)

    def test_delivery_engine_rejects_url_form(self) -> None:
        self.assert_delivery_engine_contract("https://github.com/RandomDevelopment/ci-fleet", False)

    def test_delivery_engine_rejects_credential_form(self) -> None:
        self.assert_delivery_engine_contract("user:password@RandomDevelopment/ci-fleet", False)

    def test_controller_address_is_rejected(self) -> None:
        config = copy.deepcopy(reference_config())
        first_controller(config)["ip_address"] = "192.0.2.10"
        self.assert_rejected(config, "host-local infrastructure details are forbidden")

    def test_full_lowercase_engine_ref_passes_schema_and_semantics(self) -> None:
        self.assert_engine_ref_contract("1" * 40, True)

    def test_uppercase_engine_ref_fails_schema_and_semantics(self) -> None:
        self.assert_engine_ref_contract("A" * 40, False)

    def test_short_engine_ref_fails_schema_and_semantics(self) -> None:
        self.assert_engine_ref_contract("1" * 39, False)

    def test_malformed_engine_ref_fails_schema_and_semantics(self) -> None:
        self.assert_engine_ref_contract("g" * 40, False)

    def test_zero_engine_ref_fails_schema_and_semantics(self) -> None:
        self.assert_engine_ref_contract("0" * 40, False)

    def test_active_controller_minimum_must_be_zero(self) -> None:
        config = copy.deepcopy(reference_config())
        first_controller(config)["min_runners"] = 1
        self.assert_rejected(config, "managed prewarmed runners are not supported")

    def test_drained_controller_minimum_must_be_zero(self) -> None:
        config = copy.deepcopy(reference_config())
        first_controller(config)["state"] = "drained"
        first_controller(config)["min_runners"] = 1
        self.assert_rejected(config, "managed prewarmed runners are not supported")

    def test_application_capacity_control_is_rejected(self) -> None:
        config = copy.deepcopy(reference_config())
        first_project(config)["ci_contract"]["max_parallel"] = 1
        self.assert_rejected(config, "unknown keys: max_parallel")

    def test_pool_must_submit_all_independent_jobs(self) -> None:
        config = copy.deepcopy(reference_config())
        config["runner_pools"]["trusted-ci"]["job_submission_policy"] = "max-parallel"
        self.assert_rejected(config, "leave capacity control to infrastructure")

    def test_automatic_production_is_rejected(self) -> None:
        config = copy.deepcopy(reference_config())
        config["environments"]["production"]["automatic"] = True
        self.assert_rejected(config, "production deployment must not be automatic")

    def test_unapproved_production_is_rejected(self) -> None:
        config = copy.deepcopy(reference_config())
        config["environments"]["production"]["requires_approval"] = False
        self.assert_rejected(config, "production deployment must require approval")

    def test_repository_must_be_in_pool_allowlist(self) -> None:
        config = copy.deepcopy(reference_config())
        config["runner_pools"]["trusted-ci"]["allowed_repositories"] = ["example-org/other-app"]
        self.assert_rejected(config, "explicitly allowed by its CI pool")

    def test_embedded_credential_url_is_rejected(self) -> None:
        config = copy.deepcopy(reference_config())
        config["organization"]["database_url"] = "post" + "gres://user:***@db.example.invalid/app"
        self.assert_rejected(config, "probable secret material")

    def test_secret_value_key_is_rejected(self) -> None:
        config = copy.deepcopy(reference_config())
        config["environments"]["development"]["token"] = "not-a-real-token"
        self.assert_rejected(config, "secret values are forbidden")

    def test_host_local_environment_paths_are_rejected(self) -> None:
        validation = Validation()
        with tempfile.TemporaryDirectory() as directory:
            path_list = Path(directory) / "paths"
            path_list.write_bytes(b"host.env\0ci-fleet.env\0nested/host.env\0nested/ci-fleet.env\0")
            scan_tree_path_list(path_list, validation)
        self.assertEqual(len(validation.errors), 4, validation.errors)
        self.assertTrue(all("secret-bearing files are forbidden" in error for error in validation.errors), validation.errors)

    def test_template_ci_scans_committed_file_contents(self) -> None:
        scanner = ROOT / "scripts" / "scan_committed_secrets.py"
        self.assertTrue(scanner.is_file())
        workflow = (ROOT / ".github" / "workflows" / "validate.yml").read_text(encoding="utf-8")
        self.assertIn('python3 "$scanner" --repository "$GITHUB_WORKSPACE" --commit "$commit"', workflow)
        with tempfile.TemporaryDirectory() as directory:
            repository = Path(directory)
            subprocess.run(["git", "init", "-q", str(repository)], check=True)
            for relative in ("scripts/scan_committed_secrets.py", "scripts/validate.sh"):
                path = repository / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("ghp_" + "x" * 20 + "\n", encoding="utf-8")
            subprocess.run(["git", "-C", str(repository), "add", "."], check=True)
            result = subprocess.run(
                [sys.executable, str(scanner), "--repository", str(repository)],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("scripts/scan_committed_secrets.py:1", result.stderr)
        self.assertIn("scripts/validate.sh:1", result.stderr)

    def test_committed_secret_scanner_reads_symlink_blobs(self) -> None:
        scanner = ROOT / "scripts" / "scan_committed_secrets.py"
        with tempfile.TemporaryDirectory() as directory:
            repository = Path(directory)
            subprocess.run(["git", "init", "-q", str(repository)], check=True)
            target = "ghp_" + "x" * 20
            (repository / target).write_text("clean\n", encoding="utf-8")
            (repository / "secret-link").symlink_to(target)
            subprocess.run(["git", "-C", str(repository), "add", "."], check=True)
            result = subprocess.run(
                [sys.executable, str(scanner), "--repository", str(repository)],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("secret-link:1", result.stderr)

    def test_committed_secret_scanner_reads_every_commit_in_range(self) -> None:
        scanner = ROOT / "scripts" / "scan_committed_secrets.py"
        with tempfile.TemporaryDirectory() as directory:
            repository = Path(directory)
            subprocess.run(["git", "init", "-q", str(repository)], check=True)
            subprocess.run(["git", "-C", str(repository), "config", "user.name", "Policy Test"], check=True)
            subprocess.run(["git", "-C", str(repository), "config", "user.email", "policy@example.invalid"], check=True)
            (repository / "README.md").write_text("clean\n", encoding="utf-8")
            subprocess.run(["git", "-C", str(repository), "add", "."], check=True)
            subprocess.run(["git", "-C", str(repository), "commit", "-qm", "base"], check=True)
            base = subprocess.check_output(["git", "-C", str(repository), "rev-parse", "HEAD"], text=True).strip()
            leak = repository / "temporary-leak.txt"
            leak.write_text("ghp_" + "x" * 20 + "\n", encoding="utf-8")
            subprocess.run(["git", "-C", str(repository), "add", "."], check=True)
            subprocess.run(["git", "-C", str(repository), "commit", "-qm", "add leak"], check=True)
            leaked = subprocess.check_output(["git", "-C", str(repository), "rev-parse", "HEAD"], text=True).strip()
            leak.unlink()
            subprocess.run(["git", "-C", str(repository), "add", "-u"], check=True)
            subprocess.run(["git", "-C", str(repository), "commit", "-qm", "remove leak"], check=True)
            head = subprocess.check_output(["git", "-C", str(repository), "rev-parse", "HEAD"], text=True).strip()
            for revision in (f"{base}..{head}", head, f"{head}..{leaked}"):
                with self.subTest(revision=revision):
                    result = subprocess.run(
                        [sys.executable, str(scanner), "--repository", str(repository), "--commit-range", revision],
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        text=True,
                    )
                    self.assertNotEqual(result.returncode, 0)
                    self.assertIn("temporary-leak.txt:1", result.stderr)

    def test_committed_secret_scanner_rejects_historical_forbidden_paths(self) -> None:
        scanner = ROOT / "scripts" / "scan_committed_secrets.py"
        with tempfile.TemporaryDirectory() as directory:
            repository = Path(directory)
            subprocess.run(["git", "init", "-q", str(repository)], check=True)
            subprocess.run(["git", "-C", str(repository), "config", "user.name", "Policy Test"], check=True)
            subprocess.run(["git", "-C", str(repository), "config", "user.email", "policy@example.invalid"], check=True)
            (repository / "README.md").write_text("clean\n", encoding="utf-8")
            subprocess.run(["git", "-C", str(repository), "add", "."], check=True)
            subprocess.run(["git", "-C", str(repository), "commit", "-qm", "base"], check=True)
            base = subprocess.check_output(["git", "-C", str(repository), "rev-parse", "HEAD"], text=True).strip()
            forbidden = repository / ".env"
            forbidden.write_text("MODE=test\n", encoding="utf-8")
            subprocess.run(["git", "-C", str(repository), "add", "."], check=True)
            subprocess.run(["git", "-C", str(repository), "commit", "-qm", "add forbidden path"], check=True)
            forbidden.unlink()
            subprocess.run(["git", "-C", str(repository), "add", "-u"], check=True)
            subprocess.run(["git", "-C", str(repository), "commit", "-qm", "remove forbidden path"], check=True)
            head = subprocess.check_output(["git", "-C", str(repository), "rev-parse", "HEAD"], text=True).strip()
            result = subprocess.run(
                [sys.executable, str(scanner), "--repository", str(repository), "--commit-range", f"{base}..{head}"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn(".env: forbidden secret-bearing path", result.stderr)

    def test_committed_secret_scanner_reads_nested_repository_prefix(self) -> None:
        scanner = ROOT / "scripts" / "scan_committed_secrets.py"
        with tempfile.TemporaryDirectory() as directory:
            repository = Path(directory)
            nested = repository / "config"
            nested.mkdir()
            subprocess.run(["git", "init", "-q", str(repository)], check=True)
            (nested / "fleet.json").write_text("ghp_" + "x" * 20 + "\n", encoding="utf-8")
            subprocess.run(["git", "-C", str(repository), "add", "."], check=True)
            result = subprocess.run(
                [sys.executable, str(scanner), "--repository", str(nested)],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("fleet.json:1", result.stderr)

    def test_committed_secret_scanner_reads_unstaged_tracked_edits(self) -> None:
        scanner = ROOT / "scripts" / "scan_committed_secrets.py"
        with tempfile.TemporaryDirectory() as directory:
            repository = Path(directory)
            subprocess.run(["git", "init", "-q", str(repository)], check=True)
            tracked = repository / "fleet.json"
            tracked.write_text("clean\n", encoding="utf-8")
            subprocess.run(["git", "-C", str(repository), "add", "."], check=True)
            tracked.write_text("ghp_" + "x" * 20 + "\n", encoding="utf-8")
            result = subprocess.run(
                [sys.executable, str(scanner), "--repository", str(repository)],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("fleet.json:1", result.stderr)

    def test_workflow_uses_trusted_scanner_for_complete_history(self) -> None:
        workflow = (ROOT / ".github" / "workflows" / "validate.yml").read_text(encoding="utf-8")
        for required in (
            "fetch-depth: 0",
            'git show "$BASE_SHA:$scanner"',
            'git rev-list --reverse "$HEAD_SHA"',
            'git rev-list --reverse "$BASE_SHA..$HEAD_SHA"',
            'commits+=("$HEAD_SHA")',
            '--commit "$commit"',
        ):
            self.assertIn(required, workflow)

    def test_duplicate_json_controller_id_is_rejected(self) -> None:
        validation = Validation()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "duplicate.json"
            path.write_text('{"controllers":{"ci-01":{},"ci-01":{}}}', encoding="utf-8")
            self.assertIsNone(load_json(path, validation))
        self.assertTrue(any("duplicate object key: ci-01" in error for error in validation.errors), validation.errors)

    def test_strict_mode_rejects_unchanged_example(self) -> None:
        config = copy.deepcopy(reference_config())
        project = first_project(config)
        config["organization"]["slug"] = "example-org"
        config["runner_pools"][project["ci_pool"]]["allowed_repositories"] = ["example-org/example-app"]
        project["repository"] = "example-org/example-app"
        self.assert_rejected(config, "replace the example organization", strict=True)

    def test_nonstandard_ci_entrypoint_is_rejected(self) -> None:
        config = copy.deepcopy(reference_config())
        first_project(config)["ci_contract"]["aggregate_entrypoints"]["fast"] = "npm test"
        self.assert_rejected(config, "standard aggregate fast entrypoint")

    def test_job_ceiling_above_five_minutes_is_rejected(self) -> None:
        config = copy.deepcopy(reference_config())
        first_project(config)["ci_contract"]["max_job_minutes"] = 10
        self.assert_rejected(config, "five-minute hard job ceiling")

    def test_shard_target_must_reserve_startup_time(self) -> None:
        config = copy.deepcopy(reference_config())
        first_project(config)["ci_contract"]["shard_target_minutes"] = 5
        self.assert_rejected(config, "reserve startup time")

    def test_standard_task_plan_path_is_required(self) -> None:
        config = copy.deepcopy(reference_config())
        first_project(config)["ci_contract"]["task_plan"] = "ci/custom.json"
        self.assert_rejected(config, "standard task-plan path")

    def test_updating_guide_preserves_adopter_state_before_commit(self) -> None:
        guide = (ROOT / "docs" / "UPDATING.md").read_text(encoding="utf-8")
        required_in_order = (
            "git fetch --no-tags template",
            'refs/tags/$NEW_TAG:refs/tmp/template-tag-check',
            'ADOPTER_HEAD="$(git rev-parse HEAD)"',
            'git restore --source="$ADOPTER_HEAD"',
            "run the now-reviewed target",
            "./scripts/validate.sh --strict",
            "git commit",
        )
        positions = []
        for value in required_in_order:
            self.assertIn(value, guide)
            positions.append(guide.index(value))
        self.assertEqual(positions, sorted(positions))
        self.assertNotIn("git fetch template '+refs/tags/", guide)


class CapabilityAwarePolicyTests(unittest.TestCase):
    """Issue #11: deployment policy is capability-aware and roles stay isolated."""

    def assert_rejected(self, config: dict, expected: str, *, strict: bool = False) -> None:
        errors = errors_for(config, strict=strict)
        self.assertTrue(any(expected in error for error in errors), errors)

    def set_plan(self, config: dict, plan: str | None) -> None:
        if plan is None:
            config["organization"].pop("github_plan", None)
        else:
            config["organization"]["github_plan"] = plan

    def test_reference_configuration_is_valid(self) -> None:
        self.assertEqual(errors_for(reference_config()), [])

    def test_multi_host_configuration_is_valid(self) -> None:
        config = json.loads((ROOT / "examples" / "multi-host" / "fleet.json").read_text(encoding="utf-8"))
        self.assertEqual(errors_for(config), [])

    def test_omitted_github_plan_defaults_to_free(self) -> None:
        self.set_plan(reference_config(), None)

    def test_environment_approval_overclaim_on_free_is_rejected(self) -> None:
        config = copy.deepcopy(reference_config())
        self.set_plan(config, "free")
        config["environments"]["production"]["approval_mechanism"] = "github-environment"
        self.assert_rejected(config, "unavailable for private repositories on Free and Team")

    def test_environment_approval_requires_declared_capability(self) -> None:
        config = copy.deepcopy(reference_config())
        self.set_plan(config, None)
        config["environments"]["development"]["approval_mechanism"] = "github-environment"
        self.assert_rejected(config, "requires organization.github_plan enterprise")

    def test_team_plan_supports_environment_approval(self) -> None:
        config = copy.deepcopy(reference_config())
        self.set_plan(config, "team")
        for environment in config["environments"].values():
            environment["approval_mechanism"] = "github-environment"
            environment.pop("approval_evidence", None)
        self.assert_rejected(config, "requires organization.github_plan enterprise")

    def test_enterprise_plan_supports_environment_approval(self) -> None:
        config = copy.deepcopy(reference_config())
        self.set_plan(config, "enterprise")
        for environment in config["environments"].values():
            environment["approval_mechanism"] = "github-environment"
            environment.pop("approval_evidence", None)
        self.assertEqual(errors_for(config), [])

    def test_missing_approval_mechanism_infers_fail_closed_gate(self) -> None:
        # Schema-v3 compatibility (Codex finding, PR #14): legacy environments
        # without approval_mechanism stay valid and infer the gate from the
        # declared plan — manual-external with required evidence here.
        config = copy.deepcopy(reference_config())
        self.set_plan(config, None)
        config["environments"]["development"].pop("approval_mechanism")
        config["environments"]["production"].pop("approval_mechanism")
        config["runner_pools"]["trusted-ci"]["runner_group"] = "ci-group"
        self.assertEqual(errors_for(config), [])

    def test_legacy_environment_on_capable_plan_infers_environment_gate(self) -> None:
        config = copy.deepcopy(reference_config())
        self.set_plan(config, "enterprise")
        for environment in config["environments"].values():
            environment.pop("approval_mechanism", None)
            environment.pop("approval_evidence", None)
        self.assertEqual(errors_for(config), [])

    def test_schema_keeps_approval_mechanism_optional(self) -> None:
        # Codex finding (PR #14): standards-compliant JSON Schema tools must
        # accept omission exactly like validate_config does, so legacy v3
        # environments are not rejected by editors.
        self.assertNotIn("approval_mechanism", contract_schema()["$defs"]["environment"]["required"])

    def test_evidence_identity_beside_punctuation_is_rejected(self) -> None:
        # Codex finding (PR #14): separators other than space or hyphen must
        # not let approval evidence name the requesting CI identity.
        config = copy.deepcopy(reference_config())
        for evidence in ("trusted-ci/job-log", "trusted-ci: job log", "log output of run trusted-ci"):
            config["environments"]["production"]["approval_evidence"] = evidence
            self.assert_rejected(config, "must not name ordinary-CI state")

    def test_generic_label_prose_evidence_rejected_for_explicit_manual_gate(self) -> None:
        # Codex finding (PR #14): prose reuse of one identity word is not
        # self-approval, but an explicitly declared manual-external gate must
        # still record a structured locator (round 8); generic prose fails
        # closed every mode rather than silently passing CI.
        config = copy.deepcopy(reference_config())
        config["runner_pools"]["trusted-ci"]["routing_labels"] = ["release"]
        config["environments"]["production"]["approval_evidence"] = (
            "signed release ticket recording the exact reviewed commit SHA "
            "approved by the responsible engineer"
        )
        self.assert_rejected(config, "must be a structured external approval locator")
        self.assertEqual(errors_for(reference_config()), [])

    def test_pre_branch_v3_configuration_without_evidence_fields_stays_valid(self) -> None:
        # Codex finding, round 3 (PR #14): the actual pre-change schema-v3
        # fleet.json omitted both approval_mechanism AND approval_evidence.
        # Compatibility means that exact shape keeps validating; requiring
        # evidence for inferred manual-external would force adopters to edit
        # data just to import the validator. The fixture is vendored (not read
        # from repository history) so freshly templated adopter repositories
        # without the e483998 ancestry still pass (Codex, round 7).
        config = json.loads(LEGACY_V3_FLEET_JSON)
        self.assertEqual(errors_for(config), [])

    def test_explicit_manual_gate_requires_evidence_in_every_mode(self) -> None:
        # Codex finding, round 4 (PR #14): legacy tolerance covers only
        # environments omitting BOTH new fields; an explicitly selected
        # manual-external gate needs its locator even non-strict.
        config = copy.deepcopy(reference_config())
        env = config["environments"]["production"]
        env["approval_mechanism"] = "manual-external"
        env.pop("approval_evidence", None)
        self.assert_rejected(config, "manual-external approval must record where the exact-head approval is kept")

    def test_identity_and_output_marker_split_by_prose_is_rejected(self) -> None:
        # Codex finding, round 4 (PR #14): prose between the identity and the
        # run-output marker must not defeat detection.
        config = copy.deepcopy(reference_config())
        config["environments"]["production"]["approval_evidence"] = (
            "trusted-ci record for the exact reviewed commit SHA in the workflow log"
        )
        self.assert_rejected(config, "must not name ordinary-CI state")

    def test_partial_identity_component_near_marker_is_accepted(self) -> None:
        # Codex finding, round 4 (PR #14): only the complete ordered
        # identity phrase counts — one component ("trusted") near a marker
        # must not reject legitimate external evidence.
        config = copy.deepcopy(reference_config())
        config["environments"]["production"]["approval_evidence"] = (
            "ticket:RT-1042 trusted release workflow approved"
        )
        self.assertEqual(errors_for(config), [])

    def test_initializer_placeholder_evidence_fails_every_mode(self) -> None:
        # Codex finding, round 3 (PR #14): the initializer's generated
        # production gate must not pass with a generic prose/placeholder
        # sentence; an explicit manual-external gate needs a real structured
        # locator in every mode (round 8), and --strict additionally flags the
        # REPLACE-ME placeholder wording.
        config = copy.deepcopy(reference_config())
        config["environments"]["production"]["approval_evidence"] = (
            "REPLACE-ME: record where the exact reviewed commit SHA approval is kept"
        )
        self.assert_rejected(config, "must be a structured external approval locator")
        self.assert_rejected(config, "initializer placeholder", strict=True)

    def test_controller_identity_in_evidence_is_rejected(self) -> None:
        # Codex finding, round 5 (PR #14): controller IDs and scale-set names
        # are ordinary-CI identities too — evidence citing their run output
        # is self-approval.
        config = copy.deepcopy(reference_config())
        config["environments"]["production"]["approval_evidence"] = (
            "example-ci-01 workflow job log for exact reviewed commit"
        )
        self.assert_rejected(config, "must not name ordinary-CI state")

    def test_explicit_null_approval_mechanism_is_rejected(self) -> None:
        # Codex finding, round 5 (PR #14): an explicit null is not legacy
        # field omission; it must fail closed instead of inheriting the
        # schema-v3 compatibility exception.
        config = copy.deepcopy(reference_config())
        env = config["environments"]["production"]
        env["approval_mechanism"] = None
        env.pop("approval_evidence")
        self.assert_rejected(config, "must be github-environment or manual-external")

    def test_host_address_in_approval_evidence_is_rejected(self) -> None:
        # Codex finding, round 5 (PR #14): the free-form evidence locator
        # must not become a channel for private infrastructure details;
        # host addresses and hostnames are forbidden by AGENTS.md.
        config = copy.deepcopy(reference_config())
        for evidence in (
            "approval record at https://10.0.0.12/tickets/RT-1042",
            "approval recorded on ci-runner-01.internal",
        ):
            config["environments"]["production"]["approval_evidence"] = evidence
            self.assert_rejected(config, "must not contain host addresses or internal hostnames")

    def test_marker_word_ci_identity_still_detected_beside_run_context(self) -> None:
        # Codex finding, round 3 (PR #14): a pool named like a run-output
        # marker ("run", "job", "workflow") must not disable self-approval
        # detection via the disjointness shortcut.
        config = copy.deepcopy(reference_config())
        config["runner_pools"]["trusted-ci"]["routing_labels"] = ["run"]
        config["environments"]["production"]["approval_evidence"] = "run job log"
        self.assert_rejected(config, "must not name ordinary-CI state")

    def test_non_string_enum_values_fail_closed_without_traceback(self) -> None:
        # Codex finding (PR #14): malformed arrays/objects in enum-valued
        # fields must yield structural errors, not unhashable-type tracebacks.
        mutations = (
            lambda c: c["organization"].__setitem__("github_plan", ["free"]),
            lambda c: c["controllers"]["example-ci-01"].__setitem__("state", {"active": True}),
            lambda c: c["controllers"]["example-ci-01"].__setitem__("lifecycle", ["stable"]),
            lambda c: c["host_groups"]["development-apps"].__setitem__("role", ["deployment"]),
            lambda c: c["host_groups"]["development-apps"].__setitem__("environment_class", ["development"]),
            lambda c: c["environments"]["development"].__setitem__("approval_mechanism", ["manual-external"]),
        )
        for mutate in mutations:
            with self.subTest():
                config = copy.deepcopy(reference_config())
                mutate(config)
                self.assertTrue(errors_for(config), "expected a structural rejection")

    def test_invalid_github_plan_is_rejected(self) -> None:
        self.assert_rejected(self.with_plan(reference_config(), "unlimited"), "must be free, team, or enterprise")

    def with_plan(self, config: dict, plan: str) -> dict:
        config = copy.deepcopy(config)
        self.set_plan(config, plan)
        return config

    def test_legacy_omission_of_both_fields_stays_valid_non_strict(self) -> None:
        # Round-3 compatibility, narrowed by round 4: only environments
        # omitting BOTH new fields keep the legacy v3 contract, and only in
        # non-strict mode; strict mode still demands the locator.
        config = copy.deepcopy(reference_config())
        env = config["environments"]["production"]
        env.pop("approval_evidence")
        env.pop("approval_mechanism")
        self.assertEqual(errors_for(config), [])
        self.assert_rejected(config, "manual-external approval must record where the exact-head approval is kept", strict=True)

    def test_self_approved_production_is_rejected(self) -> None:
        # A production declaration whose only approval record lives inside the
        # same unprivileged CI identity that requests deployment is a
        # self-approval: the evidence reference must not name ordinary-CI state.
        config = copy.deepcopy(reference_config())
        config["environments"]["production"]["approval_evidence"] = "trusted-ci runner group job log"
        self.assert_rejected(config, "must not name ordinary-CI state")

    def test_missing_approval_mechanism_stays_valid_and_infers_gate(self) -> None:
        # Supersedes the original required-field test after the Codex
        # schema-v3-compatibility finding: omission now infers the gate.
        config = copy.deepcopy(reference_config())
        config["environments"]["development"].pop("approval_mechanism")
        self.assertEqual(errors_for(config), [])

    def test_unknown_approval_mechanism_is_rejected(self) -> None:
        config = copy.deepcopy(reference_config())
        config["environments"]["development"]["approval_mechanism"] = "honor-system"
        self.assert_rejected(config, "must be github-environment or manual-external")

    def test_environment_may_not_target_non_deployment_host_group(self) -> None:
        config = copy.deepcopy(reference_config())
        config["host_groups"]["persistent-test-apps"]["role"] = "image-build"
        config["environments"]["staging"] = {
            "host_group": "persistent-test-apps",
            "automatic": True,
            "requires_approval": False,
            "approval_mechanism": "manual-external",
            "required_secret_names": [],
        }
        self.assert_rejected(config, "deploy only from deployment hosts")

    def test_privileged_role_kinds_are_recognized_inventory(self) -> None:
        config = copy.deepcopy(reference_config())
        config["host_groups"]["persistent-test-apps"]["role"] = "persistent-testing"
        self.assertEqual(errors_for(config), [])
        config["host_groups"]["persistent-test-apps"]["role"] = "image-build"
        self.assertEqual(errors_for(config), [])

    def test_unknown_host_group_role_is_rejected(self) -> None:
        config = copy.deepcopy(reference_config())
        config["host_groups"]["persistent-test-apps"]["role"] = "super-deployer"
        self.assert_rejected(config, "must be deployment, persistent-testing, or image-build")

    def test_ci_label_colliding_with_privileged_group_is_rejected(self) -> None:
        config = copy.deepcopy(reference_config())
        config["runner_pools"]["trusted-ci"]["routing_labels"] = ["persistent-test-apps"]
        self.assert_rejected(config, "privileged host-group identity")

    def test_ci_label_colliding_with_deployment_group_is_rejected(self) -> None:
        # Codex finding (PR #14): deployment-role host groups are privileged
        # relative to ordinary CI too.
        config = copy.deepcopy(reference_config())
        config["runner_pools"]["trusted-ci"]["routing_labels"] = ["development-apps"]
        self.assert_rejected(config, "privileged host-group identity")

    def test_evidence_word_overlap_is_conservative_but_bounded(self) -> None:
        # Codex finding (PR #14) partially applied: matching is bounded to
        # hyphen-normalized whole phrases, so substrings inside larger words
        # no longer false-positive...
        config = copy.deepcopy(reference_config())
        config["runner_pools"]["trusted-ci"]["runner_group"] = "trusted-ci"
        config["environments"]["production"]["approval_evidence"] = "doc:untrusted-city/archive/signed-approvals"
        self.assertEqual(errors_for(config), [])
        # ...but an exact reference to the CI identity still fails closed.
        config["environments"]["production"]["approval_evidence"] = "trusted-ci job log"
        self.assert_rejected(config, "must not name ordinary-CI state")

    def test_malformed_pool_does_not_crash_evidence_check(self) -> None:
        # Codex finding (PR #14): a non-object pool entry is reported as a
        # structural error without an AttributeError traceback.
        config = copy.deepcopy(reference_config())
        config["runner_pools"]["broken-pool"] = ["not-an-object"]
        self.assert_rejected(config, "must be an object")

    def test_ci_label_equal_to_role_word_is_rejected(self) -> None:
        config = copy.deepcopy(reference_config())
        config["runner_pools"]["trusted-ci"]["routing_labels"] = ["image-build"]
        self.assert_rejected(config, "privileged host-group identity")

    def test_duplicate_routing_label_across_pools_is_rejected(self) -> None:
        config = copy.deepcopy(reference_config())
        duplicate = copy.deepcopy(config["runner_pools"]["trusted-ci"])
        duplicate["runner_group"] = "other-group"
        duplicate["routing_labels"] = list(duplicate["routing_labels"])
        config["runner_pools"]["second-pool"] = duplicate
        self.assert_rejected(config, "unique across pools")

    def test_unbracketed_ipv6_in_approval_evidence_is_rejected(self) -> None:
        config = copy.deepcopy(reference_config())
        for evidence in (
            "approval recorded on 2001:db8::1 ticket RT-1042",
            "signed off at 2001:db8:85a3::8a2e:370:7334",
        ):
            config["environments"]["production"]["approval_evidence"] = evidence
            self.assert_rejected(config, "must not contain host addresses or internal hostnames")

    def test_malformed_host_group_does_not_crash_environment_validation(self) -> None:
        config = copy.deepcopy(reference_config())
        config["host_groups"]["development-apps"] = []
        self.assert_rejected(config, "must be an object")

    def test_explicit_null_approval_evidence_is_rejected_everywhere(self) -> None:
        config = copy.deepcopy(reference_config())
        for env_name in ("development", "production"):
            env = config["environments"][env_name]
            env["approval_evidence"] = None
            self.assert_rejected(config, "must be a logical reference to where exact-head approval is recorded")

    def test_ci_execution_markers_in_evidence_are_rejected(self) -> None:
        config = copy.deepcopy(reference_config())
        for evidence in (
            "trusted-ci workflow 123 approved exact reviewed commit SHA",
            "trusted-ci workflow log",
            "trusted-ci action output",
            "trusted-ci check result",
        ):
            config["environments"]["production"]["approval_evidence"] = evidence
            self.assert_rejected(config, "must not name ordinary-CI state")

    def test_credential_uri_userinfo_in_approval_evidence_is_rejected(self) -> None:
        config = copy.deepcopy(reference_config())
        for evidence in (
            "approval at https://reviewer:s3cr3t@example.com/RT-1042",
            "approved via http://admin:password@ci-log.internal/run/1",
        ):
            config["environments"]["production"]["approval_evidence"] = evidence
            self.assert_rejected(config, "must not contain credential-bearing URI userinfo")

    def test_token_only_uri_userinfo_in_approval_evidence_is_rejected(self) -> None:
        # Codex, PR #14 round 7: userinfo without a colon (token@host) is a
        # credential too; the colon-delimited regex must not be the only gate.
        config = copy.deepcopy(reference_config())
        config["environments"]["production"]["approval_evidence"] = (
            "approval at https://s3cr3t@example.com/RT-1042"
        )
        self.assert_rejected(config, "must not contain credential-bearing URI userinfo")

    def test_ci_execution_pipeline_and_build_in_evidence_are_rejected(self) -> None:
        # Codex, PR #14 round 7: pipeline/build are ordinary CI execution nouns.
        config = copy.deepcopy(reference_config())
        for evidence in (
            "trusted-ci pipeline 123 approved exact reviewed commit SHA",
            "trusted-ci build 123",
            "trusted-ci pipelines 1 and 2 approved",
        ):
            config["environments"]["production"]["approval_evidence"] = evidence
            self.assert_rejected(config, "must not name ordinary-CI state")

    def test_punctuated_bare_ipv6_in_approval_evidence_is_rejected(self) -> None:
        # Codex, PR #14 round 7: punctuation around an unbracketed IPv6 literal
        # must not let the address slip through whitespace-only tokenization.
        config = copy.deepcopy(reference_config())
        for evidence in (
            "approval recorded on (2001:db8::1), ticket RT-1042",
            "approved at [2001:db8::1]/RT-1042",
        ):
            config["environments"]["production"]["approval_evidence"] = evidence
            self.assert_rejected(config, "must not contain host addresses or internal hostnames")

    def test_semantic_version_in_approval_evidence_is_accepted(self) -> None:
        # Codex, PR #14 round 7: a dotted release version is not a hostname.
        config = copy.deepcopy(reference_config())
        config["environments"]["production"]["approval_evidence"] = (
            "ticket:RT-1042 release 1.2.3 approved"
        )
        self.assertEqual(errors_for(config), [])

    def test_production_without_structured_locator_is_rejected_strict(self) -> None:
        # Codex, PR #14 round 7: an approval gate with no ticket/path/system
        # locator must not pass strict validation.
        config = copy.deepcopy(reference_config())
        config["environments"]["production"]["approval_evidence"] = (
            "the exact reviewed commit SHA was approved"
        )
        self.assert_rejected(
            config,
            "must be a structured external approval locator",
            strict=True,
        )

    def test_prose_with_colon_is_not_a_locator_strict(self) -> None:
        # Codex PR #14 round 8 finding 1: arbitrary prose containing a colon
        # (e.g. an approval sentence) must not satisfy the structured-locator
        # rule; only a typed prefix (ticket:/url:/system:/doc:) is a locator.
        config = copy.deepcopy(reference_config())
        config["environments"]["production"]["approval_evidence"] = (
            "the exact reviewed commit SHA was approved: yes"
        )
        self.assert_rejected(
            config,
            "must be a structured external approval locator",
            strict=True,
        )

    def test_ci_execution_url_in_evidence_is_rejected(self) -> None:
        # Codex PR #14 round 8 finding 2: a manual-external locator that points
        # straight at the requesting GitHub Actions run is still ordinary-CI
        # self-approval and must be rejected regardless of configured identity.
        config = copy.deepcopy(reference_config())
        config["environments"]["production"]["approval_evidence"] = (
            "url:https://github.com/acme/app/actions/runs/123"
        )
        self.assert_rejected(
            config,
            "must not reference ordinary-CI execution URLs",
        )

    def test_single_label_host_in_evidence_is_rejected(self) -> None:
        # Codex PR #14 round 8 finding 3: an unqualified single-label host
        # names a host-local service and leaks infrastructure details the
        # evidence scan must block.
        config = copy.deepcopy(reference_config())
        config["environments"]["production"]["approval_evidence"] = (
            "url:http://ci-runner/RT-1042"
        )
        self.assert_rejected(
            config,
            "must not contain unqualified single-label hosts",
        )

    def test_explicit_manual_gate_prose_fails_every_mode(self) -> None:
        # Codex PR #14 round 8 finding 1: an explicitly declared manual-external
        # gate must record a findable structured locator in every mode, not only
        # strict; otherwise the shipped template's own prose evidence passes the
        # non-strict Validate reference configurations CI job.
        config = copy.deepcopy(reference_config())
        config["environments"]["production"]["approval_evidence"] = (
            "signed release ticket recording the exact reviewed commit SHA"
        )
        self.assert_rejected(config, "must be a structured external approval locator")
        self.assert_rejected(config, "must be a structured external approval locator", strict=True)

    def test_public_saas_approval_url_is_accepted(self) -> None:
        # Codex PR #14 round 8 finding 2: a public multi-label SaaS approval
        # record such as Atlassian must satisfy the url: locator and not be
        # mistaken for host-local infrastructure.
        config = copy.deepcopy(reference_config())
        config["environments"]["production"]["approval_evidence"] = (
            "url:https://acme.atlassian.net/browse/RT-1042"
        )
        self.assertEqual(errors_for(config), [])
        # The locator type is accepted in strict mode too; the example-org
        # strict rejection is unrelated to the evidence locator.
        config = copy.deepcopy(reference_config())
        config["organization"]["slug"] = "acme"
        config["runner_pools"]["trusted-ci"]["allowed_repositories"] = ["acme/example-app"]
        config["projects"]["example-app"]["repository"] = "acme/example-app"
        config["projects"]["example-app"]["image"] = "ghcr.io/acme/example-app"
        config["environments"]["production"]["approval_evidence"] = (
            "url:https://acme.atlassian.net/browse/RT-1042"
        )
        self.assertEqual(errors_for(config, strict=True), [])

    def test_explicit_null_github_plan_is_rejected(self) -> None:
        # Codex PR #14 round 8 finding 3: an explicit null is not key omission;
        # the schema permits only free/team/enterprise, so the validator must
        # reject null too (same explicit-null class as approval fields, round 5).
        config = copy.deepcopy(reference_config())
        config["organization"]["github_plan"] = None
        self.assert_rejected(config, "do not set it to null")

    def test_credential_query_param_in_approval_url_is_rejected(self) -> None:
        # Codex PR #14 round 9 finding 1: a query-authenticated or presigned
        # approval URL leaks a secret through a parameter the userinfo check
        # misses; reject credential-bearing query/fragment parameters.
        config = copy.deepcopy(reference_config())
        config["environments"]["production"]["approval_evidence"] = (
            "url:https://approvals.example.com/RT-1042?token=s3cr3t"
        )
        self.assert_rejected(config, "must not contain credential-bearing URI userinfo")

    def test_compressed_ipv6_in_evidence_is_rejected(self) -> None:
        # Codex PR #14 round 9 finding 2: leading/trailing compression colons
        # must survive punctuation trimming so ::1 / fe80:: are still rejected.
        config = copy.deepcopy(reference_config())
        for evidence in ("approval on ::1", "approval on fe80::"):
            config["environments"]["production"]["approval_evidence"] = evidence
            self.assert_rejected(config, "must not contain host addresses or internal hostnames")

    def test_compound_credential_param_in_approval_url_is_rejected(self) -> None:
        # Codex PR #14 round 10: compound OAuth/API param names such as
        # access_token, client_secret, and private_token must be blocked even
        # though a word boundary cannot occur after the connecting underscore.
        config = copy.deepcopy(reference_config())
        for evidence in (
            "url:https://approvals.example.com/RT-1042?access_token=s3cr3t",
            "url:https://approvals.example.com/RT-1042?client_secret=s3cr3t",
            "url:https://git.example.com/RT-1042?private_token=s3cr3t",
        ):
            config["environments"]["production"]["approval_evidence"] = evidence
            self.assert_rejected(config, "must not contain credential-bearing URI userinfo")

    def test_four_part_version_in_evidence_is_accepted(self) -> None:
        # Codex PR #14 round 9 finding 3: a four-part calendar/release version
        # is not IPv4; require valid octets so 2026.8.28.1 is not blocked.
        config = copy.deepcopy(reference_config())
        config["environments"]["production"]["approval_evidence"] = (
            "ticket:RT-1042 release 2026.8.28.1 approved"
        )
        self.assertEqual(errors_for(config), [])

    def test_credential_named_param_in_approval_url_is_rejected(self) -> None:
        # Codex PR #14 round 11 finding 1: a credential= query parameter is an
        # explicitly credential-bearing value the compound-name list omitted.
        config = copy.deepcopy(reference_config())
        config["environments"]["production"]["approval_evidence"] = (
            "url:https://approvals.example/RT?credential=s3cr3t"
        )
        self.assert_rejected(config, "must not contain credential-bearing URI userinfo")

    def test_ci_execution_marker_at_any_depth_is_rejected(self) -> None:
        # Codex PR #14 round 11 finding 2: a CI execution segment such as
        # /pipelines must be rejected regardless of how many path segments
        # precede it (e.g. CircleCI), and under any scheme.
        config = copy.deepcopy(reference_config())
        for evidence in (
            "url:https://app.circleci.com/pipelines/github/acme/app/123",
            "url:https://github.com/acme/app/actions/runs/123",
        ):
            config["environments"]["production"]["approval_evidence"] = evidence
            self.assert_rejected(config, "must not reference ordinary-CI execution URLs")

    def test_non_http_scheme_single_label_host_is_rejected(self) -> None:
        # Codex PR #14 round 11 finding 3: the url: locator accepts any scheme,
        # so a single-label host under ssh:// must still be blocked.
        config = copy.deepcopy(reference_config())
        config["environments"]["production"]["approval_evidence"] = (
            "url:ssh://ci-runner/RT-1042"
        )
        self.assert_rejected(config, "must not contain unqualified single-label hosts")

    def test_legacy_v3_configuration_stays_valid_without_history(self) -> None:
        # Codex, PR #14 round 7: vendored legacy fixture must validate when the
        # upstream object (e483998) does not exist, i.e. in freshly templated
        # adopter repositories.
        config = json.loads(LEGACY_V3_FLEET_JSON)
        self.assertEqual(errors_for(config), [])


if __name__ == "__main__":
    unittest.main()
