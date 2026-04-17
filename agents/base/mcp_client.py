"""
MCP client wrapper for Consilium agents.

Provides a typed async interface over the raw MCP SDK session, targeting all
seven Consilium KB tools:

Analyst tools:
    semantic_search, blast_radius, security_posture

Generalist tools (cite at least one of these `output_id`s for every concern):
    cost_estimate, policy_check, historian_lookup, slo_impact

Usage:
    async with KBMcpClient("http://localhost:8000/mcp") as client:
        result = await client.semantic_search("vault transit signing")
        impacts = await client.blast_radius(["aws_vpc.main"])
        posture = await client.security_posture(resource_id="aws_s3_bucket.assets")
        cost    = await client.cost_estimate(hcl_fragment=hcl)
"""

from __future__ import annotations

import logging
from typing import Any

from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

log = logging.getLogger(__name__)


class MCPError(Exception):
    """Raised when an MCP tool call returns an error field or raises."""


class KBMcpClient:
    """
    Async context-manager that wraps a FastMCP HTTP session.

    Parameters
    ----------
    url : str
        Base URL of the MCP server's HTTP endpoint, e.g.
        ``http://localhost:8000/mcp``.
    timeout : float
        Per-call timeout in seconds (default 30).
    """

    def __init__(self, url: str = "http://localhost:8000/mcp", *, timeout: float = 30.0) -> None:
        self._url = url
        self._timeout = timeout
        self._session: ClientSession | None = None
        self._cm = None

    # ------------------------------------------------------------------
    # Context-manager protocol
    # ------------------------------------------------------------------
    async def __aenter__(self) -> "KBMcpClient":
        self._cm = streamablehttp_client(self._url)
        read, write, _ = await self._cm.__aenter__()
        self._session = ClientSession(read, write)
        await self._session.__aenter__()
        await self._session.initialize()
        log.debug("MCP session initialised against %s", self._url)
        return self

    async def __aexit__(self, *exc_info: Any) -> None:
        if self._session is not None:
            await self._session.__aexit__(*exc_info)
        if self._cm is not None:
            await self._cm.__aexit__(*exc_info)

    # ------------------------------------------------------------------
    # Low-level call helper
    # ------------------------------------------------------------------
    async def _call(self, tool: str, **kwargs: Any) -> Any:
        if self._session is None:
            raise RuntimeError("KBMcpClient must be used as an async context manager")
        # Filter out None arguments so the server sees only provided params
        args = {k: v for k, v in kwargs.items() if v is not None}
        result = await self._session.call_tool(tool, args)
        # FastMCP returns content as a list of TextContent objects
        if result.isError:
            raise MCPError(f"Tool '{tool}' returned an error: {result.content}")
        if not result.content:
            return {}
        import json
        raw = result.content[0].text  # type: ignore[union-attr]
        return json.loads(raw)

    # ------------------------------------------------------------------
    # Tool wrappers
    # ------------------------------------------------------------------
    async def semantic_search(
        self,
        query: str,
        k: int = 5,
        filters: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        """
        Search the HashiCorp KB.

        Returns ``{"results": [...], "query_embedding_id": ...}``.
        """
        return await self._call("semantic_search", query=query, k=k, filters=filters)

    async def blast_radius(
        self,
        resource_ids: list[str],
        depth: int = 2,
    ) -> dict[str, Any]:
        """
        Find resources impacted by changes to ``resource_ids``.

        Returns ``{"impacted": [...], "edges_traversed": int, "truncated": bool}``.
        """
        return await self._call("blast_radius", resource_ids=resource_ids, depth=depth)

    async def security_posture(
        self,
        resource_id: str | None = None,
        hcl_fragment: str | None = None,
    ) -> dict[str, Any]:
        """
        Retrieve IAM findings and security posture.

        Returns ``{"findings": [...], "iam_principals_affected": [...]}``.
        """
        if resource_id is None and hcl_fragment is None:
            raise ValueError("Provide either resource_id or hcl_fragment")
        return await self._call(
            "security_posture",
            resource_id=resource_id,
            hcl_fragment=hcl_fragment,
        )

    # ------------------------------------------------------------------
    # Generalist tool wrappers
    # ------------------------------------------------------------------
    async def cost_estimate(
        self,
        hcl_fragment: str,
        region: str = "us-east-1",
    ) -> dict[str, Any]:
        """
        Estimate the monthly cost delta of a change.

        Returns ``{"output_id", "monthly_delta_usd", "line_items", "pricing_source", "confidence"}``.
        """
        return await self._call("cost_estimate", hcl_fragment=hcl_fragment, region=region)

    async def policy_check(
        self,
        hcl_fragment: str,
        policy_set: str = "default",
    ) -> dict[str, Any]:
        """
        Evaluate an HCL fragment against a policy-as-code rule set.

        Returns ``{"output_id", "violations", "evaluator", "policies_evaluated"}``.
        """
        return await self._call("policy_check", hcl_fragment=hcl_fragment, policy_set=policy_set)

    async def historian_lookup(
        self,
        hcl_fragment: str,
        k: int = 3,
    ) -> dict[str, Any]:
        """
        Look up past deliberations / incidents structurally similar to the change.

        Returns ``{"output_id", "matches": [...]}``.
        """
        return await self._call("historian_lookup", hcl_fragment=hcl_fragment, k=k)

    async def slo_impact(
        self,
        resource_ids: list[str],
    ) -> dict[str, Any]:
        """
        Look up SLO / change-freeze impact for the given resources.

        Returns ``{"output_id", "at_risk_services", "inside_change_freeze", "change_freeze_reason"}``.
        """
        return await self._call("slo_impact", resource_ids=resource_ids)
