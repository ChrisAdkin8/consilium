# Consilium voting architecture

**Status:** pinned for MVP (v0.1.0). Changes require a decision-log entry in [MVP_PLAN.md §6](../MVP_PLAN.md).

This document explains *who votes*, *how votes are weighted*, *how the Speaker tallies them*, and — most importantly — *why this voter set looks the way it does*.

---

## 1. The voter set

Three voters. Two non-voting roles.

| Role | Class | Veto? | Primary tools | Signs? |
|---|---|---|---|---|
| **Blast Radius** | specialist | hard-veto | `blast_radius`, Neo4j dep graph, twin plan | yes |
| **Red Team** | specialist | hard-veto | `security_posture`, IAM graph, HCL | yes |
| **Generalist** | broad | **soft-concern only** | `cost_estimate`, `policy_check`, `historian_lookup`, `slo_impact`, `semantic_search` | yes |
| Architect | drafter | — | `semantic_search` | signs the proposal, does not vote |
| Speaker | tallier | — | quorum engine | signs the final decision, does not vote |

**Verdict vocabulary:**

```
hard-veto voters:    approve | concern | veto | abstain
soft-concern voters: approve | concern | abstain     # physically cannot return "veto"
```

The Speaker rejects any vote whose verb is not in the voter's allowed vocabulary. This is a correctness property of the quorum engine, not a prompt-level convention.

### Why these three

Each voter is justified against three tests:

- **Orthogonal.** Blast Radius owns dependency/impact. Red Team owns adversarial security. Generalist owns everything else the parliament *should* weigh in on but where a signed domain-specific blocker would do more harm than good (cost, reliability, precedent, policy hits).
- **Consequential.** Each voter's domain can block an otherwise-correct change from shipping. Nothing here is theatre.
- **Evaluable from signals we have.** Each voter has a defined toolset in [docs/mcp-tools.md](./mcp-tools.md). No voter depends on a capability the MVP cannot deliver.

---

## 2. Why three voters, not four

An earlier sketch of this architecture had **four voters**: Blast Radius, Red Team, Compliance, Generalist. Compliance was proposed as a dedicated hard-veto specialist wrapping policy-as-code (OPA / Sentinel).

We rejected the four-voter design. The reasons, in descending weight:

### 2.1 False-veto arithmetic

Each hard-veto voter is an independent Bernoulli trial against the false-veto probability *p_false*. If any one of *N* voters vetoes spuriously, the change is blocked.

```
P(false reject | N hard-veto voters) = 1 − (1 − p_false)^N
```

At a plausible per-voter precision of 95% (*p_false = 0.05*):

| Hard-veto voters | False-veto rate |
|---|---|
| 1 | 5.0% |
| 2 | 9.75% |
| 3 | 14.26% |
| **4** | **18.55%** |

Two hard-veto voters is the inflection point where aggregate false-vetoes are still well below the noise floor of "a human got paged." Three or four starts producing false blocks an order of magnitude more often than real ones, which erodes operator trust — the exact thing this project is trying to build.

### 2.2 Compliance is deterministic; signed LLM opinions don't add value there

Policy-as-code (OPA, Sentinel, CloudFormation Guard) is **deterministic**. Given HCL `H` and policy set `P`, the evaluator always returns the same result. A cryptographic signature on an LLM's paraphrase of that result adds *no* non-repudiation value beyond the policy evaluator's own deterministic output — you can re-run the evaluator at audit time and check.

Signed opinions are load-bearing when the underlying reasoning is **non-deterministic and non-replayable** (an LLM's judgement at 12:34:56 UTC against a prompt version at that moment). That describes Red Team and Blast Radius. It does *not* describe "did this HCL violate OPA rule X."

The right home for policy-as-code is therefore a **deterministic tool** (`policy_check` in [docs/mcp-tools.md](./mcp-tools.md)) that the Generalist queries and cites. The Generalist's signed opinion captures "I consulted the policy evaluator at time T and it returned the following violations." The evaluator's raw output is captured in the twin's artefact. Both are verifiable.

### 2.3 MVP scope honesty

A Compliance voter requires:

- OPA or Sentinel runner deployed and versioned
- A policy corpus that matches the target cloud (AWS for the MVP)
- A per-org policy-set-selection mechanism
- A test harness like `tests/red_team/` but for compliance cases

The rough estimate is 20+ hours of additional work. The MVP's total budget is 102 hours, and every post-M4 hour is timeline-critical. A Compliance voter in the MVP means either pushing the demo by a weekend or shipping the voter with a thin policy corpus — neither is good.

Deferring Compliance-as-voter while shipping `policy_check` as a tool in M1 means the capability is present (the Generalist can cite it) and the voter elevation remains a clean post-MVP step once we have real policy-corpus buy-in.

### 2.4 Signed-provenance story is clearer with fewer voters

A viewer of the demo should be able to name all the voters from memory. "Two specialists and a generalist" is a shape that fits in one sentence: *the parliament has one voter for what breaks downstream, one for who gets owned, and one for everything else.* Four voters requires explaining why Compliance is distinct from Red Team, why it has a veto, and why the Generalist doesn't. That's a lot of words to spend on structure rather than substance.

### 2.5 The "fewer voters with richer tools" thesis

The deeper architectural claim: **LLM attention is wider than ensemble breadth**. A single Generalist with access to `cost_estimate`, `policy_check`, `historian_lookup`, and `slo_impact` can synthesise *across* those domains — noticing, for example, that a cost concern and an SLO concern stem from the same design choice. Four narrow voters miss that synthesis because each only sees its own slice.

This is the same reason we don't split Red Team into "IAM Red Team" + "Network Red Team" + "Data Red Team." We don't trust the ensemble to stitch the cross-domain attack chain back together.

---

## 3. Quorum table

`control_plane/consilium/quorum.py` implements this exactly. `abstain` is always explicit (timeout or signature-verification failure) — never silent.

| Blast Radius | Red Team | Generalist | Speaker action |
|---|---|---|---|
| approve | approve | approve | **apply** |
| approve | approve | concern | **apply**; log Generalist concern |
| approve | concern | approve | **apply**; log Red Team concern |
| approve | concern | concern | **apply**; log both concerns |
| concern | approve | approve | **apply**; log Blast Radius concern |
| concern | approve | concern | **apply**; log both concerns |
| concern | concern | approve | **apply**; log both analyst concerns |
| concern | concern | concern | **apply**; log all three concerns |
| veto | * | * | **reject** |
| * | veto | * | **reject** |
| abstain | * | * | **reject** (no quorum) |
| * | abstain | * | **reject** (no quorum) |
| * | * | abstain | **reject** (no quorum) — Generalist abstain is *also* a reject |

**Why Generalist abstain rejects.** A Generalist timeout or signature failure means we don't have a complete parliament opinion. The Speaker never manufactures a silent approval from a missing voter, even a soft-concern one. The "no quorum" rule applies to all three voters symmetrically — the distinction between hard-veto and soft-concern voters is only about the *veto* verb, not about whether their opinion is required.

**Why Generalist cannot veto.** A soft-concern voter that raised a `veto` would be treated by the quorum engine as protocol-violating and the deliberation would be marked `error` (not `reject`) with a cross-agent-confusion signal. This is enforced by the quorum engine, not the prompt, so a prompt regression cannot silently promote a concern to a veto.

**Per-voter timeout: 30 s. Total deliberation budget: 90 s.** (From [MVP_PLAN D12](../MVP_PLAN.md#6-decision-log).)

---

## 4. What the Generalist sees

Tools available to the Generalist via MCP (contracts in [docs/mcp-tools.md](./mcp-tools.md)):

| Tool | Purpose | Blocking-case example |
|---|---|---|
| `cost_estimate` | Monthly cost delta of the proposed change | "New NAT gateway in every AZ: +$135/mo × 3 AZs" |
| `policy_check` | Policy-as-code evaluator (OPA/Sentinel) | "Violates org tagging policy rule `require-owner`" |
| `historian_lookup` | Past deliberations / incidents matching structural features | "Same module shape caused INC-482 in 2025-Q4" |
| `slo_impact` | Change-window / SLO-at-risk lookup | "Peak-hour DB schema change inside the frozen window" |
| `semantic_search` | Shared with Architect; HashiCorp best-practice corpus | "This pattern is flagged in the AWS well-architected docs" |

The Generalist's prompt tells it to **cite a specific tool output** for every concern it raises. If it raises a cost concern it must quote the `cost_estimate` tool's output; if it raises a precedent concern it must reference the `historian_lookup` record ID. Uncited concerns are rejected by the verdict parser.

This is the mechanism that keeps the Generalist honest. A signed opinion that says "cost seems high" without a tool citation is not treated as a valid concern — it's treated as an `abstain` with `reason: unsupported_claim`, which (per §3) rejects the deliberation. The voter cannot manufacture vague worries.

---

## 5. When would we elevate a Generalist concern to a veto?

The `consilium_quorum_policy` Terraform resource supports per-tool escalation rules. Example:

```hcl
resource "consilium_quorum_policy" "prod" {
  hard_veto_voters    = ["blast_radius", "red_team"]
  soft_concern_voters = ["generalist"]

  escalate_concern_to_veto {
    voter       = "generalist"
    tool        = "cost_estimate"
    when        = "monthly_delta_usd > 5000"
  }
  escalate_concern_to_veto {
    voter       = "generalist"
    tool        = "slo_impact"
    when        = "change_window == 'frozen'"
  }
  escalate_concern_to_veto {
    voter       = "generalist"
    tool        = "policy_check"
    when        = "severity == 'HIGH'"
  }
}
```

This keeps the M5 quorum engine thin — it's a table of (voter, verdict, policy clause) — while letting each environment tune strictness without code changes. It also preserves the property that **escalation is deterministic**: the escalation rule fires on a tool output, not on LLM judgement, so two deliberations with the same tool output always produce the same final verdict.

**Escalation is post-MVP.** For v0.1.0, the Generalist is pure soft-concern across all rules. The escalation plumbing is the first thing to add in v0.2.0.

---

## 6. Post-MVP: when would we split the Generalist?

Any of these conditions would justify extracting a specialist voter from the Generalist's toolset:

| Condition | New specialist | Class |
|---|---|---|
| A meaningful fraction of changes now touch data-classification boundaries and `policy_check` is too coarse | **Compliance** | hard-veto |
| The `historian_lookup` corpus has grown to the point where reasoning over it is a job in itself | **Historian** | soft-concern |
| Cost signals are a recurring cause of accepted-but-regretted changes | **Cost** | soft-concern, escalating |

Each extraction requires its own test harness (5 must-block + 10 benign, mirroring `tests/red_team/`). No voter ships without its scoreboard, same rule as Red Team.

---

## 7. Decision log entry

This architecture was adopted on 2026-04-17, superseding the original 2-voter MVP design from the v0.1 MVP plan.

- **Decision.** Adopt the 3-voter structure (Blast Radius, Red Team, Generalist) for MVP v0.1.0.
- **Rejected alternative.** 4-voter design with a dedicated Compliance hard-veto voter.
- **Primary rationale.** Compliance is deterministic → belongs in a tool, not a voter; false-veto arithmetic penalises additional hard-veto voters; Generalist with rich tool access captures cost/reliability/historian without per-domain voter fragmentation.
- **Cost of the decision.** None — capability is preserved (all concerns can still block via escalation rules); only the signed-opinion fragmentation changes.
- **Review trigger.** If post-MVP deliberation volume shows the Generalist is systematically under-escalating in any one domain, split that domain into its own voter.
