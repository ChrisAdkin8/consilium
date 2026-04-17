# Consilium MVP — TODO

Execution tracker. Check items off as they are completed. Design source of truth is [MVP_PLAN.md](./MVP_PLAN.md); agent standing brief is [BUILD_PROMPT.md](./BUILD_PROMPT.md); this file is the day-to-day punch list.

Convention: `[x]` done, `[ ]` not started, `[~]` in progress.

---

## Plan enhancements (pre-M0)

- [x] M1 — pin MCP tool schemas (`semantic_search`, `blast_radius`, `security_posture`)
- [x] M2 — enumerate control plane API surface
- [x] M5 — spec quorum rule as a tally table
- [x] Decision log — add D9 (quorum), D10 (demo infra), D11 (Architect model), D12 (timeout)
- [x] §7 — extend signing unit tests with key rotation, cross-agent, replay
- [x] §12 — Observability minimum
- [x] §13 — Pre-demo runbook
- [x] Create `BUILD_PROMPT.md` — self-contained agent build brief
- [x] **3-voter architecture** — adopt Generalist soft-concern voter (2026-04-17); retire 4-voter Compliance proposal; write `docs/voting-architecture.md` with rationale (D15)

---

## Pre-flight (§3)

- [ ] Anthropic API key provisioned with ≥$75 quota
- [ ] Local machine specs verified (≥16 GB RAM, ≥50 GB disk, Docker ≥12 GB)
- [ ] Toolchain installed: Go 1.22+, Python 3.12+, Terraform 1.9+, Docker 25+
- [ ] Polyglot KB repo cloneable + runnable locally
- [ ] Sample Terraform project (~10 resources) exists for Blast Radius tests
- [ ] GitHub repo created with branch protection on `main`
- [ ] **D1** decided: project name is final

---

## M0 — Foundation (~4h)

- [x] 0.2 Directory skeleton per BUILD_PROMPT §3
- [x] 0.3 `dev/docker-compose.yml` + `dev/docker-compose.slim.yml` (Vault, Consul, Nomad, Neo4j)
- [x] 0.4 `dev/bootstrap.sh` (transit keys, AppRole, audit device, Neo4j schema; idempotent; `--reset` supported)
- [x] 0.5 GitHub Actions: ruff, pytest, compose-config, shellcheck, conditional Go provider job
- [x] 0.6 `CONTRIBUTING.md`

Acceptance:

- [x] `docker compose -f dev/docker-compose.yml up -d` — all 4 services healthy
- [ ] `./dev/bootstrap.sh` — exits 0; `vault list consilium/transit/keys` returns six keys: `speaker`, `architect`, `blast_radius`, `red_team`, `generalist`, `operator` (requires adding `generalist` to AGENTS array — not yet done)
- [ ] Push to GitHub triggers CI; workflow passes
- [ ] Teammate can follow `CONTRIBUTING.md` without clarification

---

## M1 — KB extension + MCP server (~18h)

- [x] 1.1 Fork polyglot KB → `kb_extensions/base/`
- [x] 1.2 `kb_extensions/mcp_server.py` with three analyst tools (schemas pinned in MVP_PLAN §4 M1)
- [ ] 1.2a Add four Generalist tool stubs — `cost_estimate`, `policy_check`, `historian_lookup`, `slo_impact` (deterministic fixtures, schemas final)
- [x] 1.3 Seed Neo4j with test corpus (one sample Terraform project's plan graph) + `:PriorDeliberation` mini-corpus for `historian_lookup`
- [x] 1.4 `agents/base/mcp_client.py` (extend with four Generalist tool wrappers)
- [x] 1.5 Integration test: each tool round-trips, response schemas asserted (extend: all seven tools)
- [x] 1.6 `nomad/kb_mcp.nomad.hcl`
- [x] 1.7 `docs/mcp-tools.md` (extend: add four Generalist tool contracts)

---

## M2 — Control plane + Terraform provider (~17h)

- [ ] 2.1 FastAPI skeleton with all endpoints from MVP_PLAN §4 M2 API surface
- [ ] 2.2 Vault AppRole provisioning (`control_plane/consilium/vault_setup.py`) — six keys including `generalist`
- [ ] 2.3 Consul service registration per agent (five agents)
- [ ] 2.4 Nomad stub dispatch for all five agents (sleep jobs)
- [ ] 2.5 Terraform provider scaffold + `consilium_agent` resource with `voter_class` attribute
- [ ] 2.6 `consilium_quorum_policy` resource — `hard_veto_voters` + `soft_concern_voters` split; accept `escalate_concern_to_veto` blocks (parsed, unenforced in v0.1.0)
- [ ] 2.7 `examples/minimal_parliament/main.tf` — five agents + dev quorum policy
- [ ] 2.8 E2E: `terraform apply` → 5 agents registered in Consul including `consilium-generalist`
- [ ] **D2** decided: provider talks to control plane only (or override with rationale)

---

## M3 — Agent framework + Architect (~16h)

- [ ] 3.1 `agents/base/agent.py` base class (MCP client, Anthropic client, signer)
- [ ] 3.2 `agents/base/signing.py` — includes adversarial tests (key rotation, cross-agent confusion, replay) per MVP_PLAN §7
- [ ] 3.3 `agents/architect/main.py` — `deliberate()` with KB retrieval + LLM call
- [ ] 3.4 Architect system prompt (time-box 2.5h)
- [ ] 3.5 `/deliberate` HTTP wrapper
- [ ] 3.6 Agent Dockerfile
- [ ] 3.7 Real Architect Nomad job spec
- [ ] 3.8 Integration test: intent → signed proposal → external verification
- [ ] Observability: Architect emits §12 structured JSON per phase
- [ ] **D11** decided: Architect model

---

## M4 — Blast Radius + Red Team + Generalist (~22h)

- [ ] 4.1 `agents/blast_radius/main.py`
- [ ] 4.2 HCL-to-resource-list parser
- [ ] 4.3 Blast Radius system prompt
- [ ] 4.4 `agents/red_team/main.py`
- [ ] 4.5 **Build Red Team test set first** (5 bad + 10 benign), iterate prompt against scoreboard
- [ ] 4.6 Red Team verdict parser (veto / concern / approve / abstain)
- [ ] 4.7 `agents/generalist/main.py` — parallel tool consultation + synthesis
- [ ] 4.8 `agents/generalist/citation_parser.py` — uncited concern → abstain; Generalist `veto` → error
- [ ] 4.9 Generalist system prompt — soft-concern vocabulary, cite tool output IDs
- [ ] 4.10 Promote Generalist tools from M1 stubs to M4 real-ish backends (pricing table, OPA-lite rules, `:PriorDeliberation` Cypher, `slo_registry.yaml`)
- [ ] 4.11 Generalist test set: 5 must-concern + 10 benign
- [ ] 4.12 Integration tests: all three voters return signed, verifiable opinions; adversarial signing tests pairwise across all five keys
- [ ] Observability: Blast Radius + Red Team + Generalist emit §12 structured JSON
- [ ] **D3** decided: Red Team model
- [ ] **D4** decided: minimum acceptable Red Team accuracy to ship
- [ ] **D5** decided: per-deliberation cost cap
- [ ] **D9** decided: quorum rule
- [ ] **D12** decided: per-voter deliberation timeout
- [ ] **D13** decided: Generalist model
- [ ] **D14** decided: Generalist minimum accuracy to ship

---

## M5 — Speaker orchestration + Digital Twin (~17h)

- [ ] 5.1 LangGraph workflow skeleton (all nodes stubbed)
- [ ] 5.2 `dispatch_to_analysts` — Consul service discovery + parallel HTTP to three voters
- [ ] 5.3 `tally_votes` (`control_plane/consilium/quorum.py`) — 13-row 3-voter table + two protocol invariants (veto-class enforcement, uncited-concern abstain)
- [ ] 5.4 `sign_and_audit` — compose deliberation record with three voter verdicts + their `verdict_class`
- [ ] 5.5 Digital Twin Nomad job (accepts HCL, runs `terraform plan`, writes JSON outcome)
- [ ] 5.6 `run_digital_twin` workflow node
- [ ] 5.7 `terraform_apply` node
- [ ] 5.8 `consilium submit` CLI entrypoint — phase stream includes `generalist`
- [ ] 5.9 E2E manual tests — happy, veto, **soft-concern (Scene 3)** paths
- [ ] Observability: Speaker emits §12 JSON and enforces D5 cost cap before `apply`
- [ ] **D6** decided: terraform apply path (MCP vs shell-out)
- [ ] **D10** decided: demo target infrastructure

---

## M6 — Demo polish + audit verifier + docs (~18h)

- [ ] 6.1 Build three demo Terraform projects (happy-path, veto-bait, **cost-bait** for Scene 3)
- [ ] 6.2 `consilium audit verify <id>` CLI — outputs voter-class annotation per signed opinion
- [ ] 6.3 CLI output polish (phase streaming for all three voters, colours, ASCII progress)
- [ ] §13 pre-demo runbook green (see next section)
- [ ] 6.4 Record demo video — four scenes (4–6 takes expected)
- [ ] 6.5 Demo narration / blog post — lead with "why three voters, not four"
- [ ] 6.6 Reconcile docs with shipped reality
- [ ] 6.7 Cold-install test on fresh VM (≤15 min to first deliberation)
- [ ] 6.8 `v0.1.0-mvp` release with notes
- [ ] **D7** decided: demo hosting (YouTube / LinkedIn / both)
- [ ] **D8** decided: open-source licence

### Pre-demo runbook (run night before M6.4)

- [ ] `vault status` — unsealed, not standby
- [ ] `consul catalog services` — 6 consilium services healthy (speaker, architect, blast-radius, red-team, generalist, kb-mcp)
- [ ] `nomad status` — all allocs running, no recent restarts
- [ ] Speaker logs clean (no errors/panics in last 100 lines)
- [ ] `./dev/bootstrap.sh --reset` verified this week
- [ ] Smoke: `consilium submit "add a t3.small…"` returns `deliberation_id` in ≤90s
- [ ] Smoke: `consilium submit "m5.24xlarge × 3 AZ"` returns `apply` with Generalist concern (Scene 3)
- [ ] Smoke: `consilium audit verify` prints a green chain across three voter signatures

---

## Definition of Done (§8)

- [ ] Demo video embedded in README, all four scenes from §2.3
- [ ] Red Team: 5/5 veto on known-bad, ≤1/10 false positive on benign
- [ ] Generalist: 5/5 concern on must-concern, ≤2/10 false concern on benign
- [ ] Citation parser: uncited concern → abstain; Generalist `veto` → protocol_violation
- [ ] Quorum engine enforces voter-class invariant (unit + manual smoke)
- [ ] `consilium audit verify` produces a readable cryptographic proof across all three voter signatures
- [ ] Cold install ≤15 min on fresh Linux/macOS + Docker Desktop
- [ ] Every signed artefact verifies against its agent's Vault transit key (five keys)
- [ ] Speaker rejects tampered opinions (negative test documented)
- [ ] CI green on `main`
- [ ] `v0.1.0-mvp` tag with release notes
- [ ] README, ARCHITECTURE, IMPLEMENTATION, MVP_PLAN, voting-architecture all consistent with shipped behaviour

---

*Update this file as items complete. If a task changes scope, update MVP_PLAN.md first, then mirror the change here.*
