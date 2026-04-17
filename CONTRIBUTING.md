# Contributing to Consilium

## Minimum machine specs

- 16 GB RAM (Docker Desktop allocated ≥12 GB)
- 50 GB free disk
- macOS or Linux

## Toolchain

| Tool | Minimum version | Notes |
|---|---|---|
| Docker | 25+ | Desktop or Engine |
| Go | 1.22+ | Terraform provider |
| Python | 3.12+ | Control plane, agents, CLI |
| Terraform | 1.9+ | For the provider and examples |
| Vault CLI | 1.17+ | Host-side for `bootstrap.sh` and debugging |
| `jq` | any recent | Used by `bootstrap.sh` |

Optional but recommended: `cypher-shell` (for Neo4j debugging; `bootstrap.sh` falls back to `docker exec` if missing).

## Local stack

```bash
# Full stack (Vault + Consul + Nomad + Neo4j)
docker compose -f dev/docker-compose.yml up -d

# Slim stack (no Neo4j — for agent and control-plane work that doesn't need the KB)
docker compose -f dev/docker-compose.slim.yml up -d

# Provision Vault engines/keys/AppRoles + Neo4j schema
./dev/bootstrap.sh

# Re-bootstrap from scratch
./dev/bootstrap.sh --reset
```

Dev-mode Vault runs **in-memory**. Anything (including transit keys) is lost on `docker compose down`. That is the intended behaviour for dev; production Vault is a post-MVP concern.

## Environment

Set the following in your shell or a local `.env`:

```bash
export VAULT_ADDR=http://127.0.0.1:8200
export VAULT_TOKEN=consilium-dev-root
export CONSUL_HTTP_ADDR=http://127.0.0.1:8500
export NOMAD_ADDR=http://127.0.0.1:4646
```

The bootstrap script reads these from the environment if set; otherwise it uses the dev defaults above.

## Repo layout

See [BUILD_PROMPT.md §3](./BUILD_PROMPT.md) — the tree there is the authoritative layout. Do not add top-level directories without approval.

## Conventions

- **Contracts are fixed.** [BUILD_PROMPT.md](./BUILD_PROMPT.md) §§4–8 define the MCP tool schemas, control plane API, signed envelope format, quorum rule, and log shape. Changes require a decision-log entry in MVP_PLAN.md §6.
- **Agents are fixed.** Five agents only: Speaker, Architect, Blast Radius, Red Team, Generalist. Three of them vote (Blast Radius + Red Team hold hard-veto; Generalist is soft-concern only). No other voters until post-MVP — see [docs/voting-architecture.md §6](./docs/voting-architecture.md#6-post-mvp-when-would-we-split-the-generalist) for the conditions under which the Generalist may be split into specialist voters.
- **Voter classes are structural, not prompt-level.** A soft-concern voter that returns `veto` is a protocol violation enforced by the quorum engine. Do not "fix" a Generalist veto attempt at prompt level — the engine invariant is the load-bearing control.
- **Prompts are versioned, never edited in place.** Create `agents/<name>/prompts/v2.md`; update the pointer; keep `v1.md` for reproducibility.
- **Every signed artefact uses the BUILD_PROMPT §6 envelope.** `deliberation_id` is **inside** the signed payload — this defends against replay. The envelope now carries a `verdict_class` field so the Speaker can detect cross-class protocol violations (e.g. a soft-concern voter returning `veto`).
- **Every phase emits one structured log line** per BUILD_PROMPT §8.

## Running tests

```bash
# Unit
pytest tests/unit

# Integration (requires local stack up + bootstrap completed)
pytest tests/integration

# Red Team scoreboard (M4+)
python tests/red_team/scoreboard.py

# Generalist scoreboard (M4+) — must-concern + benign test sets
python tests/generalist/scoreboard.py

# Go provider
cd provider && go test ./...
```

## Before you push

- `ruff check .`
- `pytest tests/unit`
- `go vet ./provider/...` (if provider exists)
- Docker compose files validate: `docker compose -f dev/docker-compose.yml config >/dev/null`

CI runs these on every push. See [.github/workflows/ci.yml](./.github/workflows/ci.yml).

## Progress

Work proceeds milestone by milestone per [BUILD_PROMPT.md §9](./BUILD_PROMPT.md) and [TODO.md](./TODO.md). Each milestone has a hard stop-and-report gate — don't start M*N+1* until M*N*'s acceptance criteria are green.
