# Consilium MCP Tool Contracts

This document is the source of truth for the **seven** MCP tools exposed by `kb_extensions/mcp_server.py`:

- **Analyst tools** (consumed by Architect / Blast Radius / Red Team): `semantic_search`, `blast_radius`, `security_posture`. Real backends from M1.
- **Generalist tools** (consumed exclusively by the Generalist voter): `cost_estimate`, `policy_check`, `historian_lookup`, `slo_impact`. Deterministic-fixture stubs in M1; promoted to real-ish backends in M4 (see [MVP_PLAN.md §4](../MVP_PLAN.md#milestone-4--blast-radius--red-team--generalist)).

Every Generalist concern must cite at least one tool output from this list. The citation parser (see [voting-architecture.md §4](./voting-architecture.md#4-what-the-generalist-sees)) rejects uncited concerns at opinion-ingest time.

**Do not change schemas without updating this file and bumping `docs/mcp-tools.md` in the PR description.**

---

## Server

| Property | Value |
|---|---|
| Name | `consilium-kb-mcp` |
| Transport | `streamable-http` |
| Default port | `8000` |
| Consul service | `consilium-kb-mcp` |
| Health check | TCP port 8000 |
| MCP endpoint | `http://<host>:8000/mcp` |

**Environment variables**

| Variable | Default | Purpose |
|---|---|---|
| `NEO4J_URI` | `bolt://127.0.0.1:7687` | Neo4j Bolt endpoint |
| `NEO4J_USER` | `neo4j` | Neo4j username |
| `NEO4J_PASS` | `consilium-dev` | Neo4j password |
| `CONSUL_HTTP_ADDR` | `http://127.0.0.1:8500` | Consul agent address |
| `KB_MCP_PORT` | `8000` | Bind port |
| `KB_MCP_HOST` | `0.0.0.0` | Bind host |

---

## Tool: `semantic_search`

Search the HashiCorp knowledge base for relevant documentation.

**Backend (local dev):** keyword TF-IDF over `kb_extensions/seed/corpus/hashicorp_snippets.json`.  
**Backend (production):** Amazon Kendra — see `kb_extensions/base/server.py`.

### Input

```json
{
  "query":   "<string>",
  "k":       5,
  "filters": {
    "resource_type": "<optional string, e.g. aws_s3_bucket>",
    "provider":      "<optional string: aws | vault | consul | nomad | terraform>"
  }
}
```

| Field | Type | Required | Default | Notes |
|---|---|---|---|---|
| `query` | string | yes | — | Natural-language question |
| `k` | int | no | 5 | Max results to return |
| `filters` | object | no | null | Both keys optional |

### Output

```json
{
  "results": [
    {
      "id":         "<corpus doc id>",
      "snippet":    "<first 500 chars of document text>",
      "source_uri": "<URL or path>",
      "score":      0.0
    }
  ],
  "query_embedding_id": null
}
```

### Error codes

| Code | Meaning |
|---|---|
| `embedding_backend_unavailable` | Corpus not found or embedding service down |
| `invalid_filter` | Unknown filter key or empty query |

---

## Tool: `blast_radius`

Traverse the Terraform resource dependency graph to find all resources affected
by a change to the given root resources.

**Graph:** Neo4j, nodes `Resource`, edges `DEPENDS_ON` (directional: `A -[:DEPENDS_ON]-> B` means A depends on B).  
**Query:** Starts at each `resource_id`, traverses `DEPENDS_ON` edges up to `depth` hops.

### Input

```json
{
  "resource_ids": ["aws_vpc.main", "aws_s3_bucket.assets"],
  "depth": 2
}
```

| Field | Type | Required | Default | Notes |
|---|---|---|---|---|
| `resource_ids` | string[] | yes | — | One or more Terraform IDs |
| `depth` | int | no | 2 | Traversal depth; clamped to [1, 5] |

### Output

```json
{
  "impacted": [
    {
      "id":       "aws_subnet.public_a",
      "type":     "aws_subnet",
      "relation": "DEPENDS_ON",
      "distance": 1
    }
  ],
  "edges_traversed": 4,
  "truncated": false
}
```

`truncated: true` when more than 100 impacted resources exist (hard cap).

### Error codes

| Code | Meaning |
|---|---|
| `unknown_resource` | None of the given resource IDs exist in the graph |
| `graph_timeout` | Neo4j not reachable or query timed out |

### Seed graph topology

```
aws_vpc.main
├── aws_subnet.public_a
│   └── aws_lb.web_alb
├── aws_subnet.private_a
│   ├── aws_instance.web_1 ── aws_iam_instance_profile.web_profile ── aws_iam_role.web_role
│   └── aws_instance.web_2 ── aws_iam_instance_profile.web_profile
└── aws_security_group.web
    ├── aws_lb.web_alb
    ├── aws_instance.web_1
    └── aws_instance.web_2

aws_s3_bucket.assets  (standalone — no DEPENDS_ON edges)
```

---

## Tool: `security_posture`

Return IAM principals with access to a resource and any security findings
(public access, encryption gaps, open sensitive ports).

### Input

Provide **one** of:

```json
{ "resource_id": "aws_s3_bucket.assets" }
```

or

```json
{ "hcl_fragment": "resource \"aws_s3_bucket\" \"assets\" { bucket = \"demo\" }" }
```

If `hcl_fragment` is provided, the first `resource "<type>" "<name>"` match is used as the ID.

| Field | Type | Required | Notes |
|---|---|---|---|
| `resource_id` | string | conditional | Preferred; direct Neo4j lookup |
| `hcl_fragment` | string | conditional | Regex-extracted ID |

### Output

```json
{
  "findings": [
    {
      "severity":       "HIGH",
      "code":           "PUBLIC_ACCESS_ENABLED",
      "summary":        "aws_s3_bucket.assets has public access enabled",
      "cited_policies": ["CIS-AWS-1.4", "NIST-AC-3"]
    }
  ],
  "iam_principals_affected": [
    "arn:aws:iam::123456789012:role/web-role",
    "arn:aws:iam::123456789012:user/admin"
  ]
}
```

**Severity levels:** `HIGH` | `MEDIUM` | `LOW` | `INFO`

**Finding codes:**

| Code | Severity | Trigger |
|---|---|---|
| `PUBLIC_ACCESS_ENABLED` | HIGH | `Resource.public_access = true` |
| `ENCRYPTION_DISABLED` | MEDIUM | `Resource.encrypted = false` |
| `SSH_PORT_OPEN` | HIGH | port 22 in `Resource.open_ports` |

### Error codes

| Code | Meaning |
|---|---|
| `unsupported_resource` | No `resource_id` and no parseable `hcl_fragment` |
| `no_policy_context` | Resource not found in Neo4j |
| `graph_timeout` | Neo4j not reachable |

---

## Generalist tools

The four tools below are consumed by the Generalist voter. Every concern the Generalist raises must cite an output ID from at least one of these tools; the `citation_parser.py` enforces this at opinion-ingest time.

**Implementation status:**

| Tool | M1 | M4 |
|---|---|---|
| `cost_estimate` | deterministic fixture keyed off HCL resource types | small hard-coded AWS pricing table |
| `policy_check` | deterministic fixture of ~3 rule violations | ~5 OPA-style rules evaluated by a local engine |
| `historian_lookup` | Cypher similarity over ~10 seeded `:PriorDeliberation` nodes | same, with a broader seed corpus |
| `slo_impact` | flat `slo_registry.yaml` read | same registry wired to a change-freeze calendar |

Schemas are final in M1 — the M4 promotion changes backends only, not I/O shapes.

---

## Tool: `cost_estimate`

Estimate the monthly cost delta of a proposed change.

### Input

```json
{
  "hcl_fragment": "resource \"aws_instance\" \"batch\" { instance_type = \"m5.24xlarge\" }",
  "region": "us-east-1"
}
```

| Field | Type | Required | Default | Notes |
|---|---|---|---|---|
| `hcl_fragment` | string | yes | — | HCL for the added/changed resources |
| `region` | string | no | `us-east-1` | AWS region for pricing lookup |

### Output

```json
{
  "output_id": "cost_est_01HXYZ",
  "monthly_delta_usd": 10420.80,
  "line_items": [
    { "resource": "aws_instance.batch", "sku": "m5.24xlarge", "quantity": 3, "unit_usd_month": 3473.6 }
  ],
  "pricing_source": "stub_table_v1",
  "confidence": "high"
}
```

| Field | Type | Notes |
|---|---|---|
| `output_id` | string | Stable citation ID; what the Generalist cites in its concern |
| `monthly_delta_usd` | number | Can be negative for cost-reducing changes |
| `line_items` | array | Per-resource breakdown |
| `pricing_source` | string | `stub_table_v1` in M1, `aws_pricing_api_cache_v1` in M4 |
| `confidence` | enum | `high` | `medium` | `low` |

### Error codes

| Code | Meaning |
|---|---|
| `unsupported_resource_type` | No pricing entry for the resource type |
| `unparseable_hcl` | HCL fragment could not be parsed |

---

## Tool: `policy_check`

Evaluate an HCL fragment against a policy-as-code rule set.

### Input

```json
{
  "hcl_fragment": "resource \"aws_iam_policy\" \"x\" { policy = jsonencode({Statement=[{Action=\"*\"}]}) }",
  "policy_set": "default"
}
```

| Field | Type | Required | Default | Notes |
|---|---|---|---|---|
| `hcl_fragment` | string | yes | — | |
| `policy_set` | string | no | `default` | Which rule bundle to evaluate against |

### Output

```json
{
  "output_id": "policy_chk_01HXYZ",
  "violations": [
    {
      "rule_id": "iam-no-wildcard",
      "severity": "HIGH",
      "message": "IAM policy grants * on *",
      "location": "aws_iam_policy.x"
    }
  ],
  "evaluator": "stub_rules_v1",
  "policies_evaluated": 5
}
```

| Field | Type | Notes |
|---|---|---|
| `output_id` | string | Stable citation ID |
| `violations` | array | Empty if the change passes all rules |
| `evaluator` | string | `stub_rules_v1` in M1, `opa_local_v1` in M4 |
| `policies_evaluated` | int | Count of rules the evaluator ran |

**Severity levels:** `HIGH` | `MEDIUM` | `LOW` | `INFO`.

### Error codes

| Code | Meaning |
|---|---|
| `unknown_policy_set` | `policy_set` does not exist |
| `evaluator_unavailable` | OPA / stub engine not reachable |

---

## Tool: `historian_lookup`

Find past deliberations or incidents that are structurally similar to the current change.

### Input

```json
{
  "hcl_fragment": "resource \"aws_iam_role\" \"batch\" { ... }",
  "k": 3
}
```

| Field | Type | Required | Default | Notes |
|---|---|---|---|---|
| `hcl_fragment` | string | yes | — | |
| `k` | int | no | 3 | Max matches to return; clamped to [1, 10] |

### Output

```json
{
  "output_id": "hist_01HXYZ",
  "matches": [
    {
      "deliberation_id": "del_01HABC",
      "incident_id": "INC-482",
      "structural_similarity": 0.87,
      "outcome": "vetoed",
      "summary": "Near-identical IAM trust policy caused cross-service privilege escalation on 2025-12-04"
    }
  ]
}
```

| Field | Type | Notes |
|---|---|---|
| `output_id` | string | Stable citation ID |
| `matches` | array | Empty if no seeded precedent matches |
| `structural_similarity` | number | 0.0–1.0 |
| `outcome` | enum | `applied` | `vetoed` | `concern_logged` | `incident` |

### Error codes

| Code | Meaning |
|---|---|
| `graph_timeout` | Neo4j not reachable |
| `no_corpus` | `:PriorDeliberation` seed not loaded |

---

## Tool: `slo_impact`

Check whether a change touches a service with an active SLO or sits inside a change-freeze window.

### Input

```json
{
  "resource_ids": ["aws_db_instance.payments", "aws_rds_cluster.payments_cluster"]
}
```

| Field | Type | Required | Notes |
|---|---|---|---|
| `resource_ids` | string[] | yes | Terraform IDs to check against the SLO registry |

### Output

```json
{
  "output_id": "slo_01HXYZ",
  "at_risk_services": [
    {
      "service": "payments-api",
      "slo": "p99_latency_ms < 250",
      "error_budget_remaining": 0.12
    }
  ],
  "inside_change_freeze": true,
  "change_freeze_reason": "Holiday peak freeze (active 2026-11-20 → 2026-12-28)"
}
```

| Field | Type | Notes |
|---|---|---|
| `output_id` | string | Stable citation ID |
| `at_risk_services` | array | Empty if none of the resources map to SLO-tracked services |
| `inside_change_freeze` | bool | Derived from `slo_registry.yaml` |
| `change_freeze_reason` | string\|null | Null when `inside_change_freeze` is false |

### Error codes

| Code | Meaning |
|---|---|
| `registry_not_found` | `slo_registry.yaml` missing |
| `unknown_resource` | None of the resource IDs map to a registry entry (returns empty `at_risk_services` + `inside_change_freeze: false`, not an error — this code is only raised when the registry file itself is malformed) |

---

## Running the server locally

```bash
# 1. Start the stack
docker compose -f dev/docker-compose.yml up -d

# 2. Seed Neo4j (idempotent)
python -m kb_extensions.seed.seed_neo4j

# 3. Start the MCP server
python -m kb_extensions.mcp_server

# 4. Verify Consul registration
curl -s http://localhost:8500/v1/health/service/consilium-kb-mcp?passing | jq .
```

## Running integration tests

```bash
# MCP server must be running (step 3 above)
pytest tests/integration/test_mcp_tools.py -v
```
