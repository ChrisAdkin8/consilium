"""
Consilium KB MCP server.

Exposes seven tools to Consilium agents:

Analyst tools (Architect, Blast Radius, Red Team):
  semantic_search  — keyword-ranked search over a local HashiCorp doc corpus
  blast_radius     — Neo4j DEPENDS_ON traversal to find impacted resources
  security_posture — Neo4j IAM + property analysis for a resource

Generalist tools (Generalist voter only; every concern the Generalist raises
must cite an output_id from one of these):
  cost_estimate    — monthly-cost delta for a proposed HCL change
  policy_check     — OPA-style rule evaluation (stub rule set in M1)
  historian_lookup — structural-similarity search over :PriorDeliberation nodes
  slo_impact       — change-freeze / SLO-at-risk lookup over slo_registry.yaml

Transport: streamable-http (default port 8000).
On startup the server registers itself in Consul as 'consilium-kb-mcp'.

Environment variables:
  NEO4J_URI          bolt://127.0.0.1:7687
  NEO4J_USER         neo4j
  NEO4J_PASS         consilium-dev
  CONSUL_HTTP_ADDR   http://127.0.0.1:8500
  KB_MCP_PORT        8000
  KB_MCP_HOST        0.0.0.0
"""

from __future__ import annotations

import hashlib
import json
import logging
import math
import os
import re
from pathlib import Path
from typing import Any

import httpx
from mcp.server.fastmcp import FastMCP
from neo4j import GraphDatabase
from neo4j import exceptions as neo4j_exc

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
NEO4J_URI = os.environ.get("NEO4J_URI", "bolt://127.0.0.1:7687")
NEO4J_USER = os.environ.get("NEO4J_USER", "neo4j")
NEO4J_PASS = os.environ.get("NEO4J_PASS", "consilium-dev")
CONSUL_ADDR = os.environ.get("CONSUL_HTTP_ADDR", "http://127.0.0.1:8500")
KB_MCP_PORT = int(os.environ.get("KB_MCP_PORT", "8000"))
KB_MCP_HOST = os.environ.get("KB_MCP_HOST", "0.0.0.0")

CORPUS_PATH = Path(__file__).parent / "seed" / "corpus" / "hashicorp_snippets.json"

logging.basicConfig(level=logging.INFO, format="%(levelname)s [kb-mcp] %(message)s")
log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# MCP server instance
# ---------------------------------------------------------------------------
mcp = FastMCP("consilium-kb-mcp")

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
_corpus_cache: list[dict] | None = None


def _corpus() -> list[dict]:
    global _corpus_cache
    if _corpus_cache is None:
        if CORPUS_PATH.exists():
            _corpus_cache = json.loads(CORPUS_PATH.read_text())
        else:
            log.warning("corpus not found at %s — semantic_search will return empty results", CORPUS_PATH)
            _corpus_cache = []
    return _corpus_cache


def _tfidf_score(query: str, text: str) -> float:
    """Bag-of-words overlap score; no ML dependencies."""
    q_tokens = set(re.findall(r"\w+", query.lower()))
    t_tokens = re.findall(r"\w+", text.lower())
    if not q_tokens or not t_tokens:
        return 0.0
    t_freq: dict[str, int] = {}
    for tok in t_tokens:
        t_freq[tok] = t_freq.get(tok, 0) + 1
    score = sum(math.log(1 + t_freq.get(q, 0)) for q in q_tokens)
    return round(score / math.sqrt(len(q_tokens)), 4)


def _neo4j():
    return GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASS))


# ---------------------------------------------------------------------------
# Tool: semantic_search
# ---------------------------------------------------------------------------
@mcp.tool()
def semantic_search(
    query: str,
    k: int = 5,
    filters: dict[str, str] | None = None,
) -> dict[str, Any]:
    """
    Search the HashiCorp knowledge base for relevant documentation snippets.

    Args:
        query:   Natural-language query (e.g. 'how to encrypt an S3 bucket').
        k:       Maximum number of results to return (default 5).
        filters: Optional dict with keys 'resource_type' and/or 'provider' to
                 narrow the search (e.g. {"provider": "aws"}).

    Returns:
        {
          "results": [{"id", "snippet", "source_uri", "score"}, ...],
          "query_embedding_id": null
        }

    Errors: embedding_backend_unavailable, invalid_filter
    """
    if not isinstance(query, str) or not query.strip():
        return {"results": [], "query_embedding_id": None, "error": "invalid_filter"}

    corpus = _corpus()
    scored: list[tuple[float, dict]] = []
    for doc in corpus:
        if filters:
            if "resource_type" in filters and doc.get("resource_type") != filters["resource_type"]:
                continue
            if "provider" in filters and doc.get("provider") != filters["provider"]:
                continue
        score = _tfidf_score(query, doc.get("text", ""))
        if score > 0:
            scored.append((score, doc))

    scored.sort(key=lambda x: x[0], reverse=True)
    results = [
        {
            "id": doc["id"],
            "snippet": doc.get("text", "")[:500],
            "source_uri": doc.get("source_uri", ""),
            "score": score,
        }
        for score, doc in scored[:k]
    ]
    return {"results": results, "query_embedding_id": None}


# ---------------------------------------------------------------------------
# Tool: blast_radius
# ---------------------------------------------------------------------------
@mcp.tool()
def blast_radius(
    resource_ids: list[str],
    depth: int = 2,
) -> dict[str, Any]:
    """
    Return all resources affected if the given resource IDs are changed or destroyed.

    Traverses DEPENDS_ON edges in Neo4j from each root resource up to `depth` hops.

    Args:
        resource_ids: One or more Terraform resource IDs (e.g. ["aws_vpc.main"]).
        depth:        Maximum traversal depth (default 2, max 5).

    Returns:
        {
          "impacted": [{"id", "type", "relation", "distance"}, ...],
          "edges_traversed": int,
          "truncated": bool
        }

    Errors: unknown_resource, graph_timeout
    """
    if not resource_ids:
        return {"impacted": [], "edges_traversed": 0, "truncated": False}

    depth = max(1, min(depth, 5))
    MAX_RESULTS = 100
    impacted: list[dict] = []
    edges_traversed = 0
    seen: set[str] = set()

    try:
        driver = _neo4j()
        try:
            with driver.session() as session:
                for rid in resource_ids:
                    result = session.run(
                        """
                        MATCH path = (r:Resource {id: $id})-[:DEPENDS_ON*1..$depth]->(dep:Resource)
                        RETURN dep.id   AS id,
                               dep.type AS type,
                               length(path) AS distance
                        ORDER BY distance
                        """,
                        id=rid,
                        depth=depth,
                    )
                    for rec in result:
                        edges_traversed += 1
                        if rec["id"] not in seen:
                            seen.add(rec["id"])
                            impacted.append(
                                {
                                    "id": rec["id"],
                                    "type": rec["type"],
                                    "relation": "DEPENDS_ON",
                                    "distance": rec["distance"],
                                }
                            )
        finally:
            driver.close()
    except neo4j_exc.ServiceUnavailable:
        log.error("Neo4j unavailable at %s", NEO4J_URI)
        return {"impacted": [], "edges_traversed": 0, "truncated": False, "error": "graph_timeout"}
    except neo4j_exc.ClientError as exc:
        log.error("Neo4j client error: %s", exc)
        return {"impacted": [], "edges_traversed": 0, "truncated": False, "error": "unknown_resource"}

    truncated = len(impacted) > MAX_RESULTS
    return {
        "impacted": impacted[:MAX_RESULTS],
        "edges_traversed": edges_traversed,
        "truncated": truncated,
    }


# ---------------------------------------------------------------------------
# Tool: security_posture
# ---------------------------------------------------------------------------
@mcp.tool()
def security_posture(
    resource_id: str | None = None,
    hcl_fragment: str | None = None,
) -> dict[str, Any]:
    """
    Return IAM findings and security posture for a Terraform resource.

    Provide either a resource_id (e.g. "aws_s3_bucket.assets") or an
    hcl_fragment containing one or more resource blocks to extract the ID from.

    Args:
        resource_id:  Terraform resource ID to inspect (preferred).
        hcl_fragment: Raw HCL containing resource blocks; first matched ID is used.

    Returns:
        {
          "findings": [{"severity", "code", "summary", "cited_policies"}, ...],
          "iam_principals_affected": [str, ...]
        }

    Errors: unsupported_resource, no_policy_context
    """
    # Resolve resource_id from hcl_fragment if needed
    if not resource_id and hcl_fragment:
        match = re.search(r'resource\s+"([^"]+)"\s+"([^"]+)"', hcl_fragment)
        if match:
            resource_id = f"{match.group(1)}.{match.group(2)}"

    if not resource_id:
        return {
            "findings": [],
            "iam_principals_affected": [],
            "error": "unsupported_resource",
        }

    findings: list[dict] = []
    iam_principals: list[str] = []

    try:
        driver = _neo4j()
        try:
            with driver.session() as session:
                # IAM principals that GRANT access to this resource
                result = session.run(
                    """
                    MATCH (p:IamPrincipal)-[:GRANTS]->(r:Resource {id: $id})
                    RETURN p.arn AS arn
                    """,
                    id=resource_id,
                )
                iam_principals = [rec["arn"] for rec in result]

                # Resource security properties
                result2 = session.run(
                    """
                    MATCH (r:Resource {id: $id})
                    RETURN r.public_access AS public_access,
                           r.encrypted    AS encrypted,
                           r.open_ports   AS open_ports,
                           r.type         AS type
                    """,
                    id=resource_id,
                )
                rows = list(result2)
                if not rows:
                    return {
                        "findings": [],
                        "iam_principals_affected": iam_principals,
                        "error": "no_policy_context",
                    }

                rec = rows[0]
                if rec["public_access"]:
                    findings.append(
                        {
                            "severity": "HIGH",
                            "code": "PUBLIC_ACCESS_ENABLED",
                            "summary": f"{resource_id} has public access enabled",
                            "cited_policies": ["CIS-AWS-1.4", "NIST-AC-3"],
                        }
                    )
                if rec["encrypted"] is False:
                    findings.append(
                        {
                            "severity": "MEDIUM",
                            "code": "ENCRYPTION_DISABLED",
                            "summary": f"{resource_id} is not encrypted at rest",
                            "cited_policies": ["CIS-AWS-2.1", "NIST-SC-28"],
                        }
                    )
                ports = rec["open_ports"] or []
                if 22 in ports:
                    findings.append(
                        {
                            "severity": "HIGH",
                            "code": "SSH_PORT_OPEN",
                            "summary": f"{resource_id} exposes port 22",
                            "cited_policies": ["CIS-AWS-4.1"],
                        }
                    )
        finally:
            driver.close()
    except neo4j_exc.ServiceUnavailable:
        log.error("Neo4j unavailable at %s", NEO4J_URI)
        return {"findings": [], "iam_principals_affected": [], "error": "graph_timeout"}

    return {"findings": findings, "iam_principals_affected": iam_principals}


# ---------------------------------------------------------------------------
# Generalist tool stubs (M1 — deterministic fixtures; M4 promotes to real data)
#
# Every output is keyed off a hash of the input so callers get identical
# results for identical inputs. This matters because the Generalist's signed
# opinion cites `output_id`, and a replay of the same deliberation must be
# able to re-derive the same citation.
# ---------------------------------------------------------------------------

# Cost table — per-resource-type monthly USD (stub). Missing types → 0.
_STUB_PRICING_USD_MONTH: dict[str, float] = {
    "aws_instance.t3.small":      15.18,
    "aws_instance.t3.medium":     30.37,
    "aws_instance.m5.large":      70.08,
    "aws_instance.m5.xlarge":    140.16,
    "aws_instance.m5.24xlarge": 3473.60,
    "aws_nat_gateway":            32.85,
    "aws_db_instance.db.t3.medium": 50.37,
}

_STUB_POLICY_RULES: list[dict[str, Any]] = [
    {
        "rule_id": "iam-no-wildcard",
        "severity": "HIGH",
        "message": 'IAM policy grants * on *',
        "trigger": r'"Action"\s*[:=]\s*["\[]\s*"?\*',
    },
    {
        "rule_id": "s3-no-public-read",
        "severity": "HIGH",
        "message": "S3 bucket grants public read",
        "trigger": r'acl\s*=\s*"public-read"',
    },
    {
        "rule_id": "require-owner",
        "severity": "MEDIUM",
        "message": "Resource is missing the required `owner` tag",
        "trigger": None,  # handled in code
    },
    {
        "rule_id": "sg-no-unrestricted-ingress",
        "severity": "HIGH",
        "message": "Security group allows 0.0.0.0/0 ingress",
        "trigger": r'cidr_blocks\s*=\s*\[\s*"0\.0\.0\.0/0"',
    },
    {
        "rule_id": "rds-encryption-at-rest",
        "severity": "MEDIUM",
        "message": "RDS instance does not set storage_encrypted = true",
        "trigger": None,  # handled in code
    },
]

_STUB_PRIOR_DELIBERATIONS: list[dict[str, Any]] = [
    {
        "deliberation_id": "del_2025Q4_001",
        "incident_id": "INC-482",
        "outcome": "incident",
        "fingerprint": {"iam_role": True, "wildcard_trust": True},
        "summary": "Wildcard sts:AssumeRole trust caused cross-service escalation (2025-12-04)",
    },
    {
        "deliberation_id": "del_2026Q1_017",
        "incident_id": None,
        "outcome": "vetoed",
        "fingerprint": {"s3_bucket": True, "public_access": True},
        "summary": "Public S3 bucket proposal vetoed by Red Team (2026-02-11)",
    },
]

_STUB_SLO_REGISTRY: dict[str, dict[str, Any]] = {
    "aws_db_instance.payments": {
        "service": "payments-api",
        "slo": "p99_latency_ms < 250",
        "error_budget_remaining": 0.12,
        "change_freeze": {
            "active": True,
            "reason": "Holiday peak freeze (2026-11-20 → 2026-12-28)",
        },
    },
    "aws_rds_cluster.payments_cluster": {
        "service": "payments-api",
        "slo": "p99_latency_ms < 250",
        "error_budget_remaining": 0.12,
        "change_freeze": {
            "active": True,
            "reason": "Holiday peak freeze (2026-11-20 → 2026-12-28)",
        },
    },
}


def _citation_id(prefix: str, *parts: str) -> str:
    """Deterministic citation ID derived from the tool inputs."""
    h = hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()[:12].upper()
    return f"{prefix}_{h}"


# ---------------------------------------------------------------------------
# Tool: cost_estimate
# ---------------------------------------------------------------------------
@mcp.tool()
def cost_estimate(
    hcl_fragment: str,
    region: str = "us-east-1",
) -> dict[str, Any]:
    """
    Estimate the monthly cost delta of a proposed change.

    Args:
        hcl_fragment: HCL for the added / changed resources.
        region:       AWS region for the pricing lookup (default us-east-1).

    Returns:
        {
          "output_id": "cost_est_...",
          "monthly_delta_usd": float,
          "line_items": [...],
          "pricing_source": "stub_table_v1",
          "confidence": "high" | "medium" | "low"
        }

    Errors: unsupported_resource_type, unparseable_hcl
    """
    if not isinstance(hcl_fragment, str) or not hcl_fragment.strip():
        return {"error": "unparseable_hcl", "line_items": [], "monthly_delta_usd": 0.0}

    # Very small HCL probe: (resource_type, name, instance_type?)
    resources = re.findall(
        r'resource\s+"([^"]+)"\s+"([^"]+)"\s*\{([^{}]*)\}',
        hcl_fragment,
        flags=re.DOTALL,
    )
    if not resources:
        return {"error": "unparseable_hcl", "line_items": [], "monthly_delta_usd": 0.0}

    line_items: list[dict[str, Any]] = []
    total = 0.0
    for rtype, rname, body in resources:
        # Prefer `instance_type` / `db_instance_class` / `size` keys if present
        m_inst = re.search(r'instance_type\s*=\s*"([^"]+)"', body)
        m_db   = re.search(r'instance_class\s*=\s*"([^"]+)"', body)
        sku_suffix = m_inst.group(1) if m_inst else (m_db.group(1) if m_db else None)

        sku_key = f"{rtype}.{sku_suffix}" if sku_suffix else rtype
        unit = _STUB_PRICING_USD_MONTH.get(sku_key, 0.0)

        # Deterministic fan-out: if the HCL mentions `count = N` or an AZ list,
        # treat it as quantity; otherwise 1.
        m_count = re.search(r'count\s*=\s*(\d+)', body)
        qty = int(m_count.group(1)) if m_count else 1

        line_items.append({
            "resource": f"{rtype}.{rname}",
            "sku": sku_key,
            "quantity": qty,
            "unit_usd_month": unit,
        })
        total += unit * qty

    has_unknown = any(it["unit_usd_month"] == 0.0 for it in line_items)
    confidence = "high" if not has_unknown else "low"

    return {
        "output_id": _citation_id("cost_est", hcl_fragment, region),
        "monthly_delta_usd": round(total, 2),
        "line_items": line_items,
        "pricing_source": "stub_table_v1",
        "confidence": confidence,
    }


# ---------------------------------------------------------------------------
# Tool: policy_check
# ---------------------------------------------------------------------------
@mcp.tool()
def policy_check(
    hcl_fragment: str,
    policy_set: str = "default",
) -> dict[str, Any]:
    """
    Evaluate an HCL fragment against a policy-as-code rule set.

    Args:
        hcl_fragment: HCL for the added / changed resources.
        policy_set:   Which rule bundle to evaluate (default 'default').

    Returns:
        {
          "output_id": "policy_chk_...",
          "violations": [{"rule_id","severity","message","location"}, ...],
          "evaluator": "stub_rules_v1",
          "policies_evaluated": int
        }

    Errors: unknown_policy_set, evaluator_unavailable
    """
    if policy_set != "default":
        return {"error": "unknown_policy_set", "violations": [], "policies_evaluated": 0}

    violations: list[dict[str, Any]] = []

    for rule in _STUB_POLICY_RULES:
        if rule["trigger"] and re.search(rule["trigger"], hcl_fragment):
            location_match = re.search(r'resource\s+"([^"]+)"\s+"([^"]+)"', hcl_fragment)
            location = f"{location_match.group(1)}.{location_match.group(2)}" if location_match else "unknown"
            violations.append({
                "rule_id": rule["rule_id"],
                "severity": rule["severity"],
                "message": rule["message"],
                "location": location,
            })

    # require-owner: any resource block without a `tags` section containing `owner`
    for rtype, rname, body in re.findall(
        r'resource\s+"([^"]+)"\s+"([^"]+)"\s*\{([^{}]*(?:\{[^}]*\}[^{}]*)*)\}',
        hcl_fragment,
        flags=re.DOTALL,
    ):
        if "owner" not in body:
            violations.append({
                "rule_id": "require-owner",
                "severity": "MEDIUM",
                "message": "Resource is missing the required `owner` tag",
                "location": f"{rtype}.{rname}",
            })

    # rds-encryption-at-rest: aws_db_instance without storage_encrypted = true
    for rtype, rname, body in re.findall(
        r'resource\s+"(aws_db_instance)"\s+"([^"]+)"\s*\{([^{}]*)\}',
        hcl_fragment,
        flags=re.DOTALL,
    ):
        if not re.search(r'storage_encrypted\s*=\s*true', body):
            violations.append({
                "rule_id": "rds-encryption-at-rest",
                "severity": "MEDIUM",
                "message": "RDS instance does not set storage_encrypted = true",
                "location": f"{rtype}.{rname}",
            })

    return {
        "output_id": _citation_id("policy_chk", hcl_fragment, policy_set),
        "violations": violations,
        "evaluator": "stub_rules_v1",
        "policies_evaluated": len(_STUB_POLICY_RULES),
    }


# ---------------------------------------------------------------------------
# Tool: historian_lookup
# ---------------------------------------------------------------------------
@mcp.tool()
def historian_lookup(
    hcl_fragment: str,
    k: int = 3,
) -> dict[str, Any]:
    """
    Find past deliberations or incidents that are structurally similar to a proposed change.

    Args:
        hcl_fragment: HCL for the added / changed resources.
        k:            Max matches to return (clamped to [1, 10]).

    Returns:
        {
          "output_id": "hist_...",
          "matches": [{"deliberation_id","incident_id","structural_similarity","outcome","summary"}, ...]
        }

    Errors: graph_timeout, no_corpus
    """
    k = max(1, min(int(k), 10))

    # Stub fingerprint over the HCL (what kinds of resources / patterns appear)
    fp = {
        "iam_role":        bool(re.search(r'resource\s+"aws_iam_role"', hcl_fragment)),
        "wildcard_trust":  bool(re.search(r'"Action"\s*[:=]\s*["\[]\s*"?sts:AssumeRole.*\*', hcl_fragment, re.DOTALL)),
        "s3_bucket":       bool(re.search(r'resource\s+"aws_s3_bucket"', hcl_fragment)),
        "public_access":   bool(re.search(r'(public-read|PublicRead|0\.0\.0\.0/0)', hcl_fragment)),
    }

    def _sim(a: dict[str, bool], b: dict[str, bool]) -> float:
        keys = set(a) | set(b)
        if not keys:
            return 0.0
        both_true = sum(1 for k in keys if a.get(k) and b.get(k))
        either    = sum(1 for k in keys if a.get(k) or  b.get(k))
        return round(both_true / either, 2) if either else 0.0

    scored = [
        (_sim(fp, row["fingerprint"]), row)
        for row in _STUB_PRIOR_DELIBERATIONS
    ]
    scored = [(s, r) for s, r in scored if s > 0]
    scored.sort(key=lambda x: x[0], reverse=True)

    matches = [
        {
            "deliberation_id": row["deliberation_id"],
            "incident_id": row["incident_id"],
            "structural_similarity": sim,
            "outcome": row["outcome"],
            "summary": row["summary"],
        }
        for sim, row in scored[:k]
    ]

    return {
        "output_id": _citation_id("hist", hcl_fragment, str(k)),
        "matches": matches,
    }


# ---------------------------------------------------------------------------
# Tool: slo_impact
# ---------------------------------------------------------------------------
@mcp.tool()
def slo_impact(
    resource_ids: list[str],
) -> dict[str, Any]:
    """
    Check whether a change touches any service with an active SLO / change-freeze window.

    Args:
        resource_ids: Terraform resource IDs to look up in slo_registry.yaml.

    Returns:
        {
          "output_id": "slo_...",
          "at_risk_services": [...],
          "inside_change_freeze": bool,
          "change_freeze_reason": str | null
        }

    Errors: registry_not_found
    """
    if not isinstance(resource_ids, list):
        resource_ids = []

    at_risk: list[dict[str, Any]] = []
    inside_freeze = False
    freeze_reason: str | None = None
    seen_services: set[str] = set()

    for rid in resource_ids:
        entry = _STUB_SLO_REGISTRY.get(rid)
        if not entry:
            continue
        if entry["service"] not in seen_services:
            seen_services.add(entry["service"])
            at_risk.append({
                "service": entry["service"],
                "slo": entry["slo"],
                "error_budget_remaining": entry["error_budget_remaining"],
            })
        freeze = entry.get("change_freeze") or {}
        if freeze.get("active"):
            inside_freeze = True
            freeze_reason = freeze.get("reason")

    return {
        "output_id": _citation_id("slo", "|".join(sorted(resource_ids))),
        "at_risk_services": at_risk,
        "inside_change_freeze": inside_freeze,
        "change_freeze_reason": freeze_reason,
    }


# ---------------------------------------------------------------------------
# Health endpoint (for Consul TCP check — port-open is sufficient, but
# an HTTP endpoint is added via the ASGI app after server creation)
# ---------------------------------------------------------------------------
def _register_consul() -> None:
    """Register this service in Consul (synchronous, best-effort)."""
    payload = {
        "Name": "consilium-kb-mcp",
        "ID": "consilium-kb-mcp-1",
        "Port": KB_MCP_PORT,
        "Tags": ["consilium", "mcp", "kb"],
        "Check": {
            "TCP": f"127.0.0.1:{KB_MCP_PORT}",
            "Interval": "10s",
            "Timeout": "3s",
            "DeregisterCriticalServiceAfter": "1m",
        },
    }
    try:
        resp = httpx.put(
            f"{CONSUL_ADDR}/v1/agent/service/register",
            json=payload,
            timeout=5.0,
        )
        resp.raise_for_status()
        log.info("registered in Consul as consilium-kb-mcp on port %d", KB_MCP_PORT)
    except Exception as exc:
        log.warning("Consul registration failed (non-fatal): %s", exc)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    # Wait briefly for the stack to be ready, then register in Consul.
    # The TCP check will start passing once the MCP server binds the port.
    log.info("starting consilium-kb-mcp on %s:%d", KB_MCP_HOST, KB_MCP_PORT)
    _register_consul()
    mcp.run(transport="streamable-http", host=KB_MCP_HOST, port=KB_MCP_PORT)
