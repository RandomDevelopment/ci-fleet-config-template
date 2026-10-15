#!/usr/bin/env python3
"""Regression tests for ci-fleet's non-negotiable configuration policies."""

from __future__ import annotations

import copy
import json
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from test_core_compatibility import CONFIG_FILES, EXACT_FILES, core_bytes, is_upstream_repository, verify_deployer_contract, main as compatibility_main
from validate import Validation, load_json, scan_secret_material, scan_tree_path_list, validate_config, validate_docker_network_policy, validate_rollout_evidence, validate_transition


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


def documented_artifact_errors(root: Path) -> list[str]:
    allowed_external = {
        "TEMPLATE_RELEASE",
        "next-engine-rollout-evidence.json",
        "scripts/ci/plan.json",
        "scripts/ci/run.sh",
        "scripts/install-worker-controller.sh",
        "scripts/migrate-v<old>-to-v<new>.py",
    }
    token = re.compile(
        r"`(?:python3 )?(?:\./)?((?:scripts|docs|examples)/[A-Za-z0-9_./<>-]+|"
        r"fleet(?:\.schema)?\.json|template-compatibility\.json|"
        r"(?:next-engine-rollout-evidence|engine-rollout-evidence)\.json|AGENTS\.md|SECURITY\.md|"
        r"THIRD_PARTY_NOTICES\.md|LICENSE|TEMPLATE_RELEASE)"
    )
    errors = []
    for document in ("README.md", "docs/UPDATING.md", "docs/DEPLOYMENT-POLICY.md", "docs/RELEASE.md"):
        text = (root / document).read_text(encoding="utf-8")
        for relative in token.findall(text):
            if relative not in allowed_external and not (root / relative).is_file():
                errors.append(f"{document}: documented path does not exist: {relative}")
    return sorted(set(errors))


class PolicyTests(unittest.TestCase):
    def test_deployment_boundary_supports_only_external_staging_adoption(self) -> None:
        record = json.loads((ROOT / "template-compatibility.json").read_text(encoding="utf-8"))
        boundary = record["deployment_policy_boundary"]
        self.assertEqual(boundary["version"], 2)
        self.assertEqual(boundary["status"], "external-host-policy")
        self.assertFalse(boundary["approval_validation"])
        self.assertEqual(boundary["supported_executable_roles"], ["ordinary-ci"])
        self.assertEqual(boundary["supported_external_roles"], ["standalone-staging-deployer"])
        self.assertEqual(set(boundary["excluded_executable_roles"]), {
            "persistent-tester", "image-builder", "development-deployer",
            "production-deployer", "deploy-ref-writer",
        })
        deployer = boundary["standalone_deployer"]
        self.assertEqual(deployer["contract"], "docs/DEPLOYER-HOST.md")
        self.assertEqual(deployer["installer"], "scripts/install-deployer.sh")
        self.assertEqual(deployer["supported_environment"], "staging")
        self.assertEqual(deployer["production_operations"], "disabled")
        self.assertEqual(deployer["deploy_ref_writer"], "excluded")
        self.assertEqual(deployer["host_policy_schema_version"], 1)
        self.assertEqual(deployer["fleet_fields"], [])
        self.assertFalse(deployer["host_policy_in_git"])
        self.assertFalse(deployer["approval_evidence_in_git"])

    def test_deployer_pin_and_core_bytes_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            record = json.loads((ROOT / "template-compatibility.json").read_text())
            for key, values in (
                ("commit", ("main", "v1.0.0", "c67d18d", "0" * 40, "1" * 40)),
                ("repository", ("example-org/ci-fleet",)),
            ):
                for value in values:
                    candidate = copy.deepcopy(record)
                    candidate["deployment_policy_boundary"]["standalone_deployer"]["reviewed_core"][key] = value
                    (root / "template-compatibility.json").write_text(json.dumps(candidate))
                    with patch("test_core_compatibility.urllib.request.urlopen") as fetch:
                        with self.assertRaisesRegex(RuntimeError, "exact reviewed merged core pin"):
                            verify_deployer_contract(root)
                        fetch.assert_not_called()
            (root / "template-compatibility.json").write_text(json.dumps(record))
            with patch("test_core_compatibility.urllib.request.urlopen") as fetch:
                fetch.return_value.__enter__.return_value.read.return_value = b"corrupt core bytes"
                with self.assertRaisesRegex(RuntimeError, "reviewed deployer core bytes differ"):
                    verify_deployer_contract(root)

    def test_deployer_policy_and_privileged_routing_cannot_enter_inventory(self) -> None:
        for strict in (False, True):
            for section, key, value in (
                ("root", "deployer", {"core_ref": "main"}),
                ("controller", "deployer", {"artifact": "example/app:latest"}),
                ("pool", "role", "standalone-staging-deployer"),
                ("host_group", "runner_group", "ordinary-ci"),
                ("host_group", "routing_labels", ["ordinary-ci"]),
                ("environment", "deployer_conf", "deployer.conf"),
                ("environment", "source_commit", "main"),
                ("environment", "artifact_image", "example/app:latest"),
                ("environment", "checkpoint_evidence", "checkpoint-example"),
                ("project", "deploy_ref_writer", True),
            ):
                with self.subTest(strict=strict, section=section, key=key):
                    config = reference_config()
                    targets = {
                        "root": config,
                        "controller": first_controller(config),
                        "pool": next(iter(config["runner_pools"].values())),
                        "host_group": config["host_groups"]["production-apps"],
                        "environment": config["environments"]["production"],
                        "project": first_project(config),
                    }
                    targets[section][key] = value
                    self.assert_rejected(config, f"unknown keys: {key}", strict=strict)

    def test_derived_repository_cannot_skip_deployer_verification(self) -> None:
        with patch("test_core_compatibility.is_upstream_repository", side_effect=lambda root: False if root == ROOT else is_upstream_repository(root)), \
                patch("test_core_compatibility.verify_deployer_contract", side_effect=RuntimeError("unreviewed deployer pin")) as verify, \
                patch.object(sys, "argv", ["test_core_compatibility.py"]):
            self.assertEqual(compatibility_main(), 1)
            verify.assert_called_once_with(ROOT, None)

    def test_unsupported_approval_evidence_fails_in_every_mode(self) -> None:
        for evidence in (
            "system:circleci/pipelines/123",
            "url:data:text/plain,password=fake-value",
            "url:file:///home/deployer/.ssh/config",
            "url:https://approvals.example/RT?auth=fake-value",
            "url:https://approvals.example/RT?authorization=fake-value",
            "the exact reviewed commit SHA was approved: yes",
            "ticket:RT-1042",
            None,
        ):
            for strict in (False, True):
                for explicit in (False, True):
                    with self.subTest(evidence=evidence, strict=strict, explicit=explicit):
                        config = reference_config()
                        environment = config["environments"]["production"]
                        environment["approval_evidence"] = evidence
                        if explicit:
                            environment["approval_mechanism"] = "manual-external"
                        self.assert_rejected(config, "unknown keys: approval", strict=strict)

    def test_plan_and_approval_mechanisms_are_not_supported(self) -> None:
        schema = contract_schema()
        self.assertFalse(schema["properties"]["organization"]["additionalProperties"])
        self.assertNotIn("github_plan", schema["properties"]["organization"]["properties"])
        self.assertFalse(schema["$defs"]["environment"]["additionalProperties"])
        for key in ("approval_mechanism", "approval_evidence"):
            self.assertNotIn(key, schema["$defs"]["environment"]["properties"])
        for strict in (False, True):
            for plan in ("free", "team", "enterprise", None):
                config = reference_config()
                config["organization"]["github_plan"] = plan
                self.assert_rejected(config, "unknown keys: github_plan", strict=strict)
            for mechanism in ("github-environment", "manual-external", None):
                config = reference_config()
                config["environments"]["production"]["approval_mechanism"] = mechanism
                self.assert_rejected(config, "unknown keys: approval_mechanism", strict=strict)

    def test_privileged_role_extensions_are_not_supported(self) -> None:
        schema = contract_schema()["$defs"]["host_group"]["properties"]["role"]
        self.assertEqual(schema, {"const": "deployment"})
        for role in ("persistent-testing", "image-build", "standalone-staging-deployer", "production-deployer", "deploy-ref-writer"):
            for strict in (False, True):
                config = reference_config()
                config["host_groups"]["production-apps"]["role"] = role
                self.assert_rejected(config, "must equal deployment", strict=strict)

    def test_malformed_controllers_with_approval_evidence_do_not_crash(self) -> None:
        for controllers in ([], None, "invalid", 1):
            for strict in (False, True):
                config = reference_config()
                config["controllers"] = controllers
                config["environments"]["production"]["approval_evidence"] = "ticket:RT-1042"
                self.assert_rejected(config, "$.controllers: must be a non-empty object", strict=strict)

    def test_malformed_host_groups_report_structural_errors(self) -> None:
        for value in ([], None, "invalid", 1):
            for strict in (False, True):
                config = reference_config()
                config["host_groups"]["production-apps"] = value
                self.assert_rejected(config, "$.host_groups.production-apps: must be an object", strict=strict)

    def test_non_string_enum_values_report_structural_errors(self) -> None:
        mutations = (
            lambda c, v: first_controller(c).__setitem__("state", v),
            lambda c, v: first_controller(c).__setitem__("lifecycle", v),
            lambda c, v: c["host_groups"]["production-apps"].__setitem__("role", v),
            lambda c, v: c["host_groups"]["production-apps"].__setitem__("environment_class", v),
            lambda c, v: c["organization"].__setitem__("github_plan", v),
            lambda c, v: c["environments"]["production"].__setitem__("approval_mechanism", v),
        )
        for mutate in mutations:
            for value in ([], {}, None, 1):
                for strict in (False, True):
                    with self.subTest(mutate=mutate, value=value, strict=strict):
                        config = reference_config()
                        mutate(config, value)
                        self.assertTrue(errors_for(config, strict=strict))

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
        self.assertNotIn("docker_storage_retention", controller["required"])
        retention = controller["properties"]["docker_storage_retention"]
        self.assertFalse(retention["additionalProperties"])
        self.assertEqual(retention["required"], ["exclusive_fleet_daemon"])
        self.assertIs(retention["properties"]["exclusive_fleet_daemon"]["const"], True)
        network = controller["properties"]["docker_network_policy"]
        self.assertEqual(
            network["required"],
            ["default_address_pools", "networks_per_runner", "reserve_subnets"],
        )
        self.assertEqual(network["properties"]["default_address_pools"]["maxItems"], 64)
        self.assertEqual(network["properties"]["default_bridge_cidr"], {"type": "string"})
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
        controller["max_runners"] = 1
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

    def test_standalone_docker_network_policy_requires_current_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            config_path = Path(directory) / "fleet.json"
            subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "scripts" / "init.py"),
                    "--organization", "sample-org",
                    "--project", "sample-app",
                    "--engine-ref", "1" * 40,
                    "--output", str(config_path),
                ],
                check=True,
                stdout=subprocess.DEVNULL,
            )
            config = json.loads(config_path.read_text(encoding="utf-8"))
            first_controller(config).pop("status_reporting", None)
            first_controller(config)["docker_network_policy"] = {
                "networks_per_runner": 1,
                "reserve_subnets": 1,
                "default_address_pools": [{"base": "10.255.255.0/24", "size": 28}],
                "default_bridge_cidr": "10.255.254.1/24",
            }
            config_path.write_text(json.dumps(config), encoding="utf-8")

            result = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "scripts" / "validate.py"),
                    "--strict",
                    "--skip-path-scan",
                    "--config", str(config_path),
                ],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )

            evidence_path = Path(directory) / "evidence.json"
            record = {
                "engine_ref": "1" * 40,
                "status_reporting_config": False,
                "required_status_reporting": False,
                "docker_network_policy_config": True,
            }
            evidence = {"schema_version": 1, "status_reporting_engine_capabilities": {
                next(iter(config["controllers"])): record,
            }}
            command = [
                sys.executable, str(ROOT / "scripts" / "validate.py"),
                "--strict", "--skip-path-scan", "--config", str(config_path),
                "--rollout-evidence", str(evidence_path),
            ]
            evidence_path.write_text(json.dumps(evidence))
            missing_bridge = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            self.assertNotEqual(missing_bridge.returncode, 0)
            self.assertIn("requires default bridge CIDR capability evidence", missing_bridge.stderr)
            record["docker_default_bridge_cidr_config"] = True
            evidence_path.write_text(json.dumps(evidence))
            accepted = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            self.assertEqual(accepted.returncode, 0, accepted.stderr)

        self.assertNotEqual(result.returncode, 0)
        self.assertIn(
            "requires Docker network policy configuration capability evidence for this controller and engine_ref",
            result.stderr,
        )

    def test_default_bridge_policy_rejects_unusable_overlap_and_insufficient_capacity(self) -> None:
        config = reference_config()
        controller = first_controller(config)
        controller["max_runners"] = 1
        policy = {
            "networks_per_runner": 1,
            "reserve_subnets": 1,
            "default_address_pools": [{"base": "198.51.100.0/24", "size": 28}],
            "default_bridge_cidr": "203.0.113.1/24",
        }
        controller["docker_network_policy"] = policy
        self.assertEqual(errors_for(config), [])
        for bridge, expected in (
            (None, "must be an IPv4 interface CIDR"),
            (True, "must be an IPv4 interface CIDR"),
            ("invalid", "malformed IPv4 interface CIDR"),
            ("2001:db8::1/64", "must be an IPv4 interface CIDR"),
            ("203.0.113.1/30", "at least six usable addresses"),
            ("203.0.113.0/24", "usable host address"),
            ("203.0.113.255/24", "usable host address"),
            ("198.51.100.1/24", "must not overlap"),
        ):
            with self.subTest(bridge=bridge):
                policy["default_bridge_cidr"] = bridge
                self.assert_rejected(config, expected)

        policy["default_bridge_cidr"] = "203.0.113.1/29"
        controller["max_runners"] = 5
        config["runner_pools"][controller["pool"]]["capacity_budget"] = 5
        self.assert_rejected(config, "max_runners + reserve_subnets usable container addresses")
        controller["state"] = "disabled"
        self.assertEqual(errors_for(config), [])

        policy["default_address_pools"] = [{"base": "10.255.255.0/24", "size": 28}]
        self.assert_rejected(config, "reviewed operational Docker bridge CIDR", strict=True)

    def test_bridge_review_example_is_valid_only_before_strict_operational_adoption(self) -> None:
        policy = json.loads((ROOT / "examples" / "docker-network-policy.json").read_text())
        validation = Validation()
        validate_docker_network_policy(policy, "docker_network_policy", 1, validation)
        self.assertEqual(validation.errors, [])
        validate_docker_network_policy(policy, "docker_network_policy", 1, validation, strict=True)
        self.assertTrue(any("reviewed operational Docker pool CIDR" in error for error in validation.errors))
        policy["default_address_pools"] = [{"base": "10.255.255.0/24", "size": 28}]
        validation = Validation()
        validate_docker_network_policy(policy, "docker_network_policy", 1, validation, strict=True)
        self.assertTrue(any("reviewed operational Docker bridge CIDR" in error for error in validation.errors))

    def test_bridge_capability_evidence_is_typed_for_active_and_next_records(self) -> None:
        record = {
            "engine_ref": "1" * 40,
            "status_reporting_config": False,
            "required_status_reporting": False,
            "docker_network_policy_config": True,
            "docker_default_bridge_cidr_config": True,
        }
        for source in ("engine-rollout-evidence.json", "next-engine-rollout-evidence.json"):
            evidence = {"schema_version": 1, "status_reporting_engine_capabilities": {"ci-01": record}}
            validation = Validation()
            parsed = validate_rollout_evidence(evidence, validation, source)
            self.assertEqual(validation.errors, [])
            self.assertEqual(parsed["ci-01"], record)
            for invalid in (1, "true", None):
                with self.subTest(source=source, invalid=invalid):
                    record["docker_default_bridge_cidr_config"] = invalid
                    validation = Validation()
                    self.assertEqual(validate_rollout_evidence(evidence, validation, source), {})
                    self.assertTrue(any("docker_default_bridge_cidr_config: must be a boolean" in error for error in validation.errors))
            record["docker_default_bridge_cidr_config"] = True

    def test_default_bridge_introduction_and_removal_require_separate_engine_changes(self) -> None:
        previous = reference_config()
        name = next(iter(previous["controllers"]))
        controller = first_controller(previous)
        previous["controllers"] = {name: controller}
        controller.pop("status_reporting", None)
        controller["engine_ref"] = "1" * 40
        controller["docker_network_policy"] = {
            "networks_per_runner": 1,
            "reserve_subnets": 1,
            "default_address_pools": [{"base": "198.51.100.0/24", "size": 28}],
        }
        current = copy.deepcopy(previous)
        first_controller(current)["docker_network_policy"]["default_bridge_cidr"] = "203.0.113.1/24"
        record = {
            "engine_ref": "1" * 40,
            "status_reporting_config": False,
            "required_status_reporting": False,
            "docker_network_policy_config": True,
            "docker_default_bridge_cidr_config": True,
        }
        validation = Validation()
        validate_transition(previous, current, {name: record}, validation, {name: record})
        self.assertEqual(validation.errors, [])

        validation = Validation()
        validate_transition(previous, current, {name: record}, validation, {
            name: {**record, "docker_default_bridge_cidr_config": False},
        })
        self.assertTrue(any("previous integrated state" in error and "default bridge CIDR" in error for error in validation.errors))

        first_controller(current)["engine_ref"] = "2" * 40
        promoted = {name: {**record, "engine_ref": "2" * 40}}
        validation = Validation()
        validate_transition(previous, current, promoted, validation, {name: record}, promoted)
        self.assertTrue(any("later commit" in error and "default_bridge_cidr" in error for error in validation.errors))

        first_controller(current)["engine_ref"] = "1" * 40
        validation = Validation()
        validate_transition(current, previous, {name: record}, validation, {name: record})
        self.assertEqual(validation.errors, [])
        first_controller(previous)["engine_ref"] = "2" * 40
        validation = Validation()
        validate_transition(current, previous, promoted, validation, {name: record}, promoted)
        self.assertTrue(any("must be removed before changing engine_ref" in error for error in validation.errors))

    def test_storage_retention_admits_only_explicit_exclusive_daemon(self) -> None:
        config = reference_config()
        controller = first_controller(config)
        controller["docker_storage_retention"] = {"exclusive_fleet_daemon": True}
        self.assertEqual(errors_for(config), [])
        for value, expected in (
            (None, "must be an object"),
            (False, "must be an object"),
            ([], "must be an object"),
            ({}, "missing keys: exclusive_fleet_daemon"),
            ({"exclusive_fleet_daemon": False}, "shared daemons are not admitted"),
            ({"exclusive_fleet_daemon": 1}, "shared daemons are not admitted"),
            ({"exclusive_fleet_daemon": "true"}, "shared daemons are not admitted"),
            ({"exclusive_fleet_daemon": True, "extra": True}, "unknown keys: extra"),
        ):
            with self.subTest(value=value):
                controller["docker_storage_retention"] = value
                self.assert_rejected(config, expected)
        controller.pop("docker_storage_retention")
        self.assertEqual(errors_for(config), [])

    def test_storage_retention_engine_first_admission_through_cli(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            base_path = root / "base.json"
            subprocess.run(
                [sys.executable, str(ROOT / "scripts" / "init.py"),
                 "--organization", "sample-org", "--project", "sample-app",
                 "--engine-ref", "1" * 40, "--output", str(base_path)],
                check=True, stdout=subprocess.DEVNULL,
            )
            base = json.loads(base_path.read_text())
            controller = first_controller(base)
            self.assertNotIn("docker_storage_retention", controller)
            controller.pop("status_reporting", None)
            controller.pop("docker_network_policy", None)
            admitted = copy.deepcopy(base)
            first_controller(admitted)["docker_storage_retention"] = {"exclusive_fleet_daemon": True}
            new_engine = copy.deepcopy(base)
            first_controller(new_engine)["engine_ref"] = "2" * 40
            admitted_new_engine = copy.deepcopy(admitted)
            first_controller(admitted_new_engine)["engine_ref"] = "2" * 40
            controller_name = next(iter(base["controllers"]))
            cases = (
                ("default omission", {"controllers": {}}, base, None),
                ("new controller admission", {"controllers": {}}, admitted, "new controller"),
                ("null predecessor", {"controllers": {controller_name: None}}, admitted, "new controller"),
                ("list predecessor", {"controllers": {controller_name: []}}, admitted, "new controller"),
                ("predecessor without engine", {"controllers": {controller_name: {}}}, admitted, "later commit"),
                ("admission with pin change", base, admitted_new_engine, "later commit"),
                ("later same-engine admission", base, admitted, None),
                ("retained admission", admitted, admitted, None),
                ("retained admission with pin change", admitted, admitted_new_engine,
                 "must be removed in an earlier commit before changing engine_ref"),
                ("removal with pin change", admitted, new_engine,
                 "must be removed in an earlier commit before changing engine_ref"),
                ("same-engine removal", admitted, base, None),
                ("pin change after removal", base, new_engine, None),
                ("later admission on new engine", new_engine, admitted_new_engine, None),
            )
            for name, previous, current, rejection in cases:
                with self.subTest(case=name):
                    previous_path = root / "previous.json"
                    current_path = root / "current.json"
                    previous_path.write_text(json.dumps(previous))
                    current_path.write_text(json.dumps(current))
                    result = subprocess.run(
                        [sys.executable, str(ROOT / "scripts" / "validate.py"),
                         "--strict", "--skip-path-scan", "--config", str(current_path),
                         "--previous-config", str(previous_path)],
                        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                    )
                    if rejection is None:
                        self.assertEqual(result.returncode, 0, result.stderr)
                    else:
                        self.assertNotEqual(result.returncode, 0, result.stdout)
                        self.assertIn("docker_storage_retention", result.stderr)
                        self.assertIn(rejection, result.stderr)

            previous_path.write_text(json.dumps(admitted))
            current_path.write_text(json.dumps(admitted_new_engine))
            sidecar_path = root / "next-engine-rollout-evidence.json"
            sidecar_path.write_text(json.dumps({
                "schema_version": 1,
                "status_reporting_engine_capabilities": {controller_name: {
                    "engine_ref": "2" * 40,
                    "status_reporting_config": False,
                    "required_status_reporting": False,
                }},
            }))
            with self.subTest(case="next-engine evidence cannot attest storage retention"):
                result = subprocess.run(
                    [sys.executable, str(ROOT / "scripts" / "validate.py"),
                     "--strict", "--skip-path-scan", "--config", str(current_path),
                     "--previous-config", str(previous_path),
                     "--rollout-evidence", str(sidecar_path),
                     "--previous-next-engine-rollout-evidence", str(sidecar_path)],
                    stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                )
                self.assertNotEqual(result.returncode, 0, result.stdout)
                self.assertIn("docker_storage_retention", result.stderr)
                self.assertIn("must be removed in an earlier commit before changing engine_ref", result.stderr)

    def test_rollout_cli_rejects_missing_or_malformed_previous_controllers(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            current_path = root / "current.json"
            previous_path = root / "previous.json"
            subprocess.run(
                [sys.executable, str(ROOT / "scripts" / "init.py"),
                 "--organization", "sample-org", "--project", "sample-app",
                 "--engine-ref", "1" * 40, "--output", str(current_path)],
                check=True, stdout=subprocess.DEVNULL,
            )
            current = json.loads(current_path.read_text())
            first_controller(current)["docker_storage_retention"] = {"exclusive_fleet_daemon": True}
            current_path.write_text(json.dumps(current))
            for previous in (None, [], {}, {"controllers": None}, {"controllers": []}, {"controllers": "invalid"}):
                with self.subTest(previous=previous):
                    previous_path.write_text(json.dumps(previous))
                    result = subprocess.run(
                        [sys.executable, str(ROOT / "scripts" / "validate.py"),
                         "--strict", "--skip-path-scan", "--config", str(current_path),
                         "--previous-config", str(previous_path)],
                        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                    )
                    self.assertEqual(result.returncode, 1, result.stderr)
                    self.assertIn("--previous-config: must contain a controllers object for rollout validation", result.stderr)
                    self.assertNotIn("Traceback", result.stderr)

    def test_optional_capabilities_require_previous_integrated_engine_evidence(self) -> None:
        previous = copy.deepcopy(reference_config())
        controller_name = next(iter(previous["controllers"]))
        previous["controllers"] = {controller_name: previous["controllers"][controller_name]}
        previous_controller = first_controller(previous)
        previous_controller["engine_ref"] = "1" * 40
        previous_controller.pop("status_reporting", None)
        previous_controller.pop("docker_network_policy", None)
        current = copy.deepcopy(previous)
        controller = first_controller(current)
        controller["engine_ref"] = "2" * 40
        controller["max_runners"] = 1
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

    def test_engine_upgrade_requires_previously_staged_next_engine_evidence(self) -> None:
        previous = copy.deepcopy(reference_config())
        controller_name = next(iter(previous["controllers"]))
        previous_controller = first_controller(previous)
        previous_controller["engine_ref"] = "1" * 40
        previous_controller["status_reporting"] = {
            "enabled": True,
            "config_file": "/etc/ci-fleet/monitoring.env",
        }
        previous_controller["docker_network_policy"] = {
            "networks_per_runner": 1,
            "reserve_subnets": 1,
            "default_address_pools": [{"base": "198.51.100.0/24", "size": 28}],
        }
        current = copy.deepcopy(previous)
        first_controller(current)["engine_ref"] = "2" * 40

        def evidence(engine_ref: str) -> dict:
            return {
                "schema_version": 1,
                "status_reporting_engine_capabilities": {
                    controller_name: {
                        "engine_ref": engine_ref,
                        "status_reporting_config": True,
                        "required_status_reporting": True,
                        "docker_network_policy_config": True,
                    }
                },
            }

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name, value in (
                ("previous.json", previous),
                ("current.json", current),
                ("previous-evidence.json", evidence("1" * 40)),
                ("current-evidence.json", evidence("2" * 40)),
            ):
                (root / name).write_text(json.dumps(value), encoding="utf-8")
            command = [
                sys.executable,
                str(ROOT / "scripts" / "validate.py"),
                "--config", str(root / "current.json"),
                "--previous-config", str(root / "previous.json"),
                "--rollout-evidence", str(root / "current-evidence.json"),
                "--previous-rollout-evidence", str(root / "previous-evidence.json"),
                "--next-engine-rollout-evidence", str(root / "current-evidence.json"),
                "--skip-path-scan",
            ]
            result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn(
                "requires next-engine capability evidence from the previous integrated sidecar",
                result.stderr,
            )

            (root / "previous-evidence.json").write_text(
                json.dumps({"schema_version": 1, "status_reporting_engine_capabilities": {}}),
                encoding="utf-8",
            )
            result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("requires Docker network policy configuration capability evidence", result.stderr)

    def test_staged_next_engine_evidence_permits_later_promotion(self) -> None:
        previous = copy.deepcopy(reference_config())
        controller_name = next(iter(previous["controllers"]))
        previous["controllers"] = {controller_name: previous["controllers"][controller_name]}
        controller = first_controller(previous)
        controller["engine_ref"] = "1" * 40
        controller["max_runners"] = 1
        controller["status_reporting"] = {
            "enabled": True,
            "config_file": "/etc/ci-fleet/monitoring.env",
        }
        controller["docker_network_policy"] = {
            "networks_per_runner": 1,
            "reserve_subnets": 1,
            "default_address_pools": [{"base": "198.51.100.0/24", "size": 28}],
            "default_bridge_cidr": "203.0.113.1/24",
        }
        promoted = copy.deepcopy(previous)
        first_controller(promoted)["engine_ref"] = "2" * 40
        active = {
            "engine_ref": "1" * 40,
            "status_reporting_config": True,
            "required_status_reporting": True,
            "docker_network_policy_config": True,
            "docker_default_bridge_cidr_config": True,
        }

        def evidence(record: dict) -> dict:
            return {
                "schema_version": 1,
                "status_reporting_engine_capabilities": {controller_name: record},
            }

        active_evidence = evidence(active)
        next_evidence = evidence({**active, "engine_ref": "2" * 40})
        promoted_evidence = evidence({**active, "engine_ref": "2" * 40})
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name, value in (
                ("previous.json", previous),
                ("promoted.json", promoted),
                ("active-evidence.json", active_evidence),
                ("next-evidence.json", next_evidence),
                ("empty-next-evidence.json", {
                    "schema_version": 1,
                    "status_reporting_engine_capabilities": {},
                }),
                ("promoted-evidence.json", promoted_evidence),
            ):
                (root / name).write_text(json.dumps(value), encoding="utf-8")
            base_command = [sys.executable, str(ROOT / "scripts" / "validate.py"), "--skip-path-scan"]
            staging = subprocess.run(
                [
                    *base_command,
                    "--config", str(root / "previous.json"),
                    "--previous-config", str(root / "previous.json"),
                    "--rollout-evidence", str(root / "active-evidence.json"),
                    "--previous-rollout-evidence", str(root / "active-evidence.json"),
                    "--next-engine-rollout-evidence", str(root / "next-evidence.json"),
                ],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            self.assertEqual(staging.returncode, 0, staging.stderr)

            promotion_command = [
                *base_command,
                "--config", str(root / "promoted.json"),
                "--previous-config", str(root / "previous.json"),
                "--rollout-evidence", str(root / "promoted-evidence.json"),
                "--previous-rollout-evidence", str(root / "active-evidence.json"),
            ]
            promotion = subprocess.run(
                [
                    *promotion_command,
                    "--previous-next-engine-rollout-evidence", str(root / "next-evidence.json"),
                ],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            self.assertEqual(promotion.returncode, 0, promotion.stderr)

            empty = subprocess.run(
                [
                    *promotion_command,
                    "--next-engine-rollout-evidence", str(root / "empty-next-evidence.json"),
                    "--previous-next-engine-rollout-evidence", str(root / "next-evidence.json"),
                ],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            self.assertNotEqual(empty.returncode, 0)
            self.assertIn("must contain at least one staged record", empty.stderr)

            retained = subprocess.run(
                [
                    *promotion_command,
                    "--next-engine-rollout-evidence", str(root / "next-evidence.json"),
                    "--previous-next-engine-rollout-evidence", str(root / "next-evidence.json"),
                ],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            self.assertNotEqual(retained.returncode, 0)
            self.assertIn("remove the promoted record from the sidecar", retained.stderr)

            missing = subprocess.run(
                promotion_command,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            self.assertNotEqual(missing.returncode, 0)
            self.assertIn("previous integrated sidecar", missing.stderr)

            invalid = copy.deepcopy(active_evidence)
            invalid["status_reporting_engine_capabilities"][controller_name]["engine_ref"] = "9" * 40
            (root / "invalid-active-evidence.json").write_text(json.dumps(invalid), encoding="utf-8")
            nonintegrated = subprocess.run(
                [
                    *base_command,
                    "--config", str(root / "promoted.json"),
                    "--previous-config", str(root / "previous.json"),
                    "--rollout-evidence", str(root / "promoted-evidence.json"),
                    "--previous-rollout-evidence", str(root / "invalid-active-evidence.json"),
                    "--previous-next-engine-rollout-evidence", str(root / "next-evidence.json"),
                ],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            self.assertNotEqual(nonintegrated.returncode, 0)
            self.assertIn("must match the previous integrated controller engine_ref", nonintegrated.stderr)

            for capability, expected in (
                ("engine_ref", "requires next-engine capability evidence from the previous integrated sidecar"),
                ("status_reporting_config", "requires status-reporting configuration capability evidence"),
                ("required_status_reporting", "requires required status-reporting rollout evidence"),
                ("docker_network_policy_config", "requires Docker network policy configuration capability evidence"),
                ("docker_default_bridge_cidr_config", "requires default bridge CIDR capability evidence"),
            ):
                with self.subTest(capability=capability):
                    invalid = copy.deepcopy(next_evidence)
                    record = invalid["status_reporting_engine_capabilities"][controller_name]
                    record[capability] = "3" * 40 if capability == "engine_ref" else False
                    (root / "invalid-next-evidence.json").write_text(json.dumps(invalid), encoding="utf-8")
                    insufficient = subprocess.run(
                        [
                            *promotion_command,
                            "--previous-next-engine-rollout-evidence",
                            str(root / "invalid-next-evidence.json"),
                        ],
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        text=True,
                    )
                    self.assertNotEqual(insufficient.returncode, 0)
                    self.assertIn(expected, insufficient.stderr)

    def test_network_only_staged_next_engine_evidence_permits_later_promotion(self) -> None:
        previous = copy.deepcopy(reference_config())
        controller_name = next(iter(previous["controllers"]))
        previous["controllers"] = {controller_name: previous["controllers"][controller_name]}
        controller = first_controller(previous)
        controller["engine_ref"] = "1" * 40
        controller["max_runners"] = 1
        controller.pop("status_reporting", None)
        controller["docker_network_policy"] = {
            "networks_per_runner": 1,
            "reserve_subnets": 1,
            "default_address_pools": [{"base": "198.51.100.0/24", "size": 28}],
        }
        promoted = copy.deepcopy(previous)
        first_controller(promoted)["engine_ref"] = "2" * 40
        active = {
            "engine_ref": "1" * 40,
            "status_reporting_config": False,
            "required_status_reporting": False,
            "docker_network_policy_config": True,
        }
        evidence = lambda record: {
            "schema_version": 1,
            "status_reporting_engine_capabilities": {controller_name: record},
        }

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name, value in (
                ("previous.json", previous),
                ("promoted.json", promoted),
                ("active-evidence.json", evidence(active)),
                ("next-evidence.json", evidence({**active, "engine_ref": "2" * 40})),
                ("promoted-evidence.json", evidence({**active, "engine_ref": "2" * 40})),
            ):
                (root / name).write_text(json.dumps(value), encoding="utf-8")
            command = [sys.executable, str(ROOT / "scripts" / "validate.py"), "--skip-path-scan"]
            staging = subprocess.run(
                [
                    *command,
                    "--config", str(root / "previous.json"),
                    "--previous-config", str(root / "previous.json"),
                    "--rollout-evidence", str(root / "active-evidence.json"),
                    "--previous-rollout-evidence", str(root / "active-evidence.json"),
                    "--next-engine-rollout-evidence", str(root / "next-evidence.json"),
                ],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            promotion = subprocess.run(
                [
                    *command,
                    "--config", str(root / "promoted.json"),
                    "--previous-config", str(root / "previous.json"),
                    "--rollout-evidence", str(root / "promoted-evidence.json"),
                    "--previous-rollout-evidence", str(root / "active-evidence.json"),
                    "--previous-next-engine-rollout-evidence", str(root / "next-evidence.json"),
                ],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )

        self.assertEqual(staging.returncode, 0, staging.stderr)
        self.assertEqual(promotion.returncode, 0, promotion.stderr)

    def test_status_only_disabled_staged_next_engine_evidence_permits_later_promotion(self) -> None:
        previous = copy.deepcopy(reference_config())
        controller_name = next(iter(previous["controllers"]))
        previous["controllers"] = {controller_name: previous["controllers"][controller_name]}
        controller = first_controller(previous)
        controller["engine_ref"] = "1" * 40
        controller.pop("docker_network_policy", None)
        controller["status_reporting"] = {
            "enabled": False,
            "config_file": "/etc/ci-fleet/monitoring.env",
        }
        promoted = copy.deepcopy(previous)
        first_controller(promoted)["engine_ref"] = "2" * 40

        def evidence(engine_ref: str) -> dict:
            return {
                "schema_version": 1,
                "status_reporting_engine_capabilities": {
                    controller_name: {
                        "engine_ref": engine_ref,
                        "status_reporting_config": True,
                        "required_status_reporting": False,
                    }
                },
            }

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name, value in (
                ("previous.json", previous),
                ("promoted.json", promoted),
                ("active-evidence.json", evidence("1" * 40)),
                ("next-evidence.json", evidence("2" * 40)),
                ("promoted-evidence.json", evidence("2" * 40)),
            ):
                (root / name).write_text(json.dumps(value), encoding="utf-8")
            command = [sys.executable, str(ROOT / "scripts" / "validate.py"), "--skip-path-scan"]
            staging = subprocess.run(
                [
                    *command,
                    "--config", str(root / "previous.json"),
                    "--previous-config", str(root / "previous.json"),
                    "--rollout-evidence", str(root / "active-evidence.json"),
                    "--previous-rollout-evidence", str(root / "active-evidence.json"),
                    "--next-engine-rollout-evidence", str(root / "next-evidence.json"),
                ],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            promotion = subprocess.run(
                [
                    *command,
                    "--config", str(root / "promoted.json"),
                    "--previous-config", str(root / "previous.json"),
                    "--rollout-evidence", str(root / "promoted-evidence.json"),
                    "--previous-rollout-evidence", str(root / "active-evidence.json"),
                    "--previous-next-engine-rollout-evidence", str(root / "next-evidence.json"),
                ],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )

        self.assertEqual(staging.returncode, 0, staging.stderr)
        self.assertEqual(promotion.returncode, 0, promotion.stderr)

    def test_rollout_fixtures_ignore_additional_adopter_controllers(self) -> None:
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
            project = first_project(config)
            project["repository"] = "derived-org/derived-app"
            config["runner_pools"][project["ci_pool"]]["allowed_repositories"] = [project["repository"]]
            controller = first_controller(config)
            controller["max_runners"] = 20
            config["runner_pools"][controller["pool"]]["capacity_budget"] = 20
            controller.pop("status_reporting", None)
            controller.pop("docker_network_policy", None)
            extra = copy.deepcopy(controller)
            extra.update({
                "location": "derived-site-b",
                "state": "disabled",
                "scale_set_name": "derived-ci-02",
                "engine_ref": "3" * 40,
                "status_reporting": {
                    "enabled": False,
                    "config_file": "/etc/ci-fleet/monitoring.env",
                },
            })
            config["controllers"]["derived-ci-02"] = extra
            config_path.write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")
            evidence = {
                "schema_version": 1,
                "status_reporting_engine_capabilities": {
                    "derived-ci-02": {
                        "engine_ref": "3" * 40,
                        "status_reporting_config": True,
                        "required_status_reporting": False,
                    }
                },
            }
            (derived / "engine-rollout-evidence.json").write_text(
                json.dumps(evidence, indent=2) + "\n",
                encoding="utf-8",
            )
            subprocess.run(["git", "init", "-q", str(derived)], check=True)
            subprocess.run(
                [
                    "git", "-C", str(derived), "remote", "add", "origin",
                    "https://github.com/derived-org/derived-config.git",
                ],
                check=True,
            )
            strict = subprocess.run(
                [str(derived / "scripts" / "validate.sh"), "--strict"],
                cwd=derived,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            self.assertEqual(strict.returncode, 0, strict.stderr)
            result = subprocess.run(
                [
                    sys.executable,
                    str(derived / "scripts" / "test_policy.py"),
                    "PolicyTests.test_optional_capabilities_require_previous_integrated_engine_evidence",
                    "PolicyTests.test_staged_next_engine_evidence_permits_later_promotion",
                    "PolicyTests.test_network_only_staged_next_engine_evidence_permits_later_promotion",
                    "PolicyTests.test_status_only_disabled_staged_next_engine_evidence_permits_later_promotion",
                ],
                cwd=derived,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )

        self.assertEqual(result.returncode, 0, result.stderr)

    def test_primary_rollout_evidence_rejects_nested_next_engine(self) -> None:
        validation = Validation()
        validate_rollout_evidence(
            {
                "schema_version": 1,
                "status_reporting_engine_capabilities": {
                    "example-ci-01": {
                        "engine_ref": "1" * 40,
                        "status_reporting_config": False,
                        "required_status_reporting": False,
                        "next_engine": {
                            "engine_ref": "2" * 40,
                            "status_reporting_config": False,
                            "required_status_reporting": False,
                        },
                    }
                },
            },
            validation,
        )
        self.assertTrue(any("unknown keys: next_engine" in error for error in validation.errors), validation.errors)

    def test_malformed_current_controllers_with_next_engine_sidecar_fails_cleanly(self) -> None:
        config = reference_config()
        controller_name = next(iter(config["controllers"]))
        engine_ref = first_controller(config)["engine_ref"]
        config["controllers"] = []

        def evidence(ref: str) -> dict:
            return {
                "schema_version": 1,
                "status_reporting_engine_capabilities": {
                    controller_name: {
                        "engine_ref": ref,
                        "status_reporting_config": False,
                        "required_status_reporting": False,
                    }
                },
            }

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name, value in (
                ("current.json", config),
                ("active-evidence.json", evidence(engine_ref)),
                ("next-evidence.json", evidence("1" * 40)),
            ):
                (root / name).write_text(json.dumps(value), encoding="utf-8")
            result = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "scripts" / "validate.py"),
                    "--config", str(root / "current.json"),
                    "--rollout-evidence", str(root / "active-evidence.json"),
                    "--next-engine-rollout-evidence", str(root / "next-evidence.json"),
                    "--skip-path-scan",
                ],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )

        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn("Traceback", result.stderr)
        self.assertNotIn("AttributeError", result.stderr)
        self.assertIn("$.controllers: must be a non-empty object", result.stderr)
        self.assertIn("FAILED:", result.stderr)

    def test_malformed_previous_controllers_with_next_engine_sidecar_fails_cleanly(self) -> None:
        config = reference_config()
        controller_name = next(iter(config["controllers"]))
        engine_ref = first_controller(config)["engine_ref"]
        previous = copy.deepcopy(config)
        previous["controllers"] = []

        evidence = {
            "schema_version": 1,
            "status_reporting_engine_capabilities": {
                controller_name: {
                    "engine_ref": engine_ref,
                    "status_reporting_config": False,
                    "required_status_reporting": False,
                }
            },
        }
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name, value in (
                ("current.json", config),
                ("previous.json", previous),
                ("evidence.json", evidence),
                ("previous-next-evidence.json", evidence),
            ):
                (root / name).write_text(json.dumps(value), encoding="utf-8")
            result = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "scripts" / "validate.py"),
                    "--config", str(root / "current.json"),
                    "--previous-config", str(root / "previous.json"),
                    "--rollout-evidence", str(root / "evidence.json"),
                    "--previous-rollout-evidence", str(root / "evidence.json"),
                    "--previous-next-engine-rollout-evidence", str(root / "previous-next-evidence.json"),
                    "--skip-path-scan",
                ],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )

        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn("Traceback", result.stderr)
        self.assertNotIn("AttributeError", result.stderr)
        self.assertIn("must reference a previous integrated controller", result.stderr)
        self.assertIn("FAILED:", result.stderr)

    def test_new_controller_cannot_introduce_docker_network_policy(self) -> None:
        previous = reference_config()
        current = copy.deepcopy(previous)
        controller = copy.deepcopy(first_controller(current))
        controller["state"] = "disabled"
        controller["scale_set_name"] = "new-ci-02"
        controller["docker_network_policy"] = {
            "networks_per_runner": 1,
            "reserve_subnets": 1,
            "default_address_pools": [{"base": "198.51.100.0/24", "size": 28}],
        }
        current["controllers"]["new-ci-02"] = controller
        validation = Validation()

        validate_transition(previous, current, {}, validation, {})

        self.assertTrue(any(
            "new-ci-02.docker_network_policy" in error and "new controller" in error
            for error in validation.errors
        ), validation.errors)

    def test_initializer_omits_optional_capabilities_without_engine_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "fleet.json"
            subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "scripts" / "init.py"),
                    "--organization", "sample-org",
                    "--project", "sample-app",
                    "--engine-ref", "1" * 40,
                    "--output", str(output),
                ],
                check=True,
                stdout=subprocess.DEVNULL,
            )
            config = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(output.stat().st_mode & 0o777, 0o644)
            subprocess.run(
                [
                    str(ROOT / "scripts" / "validate.sh"),
                    "--strict",
                    "--skip-path-scan",
                    "--config", str(output),
                ],
                check=True,
                stdout=subprocess.DEVNULL,
            )
        controller = first_controller(config)
        self.assertNotIn("status_reporting", controller)
        self.assertNotIn("docker_network_policy", controller)
        self.assertNotIn("docker_storage_retention", controller)
        self.assertEqual(errors_for(config), [])

    def test_initializer_bridge_fragment_keeps_optional_policy_out_of_base_config(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "fleet.json"
            base = Path(directory) / "base.json"
            command = [
                sys.executable, str(ROOT / "scripts" / "init.py"),
                "--organization", "sample-org", "--project", "sample-app",
                "--engine-ref", "1" * 40,
            ]
            subprocess.run([*command, "--output", str(base)], check=True, stdout=subprocess.DEVNULL)
            result = subprocess.run(
                [*command, "--output", str(output), "--default-bridge-cidr", "203.0.113.1/24"],
                check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
            )
            self.assertEqual(output.read_bytes(), base.read_bytes())
            self.assertIn("Review-only docker_network_policy fragment, not added to fleet.json", result.stdout)
            self.assertIn("stage per-controller engine capability evidence before manual insertion", result.stdout)
            fragment = json.loads(result.stdout[result.stdout.index("{\n"):])
            self.assertEqual(fragment["docker_network_policy"]["default_bridge_cidr"], "203.0.113.1/24")
            validation = Validation()
            validate_docker_network_policy(fragment["docker_network_policy"], "docker_network_policy", 1, validation)
            self.assertEqual(validation.errors, [])
            self.assertEqual(errors_for(json.loads(output.read_text()), strict=True), [])
            self.assertFalse(any(key in first_controller(json.loads(output.read_text())) for key in (
                "docker_network_policy", "status_reporting", "docker_storage_retention",
            )))
            for bridge in ("invalid", "198.51.100.1/24", "203.0.113.0/24", "203.0.113.1/30"):
                with self.subTest(bridge=bridge):
                    rejected = subprocess.run(
                        [*command, "--output", str(output), "--force", "--default-bridge-cidr", bridge],
                        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                    )
                    self.assertNotEqual(rejected.returncode, 0)
                    self.assertEqual(output.read_bytes(), base.read_bytes())
                    self.assertNotIn("Review-only", rejected.stdout)
            absent = Path(directory) / "absent.json"
            rejected = subprocess.run(
                [*command, "--output", str(absent), "--default-bridge-cidr", "invalid"],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
            )
            self.assertNotEqual(rejected.returncode, 0)
            self.assertFalse(absent.exists())

    def test_initializer_bridge_fragment_sizes_pool_and_limits_only_review_mode(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "fleet.json"
            command = [
                sys.executable, str(ROOT / "scripts" / "init.py"),
                "--organization", "sample-org", "--project", "sample-app",
                "--engine-ref", "1" * 40, "--output", str(output), "--force",
            ]
            for maximum, expected_size in ((14, 28), (15, 29), (30, 29)):
                with self.subTest(maximum=maximum):
                    result = subprocess.run(
                        [*command, "--capacity-budget", str(maximum), "--max-runners", str(maximum),
                         "--default-bridge-cidr", "203.0.113.1/24"],
                        check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                    )
                    policy = json.loads(result.stdout[result.stdout.index("{\n"):])["docker_network_policy"]
                    self.assertEqual(policy["default_address_pools"][0]["size"], expected_size)
                    validation = Validation()
                    validate_docker_network_policy(policy, "docker_network_policy", maximum, validation)
                    self.assertEqual(validation.errors, [])
            previous = output.read_bytes()
            too_large = [*command, "--capacity-budget", "31", "--max-runners", "31"]
            rejected = subprocess.run(
                [*too_large, "--default-bridge-cidr", "203.0.113.1/24"],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
            )
            self.assertNotEqual(rejected.returncode, 0)
            self.assertIn("at most 30 runners", rejected.stderr)
            self.assertIn("larger Docker network policies require manual review", rejected.stderr)
            self.assertEqual(output.read_bytes(), previous)
            output.unlink()
            rejected = subprocess.run(
                [*too_large, "--default-bridge-cidr", "203.0.113.1/24"],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
            )
            self.assertNotEqual(rejected.returncode, 0)
            self.assertFalse(output.exists())
            subprocess.run(too_large, check=True, stdout=subprocess.DEVNULL)
            controller = first_controller(json.loads(output.read_text()))
            self.assertEqual(controller["max_runners"], 31)
            self.assertNotIn("docker_network_policy", controller)

    def test_initializer_rejects_strict_placeholders_without_output(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "fleet.json"
            result = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "scripts" / "init.py"),
                    "--organization", "example-org",
                    "--project", "example-app",
                    "--engine-ref", "2" * 40,
                    "--output", str(output),
                ],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertFalse(output.exists())

    def test_old_engine_examples_omit_optional_capabilities(self) -> None:
        upstream = is_upstream_repository(ROOT)
        for path in (ROOT / "fleet.json", ROOT / "examples" / "multi-host" / "fleet.json"):
            with self.subTest(path=path):
                config = json.loads(path.read_text(encoding="utf-8"))
                self.assertEqual(config["schema_version"], 3)
                for controller in config["controllers"].values():
                    if upstream:
                        self.assertNotIn("docker_network_policy", controller)
                        self.assertNotIn("status_reporting", controller)
                        self.assertNotIn("docker_storage_retention", controller)
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
            "standalone_safety_deltas",
            "example_engine",
            "template_release",
            "deployment_policy_boundary",
        })
        self.assertEqual(
            compatibility["reviewed_core"],
            {
                "repository": "RandomDevelopment/ci-fleet",
                "commit": "aa9bbb27a4746fc80ce27d8932de68450b28364b",
                "embedded_template_path": "templates/config-repository",
            },
        )
        self.assertEqual(compatibility["template_contract"]["fleet_schema_version"], 3)
        self.assertEqual(compatibility["template_contract"]["validator"], "scripts/validate.py")
        self.assertEqual(compatibility["template_contract"]["initializer"], "scripts/init.py")
        self.assertEqual(
            set(compatibility["optional_capabilities"]),
            {"status_reporting", "docker_network_policy", "docker_default_bridge_cidr", "docker_storage_retention"},
        )
        self.assertTrue(all(
            value["support"] == "optional-staged"
            for name, value in compatibility["optional_capabilities"].items()
            if name != "docker_storage_retention"
        ))
        self.assertEqual(compatibility["optional_capabilities"]["docker_default_bridge_cidr"]["evidence_key"], "docker_default_bridge_cidr_config")
        self.assertEqual(compatibility["optional_capabilities"]["docker_storage_retention"], {
            "support": "optional-engine-gated", "engine_capability": "docker_storage_retention",
        })
        self.assertEqual(compatibility["standalone_safety_deltas"], [{
            "path": "scripts/validate.py",
            "reviewed_core_gap": "new controllers may introduce docker_network_policy without prior staged capability evidence",
            "standalone_enforcement": "new controllers must omit docker_network_policy until engine rollout is proven",
        }, {
            "path": "scripts/validate.py",
            "reviewed_core_gap": "malformed referenced host groups and non-string enum values can crash validation",
            "standalone_enforcement": "type-check referenced host groups and enum values and return accumulated validation errors",
        }, {
            "path": "scripts/init.py",
            "reviewed_core_gap": "initializer emits Docker network policy before per-controller engine evidence",
            "standalone_enforcement": "initializer omits optional fields; explicit bridge input emits a review-only policy fragment",
        }, {
            "path": "scripts/validate.py",
            "reviewed_core_gap": "bridge capability checks depend on transition context and engine upgrades cannot promote staged next-engine records",
            "standalone_enforcement": "always require matching bridge evidence and verify promotion from the previous integrated next-engine sidecar",
        }, {
            "path": "scripts/validate.py",
            "reviewed_core_gap": "storage retention admission is not ordered after an existing controller engine",
            "standalone_enforcement": "require same-engine admission on an existing controller and remove admission in an earlier commit before any engine_ref change",
        }])
        self.assertEqual(compatibility["example_engine"]["commit"], "8df97cc7575f47696fa82a179bbe39cd2874b1ca")
        self.assertEqual(compatibility["example_engine"]["pin_status"], "unchanged")
        self.assertEqual(compatibility["template_release"]["state"], "prepared-not-published")

    def test_exact_core_drift_check_is_pinned_and_runnable(self) -> None:
        if not is_upstream_repository(ROOT):
            self.skipTest("ordinary-CI drift probe is upstream-only; CI separately verifies the deployer")
        checker = ROOT / "scripts" / "test_core_compatibility.py"
        text = checker.read_text(encoding="utf-8")
        self.assertIn("aa9bbb27a4746fc80ce27d8932de68450b28364b", text)
        result = subprocess.run(
            [sys.executable, str(checker)],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_exact_core_drift_check_rejects_required_tree_and_allowlisted_hash_drift(self) -> None:
        if not is_upstream_repository(ROOT):
            self.skipTest("exact core compatibility is upstream-only")
        with tempfile.TemporaryDirectory() as directory:
            standalone = Path(directory) / "standalone"
            shutil.copytree(ROOT, standalone, ignore=shutil.ignore_patterns(".git", "__pycache__", "*.pyc"))
            (standalone / ".github" / "workflows" / "validate.yml").unlink()
            with (standalone / "scripts" / "init.py").open("a", encoding="utf-8") as initializer:
                initializer.write("\n# drift\n")
            result = subprocess.run(
                [sys.executable, str(ROOT / "scripts" / "test_core_compatibility.py"), "--standalone-root", str(standalone)],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("tree membership", result.stderr)
        self.assertIn("scripts/init.py: differs", result.stderr)
        self.assertIn("standalone sha256=", result.stderr)

    def test_exact_core_drift_check_rejects_corrupt_allowlisted_core_bytes(self) -> None:
        if not is_upstream_repository(ROOT):
            self.skipTest("exact core compatibility is upstream-only")
        with tempfile.TemporaryDirectory() as directory:
            core = Path(directory) / "core"
            for relative in (*EXACT_FILES, *CONFIG_FILES):
                path = core / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(core_bytes(relative, None))
            with (core / "scripts" / "validate.py").open("ab") as validator:
                validator.write(b"\n# corrupt core bytes\n")
            result = subprocess.run(
                [sys.executable, str(ROOT / "scripts" / "test_core_compatibility.py"), "--core-root", str(core)],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("scripts/validate.py: reviewed core bytes differ", result.stderr)
        self.assertIn("core sha256=", result.stderr)

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
        for artifact in (
            "template-compatibility.json",
            "engine-rollout-evidence.json",
            "next-engine-rollout-evidence.json",
            "docs/RELEASE.md",
        ):
            self.assertIn(artifact, readme)
        self.assertIn("new higher tag", updating)
        self.assertIn("scripts/migrate-v<old>-to-v<new>.py", updating)

    def test_documented_artifact_check_is_path_aware(self) -> None:
        self.assertEqual(documented_artifact_errors(ROOT), [])
        with tempfile.TemporaryDirectory() as directory:
            copy = Path(directory) / "standalone"
            shutil.copytree(ROOT, copy, ignore=shutil.ignore_patterns(".git", "__pycache__", "*.pyc"))
            with (copy / "README.md").open("a", encoding="utf-8") as readme:
                readme.write("\nRun `python3 scripts/missing-required.py`.\n")
            self.assertEqual(
                documented_artifact_errors(copy),
                ["README.md: documented path does not exist: scripts/missing-required.py"],
            )

    def test_pr_workflow_validates_against_base_fleet_and_rollout_evidence(self) -> None:
        workflow = (ROOT / ".github" / "workflows" / "validate.yml").read_text(encoding="utf-8")
        for required in (
            'git show "$BASE_SHA:fleet.json"',
            '--previous-config "$RUNNER_TEMP/previous-fleet.json"',
            'git show "$BASE_SHA:engine-rollout-evidence.json"',
            '--previous-rollout-evidence "$RUNNER_TEMP/previous-rollout-evidence.json"',
            'args+=(--next-engine-rollout-evidence next-engine-rollout-evidence.json)',
            'git show "$BASE_SHA:next-engine-rollout-evidence.json"',
            '--previous-next-engine-rollout-evidence "$RUNNER_TEMP/previous-next-engine-rollout-evidence.json"',
        ):
            self.assertIn(required, workflow)

    def test_pr_workflow_rejects_first_state_optional_capabilities(self) -> None:
        current = copy.deepcopy(reference_config())
        controller_name = next(iter(current["controllers"]))
        controller = first_controller(current)
        controller["engine_ref"] = "2" * 40
        controller["status_reporting"] = {
            "enabled": True,
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
                    "required_status_reporting": True,
                    "docker_network_policy_config": True,
                }
            },
        }
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name, value in (
                ("current.json", current),
                ("previous.json", {"controllers": {}}),
                ("evidence.json", evidence),
            ):
                (root / name).write_text(json.dumps(value), encoding="utf-8")
            result = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "scripts" / "validate.py"),
                    "--config", str(root / "current.json"),
                    "--previous-config", str(root / "previous.json"),
                    "--rollout-evidence", str(root / "evidence.json"),
                    "--skip-path-scan",
                ],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("must be omitted from a new controller", result.stderr)
        workflow = (ROOT / ".github" / "workflows" / "validate.yml").read_text(encoding="utf-8")
        self.assertRegex(
            workflow,
            r'else\n\s+printf \'\{\"controllers\":\{\}\}\\n\' >\"\$RUNNER_TEMP/previous-fleet\.json\"\n'
            r'\s+args\+=\(--previous-config \"\$RUNNER_TEMP/previous-fleet\.json\"\)\n'
            r'\s+\./scripts/validate\.sh \"\$\{args\[@\]\}\"\n\s+fi',
        )

    def test_workflow_passes_strict_operational_fixture_and_rejects_rfc_5737_fixture(self) -> None:
        workflow = (ROOT / ".github" / "workflows" / "validate.yml").read_text(encoding="utf-8")
        self.assertIn('./scripts/validate.sh --strict --skip-path-scan --config "${temporary_directory}/fleet.json"', workflow)
        self.assertIn('"base": "198.51.100.0/24"', workflow)
        self.assertIn('grep -F \'reviewed operational Docker pool CIDR\'', workflow)
        self.assertNotIn("documentation configuration unexpectedly passed strict validation", workflow)

    def test_documentation_names_the_narrow_docker_pool_address_exception(self) -> None:
        agents = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        initializer = (ROOT / "scripts" / "init.py").read_text(encoding="utf-8")
        for text in (agents, readme):
            self.assertIn("default_address_pools[].base", text)
            self.assertIn("default_bridge_cidr", text)
        self.assertIn("review controller capacity", initializer)
        self.assertNotIn("replace the RFC 5737 Docker pool", initializer)

    def test_release_update_test_executes_recorded_tag_rewrite_refusal(self) -> None:
        release_test = (ROOT / "scripts" / "test_release_update.py").read_text(encoding="utf-8")
        for required in (
            "TEMPLATE_RELEASE",
            "refs/tmp/template-tag-check",
            "was rewritten upstream; refusing to use it",
            "v1.1.0",
        ):
            self.assertIn(required, release_test)
        self.assertIn("assertNotEqual(rewrite.returncode, 0)", release_test)

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
            'git restore --source="$ADOPTER_HEAD" --staged --worktree -- fleet.json',
            'if git cat-file -e "$ADOPTER_HEAD:engine-rollout-evidence.json" 2>/dev/null; then',
            'git restore --source="$ADOPTER_HEAD" --staged --worktree -- engine-rollout-evidence.json',
            'if git cat-file -e "$ADOPTER_HEAD:next-engine-rollout-evidence.json" 2>/dev/null; then',
            'git restore --source="$ADOPTER_HEAD" --staged --worktree -- next-engine-rollout-evidence.json',
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
