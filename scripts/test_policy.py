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

    def test_schema_defines_optional_controller_capabilities(self) -> None:
        controller = contract_schema()["$defs"]["controller"]
        self.assertNotIn("docker_network_policy", controller["required"])
        self.assertNotIn("status_reporting", controller["required"])
        network = controller["properties"]["docker_network_policy"]
        self.assertEqual(
            network["required"],
            ["default_address_pools", "networks_per_runner", "reserve_subnets"],
        )
        self.assertEqual(network["properties"]["default_address_pools"]["maxItems"], 64)
        self.assertEqual(
            network["properties"]["default_address_pools"]["items"]["properties"]["size"]["maximum"],
            29,
        )
        reporting = controller["properties"]["status_reporting"]
        self.assertEqual(reporting["required"], ["enabled", "config_file"])
        self.assertEqual(
            reporting["properties"]["config_file"]["const"],
            "/etc/ci-fleet/monitoring.env",
        )

    def test_optional_docker_network_policy_enforces_core_semantics(self) -> None:
        config = copy.deepcopy(reference_config())
        controller = first_controller(config)
        policy = {
            "networks_per_runner": 1,
            "reserve_subnets": 1,
            "default_address_pools": [{"base": "198.51.100.0/24", "size": 28}],
        }
        controller["docker_network_policy"] = policy
        self.assertEqual(errors_for(config), [])

        cases = (
            ({**policy, "extra": True}, "unknown keys: extra"),
            (None, "must be an object"),
            ({**policy, "default_address_pools": [{"base": "2001:db8::/64", "size": 28}]}, "IPv4"),
            ({**policy, "default_address_pools": [{"base": "198.51.100.1/24", "size": 28}]}, "malformed"),
            ({**policy, "default_address_pools": [{"base": "198.51.100.0/24", "size": 23}]}, "impossible subnet count"),
            ({**policy, "default_address_pools": [{"base": "198.51.100.0/24", "size": 30}]}, "between 0 and 29"),
            ({**policy, "default_address_pools": [
                {"base": "198.51.100.0/24", "size": 28},
                {"base": "198.51.100.128/25", "size": 28},
            ]}, "overlaps"),
            ({**policy, "default_address_pools": [{"base": "198.51.100.0/24", "size": 29}] * 65}, "must not exceed 64"),
            ({**policy, "default_address_pools": [{"base": "198.51.100.0/29", "size": 29}]}, "controller Compose network"),
        )
        for value, expected in cases:
            with self.subTest(expected=expected):
                controller["docker_network_policy"] = value
                self.assert_rejected(config, expected)

        controller["state"] = "disabled"
        controller["max_runners"] = 100
        controller["docker_network_policy"] = {
            **policy,
            "networks_per_runner": 100,
            "default_address_pools": [{"base": "198.51.100.0/28", "size": 29}],
        }
        self.assertEqual(errors_for(config), [])
        self.assert_rejected(config, "reviewed operational Docker pool CIDR", strict=True)

    def test_optional_capabilities_require_previous_integrated_engine_evidence(self) -> None:
        previous = copy.deepcopy(reference_config())
        current = copy.deepcopy(previous)
        controller_name = next(iter(current["controllers"]))
        controller = first_controller(current)
        controller["engine_ref"] = "2" * 40
        controller["status_reporting"] = {
            "enabled": False,
            "config_file": "/etc/ci-fleet/monitoring.env",
        }
        controller["docker_network_policy"] = {
            "networks_per_runner": 1,
            "reserve_subnets": 1,
            "default_address_pools": [{"base": "198.51.100.0/24", "size": 28}],
        }
        evidence = {
            "schema_version": 1,
            "status_reporting_engine_capabilities": {
                controller_name: {
                    "engine_ref": "2" * 40,
                    "status_reporting_config": True,
                    "required_status_reporting": False,
                    "docker_network_policy_config": True,
                }
            },
        }
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name, value in (
                ("previous.json", previous),
                ("current.json", current),
                ("evidence.json", evidence),
                ("previous-evidence.json", {"schema_version": 1, "status_reporting_engine_capabilities": {}}),
            ):
                (root / name).write_text(json.dumps(value), encoding="utf-8")
            command = [
                sys.executable,
                str(ROOT / "scripts" / "validate.py"),
                "--config", str(root / "current.json"),
                "--previous-config", str(root / "previous.json"),
                "--rollout-evidence", str(root / "evidence.json"),
                "--previous-rollout-evidence", str(root / "previous-evidence.json"),
                "--skip-path-scan",
            ]
            result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("later commit", result.stderr)

            previous = copy.deepcopy(current)
            first_controller(previous).pop("status_reporting")
            first_controller(previous).pop("docker_network_policy")
            (root / "previous.json").write_text(json.dumps(previous), encoding="utf-8")
            (root / "previous-evidence.json").write_text(json.dumps(evidence), encoding="utf-8")
            result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)

        invalid = copy.deepcopy(current)
        first_controller(invalid)["status_reporting"] = None
        self.assert_rejected(invalid, "must be an object")

    def test_initializer_emits_sized_network_policy_and_omits_status_reporting(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "fleet.json"
            subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "scripts" / "init.py"),
                    "--organization", "sample-org",
                    "--project", "sample-app",
                    "--engine-ref", "1" * 40,
                    "--capacity-budget", "2",
                    "--max-runners", "2",
                    "--networks-per-runner", "2",
                    "--output", str(output),
                ],
                check=True,
                stdout=subprocess.DEVNULL,
            )
            config = json.loads(output.read_text(encoding="utf-8"))
        controller = first_controller(config)
        self.assertNotIn("status_reporting", controller)
        self.assertEqual(controller["docker_network_policy"]["networks_per_runner"], 2)
        pool = controller["docker_network_policy"]["default_address_pools"][0]
        self.assertEqual(pool["base"], "198.51.100.0/24")
        self.assertGreaterEqual(1 << (pool["size"] - 24), 6)
        self.assertEqual(errors_for(config), [])

    def test_reference_examples_publish_optional_network_policy_without_status_reporting(self) -> None:
        for path in (ROOT / "fleet.json", ROOT / "examples" / "multi-host" / "fleet.json"):
            with self.subTest(path=path):
                config = json.loads(path.read_text(encoding="utf-8"))
                self.assertEqual(config["schema_version"], 3)
                for controller in config["controllers"].values():
                    self.assertEqual(
                        controller["docker_network_policy"]["networks_per_runner"],
                        1,
                    )
                    self.assertNotIn("status_reporting", controller)
                    self.assertEqual(
                        controller["engine_ref"],
                        "8df97cc7575f47696fa82a179bbe39cd2874b1ca",
                    )
                self.assertEqual(errors_for(config), [])

    def test_compatibility_record_names_exact_core_and_staged_template_contract(self) -> None:
        compatibility = json.loads((ROOT / "template-compatibility.json").read_text(encoding="utf-8"))
        self.assertEqual(set(compatibility), {
            "schema_version",
            "reviewed_core",
            "template_contract",
            "optional_capabilities",
            "example_engine",
            "template_release",
        })
        self.assertEqual(
            compatibility["reviewed_core"],
            {
                "repository": "RandomDevelopment/ci-fleet",
                "commit": "0aed0d7e85e10050028b7d11fb12b84b3619e638",
                "embedded_template_path": "templates/config-repository",
            },
        )
        self.assertEqual(compatibility["template_contract"]["fleet_schema_version"], 3)
        self.assertEqual(compatibility["template_contract"]["validator"], "scripts/validate.py")
        self.assertEqual(compatibility["template_contract"]["initializer"], "scripts/init.py")
        self.assertEqual(
            set(compatibility["optional_capabilities"]),
            {"status_reporting", "docker_network_policy"},
        )
        self.assertTrue(all(
            value["support"] == "optional-staged"
            for value in compatibility["optional_capabilities"].values()
        ))
        self.assertEqual(compatibility["example_engine"]["commit"], "8df97cc7575f47696fa82a179bbe39cd2874b1ca")
        self.assertEqual(compatibility["example_engine"]["pin_status"], "unchanged")
        self.assertEqual(compatibility["template_release"]["state"], "prepared-not-published")

    def test_exact_core_drift_check_is_pinned_and_runnable(self) -> None:
        checker = ROOT / "scripts" / "test_core_compatibility.py"
        text = checker.read_text(encoding="utf-8")
        self.assertIn("0aed0d7e85e10050028b7d11fb12b84b3619e638", text)
        result = subprocess.run(
            [sys.executable, str(checker)],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_release_checks_and_artifacts_are_documented_in_ci(self) -> None:
        workflow = (ROOT / ".github" / "workflows" / "validate.yml").read_text(encoding="utf-8")
        for command in (
            "python3 scripts/test_core_compatibility.py",
            "python3 scripts/test_release_update.py",
            "./scripts/validate.sh --strict",
        ):
            self.assertIn(command, workflow)
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        updating = (ROOT / "docs" / "UPDATING.md").read_text(encoding="utf-8")
        for artifact in ("template-compatibility.json", "engine-rollout-evidence.json", "docs/RELEASE.md"):
            self.assertIn(artifact, readme)
        self.assertIn("new higher tag", updating)
        self.assertIn("scripts/migrate-v<old>-to-v<new>.py", updating)

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


if __name__ == "__main__":
    unittest.main()
