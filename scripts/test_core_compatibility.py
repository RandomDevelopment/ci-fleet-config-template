#!/usr/bin/env python3
"""Fail when the standalone contract drifts from one reviewed embedded template."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import urllib.request
from pathlib import Path

CORE_COMMIT = "0aed0d7e85e10050028b7d11fb12b84b3619e638"
CORE_PREFIX = "templates/config-repository"
ROOT = Path(__file__).resolve().parents[1]
STANDALONE_FILES = {
    ".github/dependabot.yml",
    ".github/workflows/validate.yml",
    ".gitignore",
    "AGENTS.md",
    "LICENSE",
    "README.md",
    "SECURITY.md",
    "THIRD_PARTY_NOTICES.md",
    "docs/RELEASE.md",
    "docs/UPDATING.md",
    "engine-rollout-evidence.json",
    "examples/multi-host/fleet.json",
    "fleet.json",
    "fleet.schema.json",
    "scripts/init.py",
    "scripts/init.sh",
    "scripts/scan_committed_secrets.py",
    "scripts/test_core_compatibility.py",
    "scripts/test_policy.py",
    "scripts/test_release_update.py",
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
    "scripts/init.py": (
        "bb47f464763be1324f13af6bd64b3017e085103f2e0c1637b7d66c33e01b3c46",
        "0acf5b340317d3b9f97ae7c0686d7c6e0513e2084f9aeb295bc3d96b90fbe5dd",
    ),
    "scripts/validate.py": (
        "a86a7fc4d9cc6aaf5098c5ef37808f5d5dc76a0e49b7a7d967f23043f4ecd122",
        "3c202840ce00ae31568d3ac2137cd1acdebf5ff9fa8807b9823e4310c9e39568",
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


def is_upstream_repository(root: Path) -> bool:
    origin = subprocess.run(
        ["git", "-C", str(root), "remote", "get-url", "origin"],
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
    )
    return not origin.returncode and origin.stdout.strip().removesuffix(".git").endswith(
        "RandomDevelopment/ci-fleet-config-template"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--core-root", type=Path, help="local exact-commit template tree for offline tests")
    parser.add_argument("--standalone-root", type=Path, default=ROOT)
    args = parser.parse_args()
    if args.standalone_root == ROOT and not is_upstream_repository(ROOT):
        print("OK: exact core compatibility is upstream-only; skipped for derived repository")
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
    if actual_files != STANDALONE_FILES:
        errors.append(
            "tree membership differs: "
            f"missing={sorted(STANDALONE_FILES - actual_files)} "
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
    print(f"OK: standalone contract matches embedded template at {CORE_COMMIT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
