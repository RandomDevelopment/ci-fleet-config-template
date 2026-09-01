#!/usr/bin/env python3
"""Fail when the standalone contract drifts from one reviewed embedded template."""

from __future__ import annotations

import argparse
import json
import sys
import urllib.request
from pathlib import Path

CORE_COMMIT = "0aed0d7e85e10050028b7d11fb12b84b3619e638"
CORE_PREFIX = "templates/config-repository"
ROOT = Path(__file__).resolve().parents[1]
EXACT_FILES = (
    "fleet.schema.json",
    "engine-rollout-evidence.json",
    "scripts/init.py",
    "scripts/validate.py",
)
CONFIG_FILES = ("fleet.json", "examples/multi-host/fleet.json")


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


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--core-root", type=Path, help="local exact-commit template tree for offline tests")
    parser.add_argument("--standalone-root", type=Path, default=ROOT)
    args = parser.parse_args()
    errors: list[str] = []
    for relative in EXACT_FILES:
        if (args.standalone_root / relative).read_bytes() != core_bytes(relative, args.core_root):
            errors.append(f"{relative}: differs from ci-fleet {CORE_COMMIT}")
    for relative in CONFIG_FILES:
        standalone = normalized_config((args.standalone_root / relative).read_bytes())
        embedded = normalized_config(core_bytes(relative, args.core_root))
        if standalone != embedded:
            errors.append(f"{relative}: differs beyond the allowlisted example engine_ref")
    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1
    print(f"OK: standalone contract matches embedded template at {CORE_COMMIT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
