# Optional host-local APT cache

The reviewed development engine at `689c7c00deb0eebcb25f2284334a9f7168a25575`
advertises `apt_cache`. The cache is disabled by default and needs no new fleet
schema field. ci-fleet does not discover, install or administer the cache server.
Keep all actual endpoints, bypass hosts and generated APT files outside public
and private configuration Git. Do not put credentials in proxy URLs.

## Adoption and scope

First review and promote an engine with `apt_cache: true` and verified managed
image IDs. Complete [manager staging](MANAGED-IMAGES.md) before adding host-local
settings because old managers reject them. Host edits and upgrades need separate
host-specific authorization; a template update performs neither.

The pinned [APT-cache runbook](https://github.com/RandomDevelopment/ci-fleet/blob/689c7c00deb0eebcb25f2284334a9f7168a25575/docs/APT-CACHE.md)
defines `CI_FLEET_APT_HTTP_PROXY` and optional `CI_FLEET_NO_PROXY` in the protected
root-owned mode-`0600` `/etc/ci-fleet/host.env`. Use only a credential-free HTTP
origin with an optional port and trailing slash. Paths, query strings, fragments,
whitespace and shell syntax are rejected. Bypass entries are at most 64 exact
DNS names or IPv4 addresses, with no ports, CIDRs or wildcards. This is APT HTTP
repository bypass policy, not a general exported `NO_PROXY` value.

The normal authorized install/upgrade procedure activates edits under existing
drain, checkpoint and rollback rules. A scheduled check alone does not apply
an edited file. Existing runners retain their prior settings. The cache must
be reachable from runner and BuildKit networks without host networking.

New runners receive a root-owned mode-`0644` APT configuration and expose its
path as `CI_FLEET_APT_CONFIG`. Managed builds receive an optional BuildKit secret
for each APT stage and retain all reviewed input and exact-image checks.
Projects must explicitly pass the file through a BuildKit/Compose secret or
copy it into a fresh task-owned runtime container before APT runs. See the
pinned runbook for complete build, Compose and runtime examples. Arbitrary
project images do not inherit the runner's APT settings automatically.

Host APT remains operator-managed. Git, curl, GitHub, language package managers
and image pulls are outside this feature. HTTPS repositories stay direct;
ci-fleet does not downgrade TLS, rewrite sources or disable package signatures.

## Outages, removal and acceptance

Enabled APT requests have a ten-second HTTP connection/data timeout and two
retries. Persistent failure fails the APT operation, with no automatic direct
fallback. These are per-attempt limits; ordinary jobs retain five minutes.

To disable, remove both host-local variables and apply the normal upgrade.
New runners/builds then receive no cache configuration or secret. Existing
runners keep prior settings. Remove settings before selecting an older engine
or manager. Checkpoint rollback can restore an earlier cache-enabled environment.

Keep endpoint-bearing job/package/cache logs private. Engine redaction does not
make arbitrary job output safe to publish. On a separately authorized inert
validation daemon, follow the upstream cold/warm, concurrent, outage, cancellation,
timeout, read-only and scoped-cleanup checks. Cache-enabled managed rebuilds must
match the reviewed image IDs built without cache. Never clear a production cache
or run global Docker prune for validation.

Live acceptance needs representative authorized shards, elapsed time, upstream
and cached package bytes and repeated package hits. Report index revalidation
separately. A successful `apt-get update` or Docker layer reuse does not prove
cached package downloads. This repository's suite establishes none of that
host or performance evidence.
