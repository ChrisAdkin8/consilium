# Consilium MVP — Build Prompt

You are a senior infrastructure engineer building the **Consilium MVP** in this repository. This document is your standing brief. Re-read it at the start of every session, and follow [MVP_PLAN.md](./MVP_PLAN.md) for long-form rationale and [TODO.md](./TODO.md) for live progress tracking.

Your single optimisation target: **a four-scene demo (§1 below), posted publicly, sharp enough that an infrastructure engineer sends it to a colleague.** Not a product. Not a platform. A demo.

---

## 1. What "done" looks like — the demo (the forcing function)

Every task you execute must advance one of these four scenes. If it doesn't, defer it and log to TODO.md under "post-MVP".

1. **Happy path (45s).** Operator runs `consilium submit "Add a t3.medium EC2 instance to staging-vpc for a batch job."` The terminal streams each phase: Architect drafting, Blast Radius analysing, Red Team probing, Generalist synthesising cost/policy/precedent/SLO signals, Twin running `terraform plan`, Speaker tallying, decision signed, apply dispatched. Final line prints the deliberation ID and a verify command.

2. **Veto (45s).** Operator runs `consilium submit "Grant the batch job role s3:PutObject on logs-bucket and sts:AssumeRole on *."` Red Team returns findings including "wildcard role trust permits privilege escalation from batch runtime to any IAM role in account." Speaker records a veto with signed rationale. **No apply fires.**

3. **Soft concern (30s).** Operator runs `consilium submit "Add an m5.24xlarge instance in every AZ for the batch job."` Red Team and Blast Radius both approve. Generalist raises a `cost_estimate` concern citing the +$X/mo delta. Speaker signs `PROCEED` with the concern attached to the audit record. **Apply still fires** — demonstrating the soft-concern mechanic and the tool-citation discipline.

4. **Audit (30s).** `consilium audit verify <deliberation_id>` on the vetoed decision. Output shows every signature verified against each agent's published Vault transit key, with timestamps and the final vote tally.

---

## 2. Operating principles (non-negotiable)

### Scope discipline
- Five agents only: **Speaker, Architect, Blast Radius, Red Team, Generalist**. Three of them vote (Blast Radius and Red Team with hard-veto; Generalist with soft-concern only). No dedicated Historian, Cost, Compliance, or Security-split voter — those concerns live as **tools** the Generalist consults, not as separate voters. See [docs/voting-architecture.md](./docs/voting-architecture.md) for the rationale behind rejecting the 4-voter design.
- No Temporal.io, no OpenTelemetry stack, no temporal graph (beyond the simple `historian_lookup` tool), no multi-environment policies beyond `dev` and `prod`, no break-glass signing, no federation, no concern-to-veto escalation rules (plumbing deferred to v0.2.0).
- If you catch yourself building infrastructure that is not on the current milestone's task list in MVP_PLAN.md §4, stop and ask.

### Milestone gates
- Execute milestones in order: **M0 → M1 → M2 → M3 → M4 → M5 → M6.**
- At the end of each milestone, **stop**. Report the acceptance-criteria outcomes. Wait for explicit "proceed to M*N+1*" before starting the next.
- Within a milestone, follow the numbered task order in MVP_PLAN.md unless dependencies clearly allow parallelism. Parallelise only independent work.

### Ask before destructive or irreversible actions
- `terraform destroy`, `docker compose down -v` (volume delete), `rm -rf`, `git push --force`, key rotation, release-tag deletion: ask first, even on scaffolding you created.
- Never skip CI hooks or signing (`--no-verify`, `--no-gpg-sign`).

### Follow the pinned contracts
- Sections 4–8 of this prompt are contracts. Do not invent parallel schemas or rename fields for stylistic reasons.
- If a contract needs to change, raise it as a decision: add or update a row in MVP_PLAN.md §6, wait for resolution, then update the contract here. Do not silently diverge.

### Budget honesty
- Each milestone and each task has an hour budget in MVP_PLAN.md. If a task exceeds **150% of its estimate**, stop and report what is blocking. Do not silently burn into the next milestone's budget.
- If an entire milestone exceeds its budget by ≥8 hours, re-plan before continuing.

### Evidence over narration
- Report outcomes with file paths, command output, and test results — not summaries of what you intended to do.
- When claiming a health check is green, paste the command and its output.

---

## 3. Repository layout

Produce this tree. Additions beyond it require approval.

```
consilium/
├── MVP_PLAN.md
├── TODO.md
├── BUILD_PROMPT.md                 # this file
├── README.md
├── CONTRIBUTING.md
├── RELEASE.md
├── dev/
│   ├── docker-compose.yml          # Vault, Consul, Nomad, Neo4j
│   ├── docker-compose.slim.yml     # omit Neo4j for low-RAM hosts
│   └── bootstrap.sh                # transit keys, AppRole, audit, Neo4j schema
├── kb_extensions/
│   ├── base/                       # vendored polyglot KB (aws- or gcp-)
│   ├── mcp_server.py               # exposes 3 tools, see §4
│   └── seed/
│       └── sample_project.tf
├── control_plane/
│   └── consilium/
│       ├── __init__.py
│       ├── api.py                  # FastAPI routes, see §5
│       ├── vault_setup.py
│       ├── consul_registry.py
│       ├── nomad_dispatch.py
│       ├── speaker.py              # LangGraph workflow
│       ├── quorum.py               # implements §7 tally rule
│       └── audit.py
├── agents/
│   ├── base/
│   │   ├── agent.py                # base class: MCP client + LLM client + signer
│   │   ├── signing.py              # Vault transit wrap/verify
│   │   ├── mcp_client.py
│   │   ├── obs.py                  # §8 structured logging helper
│   │   └── http_server.py          # /deliberate HTTP wrapper
│   ├── architect/
│   │   ├── main.py
│   │   └── prompts/
│   │       └── v1.md               # versioned; never edit, create v2.md
│   ├── blast_radius/                # hard-veto voter
│   │   ├── main.py
│   │   ├── hcl_parser.py
│   │   └── prompts/v1.md
│   ├── red_team/                    # hard-veto voter
│   │   ├── main.py
│   │   ├── verdict_parser.py
│   │   └── prompts/v1.md
│   └── generalist/                  # soft-concern voter
│       ├── main.py
│       ├── citation_parser.py       # enforces "every concern cites a tool output"
│       └── prompts/v1.md
├── provider/                       # Terraform provider (Go)
│   ├── main.go
│   └── internal/
│       ├── provider/
│       ├── resource_agent/
│       └── resource_quorum_policy/
├── nomad/
│   ├── kb_mcp.nomad.hcl
│   ├── architect.nomad.hcl
│   ├── blast_radius.nomad.hcl
│   ├── red_team.nomad.hcl
│   ├── generalist.nomad.hcl
│   ├── speaker.nomad.hcl
│   └── twin.nomad.hcl              # digital twin: runs terraform plan
├── examples/
│   └── minimal_parliament/
│       └── main.tf
├── cli/
│   └── consilium/
│       ├── __main__.py
│       ├── submit.py
│       └── audit_verify.py
├── tests/
│   ├── unit/
│   │   ├── test_signing.py         # includes §6 adversarial cases
│   │   ├── test_hcl_parser.py
│   │   └── test_quorum.py
│   ├── integration/
│   │   ├── test_mcp_tools.py
│   │   ├── test_control_plane.py
│   │   └── test_speaker.py
│   ├── red_team/
│   │   ├── bad_cases/              # 5 known-bad fixtures
│   │   ├── benign_cases/           # 10 benign fixtures
│   │   └── scoreboard.py           # prints pass/fail per case
│   └── generalist/
│       ├── concern_cases/          # 5 should-raise-concern fixtures (cost / policy / precedent / SLO)
│       ├── benign_cases/           # 10 benign fixtures (no concern expected)
│       └── scoreboard.py           # prints pass/fail per case
├── docs/
│   ├── mcp-tools.md
│   ├── schemas.md
│   ├── threat-model.md
│   └── runbook.md
└── .github/workflows/
    └── ci.yml
```

---

## 4. Contract — MCP tool schemas (M1 + M4)

Seven tools the KB extension exposes. The first three (M1) back Architect / Blast Radius / Red Team. The last four (M4) back the Generalist. Pin these before writing the server. Stub implementations are acceptable in M1 for the M4 tools — real data sources can land later, but **the schemas do not change**.

### `semantic_search` (M1)
- **consumers**: Architect, Generalist
- **input**: `{ query: string, k?: int = 5, filters?: { resource_type?: string, provider?: string } }`
- **output**: `{ results: [{ id, snippet, source_uri, score }], query_embedding_id }`
- **errors**: `embedding_backend_unavailable`, `invalid_filter`

### `blast_radius` (M1)
- **consumer**: Blast Radius
- **input**: `{ resource_ids: [string], depth?: int = 2 }`
- **output**: `{ impacted: [{ id, type, relation, distance }], edges_traversed: int, truncated: bool }`
- **errors**: `unknown_resource`, `graph_timeout`

### `security_posture` (M1)
- **consumer**: Red Team
- **input**: `{ resource_id: string } | { hcl_fragment: string }`
- **output**: `{ findings: [{ severity, code, summary, cited_policies: [string] }], iam_principals_affected: [string] }`
- **errors**: `unsupported_resource`, `no_policy_context`

### `cost_estimate` (M1 stub, M4 real data)
- **consumer**: Generalist
- **input**: `{ hcl_fragment: string, region?: string = "us-east-1" }`
- **output**: `{ monthly_delta_usd: number, line_items: [{ resource_id, type, monthly_usd }], pricing_source: string, confidence: "high" | "medium" | "low" }`
- **errors**: `unsupported_resource`, `pricing_backend_unavailable`

### `policy_check` (M1 stub, M4 real data)
- **consumer**: Generalist
- **input**: `{ hcl_fragment: string, policy_set?: string = "default" }`
- **output**: `{ violations: [{ rule_id, severity, summary, cited_controls: [string] }], evaluator: "opa" | "sentinel" | "stub", policies_evaluated: int }`
- **errors**: `policy_set_unknown`, `evaluator_unavailable`

### `historian_lookup` (M1 stub, M4 real data)
- **consumer**: Generalist
- **input**: `{ hcl_fragment: string, k?: int = 5 }`
- **output**: `{ matches: [{ deliberation_id: string | null, incident_id: string | null, summary: string, structural_similarity: number, outcome: "applied" | "rejected" | "incident" }] }`
- **errors**: `graph_timeout`

### `slo_impact` (M1 stub, M4 real data)
- **consumer**: Generalist
- **input**: `{ resource_ids: [string] }`
- **output**: `{ at_risk_services: [{ service: string, slo: string, risk: "high" | "medium" | "low" }], inside_change_freeze: bool, change_freeze_reason: string | null }`
- **errors**: `unknown_resource`, `slo_backend_unavailable`

**Citation contract for the Generalist.** Every `concern` in a Generalist opinion must reference one of the four tools above by name and include the tool's output payload. A concern without a citation is rejected by `citation_parser.py` and the opinion is recorded as `abstain` with `reason: unsupported_claim`. The Generalist's prompt (`agents/generalist/prompts/v1.md`) encodes this rule; the parser enforces it at ingest time — prompt regression cannot bypass the parser.

Write `docs/mcp-tools.md` as an extension of these, not a replacement.

---

## 5. Contract — Control plane API surface (M2)

Implement all endpoints in `control_plane/consilium/api.py`. The Terraform provider, CLI, and audit verifier all depend on this surface.

| Method | Path | Purpose |
|---|---|---|
| POST | `/agents` | Register an agent (called by `consilium_agent` create) |
| DELETE | `/agents/{name}` | Deregister (called by `consilium_agent` destroy) |
| GET | `/agents/{name}/public_key` | Return the agent's Vault transit public key — used by the audit verifier in M6.2 |
| POST | `/quorum_policies` | Upsert a quorum policy (called by `consilium_quorum_policy`) |
| POST | `/deliberations` | Submit an intent; returns `deliberation_id` |
| GET | `/deliberations/{id}` | Poll status; supports phase-stream via Server-Sent Events for the CLI |
| GET | `/deliberations/{id}/record` | Fetch the full signed deliberation record |
| GET | `/audit/{id}/chain` | Return the signature chain in the shape the verifier expects |

---

## 6. Contract — Signed envelope (M3)

Every opinion and every final decision uses this envelope. `deliberation_id` is **inside** the signed payload — this is what defends against replay.

```json
{
  "envelope_version": "1",
  "deliberation_id": "del_01HXYZ...",
  "agent": "architect|blast_radius|red_team|generalist|speaker",
  "phase": "proposal|opinion|decision",
  "issued_at": "2026-05-01T12:34:56.789Z",
  "verdict": "approve|concern|veto|abstain",
  "verdict_class": "hard-veto|soft-concern|none",
  "payload": { },
  "payload_hash": "sha256:..."
}
```

`verdict_class` is a cross-check against the quorum engine: `blast_radius` and `red_team` must use `hard-veto`; `generalist` must use `soft-concern`; the Architect and Speaker use `none`. The Speaker rejects any opinion where `verdict = "veto"` and `verdict_class = "soft-concern"` with a `protocol_violation` error — this prevents a regressed Generalist prompt from smuggling a veto through.

Wrapped with:
```json
{
  "envelope": { /* as above */ },
  "signature": "base64...",
  "key_id": "consilium/architect",
  "key_version": 3
}
```

### Adversarial test obligations (must pass before M3 ships)

Write these tests **before** writing the signer:
1. **Key rotation.** Sign with v1; rotate the transit key to v2; verify must fail with `key_version_mismatch` — not silently accept.
2. **Cross-agent confusion.** Architect's signature presented as Red Team's must fail on key-identity check, not just payload-hash check.
3. **Replay.** Same signed envelope submitted against a different `deliberation_id` must fail — because `deliberation_id` is inside the signed payload.

---

## 7. Contract — Quorum rule (M5)

`control_plane/consilium/quorum.py` implements this table exactly. `abstain` is always explicit (timeout or signature-verification failure) — never silent. Full explanation of voter classes in [docs/voting-architecture.md](./docs/voting-architecture.md).

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
| * | * | abstain | reject (no quorum) |

**Two engine invariants** (implemented as guards, not prompt conventions):

1. **Veto-class enforcement.** If `generalist` returns `verdict = "veto"`, the engine records `error` with code `protocol_violation` and rejects the deliberation — Generalist is soft-concern only and cannot issue a veto. Only `blast_radius` and `red_team` may return `veto`.
2. **Uncited-concern enforcement.** A Generalist `concern` whose payload does not reference one of {`cost_estimate`, `policy_check`, `historian_lookup`, `slo_impact`} tool outputs is rewritten to `abstain` with `reason: unsupported_claim` by `citation_parser.py` before reaching the quorum engine. This rejects the deliberation via the standard abstain path (row 13 above).

Per-voter timeout: **30s**. Total deliberation budget: **90s**. (MVP_PLAN D12.)

**Escalation** (concern → veto under policy rules) is **deferred to v0.2.0.** The MVP quorum engine evaluates the table above and nothing else.

---

## 8. Contract — Observability log (M3+)

Every agent and the Speaker emit one structured JSON line to stdout per phase transition. Docker captures it; no external infra required.

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

This is the mechanism that enforces the per-deliberation cost cap (MVP_PLAN D5) and feeds the M6.5 blog post.

---

## 9. Build sequence

Execute in order. Stop and report at each `===` gate; wait for "proceed" before continuing.

### === M0 — Foundation (4h) ===
Produce: `dev/docker-compose.yml`, `dev/docker-compose.slim.yml`, `dev/bootstrap.sh`, `.github/workflows/ci.yml`, `CONTRIBUTING.md`, directory skeleton.
**Acceptance report**: paste output of `docker compose up -d`, `./dev/bootstrap.sh`, and CI run URL. Confirm `vault list consilium/transit/keys` returns the six agent keys (`speaker`, `architect`, `blast_radius`, `red_team`, `generalist`, `operator`).

### === M1 — KB + MCP server (18h, +2h vs original for four extra tool stubs) ===
Produce: vendored `kb_extensions/base/`, `kb_extensions/mcp_server.py` implementing §4 schemas (all seven tools; `cost_estimate`, `policy_check`, `historian_lookup`, `slo_impact` may ship as deterministic stubs returning canned fixtures keyed off the input — real data sources land in M4), Neo4j seed, `agents/base/mcp_client.py`, `nomad/kb_mcp.nomad.hcl`, `docs/mcp-tools.md`, integration test.
**Acceptance report**: output of `curl http://localhost:8500/v1/health/service/consilium-kb-mcp?passing` and `pytest tests/integration/test_mcp_tools.py -v` (tests cover all seven tools).

### === M2 — Control plane + provider (17h, +1h for Generalist registration) ===
Produce: FastAPI implementation of all §5 endpoints, Vault AppRole provisioning, Consul registration, Nomad stub dispatch for all five agents (including Generalist), `provider/` with `consilium_agent` and `consilium_quorum_policy` resources, `examples/minimal_parliament/main.tf` registering all five agents plus a quorum policy that pins Generalist as soft-concern.
**Acceptance report**: `terraform apply` output, `consul catalog services` output (five services registered), `nomad alloc status` output.
**Decision to resolve**: D2 (provider talks to control plane only vs. direct to Vault/Consul).

### === M3 — Architect (16h) ===
**Signing tests FIRST**: write and pass all three §6 adversarial tests before any Architect logic. If they don't pass, stop and report — do not build the Architect on a broken signer.
Then: `agents/base/agent.py`, `agents/architect/main.py`, `agents/architect/prompts/v1.md` (time-box prompt iteration to 2.5h), Dockerfile, Nomad job, integration test.
Observability: Architect emits §8 logs per phase.
**Acceptance report**: signing test output, `pytest tests/integration/test_architect.py -v`, sample signed proposal JSON.
**Decisions to resolve**: D11 (Architect model — Sonnet 4.6 default).

### === M4 — Blast Radius + Red Team + Generalist (22h, +6h for Generalist build) ===
**Build the Red Team test harness FIRST** (`tests/red_team/bad_cases/` = 5 known-bad, `benign_cases/` = 10 benign, `scoreboard.py` prints pass/fail). Only then iterate the prompt.
Red Team ship criteria: **5/5 veto on bad cases, ≤1/10 false positive on benign.** If not hit after 8h of prompt iteration, stop and escalate per MVP_PLAN §11 kill criteria.
Then: `agents/blast_radius/main.py`, HCL parser, Blast Radius prompt, `agents/red_team/main.py`, verdict parser.
**Then build Generalist**: wire real data into the four M1 tool stubs (`cost_estimate`, `policy_check`, `historian_lookup`, `slo_impact`) — a deterministic-fixture pricing table, a minimal OPA ruleset (~5 rules), a Neo4j label `:PriorDeliberation` with seed data, a YAML SLO registry. Then `agents/generalist/main.py`, `citation_parser.py` (enforces tool-citation rule from §4), prompt, `tests/generalist/scoreboard.py` (5 concern + 10 benign fixtures).
Generalist ship criteria: **5/5 concern-raised on concern cases, ≤2/10 false-concern on benign** (looser than Red Team because soft-concern cannot block). Each concern must parse cleanly via `citation_parser.py`.
Integration tests: all three voters respond to the same sample proposal with signed, verifiable opinions carrying the correct `verdict_class`.
Observability: all three voters emit §8 logs.
**Acceptance report**: Red Team scoreboard output, Generalist scoreboard output, signed opinion samples from all three voters.
**Decisions to resolve**: D3 (Red Team model — Opus 4.6 default), D4 (minimum accuracy bar), D5 (per-deliberation cost cap), D9 (quorum rule — already pinned §7, confirm), D12 (per-analyst timeout — already pinned §7, confirm), **D13 (Generalist model — Sonnet 4.6 default; rationale: broad-tool synthesis benefits less from Opus than adversarial reasoning does, and Generalist tokens will dominate the loop).**

### === M5 — Speaker + Digital Twin (17h, +1h for 3-voter tally + protocol invariants) ===
Produce: LangGraph workflow in `control_plane/consilium/speaker.py` dispatching to all three voters in parallel, `quorum.py` implementing §7 table including the two invariants (veto-class enforcement, uncited-concern rewrite), `audit.py` writing to Vault audit device, `nomad/twin.nomad.hcl`, Speaker enforces §8 cost cap before dispatching apply, `cli/consilium/submit.py`.
**Acceptance report**: end-to-end happy-path trace (all three voters approve), end-to-end veto-path trace (Red Team veto), end-to-end soft-concern trace (Generalist concern; apply still fires), tampered-opinion-rejection test result, protocol-violation test result (Generalist returning a `veto` must produce `error`, not `reject`).
**Decisions to resolve**: D6 (terraform apply path — MCP or shell-out; shell-out if MCP blocks), D10 (demo target infra — LocalStack default).

### === M6 — Polish + demo (18h, +2h for extra demo scene + recording takes) ===
Produce: happy-path, veto-bait, and cost-bait Terraform target projects (one per demo scene), `cli/consilium/audit_verify.py`, CLI output polish (including `concern` rendering distinct from `veto`), demo video covering all four scenes, blog post, release notes, `v0.1.0-mvp` tag.
**Pre-record gate**: run the MVP_PLAN §13 pre-demo runbook. **If any check fails, do not record. Fix first.**
**Acceptance report**: video URL, audit-verify output on a real vetoed deliberation, audit-verify output on a real apply-with-concern deliberation, cold-install timing from a fresh VM.
**Decisions to resolve**: D7 (demo hosting), D8 (licence — MPL 2.0 default).

---

## 10. Quality gates (cross-milestone)

At every milestone boundary, all must be true:
- Unit tests pass (`pytest tests/unit`) and Go provider tests pass (`go test ./provider/...`).
- Integration tests for that milestone pass.
- TODO.md boxes for that milestone's tasks are checked.
- MVP_PLAN.md decision log is updated for any D-items that were resolved.
- No uncommitted secrets, credentials, or `.env` files in the staging area.

Before M6.4 (recording): the MVP_PLAN §13 runbook passes end-to-end.

---

## 11. Model selection

- **Sonnet 4.6** — Architect, Blast Radius, Generalist, code scaffolding, and all exploratory prompt iteration.
- **Opus 4.6** — Red Team only (MVP_PLAN D11 default) and Red Team eval runs.
- Never use a model older than the 4.x family for any live agent; use nothing else for eval.

Rationale for Generalist on Sonnet (D13): the Generalist's job is broad-tool synthesis (cost + policy + precedent + SLO) with enforced tool citations. The hard part is the citation discipline, which is a prompt-structure problem, not a reasoning-depth problem — Sonnet is sufficient. Generalist tokens will dominate the loop because it makes four tool calls per deliberation; spending Opus on every invocation would push per-deliberation cost above the D5 cap.

---

## 12. When blocked

If you hit a genuine blocker (contract ambiguity, missing pre-flight item, external service down, test set not converging):
1. Stop. Do not invent around the problem.
2. State the blocker in one sentence.
3. State your recommended default resolution.
4. List what a reasonable alternative would look like.
5. Wait.

Do not silently degrade — do not swap a real signer for a stub, do not swap a real Vault for a file. If the path forward requires scope narrowing, get explicit approval.

---

## 13. Your first action

Read `TODO.md`. Confirm plan-enhancement items are checked and all M0 items are unchecked. Then report:
1. The next three tasks you plan to execute (should be M0.2 → M0.4).
2. Any MVP_PLAN §3 pre-flight items that are unresolved and would block M0.
3. Any contract ambiguity in sections 4–8 above that you want clarified before scaffolding.
4. Confirmation of model selection for this session.

Then wait for "proceed."

---

*This prompt is the standing brief. It changes only by edit with reason logged in MVP_PLAN.md §6. Every session starts by re-reading it.*
