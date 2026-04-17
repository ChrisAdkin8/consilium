"""
Generalist voter — entrypoint stub.

Fully wired in M4. For now this module only:

1. Defines the opinion shape the Generalist emits (so M2 can integration-test
   the signed envelope carrier without a working LLM).
2. Holds the `deliberate()` coroutine skeleton that M4 will fill in with
   parallel tool calls + synthesis + citation enforcement.

Soft-concern verdict vocabulary: `approve | concern | abstain`. Attempting
to return `veto` is a protocol violation and is rewritten by the citation
parser to `error` before signing.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Any, Literal

from agents.base.mcp_client import KBMcpClient
from agents.generalist.citation_parser import normalize_opinion

log = logging.getLogger(__name__)

AGENT_NAME = "generalist"
VOTER_CLASS = "soft_concern"
ALLOWED_VERDICTS: tuple[str, ...] = ("approve", "concern", "abstain")


Verdict = Literal["approve", "concern", "abstain"]


@dataclass
class ToolOutputRef:
    """A Generalist concern must reference one of these."""
    tool: str
    output_id: str


@dataclass
class Concern:
    summary: str
    citations: list[ToolOutputRef] = field(default_factory=list)
    severity: str = "MEDIUM"  # HIGH | MEDIUM | LOW | INFO


@dataclass
class GeneralistOpinion:
    verdict: Verdict
    voter_class: str = VOTER_CLASS
    concerns: list[Concern] = field(default_factory=list)
    rationale: str = ""
    tool_outputs: dict[str, Any] = field(default_factory=dict)


async def _consult_tools(client: KBMcpClient, hcl: str, resource_ids: list[str]) -> dict[str, Any]:
    """Fan out across all four Generalist tools in parallel."""
    cost, policy, history, slo = await asyncio.gather(
        client.cost_estimate(hcl_fragment=hcl),
        client.policy_check(hcl_fragment=hcl),
        client.historian_lookup(hcl_fragment=hcl),
        client.slo_impact(resource_ids=resource_ids) if resource_ids else _noop_slo(),
        return_exceptions=False,
    )
    return {
        "cost_estimate": cost,
        "policy_check": policy,
        "historian_lookup": history,
        "slo_impact": slo,
    }


async def _noop_slo() -> dict[str, Any]:
    return {
        "output_id": None,
        "at_risk_services": [],
        "inside_change_freeze": False,
        "change_freeze_reason": None,
    }


async def deliberate(
    *,
    hcl_fragment: str,
    resource_ids: list[str],
    mcp_url: str,
) -> GeneralistOpinion:
    """
    Produce a Generalist opinion for the given proposal.

    M1/M2 scaffolding: returns `approve` with the raw tool outputs attached.
    M4 replaces the body with an LLM synthesis step + citation enforcement
    (via `citation_parser.normalize_opinion`).
    """
    async with KBMcpClient(mcp_url) as client:
        tool_outputs = await _consult_tools(client, hcl_fragment, resource_ids)

    # Placeholder body until M4. Real synthesis lives in prompts/v1.md.
    opinion = GeneralistOpinion(
        verdict="approve",
        concerns=[],
        rationale="M1 scaffold: no concerns raised (synthesis step not yet implemented).",
        tool_outputs=tool_outputs,
    )

    return normalize_opinion(opinion)
