#!/usr/bin/env python3
"""Fail when the standalone contract drifts from one reviewed embedded template."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
import urllib.parse
import urllib.request
from pathlib import Path

CORE_COMMIT = "aa9bbb27a4746fc80ce27d8932de68450b28364b"
DEPLOYER_CORE_COMMIT = "c67d18d24ceb5f22569d8887b94f7198a448ccde"
DEPLOYER_CORE_HASHES = {
    "docs/DEPLOYER-HOST.md": "fdf13ab7c040aaf0d054b267b7d6a56359e82dd3ac93eb915f99c35a92392375",
    "scripts/install-deployer.sh": "c7baed417d3d29d021cb65e03036ce61e8fb5d07284da4961f119a2f1d9c7e49",
    "scripts/deployer-runtime.sh": "61793276afad9f95785ec0a329fdbde6eaa24485680716b8688c5a355be20709",
    "scripts/deployer_adapter.py": "5c6119c04cecba2554cde5019b671afbffd76b0aade9d212df46d0d14bce2805",
}
CORE_PREFIX = "templates/config-repository"
ROOT = Path(__file__).resolve().parents[1]
STANDALONE_FILES = {
    ".github/dependabot.yml",
    ".github/workflows/validate.yml",
    ".github/workflows/template-update.yml",
    ".gitignore",
    "AGENTS.md",
    "LICENSE",
    "README.md",
    "SECURITY.md",
    "THIRD_PARTY_NOTICES.md",
    "docs/LOCAL-VALIDATION.md",
    "docs/RELEASE.md",
    "docs/DEPLOYMENT-POLICY.md",
    "docs/UPDATING.md",
    "engine-rollout-evidence.json",
    "examples/docker-network-policy.json",
    "examples/multi-host/fleet.json",
    "fleet.json",
    "fleet.schema.json",
    "scripts/local_validate.py",
    "scripts/run_candidate_tests.py",
    "scripts/test_candidate_runner.py",
    "scripts/test_local_validation.py",
    "scripts/test_workflow_events.py",
    "scripts/validate-local-configuration.sh",
    "scripts/init.py",
    "scripts/init.sh",
    "scripts/scan_committed_secrets.py",
    "scripts/test_core_compatibility.py",
    "scripts/test_policy.py",
    "scripts/test_release_update.py",
    "scripts/test_template_updater.py",
    "scripts/update_template.py",
    "scripts/validate.py",
    "scripts/validate.sh",
    "template-compatibility.json",
}
EXACT_FILES = (
    "fleet.schema.json",
    "engine-rollout-evidence.json",
    "scripts/init.py",
    "scripts/validate.py",
)
CONFIG_FILES = ("fleet.json", "examples/multi-host/fleet.json")
ALLOWED_STANDALONE_HASHES = {
    "examples/multi-host/fleet.json": (
        "ec0104a3891795664288c145a16e94be44eac628f8bf7aacc953ae5b3802e036",
        "04908089d4d1f5f483a815ef9ef859ae053ba572d1e6d1c898866a677bc226de",
    ),
    "fleet.json": (
        "23a434eee489bc359589f74e9ec57b07382af61f43c00905b38816df0ef5b3db",
        "12ce4b9f7146f80e5eaaa693cbeb0802f9f2f7aeaf1dcece5c0e86009d1b2e1c",
    ),
    "fleet.schema.json": (
        "88876e671f5935bb366356b2ebc723740c3a4a299fae167714e959f7b56137f2",
        "8db7995ebc7981036fa291e75fc91bf2a620099093f81aab228f3b008eaa3bca",
    ),
    "scripts/init.py": (
        "268869fa3b784880d47c71f474c62f401091c8c12949548006683200852358a8",
        "63119f09cf26659d2c0d4984543ab645263df5811df0b57ca56c92d957d0fc0a",
    ),
    "scripts/validate.py": (
        "060e581df777bb7fafd7989acede1543f216939d30e7fe9f45d3594d5e9f602a",
        "8ba212a672f5eb963e013eec213e6c4c5752a067875b108ed51a15b1395bdc21",
    ),
}


def core_bytes(relative: str, core_root: Path | None) -> bytes:
    if core_root is not None:
        return (core_root / relative).read_bytes()
    url = (
        "https://raw.githubusercontent.com/RandomDevelopment/ci-fleet/"
        f"{CORE_COMMIT}/{CORE_PREFIX}/{relative}"
    )
    with urllib.request.urlopen(url, timeout=30) as response:
        return response.read()


def normalized_config(raw: bytes) -> dict:
    value = json.loads(raw)
    # Intentional standalone difference: issue #12 preserves the older reviewed
    # example engine pin. Every other embedded configuration value must match.
    for controller in value["controllers"].values():
        controller.pop("engine_ref", None)
    return value


def verify_deployer_contract(standalone_root: Path, core_root: Path | None = None) -> None:
    record = json.loads((standalone_root / "template-compatibility.json").read_text())
    deployer = record["deployment_policy_boundary"]["standalone_deployer"]
    if deployer["reviewed_core"] != {
        "repository": "RandomDevelopment/ci-fleet", "commit": DEPLOYER_CORE_COMMIT,
    }:
        raise RuntimeError("standalone deployer must use the exact reviewed merged core pin")
    for relative, expected in DEPLOYER_CORE_HASHES.items():
        if core_root is None:
            url = f"https://raw.githubusercontent.com/RandomDevelopment/ci-fleet/{DEPLOYER_CORE_COMMIT}/{relative}"
            with urllib.request.urlopen(url, timeout=30) as response:
                raw = response.read()
        else:
            raw = (core_root / relative).read_bytes()
        if hashlib.sha256(raw).hexdigest() != expected:
            raise RuntimeError(f"{relative}: reviewed deployer core bytes differ")


def is_upstream_repository(root: Path) -> bool:
    origin = subprocess.run(
        ["git", "-C", str(root), "remote", "get-url", "origin"],
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
    )
    if origin.returncode:
        return False
    remote = origin.stdout.strip()
    if "://" not in remote:
        user_host, separator, path = remote.partition(":")
        user, at, host = user_host.partition("@")
        if not separator or not at or user != "git":
            return False
    else:
        parsed = urllib.parse.urlparse(remote)
        if parsed.scheme not in {"https", "ssh"} or (parsed.scheme == "ssh" and parsed.username != "git"):
            return False
        host, path = parsed.hostname, parsed.path
    return host == "github.com" and path.strip("/").removesuffix(".git") == (
        "RandomDevelopment/ci-fleet-config-template"
    )


class UpstreamRepositoryTests(unittest.TestCase):
    def assert_origin_identity(self, origin: str, expected: bool) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            subprocess.run(["git", "init", "-q", str(root)], check=True)
            subprocess.run(["git", "-C", str(root), "remote", "add", "origin", origin], check=True)
            self.assertEqual(is_upstream_repository(root), expected)

    def test_supported_github_origins_identify_upstream(self) -> None:
        for origin in (
            "https://github.com/RandomDevelopment/ci-fleet-config-template.git",
            "ssh://git@github.com/RandomDevelopment/ci-fleet-config-template.git",
            "git@github.com:RandomDevelopment/ci-fleet-config-template.git",
        ):
            with self.subTest(origin=origin):
                self.assert_origin_identity(origin, True)

    def test_similar_owner_suffix_is_not_upstream(self) -> None:
        self.assert_origin_identity(
            "https://github.com/AcmeRandomDevelopment/ci-fleet-config-template.git",
            False,
        )

    def test_different_repository_is_not_upstream(self) -> None:
        self.assert_origin_identity(
            "https://github.com/RandomDevelopment/not-ci-fleet-config-template.git",
            False,
        )


def verify_pinned_consumer_staging(core_root: Path | None) -> None:
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        pinned = root / "pinned"
        (pinned / "scripts").mkdir(parents=True)
        (pinned / "scripts" / "validate.py").write_bytes(core_bytes("scripts/validate.py", core_root))
        (pinned / "fleet.schema.json").write_bytes(core_bytes("fleet.schema.json", core_root))
        example_ref = json.loads((ROOT / "template-compatibility.json").read_text())["example_engine"]["commit"]
        initialized_path = root / "initialized.json"
        initialized = subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "init.py"),
             "--organization", "compatibility-org", "--project", "example-app",
             "--engine-ref", example_ref, "--output", str(initialized_path)],
            capture_output=True, text=True,
        )
        if initialized.returncode:
            raise RuntimeError(f"standalone initializer failed: {initialized.stderr}")
        initialized_controller = next(iter(json.loads(initialized_path.read_text())["controllers"].values()))
        if initialized_controller["engine_ref"] != example_ref or any(
            field in initialized_controller
            for field in ("status_reporting", "docker_network_policy", "docker_storage_retention")
        ):
            raise RuntimeError("standalone initializer changed the example pin or enabled an unstaged optional capability")
        previous = json.loads((ROOT / "fleet.json").read_text(encoding="utf-8"))
        previous["organization"]["slug"] = "compatibility-org"
        project = next(iter(previous["projects"].values()))
        project["repository"] = "compatibility-org/example-app"
        previous["runner_pools"][project["ci_pool"]]["allowed_repositories"] = [project["repository"]]
        unsupported = [
            ("organization", "github_plan", "enterprise"),
            ("environment", "approval_mechanism", "github-environment"),
            ("environment", "approval_mechanism", "manual-external"),
            ("host_group", "role", "persistent-testing"),
            ("host_group", "role", "image-build"),
        ]
        unsupported.extend(
            ("environment", "approval_evidence", evidence)
            for evidence in (
                "system:circleci/pipelines/123",
                "url:data:text/plain,password=fake-value",
                "url:file:///home/deployer/.ssh/config",
                "url:https://approvals.example/RT?auth=fake-value",
                "url:https://approvals.example/RT?authorization=fake-value",
                "the exact reviewed commit SHA was approved: yes",
                "ticket:RT-1042",
            )
        )
        for section, key, value in unsupported:
            candidate = json.loads(json.dumps(previous))
            target = {
                "organization": candidate["organization"],
                "environment": candidate["environments"]["production"],
                "host_group": candidate["host_groups"]["production-apps"],
            }[section]
            target[key] = value
            config_path = root / "unsupported-policy.json"
            config_path.write_text(json.dumps(candidate), encoding="utf-8")
            for validator_root in (pinned, ROOT):
                result = subprocess.run(
                    [sys.executable, str(validator_root / "scripts" / "validate.py"),
                     "--config", str(config_path), "--skip-path-scan"],
                    capture_output=True, text=True,
                )
                expected = "must equal deployment" if key == "role" else f"unknown keys: {key}"
                if result.returncode != 1 or expected not in result.stderr:
                    raise RuntimeError(f"{validator_root}: unsupported {section}.{key} did not fail closed: {result.stderr}")
        controller_name, controller = next(iter(previous["controllers"].items()))
        controller["engine_ref"] = "1" * 40
        controller.pop("status_reporting", None)
        controller["docker_network_policy"] = {
            "networks_per_runner": 1,
            "reserve_subnets": 1,
            "default_address_pools": [{"base": "10.255.254.0/24", "size": 28}],
            "default_bridge_cidr": "10.255.253.1/24",
        }
        promoted = json.loads(json.dumps(previous))
        promoted["controllers"][controller_name]["engine_ref"] = "2" * 40

        def evidence(engine_ref: str) -> dict:
            return {
                "schema_version": 1,
                "status_reporting_engine_capabilities": {
                    controller_name: {
                        "engine_ref": engine_ref,
                        "status_reporting_config": False,
                        "required_status_reporting": False,
                        "docker_network_policy_config": True,
                        "docker_default_bridge_cidr_config": True,
                    }
                },
            }

        paths = {
            "previous.json": previous,
            "promoted.json": promoted,
            "active-evidence.json": evidence("1" * 40),
            "promoted-evidence.json": evidence("2" * 40),
            "next-engine-rollout-evidence.json": evidence("2" * 40),
        }
        for name, value in paths.items():
            (root / name).write_text(json.dumps(value), encoding="utf-8")
        tree_paths = root / "tree-paths"
        tree_paths.write_bytes(
            b"fleet.json\0engine-rollout-evidence.json\0next-engine-rollout-evidence.json\0"
        )
        pinned_result = subprocess.run(
            [
                sys.executable,
                str(pinned / "scripts" / "validate.py"),
                "--config", str(root / "previous.json"),
                "--strict",
                "--tree-paths", str(tree_paths),
                "--rollout-evidence", str(root / "active-evidence.json"),
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        if pinned_result.returncode:
            raise RuntimeError(f"pinned core validator rejected sidecar staging: {pinned_result.stderr}")

        validator = [sys.executable, str(ROOT / "scripts" / "validate.py"), "--skip-path-scan"]
        staging = subprocess.run(
            [
                *validator,
                "--config", str(root / "previous.json"),
                "--previous-config", str(root / "previous.json"),
                "--rollout-evidence", str(root / "active-evidence.json"),
                "--previous-rollout-evidence", str(root / "active-evidence.json"),
                "--next-engine-rollout-evidence", str(root / "next-engine-rollout-evidence.json"),
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        if staging.returncode:
            raise RuntimeError(f"standalone validator rejected sidecar staging: {staging.stderr}")
        promotion_command = [
            *validator,
            "--config", str(root / "promoted.json"),
            "--previous-config", str(root / "previous.json"),
            "--rollout-evidence", str(root / "promoted-evidence.json"),
            "--previous-rollout-evidence", str(root / "active-evidence.json"),
        ]
        promotion = subprocess.run(
            [
                *promotion_command,
                "--previous-next-engine-rollout-evidence",
                str(root / "next-engine-rollout-evidence.json"),
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        if promotion.returncode:
            raise RuntimeError(f"standalone validator rejected staged promotion: {promotion.stderr}")
        missing_sidecar = subprocess.run(
            promotion_command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        if missing_sidecar.returncode == 0 or "previous integrated sidecar" not in missing_sidecar.stderr:
            raise RuntimeError("standalone validator accepted promotion without prior sidecar evidence")

        incomplete_sidecar = evidence("2" * 40)
        incomplete_sidecar["status_reporting_engine_capabilities"][controller_name].pop(
            "docker_default_bridge_cidr_config"
        )
        (root / "incomplete-sidecar.json").write_text(json.dumps(incomplete_sidecar), encoding="utf-8")
        missing_bridge = subprocess.run(
            [*promotion_command, "--previous-next-engine-rollout-evidence", str(root / "incomplete-sidecar.json")],
            capture_output=True, text=True,
        )
        if missing_bridge.returncode == 0 or "default bridge CIDR capability" not in missing_bridge.stderr:
            raise RuntimeError("standalone validator accepted bridge promotion without prior bridge capability")

        incomplete_active = evidence("1" * 40)
        incomplete_active["status_reporting_engine_capabilities"][controller_name].pop(
            "docker_default_bridge_cidr_config"
        )
        (root / "incomplete-active.json").write_text(json.dumps(incomplete_active), encoding="utf-8")
        missing_active_bridge = subprocess.run(
            [*validator, "--config", str(root / "previous.json"),
             "--rollout-evidence", str(root / "incomplete-active.json")],
            capture_output=True, text=True,
        )
        if missing_active_bridge.returncode == 0 or "default bridge CIDR capability" not in missing_active_bridge.stderr:
            raise RuntimeError("standalone validator accepted an active bridge without bridge capability evidence")

        for validator_root in (pinned, ROOT):
            command = [sys.executable, str(validator_root / "scripts" / "validate.py"),
                       "--skip-path-scan", "--strict", "--config", str(root / "candidate.json"),
                       "--rollout-evidence", str(root / "active-evidence.json")]
            for retention, expected_error in (
                ({"exclusive_fleet_daemon": True}, None),
                ({"exclusive_fleet_daemon": False}, "must be true"),
                ({"exclusive_fleet_daemon": "true"}, "must be true"),
                ({"exclusive_fleet_daemon": True, "max_age_days": 7}, "unknown keys"),
            ):
                candidate = json.loads(json.dumps(previous))
                candidate["controllers"][controller_name]["docker_storage_retention"] = retention
                (root / "candidate.json").write_text(json.dumps(candidate), encoding="utf-8")
                result = subprocess.run(command, capture_output=True, text=True)
                if expected_error is None:
                    if result.returncode:
                        raise RuntimeError(f"{validator_root}: rejected exclusive-daemon retention: {result.stderr}")
                elif result.returncode != 1 or expected_error not in result.stderr:
                    raise RuntimeError(f"{validator_root}: unsafe retention did not fail closed: {result.stderr}")

            before_bridge = json.loads(json.dumps(previous))
            before_bridge["controllers"][controller_name]["docker_network_policy"].pop("default_bridge_cidr")
            (root / "before-bridge.json").write_text(json.dumps(before_bridge), encoding="utf-8")
            (root / "candidate.json").write_text(json.dumps(previous), encoding="utf-8")
            for staged, expected_error in ((False, "previous integrated state"), (True, None)):
                prior_evidence = evidence("1" * 40)
                if not staged:
                    prior_evidence["status_reporting_engine_capabilities"][controller_name].pop(
                        "docker_default_bridge_cidr_config"
                    )
                (root / "prior-bridge-evidence.json").write_text(json.dumps(prior_evidence), encoding="utf-8")
                result = subprocess.run(
                    [*command, "--previous-config", str(root / "before-bridge.json"),
                     "--previous-rollout-evidence", str(root / "prior-bridge-evidence.json")],
                    capture_output=True, text=True,
                )
                if expected_error is None:
                    if result.returncode:
                        raise RuntimeError(f"{validator_root}: rejected staged bridge introduction: {result.stderr}")
                elif result.returncode != 1 or expected_error not in result.stderr:
                    raise RuntimeError(f"{validator_root}: unstaged bridge did not fail closed: {result.stderr}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--core-root", type=Path, help="local exact-commit template tree for offline tests")
    parser.add_argument("--deployer-core-root", type=Path, help="local exact-commit deployer tree for offline tests")
    parser.add_argument("--standalone-root", type=Path, default=ROOT)
    parser.add_argument("--derived", action="store_true", help="verify adopter deployer identity without upstream byte comparisons")
    args = parser.parse_args()
    if not unittest.TextTestRunner().run(
        unittest.defaultTestLoader.loadTestsFromTestCase(UpstreamRepositoryTests)
    ).wasSuccessful():
        return 1
    try:
        verify_deployer_contract(args.standalone_root, args.deployer_core_root)
    except (RuntimeError, OSError, ValueError, KeyError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1
    print(f"OK: external staging-deployer contract pinned to {DEPLOYER_CORE_COMMIT}")
    if args.derived or (args.standalone_root == ROOT and not is_upstream_repository(ROOT)):
        print("OK: ordinary-CI byte comparisons apply only to upstream; adopter deployer identity verified")
        return 0
    errors: list[str] = []
    used_allowlist: set[str] = set()
    actual_files = {
        path.relative_to(args.standalone_root).as_posix()
        for path in args.standalone_root.rglob("*")
        if path.is_file()
        and ".git" not in path.relative_to(args.standalone_root).parts
        and "__pycache__" not in path.relative_to(args.standalone_root).parts
        and path.suffix != ".pyc"
    }
    optional_files = {".github/workflows/validate.yml"}
    if actual_files - optional_files != STANDALONE_FILES - optional_files:
        errors.append(
            "tree membership differs: "
            f"missing={sorted(STANDALONE_FILES - optional_files - actual_files)} "
            f"unexpected={sorted(actual_files - STANDALONE_FILES)}"
        )
    for relative in EXACT_FILES:
        standalone = (args.standalone_root / relative).read_bytes()
        embedded = core_bytes(relative, args.core_root)
        if standalone != embedded:
            digest = hashlib.sha256(standalone).hexdigest()
            allowed = ALLOWED_STANDALONE_HASHES.get(relative)
            if allowed and allowed[0] == digest:
                core_digest = hashlib.sha256(embedded).hexdigest()
                if allowed[1] == core_digest:
                    used_allowlist.add(relative)
                else:
                    errors.append(f"{relative}: reviewed core bytes differ; core sha256={core_digest}")
            else:
                errors.append(f"{relative}: differs from ci-fleet {CORE_COMMIT}; standalone sha256={digest}")
    for relative in CONFIG_FILES:
        standalone_raw = (args.standalone_root / relative).read_bytes()
        standalone = normalized_config(standalone_raw)
        embedded_raw = core_bytes(relative, args.core_root)
        embedded = normalized_config(embedded_raw)
        if standalone != embedded:
            digest = hashlib.sha256(standalone_raw).hexdigest()
            allowed = ALLOWED_STANDALONE_HASHES.get(relative)
            if allowed and allowed[0] == digest:
                core_digest = hashlib.sha256(embedded_raw).hexdigest()
                if allowed[1] == core_digest:
                    used_allowlist.add(relative)
                else:
                    errors.append(f"{relative}: reviewed core bytes differ; core sha256={core_digest}")
            else:
                errors.append(
                    f"{relative}: differs beyond the example engine_ref; standalone sha256={digest}"
                )
    unused_allowlist = sorted(ALLOWED_STANDALONE_HASHES.keys() - used_allowlist)
    if unused_allowlist:
        errors.append(f"unused standalone hash allowlist entries: {unused_allowlist}")
    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1
    try:
        verify_pinned_consumer_staging(args.core_root)
    except (RuntimeError, OSError, ValueError, KeyError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1
    print(f"OK: standalone contract matches embedded template at {CORE_COMMIT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
