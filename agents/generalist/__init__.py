"""Generalist voter (soft-concern class).

Consults deterministic tools (cost_estimate, policy_check, historian_lookup,
slo_impact) and emits a signed opinion. The citation parser (this package)
enforces that every concern cites at least one tool output ID; uncited
concerns are rewritten to `abstain` before signing.

See docs/voting-architecture.md §4 for the "citation contract" rationale.
"""
