#!/usr/bin/env bash
set -Eeuo pipefail
cd "${CI_FLEET_VALIDATION_ROOT:?source checkout is required}"
BASE_SHA=${CI_FLEET_VALIDATION_BASE:?base commit is required}
validator="${CI_FLEET_VALIDATOR_ROOT:?trusted validator checkout is required}/scripts/validate.py"
temporary_directory=$(mktemp -d)
trap 'rm -rf "$temporary_directory"' EXIT

if [[ ${CI_FLEET_INITIALIZER_ONLY:-false} != true ]]; then
git ls-tree -rz --name-only HEAD >"$temporary_directory/tree-paths"
args=(--config "$PWD/fleet.json" --tree-paths "$temporary_directory/tree-paths")
if [[ ${CI_FLEET_TEMPLATE_FIXTURES:?fixture identity is required} != true ]]; then args+=(--strict); fi
if [[ -f engine-rollout-evidence.json ]]; then args+=(--rollout-evidence "$PWD/engine-rollout-evidence.json"); fi
# Reviewed standalone transitions include stricter rules than the older engine baseline.
if [[ ${CI_FLEET_STATIC_ENGINE_POLICY:-false} != true ]]; then
if [[ -f next-engine-rollout-evidence.json ]] || git cat-file -e "$BASE_SHA:next-engine-rollout-evidence.json" 2>/dev/null; then
  if ! python3 -I "$validator" --help | grep -q -- --next-engine-rollout-evidence; then
    echo 'Pinned validator lacks next-engine transition support; keep adoption gated until a reviewed supporting engine exists.' >&2
    exit 1
  fi
fi
if [[ -f next-engine-rollout-evidence.json ]]; then
  args+=(--next-engine-rollout-evidence "$PWD/next-engine-rollout-evidence.json")
fi
if git cat-file -e "$BASE_SHA:fleet.json" 2>/dev/null; then
  git show "$BASE_SHA:fleet.json" >"$temporary_directory/previous-fleet.json"
else
  printf '{"controllers":{}}\n' >"$temporary_directory/previous-fleet.json"
fi
args+=(--previous-config "$temporary_directory/previous-fleet.json")
if git cat-file -e "$BASE_SHA:engine-rollout-evidence.json" 2>/dev/null; then
  git show "$BASE_SHA:engine-rollout-evidence.json" >"$temporary_directory/previous-rollout-evidence.json"
  args+=(--previous-rollout-evidence "$temporary_directory/previous-rollout-evidence.json")
fi
if git cat-file -e "$BASE_SHA:next-engine-rollout-evidence.json" 2>/dev/null; then
  git show "$BASE_SHA:next-engine-rollout-evidence.json" >"$temporary_directory/previous-next-engine-rollout-evidence.json"
  args+=(--previous-next-engine-rollout-evidence "$temporary_directory/previous-next-engine-rollout-evidence.json")
fi
fi
python3 -I "$validator" "${args[@]}"
python3 -I "$validator" --config "$PWD/examples/multi-host/fleet.json" --tree-paths "$temporary_directory/tree-paths"

fi
if [[ ${CI_FLEET_CONFIG_ONLY:-false} == true ]]; then exit 0; fi

engine_ref=$(python3 -I -c 'import json; print(next(iter(json.load(open("fleet.json", encoding="utf-8"))["controllers"].values()))["engine_ref"])')
if ./scripts/init.sh --organization test-company --project test-app --output "$temporary_directory/missing-engine.json"; then
  echo 'initializer accepted a missing engine revision' >&2
  exit 1
fi
test ! -e "$temporary_directory/missing-engine.json"
if ./scripts/init.sh --organization test-company --project test-app --registry BAD --engine-ref "$engine_ref" --output "$temporary_directory/invalid.json"; then
  echo 'initializer accepted an invalid registry' >&2
  exit 1
fi
test ! -e "$temporary_directory/invalid.json"
./scripts/init.sh --organization test-company --project test-app --engine-ref "$engine_ref" --output "$temporary_directory/fleet.json"
test "$(stat -c '%a' "$temporary_directory/fleet.json")" = 644
python3 -I "$validator" --strict --skip-path-scan --config "$temporary_directory/fleet.json"
python3 -I -c 'import json,sys; value=json.load(open(sys.argv[1], encoding="utf-8")); next(iter(value["controllers"].values()))["docker_network_policy"]={"networks_per_runner": 1, "reserve_subnets": 1, "default_address_pools": [{"base": "198.51.100.0/24", "size": 28}]}; json.dump(value, open(sys.argv[2], "w", encoding="utf-8"), indent=2)' "$temporary_directory/fleet.json" "$temporary_directory/rfc-5737.json"
if python3 -I "$validator" --strict --skip-path-scan --config "$temporary_directory/rfc-5737.json" 2>"$temporary_directory/strict-errors"; then
  echo 'RFC 5737 fixture unexpectedly passed strict validation' >&2
  exit 1
fi
grep -F 'reviewed operational Docker pool CIDR' "$temporary_directory/strict-errors"
