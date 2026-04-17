#!/usr/bin/env bash
# Consilium dev-environment bootstrap.
#
# Provisions:
#   - Vault transit secrets engine at consilium/transit
#   - Six transit keys: speaker, architect, blast_radius, red_team, generalist, operator
#   - Vault file audit device at /vault/logs/audit.log
#   - AppRole auth with per-agent policies + roles
#   - Neo4j constraints/indexes for the KB graph
#
# Idempotent. Use --reset to wipe Consilium-scoped state and rebuild.
#
# Assumes docker compose has been brought up via:
#   docker compose -f dev/docker-compose.yml up -d
# (or the slim variant — the script skips Neo4j if the container is absent).

set -euo pipefail

RESET=false
if [[ "${1:-}" == "--reset" ]]; then
  RESET=true
fi

export VAULT_ADDR="${VAULT_ADDR:-http://127.0.0.1:8200}"
export VAULT_TOKEN="${VAULT_TOKEN:-consilium-dev-root}"

VAULT_CONTAINER="${VAULT_CONTAINER:-consilium-vault}"

NEO4J_USER="${NEO4J_USER:-neo4j}"
NEO4J_PASS="${NEO4J_PASS:-consilium-dev}"

AGENTS=(speaker architect blast_radius red_team generalist operator)

log()  { printf '[bootstrap] %s\n' "$*"; }
die()  { printf '[bootstrap][FATAL] %s\n' "$*" >&2; exit 1; }
need() { command -v "$1" >/dev/null 2>&1 || die "missing required tool: $1"; }

need docker
need curl
need jq

docker inspect "$VAULT_CONTAINER" >/dev/null 2>&1 \
  || die "$VAULT_CONTAINER container not found — is the dev stack up?"

# Run the vault CLI inside the container so this script is independent of
# whatever `vault` binary (if any) the user has on their local PATH. The
# container image always ships a vault CLI matching the server version.
vault() {
  docker exec -i \
    -e VAULT_ADDR=http://127.0.0.1:8200 \
    -e VAULT_TOKEN="$VAULT_TOKEN" \
    "$VAULT_CONTAINER" vault "$@"
}

log "waiting for Vault at $VAULT_ADDR..."
for _ in {1..30}; do
  if curl -sf "$VAULT_ADDR/v1/sys/health?standbyok=true" >/dev/null 2>&1; then
    break
  fi
  sleep 1
done
curl -sf "$VAULT_ADDR/v1/sys/health?standbyok=true" >/dev/null \
  || die "Vault not reachable at $VAULT_ADDR — is the stack up?"

if $RESET; then
  log "RESET: removing existing Consilium state from Vault"
  vault secrets disable consilium/transit 2>/dev/null || true
  vault audit disable file-audit 2>/dev/null || true
  vault auth disable approle 2>/dev/null || true
fi

# --- Transit engine ---------------------------------------------------------
if ! vault secrets list -format=json | jq -e '."consilium/transit/"' >/dev/null; then
  log "enabling transit at consilium/transit"
  vault secrets enable -path=consilium/transit transit >/dev/null
else
  log "transit engine already enabled at consilium/transit"
fi

# --- Transit keys (one per agent identity) ----------------------------------
for agent in "${AGENTS[@]}"; do
  if vault read -format=json "consilium/transit/keys/$agent" >/dev/null 2>&1; then
    log "transit key exists: $agent"
  else
    log "creating transit key: $agent (ed25519)"
    vault write -f "consilium/transit/keys/$agent" \
      type=ed25519 derived=false exportable=false >/dev/null
  fi
done

# --- Audit device (file sink inside the Vault container) --------------------
if vault audit list -format=json 2>/dev/null | jq -e '."file-audit/"' >/dev/null; then
  log "audit device already enabled"
else
  log "enabling file audit device at /vault/logs/audit.log"
  vault audit enable -path=file-audit file file_path=/vault/logs/audit.log >/dev/null
fi

# --- AppRole auth -----------------------------------------------------------
if vault auth list -format=json 2>/dev/null | jq -e '."approle/"' >/dev/null; then
  log "AppRole auth already enabled"
else
  log "enabling AppRole auth"
  vault auth enable approle >/dev/null
fi

# --- Per-agent policies + AppRole roles -------------------------------------
for agent in "${AGENTS[@]}"; do
  policy_name="consilium-$agent"
  if vault policy list 2>/dev/null | grep -qx "$policy_name"; then
    log "policy exists: $policy_name"
  else
    log "creating policy: $policy_name"
    vault policy write "$policy_name" - >/dev/null <<EOF
# Agent $agent may only sign under its own transit key.
path "consilium/transit/sign/$agent" {
  capabilities = ["update"]
}
path "consilium/transit/sign/$agent/*" {
  capabilities = ["update"]
}
# All agents may verify any signature (to support cross-agent verification).
path "consilium/transit/verify/+" {
  capabilities = ["update"]
}
path "consilium/transit/verify/+/*" {
  capabilities = ["update"]
}
# All agents may read any public key (for signature verification by name).
path "consilium/transit/keys/+" {
  capabilities = ["read"]
}
EOF
  fi

  role_name="consilium-$agent"
  existing_roles=$(vault list -format=json auth/approle/role 2>/dev/null || echo '[]')
  if echo "$existing_roles" | jq -e --arg r "$role_name" 'index($r)' >/dev/null; then
    log "AppRole exists: $role_name"
  else
    log "creating AppRole: $role_name"
    vault write "auth/approle/role/$role_name" \
      token_policies="$policy_name" \
      token_ttl=1h \
      token_max_ttl=4h >/dev/null
  fi
done

log "Vault bootstrap complete. Transit keys:"
vault list consilium/transit/keys

# --- Neo4j schema -----------------------------------------------------------
if docker inspect consilium-neo4j >/dev/null 2>&1; then
  log "applying Neo4j schema via docker exec consilium-neo4j..."

  # Wait for Neo4j to answer on bolt.
  for _ in {1..30}; do
    if docker exec consilium-neo4j cypher-shell -u "$NEO4J_USER" -p "$NEO4J_PASS" \
         "RETURN 1" >/dev/null 2>&1; then
      break
    fi
    sleep 2
  done

  docker exec -i consilium-neo4j cypher-shell -u "$NEO4J_USER" -p "$NEO4J_PASS" <<'CYPHER'
CREATE CONSTRAINT resource_id IF NOT EXISTS
FOR (r:Resource) REQUIRE r.id IS UNIQUE;

CREATE CONSTRAINT iam_principal_arn IF NOT EXISTS
FOR (p:IamPrincipal) REQUIRE p.arn IS UNIQUE;

CREATE INDEX resource_type IF NOT EXISTS
FOR (r:Resource) ON (r.type);

CREATE INDEX resource_provider IF NOT EXISTS
FOR (r:Resource) ON (r.provider);
CYPHER

  log "Neo4j schema applied"
else
  log "consilium-neo4j container not running (slim stack?) — skipping Neo4j schema"
fi

log "bootstrap complete."
