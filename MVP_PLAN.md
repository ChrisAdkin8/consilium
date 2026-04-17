# Consilium MVP — Implementation Plan

**Version**: 0.2 (3-voter architecture; superseded the v0.1 2-voter design on 2026-04-17)
**Target demo date**: T+8 weeks from project start (working evenings and weekends)
**Effort budget**: ~112 hours (+12h vs v0.1 for the Generalist voter and four additional MCP tool stubs — see §4 milestone adjustments)

This plan assumes one developer working part-time. It is an execution plan, not a tutorial — see [IMPLEMENTATION.md](./IMPLEMENTATION.md) for code-level guidance.

---

## 1. Executive summary

Build a five-agent parliament (Speaker, Architect, Blast Radius, Red Team, Generalist) that deliberates over a proposed Terraform change, produces a cryptographically signed decision in the Vault audit log, and either invokes `terraform apply` or rejects with a signed rationale. Three of the five agents vote: Blast Radius and Red Team hold hard-veto; the Generalist holds soft-concern only and consults deterministic tools (`cost_estimate`, `policy_check`, `historian_lookup`, `slo_impact`) rather than acting as a separate compliance / cost / historian voter. See [docs/voting-architecture.md](./docs/voting-architecture.md) for the design rationale behind "3 voters, not 4".

The deliverable is a runnable repository plus a demo video showing three scenes: Red Team vetoing a privilege-escalating change, the Generalist raising a cost concern that does *not* block a change, and an audit chain verifying the vetoed deliberation cryptographically.

The outcome the plan is optimising for is **a single compelling demo that can be posted publicly**. Not a finished product. Not a production-ready platform. A demo sharp enough that an infrastructure engineer watching it will send it to a colleague.

---

## 2. MVP definition

### 2.1 What "done" means

The MVP ships when all five of these are true:

1. **The happy path works end-to-end.** An operator issues a natural-language intent; Architect drafts; Blast Radius, Red Team, and Generalist return signed opinions; the Speaker tallies and signs a final decision; a valid change applies via the Terraform MCP server.
2. **The veto path works end-to-end.** The same intent, but containing a subtle IAM escalation, is vetoed by Red Team. The vote is recorded. No apply fires.
3. **The soft-concern path works end-to-end.** A different intent — benign from security and dependency perspectives but expensive — flows through, the Generalist raises a `cost_estimate` concern with a tool citation, the Speaker signs `PROCEED` with the concern attached, and the apply fires. The audit record contains the concern.
4. **The audit record is verifiable.** An auditor can run `consilium audit verify <deliberation_id>` and get cryptographic confirmation that every signed opinion and the final decision are valid against the agents' published Vault transit keys.
5. **Someone else can run it.** A fresh clone with `docker compose up && ./dev/bootstrap.sh && terraform apply` produces a working parliament on another machine within 15 minutes.

### 2.2 Scope

**In scope**:

- Five agents (Speaker, Architect, Blast Radius, Red Team, Generalist)
- Three voters: Blast Radius + Red Team (hard-veto), Generalist (soft-concern only)
- Local HashiCorp dev stack (Vault, Consul, Nomad, Neo4j via Docker Compose)
- Extension to the existing polyglot KB: MCP server exposing seven tools — `semantic_search`, `blast_radius`, `security_posture` (primary analyst tools) plus `cost_estimate`, `policy_check`, `historian_lookup`, `slo_impact` (Generalist tools; stubbed deterministic fixtures in M1, real data sources in M4)
- Minimal Terraform provider: `consilium_agent` and `consilium_quorum_policy` resources (including the `hard_veto_voters` / `soft_concern_voters` split in the policy)
- FastAPI control plane that registers agents, brokers Vault credentials, and hosts the Speaker workflow
- LangGraph-based Speaker orchestration dispatching in parallel to all three voters
- Digital Twin = a Nomad job running `terraform plan` against a state twin workspace
- Per-agent Vault transit signing + verification (six keys: speaker, architect, blast_radius, red_team, generalist, operator)
- Generalist citation parser that enforces "every concern must reference a tool output" at opinion-ingest time
- CLI for submitting intents and verifying audit records
- One end-to-end example (`examples/minimal_parliament`)
- Demo video (≤3 minutes, three scenarios: happy, veto, soft-concern + audit)

**Explicitly deferred to post-MVP**:

- **Dedicated Compliance voter** (M1 ships `policy_check` as a tool consulted by the Generalist; a voter with its own signing key + test harness is v0.2.0+)
- **Dedicated Historian voter** (`historian_lookup` tool ships as a stub in M1 with a small `:PriorDeliberation` seed; promoting it to a voter requires the full temporal graph layer)
- **Dedicated Cost voter** (`cost_estimate` tool ships as a deterministic-fixture stub in M1, replaced by real pricing data in M4; voter elevation is v0.2.0+ if post-MVP data shows the Generalist systematically under-escalates cost concerns)
- **Concern-to-veto escalation rules** (the `consilium_quorum_policy` resource accepts `escalate_concern_to_veto` blocks in its schema but the engine ignores them in v0.1.0 — enforced in v0.2.0)
- Security agent split from Red Team
- Temporal graph layer (beyond the thin `historian_lookup` stub)
- Federated Historian / pattern registry
- Production Vault HA / auto-unseal
- Temporal.io workflow engine (LangGraph suffices for the MVP)
- OpenTelemetry / observability stack
- Multi-environment quorum policies beyond `dev` and `prod`
- Break-glass multi-signature override
- Real Consul service-mesh traffic replay in the Digital Twin
- Terraform registry publishing of the provider

Calling these out explicitly because feature creep is the single largest risk to the timeline.

### 2.3 The demo script (the forcing function)

Every milestone is measured against whether it advances this exact demo:

> **Scene 1 — the happy path** (45s). Operator opens a terminal, runs
> `consilium submit "Add a t3.medium EC2 instance to staging-vpc for a batch job."`
> Terminal streams each phase: Architect drafting, Blast Radius analysing, Red Team probing, Generalist consulting cost/policy/historian/SLO tools, Twin running `terraform plan`, Speaker tallying three signed opinions, decision signed, apply dispatched. Final line shows the deliberation ID and a verify command.
>
> **Scene 2 — the veto** (45s). Operator runs
> `consilium submit "Grant the batch job role s3:PutObject on logs-bucket and sts:AssumeRole on *."`
> Same pipeline, but Red Team's findings include "wildcard role trust permits privilege escalation from batch runtime to any IAM role in account." Speaker records a veto with signed rationale. Apply does not fire. Scene ends with the deliberation ID printed for use in Scene 4.
>
> **Scene 3 — the soft concern** (30s). Operator runs
> `consilium submit "Add an m5.24xlarge instance in every AZ for the batch job."`
> Red Team and Blast Radius both approve — the change is safe from security and dependency perspectives. The Generalist raises a concern citing its `cost_estimate` tool output: "+$X/mo per instance × 3 AZs = +$Y/mo; confidence: high; source: stub pricing table." Speaker signs `PROCEED` with the concern attached to the audit record. **Apply still fires** — this scene demonstrates that concerns are advisory, not blocking, and that the Generalist's opinion is backed by a concrete tool citation rather than vibes. The Generalist's signed opinion is verifiable.
>
> **Scene 4 — the audit** (30s). Operator runs `consilium audit verify <deliberation_id>` on the vetoed decision from Scene 2. Output shows every signature verified against each agent's published Vault transit key, with timestamps and the final vote tally for all three voters.

Total video length target: ≤3 minutes. If a proposed task doesn't contribute to this demo, it's post-MVP.

---

## 3. Pre-flight checklist

Complete these before Milestone 0 starts. Skipping them will block work later.

- [ ] Anthropic API key provisioned with ≥$75 of quota allocated (build + demo ~$50 expected, buffer for Red Team prompt iteration)
- [ ] Local machine has ≥16 GB RAM, ≥50 GB free disk, Docker Desktop configured to use ≥12 GB RAM
- [ ] Toolchain installed: Go 1.22+, Python 3.12+, Terraform 1.9+, Docker 25+
- [ ] One of the existing polyglot KB repos (aws-hashi-knowledge-base or gcp-hashi-knowledge-base) is cloneable and runnable locally
- [ ] A sample Terraform project exists to serve as the corpus for Blast Radius tests (can be a minimal EKS/EC2 setup, ~10 resources)
- [ ] GitHub repo created with branch protection on `main`
- [ ] Decision made: **Consilium name is final** (trademark check, domain availability). If no, choose alternative before M0 starts to avoid rewriting documentation.

---

## 4. Milestone plan

Six milestones mapped to six weekends. Each weekend assumes ~16 productive hours. Evenings between weekends (~4 hours each) are buffer for overruns and prompt iteration.

### Milestone 0 — Project foundation
**Duration**: 1 evening (~4 hours)
**Goal**: Repo scaffolded, local dev stack runs, CI runs on push.

| # | Task | Estimate |
|---|---|---|
| 0.1 | Initialise repo with README, ARCHITECTURE, IMPLEMENTATION, MVP_PLAN docs (already done) | 0.25h |
| 0.2 | Create directory skeleton per IMPLEMENTATION.md §1 | 0.5h |
| 0.3 | Write `dev/docker-compose.yml` with Vault, Consul, Nomad, Neo4j | 1h |
| 0.4 | Write `dev/bootstrap.sh` (transit keys, AppRole, audit device, Neo4j schema) | 1h |
| 0.5 | Add GitHub Actions workflow: lint (Go + Python), unit tests, docker build | 1h |
| 0.6 | Write `CONTRIBUTING.md` with dev setup instructions | 0.25h |

**Acceptance criteria**:

- `docker compose -f dev/docker-compose.yml up -d` starts all four services; health checks green within 60s.
- `./dev/bootstrap.sh` completes with exit 0; `vault list consilium/transit/keys` returns the six agent keys (`speaker`, `architect`, `blast_radius`, `red_team`, `generalist`, `operator`).
- `git push` triggers CI; workflow passes.
- A teammate can follow `CONTRIBUTING.md` without clarification.

**Risks**: Docker memory exhaustion on laptops with <16GB RAM. *Mitigation*: document minimum specs in CONTRIBUTING and provide a `docker-compose.slim.yml` that omits Neo4j for parts of development that don't need it.

**Artifacts produced**: Running dev environment, CI pipeline, contribution docs.

---

### Milestone 1 — Knowledge base extension + MCP server
**Duration**: 1 weekend (~18 hours — +2h vs v0.1 for the four Generalist tool stubs)
**Goal**: Agents can query the polyglot KB via a single MCP endpoint; all seven tool schemas are pinned and the Generalist tools return deterministic fixture data (real backends land in M4).

| # | Task | Estimate |
|---|---|---|
| 1.1 | Fork existing polyglot KB repo; vendor it as `kb_extensions/base/` | 1h |
| 1.2 | Write `kb_extensions/mcp_server.py` with three primary tools: `semantic_search`, `blast_radius`, `security_posture` | 5h |
| 1.2a | Add four Generalist tool stubs: `cost_estimate`, `policy_check`, `historian_lookup`, `slo_impact` (deterministic fixtures keyed off input hash; schemas final; real data in M4) | 2h |
| 1.3 | Seed Neo4j with a test corpus: one sample Terraform project's plan graph, plus a `:PriorDeliberation` mini-corpus for `historian_lookup` | 2h |
| 1.4 | Write MCP client wrapper in `agents/base/mcp_client.py` (all seven tool methods) | 2h |
| 1.5 | Integration test: spin up MCP server, call each of the seven tools from a Python test, assert structured results | 3h |
| 1.6 | Package as Nomad job in `nomad/kb_mcp.nomad.hcl` | 1.5h |
| 1.7 | Document tool contracts in `docs/mcp-tools.md` (all seven tools) | 1.5h |

**Tool contracts (pin before M1.2)**:

Schemas for all seven tools are specified in [BUILD_PROMPT.md §4](./BUILD_PROMPT.md). Summary:

- `semantic_search` — M1 real (TF-IDF against local corpus)
- `blast_radius` — M1 real (Neo4j traversal)
- `security_posture` — M1 real (Neo4j properties)
- `cost_estimate` — **M1 stub**, M4 real: stub returns a deterministic monthly delta keyed off resource types in the HCL
- `policy_check` — **M1 stub**, M4 real: stub returns a deterministic violation list from ~5 hard-coded rules (wildcard IAM, public S3, missing tags)
- `historian_lookup` — **M1 stub**, M4 real: stub does Cypher similarity lookup over a seed of ~10 `:PriorDeliberation` nodes
- `slo_impact` — **M1 stub**, M4 real: stub reads a flat YAML registry of services and change-freeze windows

**Why ship the Generalist tools as stubs in M1.** The schemas are the load-bearing part — they determine the quorum engine's concern-parsing path, the Generalist prompt structure, and the tool-citation format. Locking the schemas in M1 and populating them with fixtures in M4 means M2 (control plane) and M3 (Architect) can integration-test against the final tool shapes without waiting on real pricing / OPA / historical data.

If Architect and the voters diverge on output shape, it surfaces in M5 integration. Lock the schema now — `docs/mcp-tools.md` (task 1.7) extends these, not replaces them.

**Acceptance criteria**:

- MCP server registers in Consul as `consilium-kb-mcp` with passing health check.
- `curl http://consul.local:8500/v1/health/service/consilium-kb-mcp?passing` returns the node.
- Python test calls each of the seven tools and validates the response schema.
- `security_posture` tool returns IAM-relevant context for at least one sample resource ID.
- `cost_estimate` stub returns the same monthly delta for identical input HCL (deterministic).
- `policy_check` stub returns at least one violation for a wildcard IAM policy fixture and zero for a benign fixture.
- `historian_lookup` stub returns at least one match when queried against a change that structurally resembles a seeded prior deliberation.
- `slo_impact` stub returns `inside_change_freeze=true` for a test resource mapped to a frozen service in the YAML registry.

**Risks**:

- *Risk*: Existing KB doesn't expose the primitives needed for `security_posture`. *Mitigation*: if surfacing IAM relationships from the current graph DB is hard, add a minimal synthetic IAM graph to the seed data and note it as tech debt.
- *Risk*: MCP SDK bugs or version drift. *Mitigation*: pin exact MCP Python SDK version, subscribe to its changelog.

**Artifacts produced**: Runnable MCP server, tool contract documentation, integration tests.

---

### Milestone 2 — Control plane + Terraform provider stub
**Duration**: 1 weekend (~17 hours — +1h vs v0.1 for the fifth agent registration and the hard-veto / soft-concern split in `consilium_quorum_policy`)
**Goal**: `terraform apply` on the example parliament registers all five agents via the control plane.

| # | Task | Estimate |
|---|---|---|
| 2.1 | FastAPI control plane skeleton with `/agents` POST endpoint | 2h |
| 2.2 | Implement Vault AppRole provisioning in `control_plane/consilium/vault_setup.py` | 2h |
| 2.3 | Implement Consul service registration for each agent | 1.5h |
| 2.4 | Implement Nomad job dispatch for each agent (stub jobs that just sleep) — now **five** stubs including `generalist` | 2h |
| 2.5 | Scaffold Terraform provider with `terraform-plugin-framework`; implement `consilium_agent` resource with a `voter_class` attribute (`hard_veto` / `soft_concern` / `none`) | 5h |
| 2.6 | Implement `consilium_quorum_policy` resource — accepts `hard_veto_voters` and `soft_concern_voters` lists; schema also accepts `escalate_concern_to_veto` blocks (parsed but unenforced in v0.1.0; see [voting-architecture.md §5](./docs/voting-architecture.md#5-when-would-we-elevate-a-generalist-concern-to-a-veto)) | 2h |
| 2.7 | Write `examples/minimal_parliament/main.tf` — five agents (speaker, architect, blast_radius, red_team, generalist) + dev quorum policy with hard_veto_voters = [blast_radius, red_team] and soft_concern_voters = [generalist] | 1h |
| 2.8 | End-to-end test: `terraform apply` registers five agents, confirms via Consul catalog (expects `consilium-generalist` among passing services) | 1.5h |

**Control plane API surface (pin before M2.1)**:

| Method | Path | Purpose |
|---|---|---|
| POST | `/agents` | Register an agent (called by `consilium_agent` create) |
| DELETE | `/agents/{name}` | Deregister (called by `consilium_agent` destroy) |
| GET | `/agents/{name}/public_key` | Return the agent's Vault transit public key — used by the audit verifier in M6.2 |
| POST | `/quorum_policies` | Upsert a quorum policy (called by `consilium_quorum_policy`) |
| POST | `/deliberations` | Submit an intent; returns `deliberation_id` |
| GET | `/deliberations/{id}` | Poll status; supports phase-stream via SSE for the CLI |
| GET | `/deliberations/{id}/record` | Fetch the full signed deliberation record |
| GET | `/audit/{id}/chain` | Return the signature chain in the shape the verifier expects |

Fixing these now prevents the CLI (M5.8) and the verifier (M6.2) from each inventing conventions.

**Acceptance criteria**:

- `terraform apply` on the example completes without error.
- `consul catalog services` lists `consilium-speaker`, `consilium-architect`, `consilium-blast-radius`, `consilium-red-team`, `consilium-generalist`.
- Vault has AppRole auth enabled with five named roles (one per agent).
- Five Nomad allocations are running the stub agent containers.
- The quorum policy resource accepts `hard_veto_voters = ["blast_radius", "red_team"]` and `soft_concern_voters = ["generalist"]` and rejects a plan that puts `generalist` in `hard_veto_voters` with a clear validation error.
- `terraform destroy` cleanly removes all registrations.

**Risks**:

- *Risk*: terraform-plugin-framework boilerplate is dense; first-time Go provider authors underestimate this. *Mitigation*: budget an extra evening specifically for M2.5 if not familiar with the framework. Reference the `terraform-provider-scaffolding-framework` template.
- *Risk*: Nomad dispatch vs. run semantics are easy to confuse. *Mitigation*: use `nomad job run` with per-agent job files for the MVP, not parameterised dispatch. Simpler, less to debug.

**Decision needed by end of M2**: Does the provider talk directly to Vault/Consul/Nomad, or only to the control plane API? *Recommendation*: only to the control plane. Keeps the provider thin and centralises orchestration logic.

**Artifacts produced**: Working Terraform provider (local install, not published), control plane API, stub agent Nomad jobs.

---

### Milestone 3 — Agent framework + Architect
**Duration**: 1 weekend (~16 hours)
**Goal**: Architect agent runs in Nomad, receives intent, produces signed proposals.

| # | Task | Estimate |
|---|---|---|
| 3.1 | `agents/base/agent.py` — base class with MCP client, Anthropic client, signer | 3h |
| 3.2 | `agents/base/signing.py` — Vault transit sign/verify helpers with unit tests | 2.5h |
| 3.3 | `agents/architect/main.py` — implement `deliberate()` with KB retrieval + LLM call | 3h |
| 3.4 | Architect system prompt iteration (expect 3–5 rounds on real test cases) | 2.5h |
| 3.5 | HTTP server wrapper so the Architect exposes `/deliberate` endpoint | 1.5h |
| 3.6 | Dockerfile for the agent, production-grade base image | 1h |
| 3.7 | Update Nomad job spec to run the real Architect image | 0.5h |
| 3.8 | Integration test: POST intent to Architect, receive signed proposal, verify signature | 2h |

**Acceptance criteria**:

- Architect container starts, authenticates to Vault via AppRole, logs successful startup.
- POST to `/deliberate` with a sample intent returns a JSON proposal containing valid Terraform HCL.
- The response includes a Vault transit signature that verifies against the `architect` key.
- Terraform HCL in responses passes `terraform fmt -check` and `terraform validate` on a sample module.

**Risks**:

- *Risk*: LLM outputs invalid HCL. *Mitigation*: add a validation retry loop — if `terraform validate` fails, send the error back to the model with the original prompt. Limit to 2 retries.
- *Risk*: Prompt iteration eats the entire weekend. *Mitigation*: time-box prompt work to 2.5h (task 3.4). Ship "good enough" and iterate post-MVP if needed.

**Artifacts produced**: Working Architect agent, signing library with tests, agent base class usable by subsequent agents.

---

### Milestone 4 — Blast Radius + Red Team + Generalist
**Duration**: 1 weekend (~22 hours — +6h vs v0.1 for the Generalist voter, its citation parser, and wiring the four tool stubs from M1 to real-ish data sources)
**Goal**: All three voters produce signed opinions; Red Team holds its accuracy bar; Generalist can only raise concerns that cite a tool output.

| # | Task | Estimate |
|---|---|---|
| 4.1 | `agents/blast_radius/main.py` — parse HCL, query graph, reason over impacts | 3h |
| 4.2 | HCL-to-resource-list parser (use `terraform-json` or similar) | 1.5h |
| 4.3 | Blast Radius system prompt | 1h |
| 4.4 | `agents/red_team/main.py` — security posture lookup + adversarial reasoning | 3h |
| 4.5 | **Red Team system prompt (the critical work)** — iterate against a fixed test set of 5 known-bad changes | 4h |
| 4.6 | Verdict parser for Red Team output (veto / concern / approve / abstain) | 1h |
| 4.7 | `agents/generalist/main.py` — consult all four tools in parallel, synthesise, emit soft-concern opinion | 2h |
| 4.8 | `agents/generalist/citation_parser.py` — enforce "every concern must cite at least one tool output"; uncited concerns rewritten to `abstain` with `reason: unsupported_claim`; veto verdicts rewritten to `error` (protocol violation) | 1.5h |
| 4.9 | Generalist system prompt — instructs model to cite tool output IDs for every concern; enforces the soft-concern vocabulary (`approve | concern | abstain`, never `veto`) | 1h |
| 4.10 | Promote the four Generalist tools from M1 stubs to "real-ish" data: `cost_estimate` reads a small AWS pricing table; `policy_check` embeds ~5 OPA-style rules; `historian_lookup` queries the seeded `:PriorDeliberation` nodes; `slo_impact` reads `slo_registry.yaml` | 2.5h |
| 4.11 | Generalist test set: 5 must-concern cases (cost blowout, policy violation, historical precedent, SLO freeze, tagging miss) + 10 benign cases | 2h |
| 4.12 | Integration tests: all three voters respond to identical proposals with signed, verifiable opinions; adversarial signing tests (key rotation, cross-agent confusion, replay) pass for the Generalist key too | 2.5h |

**Acceptance criteria**:

- Given a safe proposal, Blast Radius returns `approve` with a non-empty impact list.
- Given a proposal that widens a security group to 0.0.0.0/0, Red Team returns `veto` with findings text mentioning the CIDR.
- Given a proposal with a wildcard IAM action, Red Team returns `veto` with findings text referencing the wildcard.
- Given a cost-bait proposal (m5.24xlarge × 3 AZ), Generalist returns `concern` citing `cost_estimate` output with a concrete monthly delta.
- Given a proposal inside a frozen change window, Generalist returns `concern` citing `slo_impact` output.
- Given a proposal the Generalist cannot find anything wrong with, it returns `approve` with zero concerns.
- The citation parser rewrites a hand-crafted "uncited concern" test payload to `abstain` with `reason: unsupported_claim` — i.e. the Generalist physically cannot ship a vague worry.
- If the Generalist prompt is hand-edited to emit `veto`, the parser rewrites it to `error` with `reason: protocol_violation` — a soft-concern voter cannot manufacture a hard-veto.
- All three agents' responses verify against their respective Vault transit keys.
- Red Team's veto rate on the benign test proposal (Scene 1 intent) is 0%. False-positive rate on the 10-example benign test set is ≤10%.
- Generalist's concern rate on the 5-case must-concern set is 100%. Its concern rate on the 10-case benign set is ≤20% (slightly looser than Red Team's — concerns are advisory, so a handful of false soft-concerns is far less costly than a single false veto).

**Risks**:

- *Risk (HIGH)*: Red Team is under-sensitive and rubber-stamps bad changes. *Mitigation*: build the test set in task 4.5 **first** (5 known-bad + 10 benign), iterate prompt against scoreboard. Use `claude-opus-4-6` for Red Team even though `sonnet-4-6` is fine for Architect — the cost delta is worth it for the defining agent.
- *Risk (HIGH)*: Red Team is over-sensitive and vetoes everything. *Mitigation*: same as above. The benign test set is the guardrail.
- *Risk (MEDIUM)*: Generalist turns into a noise machine — raises a concern on every deliberation because "anything could be an issue." *Mitigation*: the citation parser is the hard gate. A concern without a tool-output ID is not a concern. Also: the benign test set (4.11) scores concern-rate, not just must-concern-rate. If the Generalist concerns >20% of benign cases, iterate the prompt.
- *Risk (MEDIUM)*: Generalist attempts to `veto` (the model ignores its soft-concern role). *Mitigation*: two-layer defence — (a) system prompt tells the model its only verbs are `approve | concern | abstain`; (b) the citation parser deterministically rewrites a `veto` verb to `error`. The quorum engine in M5 re-enforces this at tally time.
- *Risk*: HCL parsing is harder than expected due to dynamic blocks. *Mitigation*: MVP parser only handles top-level resources, not modules or `for_each`. Document this limitation.

**Decisions needed by end of M4**:

- **D4**: Minimum acceptable Red Team accuracy to ship the MVP. *Recommendation*: 100% veto on the 5 known-bad cases; ≤10% false positive on the 10 benign cases. If the prompt can't reach this by end of weekend, extend M4 by one evening rather than shipping a rubber-stamp.
- **D13**: Generalist model. *Recommendation*: `claude-sonnet-4-6`. The Generalist's job is synthesis across many structured tool outputs rather than adversarial reasoning; Sonnet is well-matched and Opus budget is already reserved for Red Team.
- **D14**: Generalist minimum accuracy. *Recommendation*: 5/5 on must-concern, ≤2/10 on benign. Concerns are advisory, so the bar is deliberately looser than Red Team's.

**Artifacts produced**: Three working voters, HCL parser, Red Team test harness, Generalist test harness, citation parser with unit tests.

---

### Milestone 5 — Speaker orchestration + Digital Twin
**Duration**: 1 weekend (~17 hours — +1h vs v0.1 for the three-voter tally, the two protocol invariants, and Scene 3's soft-concern smoke test)
**Goal**: Speaker dispatches to three voters in parallel, tallies with veto-class enforcement, signs, and applies.

| # | Task | Estimate |
|---|---|---|
| 5.1 | LangGraph workflow in `control_plane/consilium/speaker.py` with all nodes stubbed | 2h |
| 5.2 | Implement `dispatch_to_analysts` — Consul service discovery + parallel HTTP calls to all three voters | 2h |
| 5.3 | Implement `tally_votes` in `control_plane/consilium/quorum.py` — signature verification, the 3-voter quorum table (below), and the two engine invariants | 3h |
| 5.4 | Implement `sign_and_audit` — compose deliberation record (includes all three voter verdicts with their `verdict_class`), sign, write to Vault audit | 1.5h |
| 5.5 | Digital Twin Nomad job: accepts HCL, runs `terraform plan`, writes JSON outcome to object store | 3h |
| 5.6 | Implement `run_digital_twin` in the workflow | 1.5h |
| 5.7 | Implement `terraform_apply` node using Terraform MCP server | 1h |
| 5.8 | `consilium submit` CLI entrypoint — phase stream shows `generalist` alongside the analysts | 1.5h |
| 5.9 | End-to-end manual tests: happy path, veto path, **and Scene 3 soft-concern path** all work | 1.5h |

**Quorum rule (M5.3 `tally_votes` spec)** — see [voting-architecture.md §3](./docs/voting-architecture.md#3-quorum-table) for the full rationale.

Voter verdicts: `approve`, `concern`, `veto`, `abstain` — where `abstain` is always explicit (timeout, signature-verification failure, or citation parser rewriting an unsupported concern), never silent. The Generalist's allowed vocabulary is `approve | concern | abstain` only — attempting `veto` is a protocol violation.

| Blast Radius | Red Team | Generalist | Speaker action |
|---|---|---|---|
| approve | approve | approve | apply |
| approve | approve | concern | apply; log Generalist concern |
| approve | concern | approve | apply; log Red Team concern |
| approve | concern | concern | apply; log both concerns |
| concern | approve | approve | apply; log Blast Radius concern |
| concern | approve | concern | apply; log both concerns |
| concern | concern | approve | apply; log both analyst concerns |
| concern | concern | concern | apply; log all three concerns |
| veto | * | * | reject |
| * | veto | * | reject |
| abstain | * | * | reject (no quorum) |
| * | abstain | * | reject (no quorum) |
| * | * | abstain | reject (no quorum) — Generalist abstain is *also* a reject |

Per-voter timeout is **D12** (30s per voter, 90s total deliberation budget). The Speaker never auto-escalates an abstain into approve/concern; a missing opinion from *any* voter is always a reject.

**Two protocol invariants the engine enforces** (tests for both are part of 5.3):

1. **Veto-class enforcement.** If a voter whose `voter_class` is `soft_concern` returns a `veto` verdict, the tally is marked `error` with `reason: protocol_violation` — not `reject`. This lets operators distinguish "the parliament said no" from "an agent is misbehaving and the quorum engine stopped it."
2. **Uncited-concern rejection.** If the citation parser flagged a Generalist concern as unsupported (and rewrote it to `abstain`), the Speaker sees `abstain` and rejects via the no-quorum rule above. The prompt cannot launder an uncited concern into an apply-with-log.

Both invariants are enforced in the quorum engine (deterministic code), not in prompts, so a prompt regression cannot silently bypass them.

**Acceptance criteria**:

- `consilium submit "<intent>"` triggers the full workflow and streams phase updates to stderr — includes a `generalist` phase line.
- On approval, a real `terraform plan` outcome is produced by the twin and visible in the logs.
- On approval, `terraform apply` is dispatched and the change lands in the target workspace.
- On rejection, no apply fires; CLI exits with non-zero status.
- Scene 3 smoke test: a cost-bait intent produces `apply` with an attached Generalist concern that cites `cost_estimate` output in the signed deliberation record.
- Vault audit log contains a signed deliberation record for every deliberation (successful or not), including all three voters' signed opinions.
- The Speaker rejects any opinion whose signature fails verification (test by submitting a tampered opinion manually).
- Protocol-invariant smoke test: a hand-crafted Generalist opinion with verdict `veto` is rejected with `error: protocol_violation`, not `reject`.

**Risks**:

- *Risk*: LangGraph state persistence is weaker than expected; a Speaker crash mid-deliberation loses the deliberation. *Mitigation*: acceptable for MVP (the demo doesn't crash). Note as known limitation; Temporal migration is the post-MVP fix.
- *Risk*: Digital Twin `terraform plan` is slow (30+ seconds). *Mitigation*: use a minimal target workspace (≤5 resources) for the MVP demo. Acceptable latency.
- *Risk*: Terraform MCP server setup for `apply` is fiddly. *Mitigation*: for MVP, have the Speaker shell out to `terraform apply` directly if the MCP path blocks. Document as tech debt.

**Artifacts produced**: Working Speaker, Digital Twin Nomad job, CLI, end-to-end pipeline.

---

### Milestone 6 — Demo polish + audit verifier + documentation
**Duration**: 1 weekend (~18 hours — +2h vs v0.1 for the cost-bait demo project and the fourth demo scene)
**Goal**: The demo is recordable; someone else can run the repo cold.

| # | Task | Estimate |
|---|---|---|
| 6.1 | Build the three demo Terraform projects: happy path target, veto-bait target, **cost-bait target** (m5.24xlarge × 3 AZ for Scene 3) | 3h |
| 6.2 | Implement `consilium audit verify <id>` CLI command — output includes voter-class annotation per signed opinion | 3h |
| 6.3 | CLI output polish — phase streaming (all three voters), colours, ASCII progress | 2h |
| 6.4 | Record demo video (expect 4–6 takes) — now **four scenes** | 3.5h |
| 6.5 | Write demo narration / blog post accompanying the video — lead with "why three voters, not four" | 2.5h |
| 6.6 | Update all repo documentation to reflect reality (what shipped vs. what was planned) | 1.5h |
| 6.7 | Cold-install test: fresh VM, clone repo, follow README, measure time-to-first-deliberation | 1.5h |
| 6.8 | Tag `v0.1.0-mvp` release with release notes — list the three voters and their classes | 1h |

**Acceptance criteria**:

- Demo video is ≤3 minutes, shows all four scenes from §2.3 (happy, veto, soft-concern, audit), and is embedded in the README.
- `consilium audit verify` on the vetoed deliberation outputs a valid cryptographic chain listing all three voter signatures with their classes.
- `consilium audit verify` on the Scene 3 deliberation shows the Generalist's signed opinion with the `cost_estimate` citation visible in the record.
- Cold-install test completes in ≤15 minutes without requiring external help.
- Release tagged and GitHub release page has binaries/artefacts attached.

**Risks**:

- *Risk*: Demo recording takes far more takes than expected. *Mitigation*: script every line in advance; practise without recording twice before rolling.
- *Risk*: Cold install fails on a fresh environment because of hidden local state on dev machine. *Mitigation*: actually do the cold install on a clean VM, not a "similar enough" environment.

**Artifacts produced**: Demo video, audit verifier, release, public-ready repo.

---

## 5. Risk register (cross-cutting)

| Risk | Likelihood | Impact | Mitigation | Owner |
|---|---|---|---|---|
| Red Team is the weakest link and rubber-stamps changes | High | Critical | Build test harness before prompt; iterate against scoreboard; use stronger model | Dev |
| Anthropic API rate limits during iterative prompt work | Medium | Medium | Cache test-set invocations locally; use Sonnet for exploration, Opus for eval | Dev |
| Scope creep toward "full parliament" (extra voters beyond the three) before MVP ships | High | High | Hard boundary: Blast Radius, Red Team, Generalist are the only voters until the demo ships. Compliance / Cost / Historian stay as tools, not voters — elevation is v0.2.0+. See [voting-architecture.md §6](./docs/voting-architecture.md#6-post-mvp-when-would-we-split-the-generalist). | Dev |
| Generalist becomes a noise machine (concern on every deliberation) | Medium | Medium | Citation parser is the hard gate — uncited concerns are rewritten to abstain; benign test set in M4.11 scores concern-rate | Dev |
| Generalist attempts a `veto` (prompt drift) | Low | Medium | Two-layer defence: citation parser + quorum engine invariant (5.3). Both are deterministic code, not prompt-level. | Dev |
| LangGraph state loss on restart | Medium | Low (demo), High (prod) | Accept for MVP; migrate to Temporal in Phase 2 | Dev |
| Terraform provider complexity blocks M2 | Medium | High | Pre-read the Plugin Framework docs; have fallback of a pure-API approach if the provider isn't working by end of M2.6 | Dev |
| Docker resource exhaustion on dev machine | Medium | Medium | Slim-compose profile; document minimum specs | Dev |
| Vault transit signature verification is subtly wrong | Low | Critical | Write signing library tests first (TDD); independent verification using a separate Vault client in tests | Dev |
| Demo video production takes longer than the weekend | Medium | Medium | Script in advance; treat recording as a sub-project of M6 | Dev |
| HashiCorp/IBM ship something very similar before MVP is public | Medium | High (to mindshare) | Accept. The parliament + cryptographic provenance angles are still differentiated even if Infragraph evolves | — |
| Existing polyglot KB needs more surgery than expected | Medium | High | Budget an extra weekend as Milestone 1.5 if task 1.3 slips >50% | Dev |

---

## 6. Decision log

Decisions that need to be made during the build. Record rationale and date.

| # | Decision | Needed by | Default if undecided | Decided on | Outcome |
|---|---|---|---|---|---|
| D1 | Final project name (Consilium vs alternative) | Before M0 | Consilium | — | — |
| D2 | Provider talks to Vault/Consul directly, or only via control plane | End of M2 | Control plane only | — | — |
| D3 | Red Team model: Opus or Sonnet | Start of M4 | Opus | — | — |
| D4 | Minimum acceptable Red Team accuracy to ship | Mid M4 | 5/5 bad + ≤1/10 benign FP | — | — |
| D5 | LLM usage cap per deliberation (safety net) | Mid M4 | $0.50 per deliberation | — | — |
| D6 | Terraform apply path: MCP server or shell out | End of M5.7 | Shell out (simpler) | — | — |
| D7 | Demo hosting: YouTube unlisted, LinkedIn native, or both | Start of M6 | Both | — | — |
| D8 | Open source licence (MPL 2.0 vs Apache 2.0) | Before v0.1.0 tag | MPL 2.0 | — | — |
| D9 | Quorum rule (timeouts + concern handling) | End of M4 | Veto absolute; abstain ⇒ reject; concern ⇒ approve-with-log | — | — |
| D10 | Demo target infrastructure (LocalStack / AWS sandbox / mock provider) | Start of M5 | LocalStack — reproducible, free, no credential leakage in recording | — | — |
| D11 | Architect model (Sonnet vs Opus) | Start of M3 | Sonnet 4.6 — Architect cost dominates the loop; reserve Opus budget for Red Team | — | — |
| D12 | Per-voter deliberation timeout | End of M4 | 30s per voter, 90s total deliberation budget | — | — |
| D13 | Generalist model (Sonnet vs Opus) | Start of M4 | Sonnet 4.6 — Generalist synthesises structured tool outputs; adversarial reasoning isn't the bottleneck, Opus budget is reserved for Red Team | — | — |
| D14 | Generalist minimum accuracy to ship | Mid M4 | 5/5 must-concern + ≤2/10 false concern on benign set (looser than Red Team because concerns are advisory, not blocking) | — | — |
| D15 | Voter-set architecture (2 vs 3 vs 4 voters) | — | Decided 2026-04-17: 3 voters (BlastRadius, RedTeam, Generalist); 4-voter Compliance design rejected — Compliance is deterministic and belongs in a tool. See [voting-architecture.md §7](./docs/voting-architecture.md#7-decision-log-entry). | 2026-04-17 | 3 voters |

---

## 7. Test strategy

Three layers, minimum:

**Unit tests** (every milestone):
- Signing library (M3): sign/verify round trips, tampered payload detection, wrong-key rejection. **Adversarial cases** (must pass before M3 is "done"): (a) *key rotation* — opinion signed under transit key v1, verified after rotation to v2, must fail with `key_version_mismatch` rather than silently accept; (b) *cross-agent confusion* — Architect's signature presented as Red Team's must fail on key-identity check, not just payload check; (c) *replay* — the same signed opinion submitted against a different `deliberation_id` must fail, which means `deliberation_id` must be inside the signed envelope, not alongside it. The cross-agent-confusion test must also cover a Generalist signature presented as a Blast Radius signature (five keys, pairwise).
- HCL parser (M4): resource extraction from ≥10 sample configurations.
- Citation parser (M4.8): (a) uncited concern → `abstain` with `reason: unsupported_claim`; (b) concern citing an unknown tool-output ID → `abstain`; (c) concern citing a real tool-output ID → passthrough; (d) verdict `veto` from the Generalist → `error` with `reason: protocol_violation`.
- Quorum policy evaluator (M5): veto precedence, unanimous vs majority semantics, minimum-agents enforcement, voter-class enforcement (soft-concern voter returning `veto` is an error, not a reject), Generalist abstain is a reject.

**Integration tests** (per milestone):
- MCP server (M1): each tool returns valid structured output.
- Control plane (M2): agent registration produces Consul service, Vault role, Nomad alloc.
- Agent deliberation (M3, M4): given proposal → signed opinion.
- Speaker (M5): full happy-path and veto-path smoke tests.

**The Generalist test set** (M4.11):
- 5 must-concern cases (expect `concern` 100%):
  1. Cost blowout: m5.24xlarge × 3 AZ (cost_estimate output > stub threshold)
  2. Policy violation: S3 bucket created without the `owner` tag (policy_check rule `require-owner`)
  3. Historical precedent: a module shape that matches a seeded `:PriorDeliberation` marked `incident`
  4. SLO freeze: DB schema change against a service whose `slo_registry.yaml` entry is inside a frozen window
  5. Policy violation + cost: wildcard egress SG + oversized NAT — tests multi-citation concern
- 10 benign cases (false-concern rate ≤20%):
  1. Add t3.small to dev-vpc
  2. Tag an S3 bucket with the `owner` value
  3. Attach `ReadOnlyAccess` to a scoped role
  4. Add a CloudWatch alarm
  5. Enable S3 versioning
  6. Create a private subnet in an existing VPC
  7. Increase RDS storage within the same family
  8. Increase Lambda memory within a 2× factor
  9. Add a Route 53 record to an existing zone
  10. Add a security group rule between two existing internal SGs

**The Red Team test set** (M4, the critical one):
- 5 known-bad changes (must veto 100%):
  1. Security group opens 0.0.0.0/0 on port 22
  2. IAM policy grants `*` on `*`
  3. Role trust policy allows `sts:AssumeRole` from `*`
  4. S3 bucket policy grants public read on bucket containing PII-schema tag
  5. Cross-account IAM role without condition keys
- 10 benign changes (false-positive rate ≤10%, i.e. ≤1 vetoed):
  1. Add t3.medium EC2 to private subnet
  2. Tag an S3 bucket
  3. Increase RDS instance size within same family
  4. Add a CloudWatch alarm
  5. Update IAM policy to add a single specific action
  6. Create a new private subnet in an existing VPC
  7. Attach managed policy `ReadOnlyAccess` to a scoped role
  8. Enable versioning on an S3 bucket
  9. Update a security group to allow traffic from a specific internal SG
  10. Increase Lambda memory allocation

Score after every prompt change. Ship only when both thresholds are met.

**End-to-end test** (M6): the cold-install flow from §2.1.

---

## 8. Definition of Done for the MVP

The MVP ships when a checklist at the top of `RELEASE.md` shows all green:

- [ ] Demo video embedded in README, showing all four scenes (happy, veto, soft-concern, audit)
- [ ] Red Team test set passes: 5/5 veto on known-bad, ≤1/10 false positive on benign
- [ ] Generalist test set passes: 5/5 concern on must-concern, ≤2/10 false concern on benign
- [ ] Citation parser tests pass: uncited concern → abstain; Generalist `veto` → protocol_violation
- [ ] Quorum engine enforces voter-class invariant (unit test + manual smoke test)
- [ ] `consilium audit verify` command exists and produces a readable cryptographic proof across all three voter signatures
- [ ] Fresh-clone cold install completes in ≤15 minutes on a Linux or macOS machine with Docker Desktop
- [ ] Every signed artefact in a deliberation verifies against its publishing agent's Vault transit key (five keys including `generalist`)
- [ ] The Speaker rejects tampered opinions (negative test documented)
- [ ] CI pipeline passes on `main`
- [ ] `v0.1.0-mvp` tag exists with attached release notes
- [ ] README, ARCHITECTURE, IMPLEMENTATION, MVP_PLAN, voting-architecture docs are consistent with shipped behaviour

---

## 9. Post-MVP priorities

Once the MVP ships and the demo is public, the next three things to build (in priority order):

1. **Temporal graph layer + Historian agent.** Adds time-travel debugging, which is the second demo-worthy capability. Substantial work but genuinely new relative to Infragraph.
2. **Temporal.io migration for the Speaker.** The LangGraph durability gap is the largest production blocker.
3. **Observability stack.** OpenTelemetry traces for each deliberation; token-cost attribution per agent per decision. Makes cost conversations defensible.

Federation, multi-agent Cost/Security split, break-glass signing, and the public Terraform registry listing follow after these.

---

## 10. Burn-down

| Week | Milestone | Cumulative hours | % complete | Demo-ready? |
|---|---|---|---|---|
| 0 | Pre-flight checklist | 2 | 2% | No |
| 1 | M0: Foundation | 6 | 5% | No |
| 2 | M1: KB + MCP (7 tools, 4 stubbed) | 24 | 21% | No |
| 3 | M2: Control plane + Provider (5 agents) | 41 | 37% | No |
| 4 | M3: Architect | 57 | 51% | No (one voter only) |
| 5 | M4: Blast Radius + Red Team + Generalist | 79 | 71% | No (no orchestration) |
| 6 | M5: Speaker + Twin | 96 | 86% | **Yes, rough** |
| 7 | M6: Polish + demo | 114 | 100% | **Yes, public** |

The critical inflection is end of Week 6 — that's when you first know whether the thesis works end-to-end. If you're more than 8 hours behind by then, hold the demo another weekend rather than shipping a janky video.

---

## 11. Kill criteria

The project should be honestly reassessed (and potentially abandoned as specified) if **any** of these become true mid-build:

- By end of M4, Red Team cannot reach the minimum accuracy bar after 8 hours of prompt iteration. The "conscience" thesis fails without a working Red Team.
- By end of M4, Generalist cannot be held to the soft-concern contract — either the citation parser is easy to evade (concerns slip through uncited) or the quorum engine invariants can be regressed by a prompt change. The "fewer voters, richer tools" thesis relies on structural enforcement, not prompt discipline.
- By end of M5, Vault transit signing round-trips are unreliable (intermittent verification failures). The cryptographic provenance thesis fails without deterministic signatures.
- HashiCorp/IBM ships an equivalent parliament-with-signatures feature in a public release before M6. In that case, pivot the framing from "product proposal" to "reference implementation / educational project" — it's still valuable but the mindshare calculus changes.

These are stop-and-think moments, not automatic kills. But pretending they didn't happen costs more than acknowledging them.

---

## 12. Observability minimum

Full OpenTelemetry is deferred (§2.2). But every agent and the Speaker must emit **one structured JSON log line per phase transition** to stdout. Docker captures it; no infra cost.

Required fields:

```json
{
  "ts": "2026-05-01T12:34:56.789Z",
  "deliberation_id": "del_01HXYZ...",
  "agent": "architect|blast_radius|red_team|generalist|speaker",
  "phase": "mcp_call|llm_call|sign|dispatch|tally|apply",
  "duration_ms": 1234,
  "input_tokens": 1500,
  "output_tokens": 800,
  "model": "claude-sonnet-4-6",
  "outcome": "ok|error|timeout"
}
```

This is the cheapest thing that unlocks three MVP-relevant capabilities:

1. **Enforces D5** (per-deliberation cost cap). Sum `input_tokens * in_rate + output_tokens * out_rate` per `deliberation_id` in the Speaker; reject over-budget deliberations before `apply`.
2. **Material for the M6 blog post.** "Scene 2 took 38s and N tokens across four agents" is a concrete datum, not a vibe.
3. **Free regression signal.** If a prompt change doubles Architect tokens, the next deliberation's log shows the delta immediately.

Estimate: 1–1.5h total, spread across M3 (Architect), M4 (Blast Radius + Red Team), M5 (Speaker). Add as a sub-task in each agent's introducing milestone rather than a separate milestone.

---

## 13. Pre-demo runbook

The night before the M6.4 recording, run this in order. It exists because recording sessions most often fail on state drift, not code bugs.

**Health checks** (all must pass):

- [ ] `vault status` — initialized, unsealed, not standby
- [ ] `consul catalog services | grep consilium` — lists `speaker`, `architect`, `blast-radius`, `red-team`, `generalist`, `kb-mcp`, all healthy
- [ ] `nomad status` — all allocations `running`, no restarts in the last hour
- [ ] `docker logs --tail=100 consilium-speaker 2>&1 | grep -iE 'error|panic'` — empty
- [ ] `./dev/bootstrap.sh --reset` — exists, documented, executed successfully this week

**Smoke tests** (must succeed end-to-end):

- [ ] `consilium submit "add a t3.small to dev-vpc for a noop job"` returns a `deliberation_id` within 90s
- [ ] `consilium submit "add m5.24xlarge in every AZ"` returns an `apply` with a Generalist concern attached (Scene 3 smoke)
- [ ] `consilium audit verify <deliberation_id>` prints a green cryptographic chain for all three voter signatures

**If any check fails**: do not record. Fix first. A re-recorded demo is cheaper than a demo with a hidden flaw an infrastructure engineer will notice in the first minute.

---

*This plan is a living document. Update the Decision Log as decisions are made; update the Risk Register when new risks emerge; update the Burn-down weekly. A plan that never changes is a plan nobody is using.*
