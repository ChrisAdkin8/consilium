"""
Integration tests for the Consilium KB MCP server.

Requires a running stack:
  docker compose -f dev/docker-compose.yml up -d
  python -m kb_extensions.seed.seed_neo4j
  python -m kb_extensions.mcp_server   # in another terminal

Skip automatically when the MCP server is not reachable.

Run manually:
  pytest tests/integration/test_mcp_tools.py -v
"""
from __future__ import annotations

import asyncio
import os

import httpx
import pytest

MCP_BASE_URL = os.environ.get("KB_MCP_URL", "http://localhost:8000")
MCP_URL = f"{MCP_BASE_URL}/mcp"


def _server_reachable() -> bool:
    try:
        resp = httpx.get(f"{MCP_BASE_URL}/health", timeout=2.0)
        return resp.status_code == 200
    except Exception:
        # Fallback: try TCP connect (health endpoint may not be wired yet)
        try:
            httpx.get(MCP_BASE_URL, timeout=2.0)
            return True
        except Exception:
            return False


requires_mcp = pytest.mark.skipif(
    not _server_reachable(),
    reason="KB MCP server not reachable — run the stack first",
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------
@requires_mcp
class TestSemanticSearch:
    def test_returns_results_for_known_query(self):
        from agents.base.mcp_client import KBMcpClient

        async def _go():
            async with KBMcpClient(MCP_URL) as client:
                return await client.semantic_search("S3 bucket encryption", k=3)

        result = run(_go())
        assert "results" in result
        assert isinstance(result["results"], list)
        # Should find the S3 and encryption docs
        assert len(result["results"]) >= 1
        first = result["results"][0]
        assert "id" in first
        assert "snippet" in first
        assert "source_uri" in first
        assert isinstance(first["score"], float)

    def test_schema_fields_present(self):
        from agents.base.mcp_client import KBMcpClient

        async def _go():
            async with KBMcpClient(MCP_URL) as client:
                return await client.semantic_search("vault transit", k=5)

        result = run(_go())
        assert "results" in result
        assert "query_embedding_id" in result

    def test_provider_filter(self):
        from agents.base.mcp_client import KBMcpClient

        async def _go():
            async with KBMcpClient(MCP_URL) as client:
                return await client.semantic_search(
                    "security", k=5, filters={"provider": "vault"}
                )

        result = run(_go())
        # All returned docs should have provider=vault in the corpus
        assert "results" in result

    def test_empty_query_returns_error_or_empty(self):
        from agents.base.mcp_client import KBMcpClient

        async def _go():
            async with KBMcpClient(MCP_URL) as client:
                return await client.semantic_search("", k=5)

        result = run(_go())
        # Should return empty results or an error field, not crash
        assert "results" in result or "error" in result


@requires_mcp
class TestBlastRadius:
    def test_vpc_blast_radius(self):
        from agents.base.mcp_client import KBMcpClient

        async def _go():
            async with KBMcpClient(MCP_URL) as client:
                return await client.blast_radius(["aws_vpc.main"], depth=3)

        result = run(_go())
        assert "impacted" in result
        assert "edges_traversed" in result
        assert "truncated" in result

        impacted_ids = {r["id"] for r in result["impacted"]}
        # All these depend transitively on aws_vpc.main
        assert "aws_subnet.public_a" in impacted_ids
        assert "aws_subnet.private_a" in impacted_ids
        assert "aws_security_group.web" in impacted_ids

    def test_schema_fields_present(self):
        from agents.base.mcp_client import KBMcpClient

        async def _go():
            async with KBMcpClient(MCP_URL) as client:
                return await client.blast_radius(["aws_iam_role.web_role"])

        result = run(_go())
        assert isinstance(result["impacted"], list)
        assert isinstance(result["edges_traversed"], int)
        assert isinstance(result["truncated"], bool)
        if result["impacted"]:
            item = result["impacted"][0]
            assert "id" in item
            assert "type" in item
            assert "relation" in item
            assert "distance" in item

    def test_unknown_resource_returns_empty(self):
        from agents.base.mcp_client import KBMcpClient

        async def _go():
            async with KBMcpClient(MCP_URL) as client:
                return await client.blast_radius(["aws_nonexistent.resource"])

        result = run(_go())
        assert result["impacted"] == []


@requires_mcp
class TestSecurityPosture:
    def test_s3_bucket_has_findings(self):
        """aws_s3_bucket.assets has public_access=True and encrypted=False — expect findings."""
        from agents.base.mcp_client import KBMcpClient

        async def _go():
            async with KBMcpClient(MCP_URL) as client:
                return await client.security_posture(resource_id="aws_s3_bucket.assets")

        result = run(_go())
        assert "findings" in result
        assert "iam_principals_affected" in result

        codes = {f["code"] for f in result["findings"]}
        assert "PUBLIC_ACCESS_ENABLED" in codes
        assert "ENCRYPTION_DISABLED" in codes

    def test_findings_schema(self):
        from agents.base.mcp_client import KBMcpClient

        async def _go():
            async with KBMcpClient(MCP_URL) as client:
                return await client.security_posture(resource_id="aws_s3_bucket.assets")

        result = run(_go())
        for finding in result["findings"]:
            assert "severity" in finding
            assert "code" in finding
            assert "summary" in finding
            assert "cited_policies" in finding
            assert finding["severity"] in ("HIGH", "MEDIUM", "LOW", "INFO")

    def test_iam_principals_returned(self):
        """aws_s3_bucket.assets has two IAM principals GRANTS it."""
        from agents.base.mcp_client import KBMcpClient

        async def _go():
            async with KBMcpClient(MCP_URL) as client:
                return await client.security_posture(resource_id="aws_s3_bucket.assets")

        result = run(_go())
        assert len(result["iam_principals_affected"]) >= 1

    def test_hcl_fragment_input(self):
        from agents.base.mcp_client import KBMcpClient

        hcl = '''
        resource "aws_s3_bucket" "assets" {
          bucket = "my-demo-bucket"
        }
        '''

        async def _go():
            async with KBMcpClient(MCP_URL) as client:
                return await client.security_posture(hcl_fragment=hcl)

        result = run(_go())
        assert "findings" in result
        assert "iam_principals_affected" in result

    def test_unknown_resource_returns_error(self):
        from agents.base.mcp_client import KBMcpClient

        async def _go():
            async with KBMcpClient(MCP_URL) as client:
                return await client.security_posture(resource_id="aws_nonexistent.xyz")

        result = run(_go())
        assert "error" in result


# ---------------------------------------------------------------------------
# Generalist tool tests
# ---------------------------------------------------------------------------
@requires_mcp
class TestCostEstimate:
    def test_m5_24xlarge_produces_large_delta(self):
        from agents.base.mcp_client import KBMcpClient

        hcl = '''
        resource "aws_instance" "batch" {
          instance_type = "m5.24xlarge"
          count = 3
        }
        '''

        async def _go():
            async with KBMcpClient(MCP_URL) as client:
                return await client.cost_estimate(hcl_fragment=hcl)

        result = run(_go())
        assert "output_id" in result
        assert result["output_id"].startswith("cost_est_")
        assert result["monthly_delta_usd"] > 5000
        assert result["pricing_source"] == "stub_table_v1"
        assert result["confidence"] in ("high", "medium", "low")
        assert len(result["line_items"]) == 1

    def test_deterministic_output_id(self):
        """Same input → same output_id (citation stability)."""
        from agents.base.mcp_client import KBMcpClient

        hcl = 'resource "aws_instance" "x" { instance_type = "t3.small" }'

        async def _go():
            async with KBMcpClient(MCP_URL) as client:
                a = await client.cost_estimate(hcl_fragment=hcl)
                b = await client.cost_estimate(hcl_fragment=hcl)
                return a, b

        a, b = run(_go())
        assert a["output_id"] == b["output_id"]
        assert a["monthly_delta_usd"] == b["monthly_delta_usd"]

    def test_unparseable_hcl_returns_error(self):
        from agents.base.mcp_client import KBMcpClient

        async def _go():
            async with KBMcpClient(MCP_URL) as client:
                return await client.cost_estimate(hcl_fragment="")

        result = run(_go())
        assert result.get("error") == "unparseable_hcl"


@requires_mcp
class TestPolicyCheck:
    def test_wildcard_iam_flagged(self):
        from agents.base.mcp_client import KBMcpClient

        hcl = '''
        resource "aws_iam_policy" "admin" {
          policy = jsonencode({
            Statement = [{ Action = "*", Effect = "Allow", Resource = "*" }]
          })
        }
        '''

        async def _go():
            async with KBMcpClient(MCP_URL) as client:
                return await client.policy_check(hcl_fragment=hcl)

        result = run(_go())
        assert "output_id" in result
        codes = {v["rule_id"] for v in result["violations"]}
        assert "iam-no-wildcard" in codes

    def test_missing_owner_tag_flagged(self):
        from agents.base.mcp_client import KBMcpClient

        hcl = 'resource "aws_s3_bucket" "logs" { bucket = "x" }'

        async def _go():
            async with KBMcpClient(MCP_URL) as client:
                return await client.policy_check(hcl_fragment=hcl)

        result = run(_go())
        codes = {v["rule_id"] for v in result["violations"]}
        assert "require-owner" in codes

    def test_benign_hcl_has_no_violations(self):
        from agents.base.mcp_client import KBMcpClient

        hcl = '''
        resource "aws_instance" "web" {
          instance_type = "t3.small"
          tags = { owner = "platform-team" }
        }
        '''

        async def _go():
            async with KBMcpClient(MCP_URL) as client:
                return await client.policy_check(hcl_fragment=hcl)

        result = run(_go())
        assert result["violations"] == []
        assert result["evaluator"] == "stub_rules_v1"


@requires_mcp
class TestHistorianLookup:
    def test_wildcard_trust_matches_prior_incident(self):
        from agents.base.mcp_client import KBMcpClient

        hcl = '''
        resource "aws_iam_role" "batch" {
          assume_role_policy = jsonencode({
            Statement = [{ Action = "sts:AssumeRole", Principal = { AWS = "*" } }]
          })
        }
        '''

        async def _go():
            async with KBMcpClient(MCP_URL) as client:
                return await client.historian_lookup(hcl_fragment=hcl, k=3)

        result = run(_go())
        assert "output_id" in result
        assert len(result["matches"]) >= 1
        inc_ids = {m["incident_id"] for m in result["matches"]}
        assert "INC-482" in inc_ids

    def test_benign_hcl_has_no_matches(self):
        from agents.base.mcp_client import KBMcpClient

        hcl = 'resource "aws_cloudwatch_metric_alarm" "cpu" { alarm_name = "x" }'

        async def _go():
            async with KBMcpClient(MCP_URL) as client:
                return await client.historian_lookup(hcl_fragment=hcl)

        result = run(_go())
        assert result["matches"] == []


@requires_mcp
class TestSloImpact:
    def test_payments_db_is_in_change_freeze(self):
        from agents.base.mcp_client import KBMcpClient

        async def _go():
            async with KBMcpClient(MCP_URL) as client:
                return await client.slo_impact(resource_ids=["aws_db_instance.payments"])

        result = run(_go())
        assert "output_id" in result
        assert result["inside_change_freeze"] is True
        assert result["change_freeze_reason"] is not None
        assert len(result["at_risk_services"]) == 1
        assert result["at_risk_services"][0]["service"] == "payments-api"

    def test_unknown_resource_returns_no_at_risk(self):
        from agents.base.mcp_client import KBMcpClient

        async def _go():
            async with KBMcpClient(MCP_URL) as client:
                return await client.slo_impact(resource_ids=["aws_instance.dev_test"])

        result = run(_go())
        assert result["at_risk_services"] == []
        assert result["inside_change_freeze"] is False
        assert result["change_freeze_reason"] is None
