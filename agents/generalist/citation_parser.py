"""
Citation parser for the Generalist voter.

Two invariants this module enforces before an opinion is signed:

1. Every concern must cite at least one tool output ID returned by one of the
   four Generalist tools (cost_estimate, policy_check, historian_lookup,
   slo_impact). A concern without a citation is an *unsupported claim* and
   is rewritten to an `abstain` verdict with `reason: unsupported_claim` —
   this causes the quorum engine (docs/voting-architecture.md §3) to reject
   the deliberation for lack of quorum.

2. The Generalist's allowed verb set is `approve | concern | abstain`.
   A `veto` from the Generalist is a protocol violation — it is rewritten
   to the sentinel verdict `error` with `reason: protocol_violation`. The
   quorum engine (M5) raises `error` rather than `reject`, so operators
   can distinguish "the parliament said no" from "an agent misbehaved."

Both invariants are *deterministic*: they cannot be regressed by a prompt
change. See docs/voting-architecture.md §3 for why this matters.
"""

from __future__ import annotations

import logging
from typing import Any

log = logging.getLogger(__name__)

VALID_GENERALIST_TOOLS: frozenset[str] = frozenset({
    "cost_estimate",
    "policy_check",
    "historian_lookup",
    "slo_impact",
})


class ProtocolViolation(Exception):
    """Raised when a Generalist opinion structurally cannot be sent."""


def _collect_valid_output_ids(tool_outputs: dict[str, Any]) -> set[str]:
    """Every citation ID the Generalist is allowed to reference, keyed off the
    tool outputs it actually consulted in this deliberation."""
    ids: set[str] = set()
    for tool_name, payload in (tool_outputs or {}).items():
        if tool_name not in VALID_GENERALIST_TOOLS:
            continue
        if not isinstance(payload, dict):
            continue
        oid = payload.get("output_id")
        if isinstance(oid, str) and oid:
            ids.add(oid)
    return ids


def normalize_opinion(opinion: Any) -> Any:
    """
    Enforce the two invariants above on a `GeneralistOpinion` dataclass (or
    any object with `verdict`, `concerns`, `tool_outputs`, `rationale`
    attributes).

    Returns the (possibly rewritten) opinion. Raises `ProtocolViolation`
    only if the input shape is unrecognisable.
    """
    try:
        verdict = opinion.verdict
        concerns = opinion.concerns
        tool_outputs = getattr(opinion, "tool_outputs", {}) or {}
    except AttributeError as exc:
        raise ProtocolViolation(f"opinion object missing required fields: {exc}") from exc

    # Invariant 2: Generalist cannot veto.
    if verdict == "veto":
        log.error("Generalist attempted verdict=veto — rewriting to error/protocol_violation")
        opinion.verdict = "error"
        opinion.rationale = (
            (getattr(opinion, "rationale", "") or "")
            + "\n[protocol_violation] Generalist is a soft-concern voter and cannot veto."
        ).strip()
        return opinion

    # Reject anything outside the allowed vocabulary (defence-in-depth).
    if verdict not in ("approve", "concern", "abstain", "error"):
        log.error("Generalist returned unknown verdict=%r — rewriting to error", verdict)
        opinion.verdict = "error"
        opinion.rationale = (
            (getattr(opinion, "rationale", "") or "")
            + f"\n[protocol_violation] Unknown verdict {verdict!r} from soft-concern voter."
        ).strip()
        return opinion

    # Invariant 1: every concern must cite a valid tool output ID.
    valid_ids = _collect_valid_output_ids(tool_outputs)
    unsupported: list[str] = []

    for concern in list(concerns or []):
        citations = getattr(concern, "citations", []) or []
        if not citations:
            unsupported.append(getattr(concern, "summary", "<no summary>"))
            continue
        cited_ids = {
            getattr(ref, "output_id", None)
            for ref in citations
            if getattr(ref, "tool", None) in VALID_GENERALIST_TOOLS
        }
        cited_ids.discard(None)
        if not cited_ids.intersection(valid_ids):
            unsupported.append(getattr(concern, "summary", "<no summary>"))

    if unsupported and verdict == "concern":
        log.warning(
            "Generalist concern(s) uncited — rewriting opinion to abstain: %r",
            unsupported,
        )
        opinion.verdict = "abstain"
        opinion.concerns = []
        opinion.rationale = (
            "[unsupported_claim] The following concerns had no valid tool citation "
            "and were rejected by the citation parser: " + "; ".join(unsupported)
        )

    return opinion
