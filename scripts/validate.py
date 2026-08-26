#!/usr/bin/env python3
"""Validate a ci-fleet organization configuration without third-party packages."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
SLUG = re.compile(r"^[a-z0-9][a-z0-9-]{0,62}$")
ORG_SLUG = re.compile(r"^[a-z0-9][a-z0-9-]{0,38}$")
REPOSITORY = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
IMAGE = re.compile(r"^[a-z0-9.-]+/[a-z0-9._/-]+$")
SECRET_NAME = re.compile(r"^[A-Z][A-Z0-9_]*$")
COMMIT_SHA = re.compile(r"^[0-9a-f]{40}$")
HIGH_CONFIDENCE_SECRET_PATTERNS = (
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    re.compile(r"github_pat_[A-Za-z0-9_]{20,}"),
    re.compile(r"gh[opusr]_[A-Za-z0-9]{20,}"),
    re.compile(r"AKIA[0-9A-Z]{16}"),
    re.compile(r"(?:postgres|mysql|mongodb(?:\+srv)?|redis)://[^\s/:]+:[^\s/@]+@"),
)
FORBIDDEN_SECRET_KEYS = {
    "access_token",
    "api_key",
    "credential",
    "credentials",
    "database_url",
    "password",
    "private_key",
    "secret",
    "secret_value",
    "token",
}
FORBIDDEN_INFRASTRUCTURE_KEYS = {
    "backup_id",
    "backup_snapshot",
    "backup_storage",
    "disk_storage",
    "host_address",
    "hostname",
    "ip",
    "ip_address",
    "proxmox_vmid",
    "ssh_host",
    "ssh_password",
    "ssh_private_key",
    "vm_id",
    "vmid",
}
FORBIDDEN_FILENAMES = re.compile(r"(?:^|/)(?:\.env(?:\..+)?|host\.env|ci-fleet\.env)$|\.(?:key|pem|p12|pfx)$", re.IGNORECASE)
FORBIDDEN_DIRECTORIES = {"credentials", "private", "secrets"}


class Validation:
    def __init__(self) -> None:
        self.errors: list[str] = []

    def require(self, condition: bool, path: str, message: str) -> None:
        if not condition:
            self.errors.append(f"{path}: {message}")

    def exact_keys(self, value: Any, path: str, required: set[str], optional: set[str] | None = None) -> bool:
        if not isinstance(value, dict):
            self.errors.append(f"{path}: must be an object")
            return False
        optional = optional or set()
        keys = set(value)
        missing = required - keys
        unknown = keys - required - optional
        if missing:
            self.errors.append(f"{path}: missing keys: {', '.join(sorted(missing))}")
        if unknown:
            self.errors.append(f"{path}: unknown keys: {', '.join(sorted(unknown))}")
        return not missing


def load_json(path: Path, validation: Validation) -> Any:
    def reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        value: dict[str, Any] = {}
        for key, child in pairs:
            if key in value:
                raise ValueError(f"duplicate object key: {key}")
            value[key] = child
        return value

    try:
        return json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=reject_duplicate_keys)
    except FileNotFoundError:
        validation.errors.append(f"{path}: file not found")
    except json.JSONDecodeError as exc:
        validation.errors.append(f"{path}:{exc.lineno}:{exc.colno}: invalid JSON: {exc.msg}")
    except ValueError as exc:
        validation.errors.append(f"{path}: invalid JSON: {exc}")
    return None


def strings_in(value: Any, path: str = "$"):
    if isinstance(value, dict):
        for key, child in value.items():
            yield from strings_in(child, f"{path}.{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            yield from strings_in(child, f"{path}[{index}]")
    elif isinstance(value, str):
        yield path, value


def scan_secret_material(config: Any, validation: Validation) -> None:
    def scan_keys(value: Any, path: str = "$") -> None:
        if isinstance(value, dict):
            for key, child in value.items():
                normalized = key.lower()
                if normalized in FORBIDDEN_SECRET_KEYS:
                    validation.errors.append(
                        f"{path}.{key}: secret values are forbidden; store only an uppercase secret name"
                    )
                if normalized in FORBIDDEN_INFRASTRUCTURE_KEYS:
                    validation.errors.append(
                        f"{path}.{key}: host-local infrastructure details are forbidden in Git-authored policy"
                    )
                scan_keys(child, f"{path}.{key}")
        elif isinstance(value, list):
            for index, child in enumerate(value):
                scan_keys(child, f"{path}[{index}]")

    scan_keys(config)
    for path, value in strings_in(config):
        for pattern in HIGH_CONFIDENCE_SECRET_PATTERNS:
            if pattern.search(value):
                validation.errors.append(f"{path}: probable secret material is forbidden")
                break


def scan_forbidden_paths(repo_root: Path, validation: Validation) -> None:
    for path in repo_root.rglob("*"):
        try:
            relative = path.relative_to(repo_root)
        except ValueError:
            continue
        if ".git" in relative.parts:
            continue
        relative_text = relative.as_posix()
        if path.is_dir() and path.name.lower() in FORBIDDEN_DIRECTORIES:
            validation.errors.append(f"{relative_text}/: secret-bearing directory names are forbidden")
        elif path.is_file() and FORBIDDEN_FILENAMES.search(relative_text):
            validation.errors.append(f"{relative_text}: secret-bearing files are forbidden")


def scan_tree_path_list(path_list: Path, validation: Validation) -> None:
    try:
        raw_paths = path_list.read_bytes().split(b"\0")
    except OSError as error:
        validation.errors.append(f"{path_list}: cannot read tree path list: {error}")
        return
    for raw_path in raw_paths:
        if not raw_path:
            continue
        try:
            relative_text = raw_path.decode("utf-8")
        except UnicodeDecodeError:
            validation.errors.append("repository tree contains a non-UTF-8 path")
            continue
        parts = Path(relative_text).parts
        if any(part.lower() in FORBIDDEN_DIRECTORIES for part in parts[:-1]):
            validation.errors.append(f"{relative_text}: secret-bearing directory names are forbidden")
        elif FORBIDDEN_FILENAMES.search(relative_text):
            validation.errors.append(f"{relative_text}: secret-bearing files are forbidden")


def evidence_tokens(text: str) -> list[str]:
    """Tokenize approval evidence, splitting on every non-token separator.

    Punctuation must not let evidence name a CI identity beside run-output
    context (``trusted-ci/job-log``, ``trusted-ci: job log``), so any
    character that is not a slug token character acts as a delimiter and
    hyphens inside tokens are normalized to spaces.
    """
    return [
        re.sub(r"[-_]+", " ", chunk).strip()
        for chunk in re.split(r"[^0-9a-z]+", text.lower())
        if chunk
    ]


# ponytail: phrase + marker-word heuristic — it fails closed on evidence
# that names the CI identity and mentions run-output words, but cannot parse
# meaning; replace with structured evidence fields (type + locator) if
# false positives ever matter.
EVIDENCE_RUN_OUTPUT_MARKERS = frozenset({
    "artifact", "artifacts", "action", "actions", "check", "checks",
    "console", "job", "jobs", "log", "logs",
    "output", "run", "runner", "runners", "runs", "stdout",
    "workflow", "workflows",
})

def _split_ipv6_zone(address: str) -> tuple[str, str]:
    if "%25" in address:
        address, zone = address.split("%25", 1)
        return address, zone
    if "%" in address:
        address, zone = address.split("%", 1)
        return address, zone
    return address, ""


def evidence_contains_bare_ipv6(text: str) -> bool:
    for token in text.split():
        if token.startswith("[") and token.endswith("]"):
            continue
        candidate, _ = _split_ipv6_zone(token)
        if candidate.count(":") >= 2 and re.fullmatch(r"[0-9a-f:]+", candidate, re.IGNORECASE):
            return True
    return False


FORBIDDEN_CREDENTIAL_USERINFO = re.compile(r"//[^@/\s]+:[^@/\s]+@")


def evidence_contains_credentials(text: str) -> bool:
    return bool(FORBIDDEN_CREDENTIAL_USERINFO.search(text))


# Host-local infrastructure details must never enter the Git-authored
# configuration through the free-form evidence locator (AGENTS.md).
FORBIDDEN_EVIDENCE_ADDRESS = re.compile(
    r"(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}"
    r"|\[[0-9a-f:]+%?[^\]]*\]"  # bracketed IPv6 with optional zone
    r"|[a-z0-9-]+(?:\.[a-z0-9-]+){2,}"  # >=3-label hostname
    r"|[a-z0-9-]+(?:\.[a-z0-9-]+)*\.(?:internal|local|lan|corp|private|home|intranet)\b)",
    re.IGNORECASE,
)


def evidence_names_ci_state(evidence: str, identity: str) -> bool:
    """True when the evidence names the complete CI identity phrase.

    The identity must appear as a contiguous ordered token phrase (its
    hyphen components normalized to words) anywhere in the evidence, and
    run-output vocabulary must also occur somewhere. Splitting the two by
    prose does not help: evidence that names the CI workflow log as its
    approval record is self-approval regardless of distance (Codex, PR #14).
    """
    tokens = evidence_tokens(evidence)
    wanted = evidence_tokens(identity)
    if not wanted:
        return False
    span = len(wanted)
    for start in range(len(tokens) - span + 1):
        if tokens[start:start + span] == wanted:
            return bool(set(tokens) & EVIDENCE_RUN_OUTPUT_MARKERS)
    return False


def validate_config(config: Any, validation: Validation, strict: bool) -> None:
    required_top = {
        "schema_version",
        "organization",
        "runner_pools",
        "controllers",
        "host_groups",
        "environments",
        "projects",
    }
    if not validation.exact_keys(config, "$", required_top, {"$schema"}):
        return

    validation.require(config.get("schema_version") == 3, "$.schema_version", "must equal 3")

    organization = config.get("organization")
    organization_keys = {"slug", "registry", "delivery_engine", "workflow_ref_policy"}
    if validation.exact_keys(organization, "$.organization", organization_keys, {"github_plan"}):
        slug = organization.get("slug")
        registry = organization.get("registry")
        engine = organization.get("delivery_engine")
        validation.require(isinstance(slug, str) and bool(ORG_SLUG.fullmatch(slug)), "$.organization.slug", "must be a lowercase GitHub organization slug")
        validation.require(isinstance(registry, str) and bool(IMAGE.fullmatch(registry)), "$.organization.registry", "must be a registry namespace such as ghcr.io/acme")
        validation.require(isinstance(engine, str) and bool(REPOSITORY.fullmatch(engine)), "$.organization.delivery_engine", "must be an owner/repository name")
        validation.require(engine == "RandomDevelopment/ci-fleet", "$.organization.delivery_engine", "must use the fixed reviewed public engine repository")
        validation.require(organization.get("workflow_ref_policy") == "immutable-commit", "$.organization.workflow_ref_policy", "must equal immutable-commit")
        plan = organization.get("github_plan")
        validation.require(plan is None or (isinstance(plan, str) and plan in {"free", "team", "enterprise"}), "$.organization.github_plan", "must be free, team, or enterprise; omitted means free")
        if strict:
            validation.require(slug != "example-org", "$.organization.slug", "replace the example organization before use")

    pools = config.get("runner_pools")
    if not isinstance(pools, dict) or not pools:
        validation.errors.append("$.runner_pools: must be a non-empty object")
        pools = {}
    pool_capacity: dict[str, int] = {}
    runner_groups: dict[str, str] = {}
    for name, pool in pools.items():
        path = f"$.runner_pools.{name}"
        validation.require(isinstance(name, str) and bool(SLUG.fullmatch(name)), path, "pool name must be a lowercase slug")
        pool_keys = {
            "runner_group",
            "routing_labels",
            "allowed_repositories",
            "public_repositories",
            "capacity_budget",
            "job_submission_policy",
        }
        if not validation.exact_keys(pool, path, pool_keys):
            continue
        runner_group = pool.get("runner_group")
        labels = pool.get("routing_labels")
        repos = pool.get("allowed_repositories")
        validation.require(isinstance(runner_group, str) and bool(SLUG.fullmatch(runner_group)), f"{path}.runner_group", "must be a lowercase logical runner-group slug")
        if isinstance(runner_group, str) and SLUG.fullmatch(runner_group):
            if runner_group in runner_groups:
                validation.errors.append(f"{path}.runner_group: must be unique; also used by {runner_groups[runner_group]}")
            else:
                runner_groups[runner_group] = name
        validation.require(isinstance(labels, list) and bool(labels), f"{path}.routing_labels", "must be a non-empty list")
        if isinstance(labels, list):
            validation.require(len(labels) == len(set(labels)), f"{path}.routing_labels", "must contain unique labels")
            for index, label in enumerate(labels):
                validation.require(isinstance(label, str) and bool(SLUG.fullmatch(label)), f"{path}.routing_labels[{index}]", "must be a lowercase slug")
                validation.require(str(label).lower() != "self-hosted", f"{path}.routing_labels[{index}]", "do not repeat GitHub's implicit self-hosted label")
        validation.require(isinstance(repos, list) and bool(repos), f"{path}.allowed_repositories", "must be a non-empty list")
        if isinstance(repos, list):
            validation.require(len(repos) == len(set(repos)), f"{path}.allowed_repositories", "must contain unique repositories")
            for index, repository in enumerate(repos):
                validation.require(isinstance(repository, str) and bool(REPOSITORY.fullmatch(repository)), f"{path}.allowed_repositories[{index}]", "must be owner/repository")
        validation.require(pool.get("public_repositories") is False, f"{path}.public_repositories", "must be false; this fleet is for trusted private repositories")
        budget = pool.get("capacity_budget")
        validation.require(type(budget) is int and budget > 0, f"{path}.capacity_budget", "must be a positive infrastructure capacity budget")
        if type(budget) is int and budget > 0:
            pool_capacity[name] = budget
        validation.require(pool.get("job_submission_policy") == "all-independent-jobs", f"{path}.job_submission_policy", "must submit every independent job and leave capacity control to infrastructure")

    controllers = config.get("controllers")
    if not isinstance(controllers, dict) or not controllers:
        validation.errors.append("$.controllers: must be a non-empty object")
        controllers = {}
    reserved_capacity = {name: 0 for name in pools}
    scale_sets: dict[str, str] = {}
    controller_keys = {
        "pool",
        "location",
        "state",
        "scale_set_name",
        "lifecycle",
        "engine_ref",
        "min_runners",
        "max_runners",
        "runner_resources",
    }
    for name, controller in controllers.items():
        path = f"$.controllers.{name}"
        validation.require(isinstance(name, str) and bool(SLUG.fullmatch(name)), path, "controller ID must be a unique lowercase slug")
        if not validation.exact_keys(controller, path, controller_keys):
            continue
        pool_name = controller.get("pool")
        location = controller.get("location")
        state = controller.get("state")
        scale_set = controller.get("scale_set_name")
        lifecycle = controller.get("lifecycle")
        engine_ref = controller.get("engine_ref")
        minimum = controller.get("min_runners")
        maximum = controller.get("max_runners")
        validation.require(isinstance(pool_name, str) and pool_name in pools, f"{path}.pool", "must reference a declared runner pool")
        validation.require(isinstance(location, str) and bool(SLUG.fullmatch(location)), f"{path}.location", "must be a logical location slug, never an address")
        validation.require(state in {"active", "drained", "disabled"} if isinstance(state, str) else False, f"{path}.state", "must be active, drained, or disabled")
        validation.require(isinstance(scale_set, str) and bool(SLUG.fullmatch(scale_set)), f"{path}.scale_set_name", "must be a lowercase scale-set slug")
        if isinstance(scale_set, str) and isinstance(name, str):
            validation.require(name in scale_set, f"{path}.scale_set_name", "must include the controller ID required by managed preflight")
        if isinstance(scale_set, str):
            if scale_set in scale_sets:
                validation.errors.append(f"{path}.scale_set_name: must be unique; also used by {scale_sets[scale_set]}")
            else:
                scale_sets[scale_set] = name
        validation.require(lifecycle in {"experimental", "stable", "retiring"} if isinstance(lifecycle, str) else False, f"{path}.lifecycle", "must be experimental, stable, or retiring")
        validation.require(isinstance(engine_ref, str) and bool(COMMIT_SHA.fullmatch(engine_ref)) and engine_ref != "0" * 40, f"{path}.engine_ref", "must be a nonzero full lowercase commit SHA")
        validation.require(type(minimum) is int and minimum >= 0, f"{path}.min_runners", "must be a non-negative integer")
        validation.require(type(maximum) is int and maximum > 0, f"{path}.max_runners", "must be a positive integer")
        if type(minimum) is int and type(maximum) is int:
            validation.require(minimum <= maximum, f"{path}.min_runners", "must not exceed max_runners")
        validation.require(minimum == 0, f"{path}.min_runners", "must be zero because managed prewarmed runners are not supported")
        resources = controller.get("runner_resources")
        if validation.exact_keys(resources, f"{path}.runner_resources", {"cpu_cores", "memory_mib"}):
            cpu = resources.get("cpu_cores")
            memory = resources.get("memory_mib")
            validation.require(type(cpu) is int and cpu > 0, f"{path}.runner_resources.cpu_cores", "must be a positive integer")
            validation.require(type(memory) is int and memory >= 512, f"{path}.runner_resources.memory_mib", "must be at least 512 MiB")
        if isinstance(pool_name, str) and pool_name in pools and state != "disabled" and type(maximum) is int and maximum > 0:
            reserved_capacity[pool_name] += maximum

    for pool_name, pool in pools.items():
        labels = pool.get("routing_labels") if isinstance(pool, dict) else None
        if isinstance(labels, list):
            for index, label in enumerate(labels):
                if isinstance(label, str):
                    validation.require(label not in scale_sets, f"$.runner_pools.{pool_name}.routing_labels[{index}]", "must not equal a controller scale-set name")

    for name, reserved in reserved_capacity.items():
        budget = pool_capacity.get(name)
        if budget is not None:
            validation.require(reserved <= budget, f"$.runner_pools.{name}.capacity_budget", f"must cover {reserved} runners reserved by active or drained controllers")

    groups = config.get("host_groups")
    if not isinstance(groups, dict) or not groups:
        validation.errors.append("$.host_groups: must be a non-empty object")
        groups = {}
    for name, group in groups.items():
        path = f"$.host_groups.{name}"
        validation.require(bool(SLUG.fullmatch(name)), path, "host group name must be a lowercase slug")
        if validation.exact_keys(group, path, {"role", "environment_class"}):
            role = group.get("role")
            validation.require(isinstance(role, str) and role in {"deployment", "persistent-testing", "image-build"}, f"{path}.role", "must be deployment, persistent-testing, or image-build; ordinary CI pools never carry a privileged role")
            environment_class = group.get("environment_class")
            validation.require(isinstance(environment_class, str) and environment_class in {"development", "staging", "production"}, f"{path}.environment_class", "must be development, staging, or production")

    # Ordinary-CI routing labels are the only way a project workflow selects its
    # runners; a privileged host group reusing one would let unprivileged jobs
    # route onto privileged hosts. JSON Schema cannot compare across objects.
    # Every declared host group is privileged relative to ordinary CI,
    # deployment groups included.
    privileged_identities = {role for role in ("deployment", "persistent-testing", "image-build")}
    privileged_identities.update(name for name, group in groups.items() if isinstance(group, dict))
    ci_labels: dict[str, str] = {}
    for pool_name, pool in pools.items():
        labels = pool.get("routing_labels") if isinstance(pool, dict) else None
        if not isinstance(labels, list):
            continue
        for index, label in enumerate(labels):
            if isinstance(label, str):
                other = ci_labels.get(label)
                validation.require(
                    other is None,
                    f"$.runner_pools.{pool_name}.routing_labels[{index}]",
                    f"must be unique across pools; also used by {other}" if other else "must be unique across pools",
                )
                if other is None:
                    ci_labels[label] = pool_name
                if label in privileged_identities:
                    validation.require(False, f"$.runner_pools.{pool_name}.routing_labels[{index}]", f"must not collide with privileged host-group identity {label}")

    plan = config.get("organization", {}).get("github_plan") if isinstance(config.get("organization"), dict) else None
    environment_capable = plan == "enterprise"

    environments = config.get("environments")
    if not isinstance(environments, dict) or not environments:
        validation.errors.append("$.environments: must be a non-empty object")
        environments = {}
    for name, environment in environments.items():
        path = f"$.environments.{name}"
        validation.require(bool(SLUG.fullmatch(name)), path, "environment name must be a lowercase slug")
        if not validation.exact_keys(
            environment,
            path,
            {"host_group", "automatic", "requires_approval", "required_secret_names"},
            {"approval_mechanism", "approval_evidence"},
        ):
            continue
        host_group = environment.get("host_group")
        validation.require(host_group in groups, f"{path}.host_group", "must reference a declared deployment host group")
        referenced_group = groups.get(host_group) if isinstance(groups.get(host_group), dict) else None
        if referenced_group is not None:
            validation.require(
                referenced_group.get("role") == "deployment",
                f"{path}.host_group",
                "must reference a deployment-role host group; environments deploy only from deployment hosts",
            )
        validation.require(type(environment.get("automatic")) is bool, f"{path}.automatic", "must be a boolean")
        requires_approval = environment.get("requires_approval")
        validation.require(type(requires_approval) is bool, f"{path}.requires_approval", "must be a boolean")
        mechanism = environment.get("approval_mechanism")
        validation.require(mechanism is None or (isinstance(mechanism, str) and mechanism in {"github-environment", "manual-external"}), f"{path}.approval_mechanism", "must be github-environment or manual-external")
        declared_mechanism = mechanism if mechanism is not None else None
        legacy_omission = "approval_mechanism" not in environment
        if mechanism is None and not legacy_omission:
            # An explicit null is a malformed value, not legacy field
            # omission; it must not inherit the schema-v3 compatibility
            # exception (Codex, PR #14 round 5).
            validation.require(False, f"{path}.approval_mechanism", "must be github-environment or manual-external")
        if mechanism is None:
            # Schema-v3 compatibility: absent approval_mechanism infers the
            # fail-closed gate instead of rejecting every existing adopter
            # configuration (Codex finding, PR #14).
            mechanism = "github-environment" if environment_capable else "manual-external"
        evidence_present = "approval_evidence" in environment
        evidence = environment.get("approval_evidence")
        validation.require(
            (not evidence_present and evidence is None) or (isinstance(evidence, str) and bool(evidence.strip())),
            f"{path}.approval_evidence",
            "must be a logical reference to where exact-head approval is recorded, never a secret value",
        )
        if mechanism == "github-environment" and not environment_capable:
            validation.require(False, f"{path}.approval_mechanism", "github-environment required-reviewer approval requires organization.github_plan enterprise; protected Environments and required reviewers are unavailable for private repositories on Free and Team — use manual-external")
        if mechanism == "manual-external" and requires_approval and not isinstance(evidence, str):
            # Legacy schema-v3 compatibility: only environments that omit
            # BOTH new fields (approval_mechanism and approval_evidence) are
            # tolerated without evidence; an explicitly selected manual gate
            # must record its locator in every mode (Codex, PR #14 round 3).
            if declared_mechanism is not None or strict:
                validation.require(False, f"{path}.approval_evidence", "manual-external approval must record where the exact-head approval is kept")
        if isinstance(evidence, str) and "REPLACE-ME:" in evidence:
            # The initializer's placeholder: it names no actual approval
            # record, so strict mode refuses to bless it (Codex, PR #14
            # round 3). Non-strict stays silent for legacy import paths.
            if strict:
                validation.require(False, f"{path}.approval_evidence", "is an initializer placeholder; record a real approval locator (ticket, path, or system reference)")
        if isinstance(evidence, str):
            validation.require(
                evidence_contains_credentials(evidence) is False,
                f"{path}.approval_evidence",
                "must not contain credential-bearing URI userinfo",
            )
            validation.require(
                not evidence_contains_bare_ipv6(evidence),
                f"{path}.approval_evidence",
                "must not contain host addresses or internal hostnames; reference the approval record by ticket, path, or system name only (AGENTS.md forbids infrastructure details in configuration)",
            )
            validation.require(
                FORBIDDEN_EVIDENCE_ADDRESS.search(evidence) is None,
                f"{path}.approval_evidence",
                "must not contain host addresses or internal hostnames; reference the approval record by ticket, path, or system name only (AGENTS.md forbids infrastructure details in configuration)",
            )
            for pool_name, pool in pools.items():
                if not isinstance(pool, dict):
                    continue
                identities = {str(pool_name), str(pool.get("runner_group") or "")}
                labels = pool.get("routing_labels")
                if isinstance(labels, list):
                    identities.update(str(label) for label in labels if isinstance(label, str))
                hit = next((identity for identity in identities if evidence_names_ci_state(evidence, identity)), None)
                if hit is None:
                    # Controller IDs and scale-set names are ordinary-CI
                    # identities too: their workflow logs are self-approval
                    # evidence just like pool outputs (Codex, PR #14).
                    controllers = config.get("controllers")
                    controller_ids = list(controllers) if isinstance(controllers, dict) else []
                    scale_sets = [
                        str(controller.get("scale_set_name"))
                        for controller in controllers.values()
                        if isinstance(controllers, dict) and isinstance(controller, dict) and controller.get("scale_set_name")
                    ]
                    hit = next(
                        (
                            identity
                            for identity in (*controller_ids, *scale_sets)
                            if evidence_names_ci_state(evidence, identity)
                        ),
                        None,
                    )
                validation.require(
                    hit is None,
                    f"{path}.approval_evidence",
                    f"must not name ordinary-CI state ({hit}) as its own approval; approval evidence lives outside the requesting CI identity",
                )
        names = environment.get("required_secret_names")
        validation.require(isinstance(names, list), f"{path}.required_secret_names", "must be a list")
        if isinstance(names, list):
            validation.require(len(names) == len(set(names)), f"{path}.required_secret_names", "must contain unique names")
            for index, secret_name in enumerate(names):
                validation.require(isinstance(secret_name, str) and bool(SECRET_NAME.fullmatch(secret_name)), f"{path}.required_secret_names[{index}]", "must be an uppercase secret name, never a value")
        if host_group in groups and isinstance(groups.get(host_group), dict) and groups[host_group].get("environment_class") == "production":
            validation.require(environment.get("automatic") is False, f"{path}.automatic", "production deployment must not be automatic")
            validation.require(environment.get("requires_approval") is True, f"{path}.requires_approval", "production deployment must require approval")

    projects = config.get("projects")
    if not isinstance(projects, dict) or not projects:
        validation.errors.append("$.projects: must be a non-empty object")
        projects = {}
    for name, project in projects.items():
        path = f"$.projects.{name}"
        validation.require(bool(SLUG.fullmatch(name)), path, "project name must be a lowercase slug")
        if not validation.exact_keys(project, path, {"repository", "image", "ci_pool", "ci_contract", "deployments"}):
            continue
        repository = project.get("repository")
        image = project.get("image")
        pool_name = project.get("ci_pool")
        validation.require(isinstance(repository, str) and bool(REPOSITORY.fullmatch(repository)), f"{path}.repository", "must be owner/repository")
        validation.require(isinstance(image, str) and bool(IMAGE.fullmatch(image)), f"{path}.image", "must be a container image path without a mutable tag")
        validation.require(isinstance(pool_name, str) and pool_name in pools, f"{path}.ci_pool", "must reference a declared runner pool")
        if isinstance(pool_name, str) and pool_name in pools and isinstance(pools[pool_name].get("allowed_repositories"), list):
            validation.require(repository in pools[pool_name]["allowed_repositories"], f"{path}.repository", "must be explicitly allowed by its CI pool")
        contract = project.get("ci_contract")
        contract_path = f"{path}.ci_contract"
        contract_keys = {
            "runner_entrypoint",
            "task_plan",
            "aggregate_entrypoints",
            "target_wall_clock_minutes",
            "max_job_minutes",
            "shard_target_minutes",
        }
        if validation.exact_keys(contract, contract_path, contract_keys):
            validation.require(contract.get("runner_entrypoint") == "./scripts/ci/run.sh", f"{contract_path}.runner_entrypoint", "must use the standard task runner")
            validation.require(contract.get("task_plan") == "./scripts/ci/plan.json", f"{contract_path}.task_plan", "must use the standard task-plan path")
            validation.require(contract.get("target_wall_clock_minutes") == 5, f"{contract_path}.target_wall_clock_minutes", "must equal the five-minute fleet goal")
            validation.require(contract.get("max_job_minutes") == 5, f"{contract_path}.max_job_minutes", "must enforce a five-minute hard job ceiling")
            shard_target = contract.get("shard_target_minutes")
            validation.require(type(shard_target) is int and 1 <= shard_target <= 4, f"{contract_path}.shard_target_minutes", "must be between one and four minutes to reserve startup time")
            entrypoints = contract.get("aggregate_entrypoints")
            aggregate_path = f"{contract_path}.aggregate_entrypoints"
            if validation.exact_keys(entrypoints, aggregate_path, {"fast", "full"}):
                validation.require(entrypoints.get("fast") == "./scripts/ci/run.sh fast", f"{aggregate_path}.fast", "must use the standard aggregate fast entrypoint")
                validation.require(entrypoints.get("full") == "./scripts/ci/run.sh full", f"{aggregate_path}.full", "must use the standard aggregate full entrypoint")
        deployments = project.get("deployments")
        validation.require(isinstance(deployments, list) and bool(deployments), f"{path}.deployments", "must be a non-empty list")
        if isinstance(deployments, list):
            validation.require(len(deployments) == len(set(deployments)), f"{path}.deployments", "must contain unique environments")
            for index, deployment in enumerate(deployments):
                validation.require(deployment in environments, f"{path}.deployments[{index}]", "must reference a declared environment")
        if strict:
            validation.require(repository != "example-org/example-app", f"{path}.repository", "replace the example repository before use")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=ROOT / "fleet.json", help="configuration file to validate")
    parser.add_argument("--strict", action="store_true", help="reject unchanged example values")
    parser.add_argument("--skip-path-scan", action="store_true", help="skip repository path checks (for external fixtures)")
    parser.add_argument("--tree-paths", type=Path, help="NUL-delimited committed paths to scan instead of the local template tree")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    validation = Validation()
    config = load_json(args.config.resolve(), validation)
    schema = load_json(ROOT / "fleet.schema.json", validation)
    if schema is not None:
        validation.require(schema.get("$schema") == "https://json-schema.org/draft/2020-12/schema", "fleet.schema.json.$schema", "must use JSON Schema draft 2020-12")
    if config is not None:
        scan_secret_material(config, validation)
        validate_config(config, validation, args.strict)
    if args.tree_paths is not None:
        scan_tree_path_list(args.tree_paths, validation)
    elif not args.skip_path_scan:
        scan_forbidden_paths(ROOT, validation)

    if validation.errors:
        for error in validation.errors:
            print(f"ERROR: {error}", file=sys.stderr)
        print(f"FAILED: {len(validation.errors)} validation error(s)", file=sys.stderr)
        return 1
    print(f"OK: {args.config} satisfies the ci-fleet configuration contract")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
