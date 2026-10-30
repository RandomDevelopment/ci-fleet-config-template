#!/usr/bin/env python3
"""Propose one reviewed template release update without running imported code."""

from __future__ import annotations

import json
import os
import re
import subprocess
import tempfile
from pathlib import Path
from urllib.parse import quote

UPSTREAM = "RandomDevelopment/ci-fleet-config-template"
SOURCE = f"https://github.com/{UPSTREAM}.git"
BRANCH = "automation/template-update"
STATUS = ".github/template-update-status.json"
SETTINGS = ".github/template-updater.json"
PRESERVED = {"fleet.json", "engine-rollout-evidence.json", "next-engine-rollout-evidence.json", SETTINGS}
INITIAL_OID = "0e54aaa09d0565ce103035f213953639fc068a73"
SEMVER = re.compile(r"v(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\Z")
OID = re.compile(r"[0-9a-f]{40}\Z")


def run(*args: str, input: bytes | None = None, env: dict | None = None) -> bytes:
    result = subprocess.run(args, input=input, capture_output=True, env=env, timeout=45)
    if result.returncode:
        # Do not echo command output: an authentication failure may contain credentials.
        raise RuntimeError(f"{args[0]} {args[1]} failed with exit code {result.returncode}")
    return result.stdout


def git(*args: str, **kwargs) -> str:
    return run("git", *args, **kwargs).decode().strip()


def api(path: str):
    return json.loads(run("gh", "api", path))


def version(tag: str) -> tuple[int, ...]:
    match = SEMVER.fullmatch(tag)
    if not match:
        raise ValueError("expected a stable vMAJOR.MINOR.PATCH release tag")
    return tuple(map(int, match.groups()))


def records(raw: str) -> dict[str, str]:
    result = {}
    previous = (-1, -1, -1)
    for line in raw.splitlines():
        tag, oid = line.split()
        if version(tag) <= previous or not OID.fullmatch(oid):
            raise ValueError("TEMPLATE_RELEASE must contain increasing tags and full tag object IDs")
        if tag == "v1.0.0" and oid != INITIAL_OID:
            raise ValueError("v1.0.0 differs from its published tag object ID")
        previous = version(tag)
        result[tag] = oid
    if not result:
        raise ValueError("record the reviewed starting release in TEMPLATE_RELEASE first")
    return result


def tree(ref: str) -> dict[str, tuple[str, str]]:
    entries = {}
    for entry in run("git", "ls-tree", "-rz", ref).split(b"\0"):
        if entry:
            metadata, path = entry.split(b"\t", 1)
            mode, _, oid = metadata.decode().split()
            entries[path.decode()] = (mode, oid)
    return entries


def read_file(ref: str, path: str) -> str:
    return git("show", f"{ref}:{path}")


def verify_release(release: dict, expected: str | None = None) -> dict:
    tag = release["tag_name"]
    version(tag)
    if release["draft"] or release["prerelease"] or not release.get("published_at"):
        raise ValueError(f"{tag} is not a published stable release")
    identities = {}
    for key, label in (
        ("oid", "Annotated tag object ID"),
        ("commit", "Template commit"),
        ("core", "Reviewed ci-fleet commit"),
    ):
        matches = re.findall(rf"^- {re.escape(label)}: `([0-9a-f]{{40}})`\s*$", release.get("body") or "", re.M)
        if len(matches) != 1:
            raise ValueError(f"{tag} release notes must name exactly one {label}")
        identities[key] = matches[0]
    if expected and identities["oid"] != expected:
        raise ValueError(f"{tag} was rewritten in its release notes")
    if tag == "v1.0.0" and identities["oid"] != INITIAL_OID:
        raise ValueError("v1.0.0 was rewritten")
    ref = "refs/template-updater/verified"
    git("update-ref", "-d", ref)
    try:
        git("fetch", "--no-tags", SOURCE, f"refs/tags/{tag}:{ref}")
        oid = git("rev-parse", ref)
        if oid != identities["oid"] or git("cat-file", "-t", ref) != "tag":
            raise ValueError(f"{tag} tag object does not match the published annotated tag identity")
        tag_header = git("cat-file", "-p", ref).split("\n\n", 1)[0].splitlines()
        if f"tag {tag}" not in tag_header or "type commit" not in tag_header:
            raise ValueError(f"{tag} must be an annotated tag directly naming a commit")
        commit = git("rev-parse", f"{ref}^{{commit}}")
        if commit != identities["commit"]:
            raise ValueError(f"{tag} peeled commit does not match the published identity")
        compatibility = json.loads(read_file(commit, "template-compatibility.json"))
        core = compatibility["reviewed_core"]
        if (core["repository"] != "RandomDevelopment/ci-fleet"
                or core["commit"] != identities["core"]):
            raise ValueError(f"{tag} reviewed core identity differs from the compatibility record")
        if compatibility["schema_version"] != 1:
            raise ValueError(f"{tag} has an unsupported compatibility record version")
        boundary = compatibility["deployment_policy_boundary"]
        if boundary["version"] >= 2:
            body = release.get("body") or ""
            matches = re.findall(r"^- Reviewed deployer ci-fleet commit: `([0-9a-f]{40})`\s*$",
                                 body, re.M)
            if len(matches) != 1 or len(re.findall(r"^- Reviewed deployer ci-fleet commit:", body, re.M)) != 1:
                raise ValueError(f"{tag} release notes must name exactly one Reviewed deployer ci-fleet commit")
            deployer = boundary["standalone_deployer"]["reviewed_core"]
            if (deployer["repository"] != "RandomDevelopment/ci-fleet"
                    or deployer["commit"] != matches[0]):
                raise ValueError(f"{tag} reviewed deployer identity differs from the compatibility record")
            identities["deployer_core"] = matches[0]
        return {"tag": tag, **identities, "compatibility": compatibility}
    finally:
        git("update-ref", "-d", ref)


def require_review(repository: str, base: str) -> None:
    try:
        protection = api(f"repos/{repository}/branches/{quote(base, safe='')}/protection")
    except RuntimeError:
        raise ValueError("cannot read default-branch protection; enable the documented review/check gate "
                         "and grant the bot Administration read permission") from None
    reviews = protection.get("required_pull_request_reviews") or {}
    checks = protection.get("required_status_checks") or {}
    contexts = set(checks.get("contexts", [])) | {check["context"] for check in checks.get("checks", [])}
    bypass = reviews.get("bypass_pull_request_allowances") or {}
    if not (
        reviews.get("required_approving_review_count", 0) >= 1
        and reviews.get("dismiss_stale_reviews")
        and not any(bypass.values())
        and protection.get("enforce_admins", {}).get("enabled")
        and checks.get("strict")
        and "validate" in contexts
    ):
        raise ValueError("default branch must require review, dismiss stale approvals, enforce admins, "
                         "have no review bypasses, and require up-to-date validate checks")


def preserved_paths(head: str) -> set[str]:
    paths = set(PRESERVED)
    if SETTINGS in tree(head):
        settings = json.loads(read_file(head, SETTINGS))
        if set(settings) != {"preserve"} or not isinstance(settings["preserve"], list):
            raise ValueError(f"{SETTINGS} must contain only a preserve list")
        for path in settings["preserve"]:
            if (not isinstance(path, str) or not path or path.startswith("/")
                    or any(part in {"", ".", "..", ".git"} for part in path.split("/"))):
                raise ValueError("preserve paths must be relative file or directory paths without trailing slashes")
            paths.add(path)
    return paths


def set_entry(path: str, entry: tuple[str, str] | None, env: dict) -> None:
    if entry:
        git("update-index", "--add", "--cacheinfo", entry[0], entry[1], path, env=env)
    else:
        git("update-index", "--force-remove", "--", path, env=env)


def set_json(path: str, value: dict, env: dict) -> None:
    oid = git("hash-object", "-w", "--stdin", input=(json.dumps(value, indent=2) + "\n").encode())
    set_entry(path, ("100644", oid), env)


def prepare_tree(head: str, baseline: dict, target: dict) -> tuple[str, list[str]]:
    """Merge snapshots using the recorded release even without fork ancestry."""
    paths = preserved_paths(head)
    base_tree, target_tree, adopter_tree = tree(baseline["commit"]), tree(target["commit"]), tree(head)
    reasons = []
    contract = target["compatibility"]["template_contract"]
    if json.loads(read_file(head, "fleet.json"))["schema_version"] != contract["fleet_schema_version"]:
        reasons.append("Schema migration required; follow docs/UPDATING.md and the release migration notes.")
    if any(contract.get(key) != baseline["compatibility"]["template_contract"].get(key)
           for key in ("managed_images", "managed_image_identity")):
        reasons.append("Managed-image policy changed; follow the manager bootstrap migration in docs/UPDATING.md.")
    policy = target["compatibility"]["deployment_policy_boundary"]
    if policy != baseline["compatibility"]["deployment_policy_boundary"]:
        reasons.append("Deployment policy compatibility changed; review the new boundary manually.")
    with tempfile.TemporaryDirectory() as directory:
        env = {**os.environ, "GIT_INDEX_FILE": str(Path(directory) / "index")}
        if not reasons:
            git("read-tree", target["commit"], env=env)
            # Make protected paths unchanged upstream, including additions and deletions.
            for path in base_tree.keys() | target_tree.keys():
                if any(path == owned or path.startswith(owned + "/") for owned in paths):
                    set_entry(path, base_tree.get(path), env)
            filtered = git("commit-tree", git("write-tree", env=env), "-p", baseline["commit"],
                           "-m", "Template snapshot with adopter-owned paths excluded")
            merged = subprocess.run(
                ["git", "merge-tree", "--write-tree", "--name-only", "--no-messages", "-z",
                 f"--merge-base={baseline['commit']}", head, filtered], capture_output=True, timeout=45,
            )
            if merged.returncode not in (0, 1):
                raise RuntimeError("git merge-tree failed")
            output = merged.stdout.decode().split("\0")
            if merged.returncode:
                reasons.extend(f"Merge conflict in {path}" for path in output[1:] if path)
            else:
                git("read-tree", output[0], env=env)
                for path in adopter_tree.keys() | target_tree.keys() | base_tree.keys():
                    if any(path == owned or path.startswith(owned + "/") for owned in paths):
                        set_entry(path, adopter_tree.get(path), env)
                raw = read_file(head, "TEMPLATE_RELEASE") + f"\n{target['tag']} {target['oid']}\n"
                oid = git("hash-object", "-w", "--stdin", input=raw.encode())
                set_entry("TEMPLATE_RELEASE", ("100644", oid), env)
        if reasons:
            git("read-tree", head, env=env)
            set_json(STATUS, {"release": {key: target[key] for key in ("tag", "oid", "commit", "core")},
                              "manual_handling": reasons}, env)
        else:
            set_entry(STATUS, None, env)
        return git("write-tree", env=env), reasons


def publish(repository: str, base: str, head: str, old: str | None, proposed: str,
            target: dict, reasons: list[str], pr: dict | None) -> None:
    title = f"{'Manual template update' if reasons else 'Update template'} to {target['tag']}"
    body = (f"Published template release: https://github.com/{UPSTREAM}/releases/tag/{target['tag']}\n\n"
            f"- Annotated tag object ID: `{target['oid']}`\n"
            f"- Template commit: `{target['commit']}`\n"
            f"- Reviewed ci-fleet commit: `{target['core']}`\n\n"
            "Fleet settings, delivery policy, and active/next-engine rollout evidence are preserved. "
            "Engine-pin upgrades require a separate PR. Imported code has not been executed by the updater. "
            "Review the diff and normal validation before merging.\n")
    if reasons:
        body += "\nManual handling required. No template files were updated.\n\n" + "\n".join(f"- {r}" for r in reasons)
    if old and git("rev-parse", f"{old}^{{tree}}") == proposed and git("rev-parse", f"{old}^") == head:
        commit = old
    else:
        commit = git("commit-tree", proposed, "-p", head, "-m", title)
    if commit != old:
        git("push", "origin", f"--force-with-lease=refs/heads/{BRANCH}:{old or ''}",
            f"{commit}:refs/heads/{BRANCH}")
    with tempfile.TemporaryDirectory() as directory:
        body_file = Path(directory) / "body.md"
        body_file.write_text(body + "\n", encoding="utf-8")
        if pr:
            # Keep manual work in draft; never automatically mark a maintainer's draft ready.
            if reasons and not pr["isDraft"]:
                run("gh", "pr", "ready", str(pr["number"]), "--undo", "--repo", repository)
            run("gh", "pr", "edit", str(pr["number"]), "--repo", repository,
                "--title", title, "--body-file", str(body_file), "--base", base)
        else:
            args = ["gh", "pr", "create", "--repo", repository, "--base", base, "--head", BRANCH,
                    "--title", title, "--body-file", str(body_file)]
            if reasons:
                args.append("--draft")
            print(run(*args).decode().strip())


def main() -> None:
    repository = os.environ["GITHUB_REPOSITORY"]
    if repository == UPSTREAM:
        raise ValueError("the updater is for adopters, not the public template")
    if git("status", "--porcelain"):
        raise ValueError("the updater requires a clean checkout")
    base = api(f"repos/{repository}")["default_branch"]
    require_review(repository, base)
    git("fetch", "--no-tags", "origin", f"+refs/heads/{base}:refs/remotes/origin/{base}")
    head = git("rev-parse", f"refs/remotes/origin/{base}")
    history = records(read_file(head, "TEMPLATE_RELEASE"))
    prs = json.loads(run("gh", "pr", "list", "--repo", repository, "--state", "open", "--head", BRANCH,
                         "--json", "number,isDraft,isCrossRepository"))
    if len(prs) > 1 or any(pr["isCrossRepository"] for pr in prs):
        raise ValueError("the reserved updater branch must have at most one same-repository PR")
    refs = git("ls-remote", "--heads", "origin", f"refs/heads/{BRANCH}").split()
    old = refs[0] if refs else None
    expected = dict(history)
    if old:
        git("fetch", "--no-tags", "origin", f"refs/heads/{BRANCH}")
        old_tree = tree(old)
        if "TEMPLATE_RELEASE" in old_tree:
            for tag, oid in records(read_file(old, "TEMPLATE_RELEASE")).items():
                if tag in expected and expected[tag] != oid:
                    raise ValueError(f"{tag} identity differs between default and updater branches")
                expected[tag] = oid
        if STATUS in old_tree:
            identity = json.loads(read_file(old, STATUS))["release"]
            if identity["tag"] in expected and expected[identity["tag"]] != identity["oid"]:
                raise ValueError("pending release identity differs from recorded history")
            expected[identity["tag"]] = identity["oid"]
    pages = json.loads(run("gh", "api", f"repos/{UPSTREAM}/releases?per_page=100", "--paginate", "--slurp"))
    releases = {release["tag_name"]: release for page in pages for release in page
                if SEMVER.fullmatch(release["tag_name"]) and not release["draft"]
                and not release["prerelease"] and release.get("published_at")}
    verified = {}
    for tag, oid in expected.items():
        if tag not in releases:
            raise ValueError(f"recorded release {tag} is no longer published")
        verified[tag] = verify_release(releases[tag], oid)
    current = next(reversed(history))
    latest = max(releases, key=version)
    if version(latest) <= version(current):
        print("No newer published template release.")
        return
    target = verified.get(latest) or verify_release(releases[latest])
    proposed, reasons = prepare_tree(head, verified[current], target)
    publish(repository, base, head, old, proposed, target, reasons, prs[0] if prs else None)
    print("Manual handling required." if reasons else "Template update PR refreshed; review and validation required.")


if __name__ == "__main__":
    try:
        main()
    except (KeyError, ValueError, RuntimeError, subprocess.TimeoutExpired) as error:
        raise SystemExit(f"Template update stopped: {error}") from None
