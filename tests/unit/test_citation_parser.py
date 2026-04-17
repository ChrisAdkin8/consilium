"""
Unit tests for `agents.generalist.citation_parser.normalize_opinion`.

These tests pin the two protocol invariants enforced deterministically by the
citation parser (see docs/voting-architecture.md §3):

  1. A soft-concern voter cannot return `veto`. Doing so is rewritten to the
     sentinel verdict `error` with `reason: protocol_violation`.
  2. Every `concern` must cite at least one `output_id` returned by one of the
     four Generalist MCP tools. Uncited concerns cause the whole opinion to be
     rewritten to `abstain` with `reason: unsupported_claim`.

If either test starts failing, the voting architecture contract has regressed
— do not patch the tests, fix the parser.
"""
from __future__ import annotations

from agents.generalist.citation_parser import normalize_opinion
from agents.generalist.main import Concern, GeneralistOpinion, ToolOutputRef


def _opinion(**kwargs) -> GeneralistOpinion:
    defaults = dict(verdict="approve", concerns=[], rationale="", tool_outputs={})
    defaults.update(kwargs)
    return GeneralistOpinion(**defaults)


# ---------------------------------------------------------------------------
# Invariant 2 — Generalist cannot veto
# ---------------------------------------------------------------------------
class TestVetoRewrite:
    def test_veto_verdict_rewritten_to_error(self):
        op = _opinion(verdict="veto", rationale="this is bad")
        result = normalize_opinion(op)
        assert result.verdict == "error"
        assert "protocol_violation" in result.rationale
        assert "cannot veto" in result.rationale

    def test_unknown_verdict_rewritten_to_error(self):
        op = _opinion(verdict="nope")
        result = normalize_opinion(op)
        assert result.verdict == "error"
        assert "protocol_violation" in result.rationale

    def test_legal_verdicts_pass_through(self):
        for v in ("approve", "abstain"):
            op = _opinion(verdict=v)
            assert normalize_opinion(op).verdict == v


# ---------------------------------------------------------------------------
# Invariant 1 — every concern must cite a valid tool output_id
# ---------------------------------------------------------------------------
class TestCitationEnforcement:
    def test_uncited_concern_rewrites_to_abstain(self):
        op = _opinion(
            verdict="concern",
            concerns=[Concern(summary="vague worry", citations=[])],
            tool_outputs={"cost_estimate": {"output_id": "cost_est_abc"}},
        )
        result = normalize_opinion(op)
        assert result.verdict == "abstain"
        assert result.concerns == []
        assert "unsupported_claim" in result.rationale

    def test_concern_with_valid_citation_passes(self):
        op = _opinion(
            verdict="concern",
            concerns=[Concern(
                summary="$10k/mo delta",
                citations=[ToolOutputRef(tool="cost_estimate", output_id="cost_est_abc")],
            )],
            tool_outputs={"cost_estimate": {"output_id": "cost_est_abc"}},
        )
        result = normalize_opinion(op)
        assert result.verdict == "concern"
        assert len(result.concerns) == 1

    def test_citation_referencing_unknown_tool_is_rejected(self):
        op = _opinion(
            verdict="concern",
            concerns=[Concern(
                summary="made up",
                citations=[ToolOutputRef(tool="tarot_reading", output_id="tar_123")],
            )],
            tool_outputs={"cost_estimate": {"output_id": "cost_est_abc"}},
        )
        result = normalize_opinion(op)
        assert result.verdict == "abstain"
        assert "unsupported_claim" in result.rationale

    def test_citation_with_stale_output_id_is_rejected(self):
        op = _opinion(
            verdict="concern",
            concerns=[Concern(
                summary="quoting an ID from some other deliberation",
                citations=[ToolOutputRef(tool="cost_estimate", output_id="cost_est_DEADBEEF")],
            )],
            tool_outputs={"cost_estimate": {"output_id": "cost_est_abc"}},
        )
        result = normalize_opinion(op)
        assert result.verdict == "abstain"

    def test_approve_verdict_never_rewrites_even_if_empty_concerns(self):
        op = _opinion(verdict="approve", concerns=[], tool_outputs={})
        assert normalize_opinion(op).verdict == "approve"

    def test_mixed_concerns_one_uncited_still_rewrites(self):
        """Any uncited concern poisons the whole opinion — you don't get to
        slip one vague worry in alongside a cited one."""
        op = _opinion(
            verdict="concern",
            concerns=[
                Concern(
                    summary="real concern",
                    citations=[ToolOutputRef(tool="cost_estimate", output_id="cost_est_abc")],
                ),
                Concern(summary="vague worry", citations=[]),
            ],
            tool_outputs={"cost_estimate": {"output_id": "cost_est_abc"}},
        )
        result = normalize_opinion(op)
        assert result.verdict == "abstain"
