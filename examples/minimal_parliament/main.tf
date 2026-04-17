###############################################################################
# Minimal Consilium Parliament — local dev example.
#
# What this does:
#   Registers the five agents of a Consilium parliament (Speaker, Architect, two
#   hard-veto voters, and the Generalist soft-concern voter) against a locally
#   running control plane, and declares the quorum policy that governs how
#   their opinions are tallied.
#
# Prerequisites:
#   task dev:up         # starts Vault / Consul / Nomad / Neo4j / MCP in Docker
#   task vault-keys     # provisions the six transit signing keys
#   task control-plane  # `uvicorn consilium.app:app --port 9000`
#
# Then from this directory:
#   terraform init
#   terraform apply
#
# Expected result:
#   - Five Nomad jobs running (one per agent), discoverable via Consul.
#   - A `consilium_quorum_policy.dev` resource in state.
#   - `consul catalog services` lists `consilium-generalist` alongside the
#     other four.
#
# Deliberate with:
#   consilium submit path/to/change.tf
###############################################################################

terraform {
  required_providers {
    consilium = {
      source  = "hashicorp/consilium"
      version = ">= 0.1.0"
    }
  }
}

provider "consilium" {
  control_plane_url = "http://localhost:9000"
}

# ---------------------------------------------------------------------------
# Non-voting agents
# ---------------------------------------------------------------------------
resource "consilium_agent" "speaker" {
  name        = "speaker"
  role        = "speaker"
  voter_class = "none"
  model       = "claude-sonnet-4-6"
}

resource "consilium_agent" "architect" {
  name        = "architect"
  role        = "architect"
  voter_class = "none"
  model       = "claude-sonnet-4-6"
}

# ---------------------------------------------------------------------------
# Hard-veto voters — a single veto from either one rejects the deliberation.
# ---------------------------------------------------------------------------
resource "consilium_agent" "blast_radius" {
  name        = "blast_radius"
  role        = "voter"
  voter_class = "hard_veto"
  model       = "claude-sonnet-4-6"
}

resource "consilium_agent" "red_team" {
  name        = "red_team"
  role        = "voter"
  voter_class = "hard_veto"
  model       = "claude-opus-4-6"
}

# ---------------------------------------------------------------------------
# Soft-concern voter — can `approve | concern | abstain` only. Attempting
# `veto` is a protocol violation (see agents/generalist/citation_parser.py).
# ---------------------------------------------------------------------------
resource "consilium_agent" "generalist" {
  name        = "generalist"
  role        = "voter"
  voter_class = "soft_concern"
  model       = "claude-sonnet-4-6"
}

# ---------------------------------------------------------------------------
# Quorum policy.
#
# `hard_veto_voters` and `soft_concern_voters` are the authoritative lists the
# engine uses to tally opinions. Listing a voter in the wrong list is a
# config error (the engine cross-checks against each agent's `voter_class`).
#
# `escalate_concern_to_veto` blocks are parsed and validated in v0.1.0 but
# NOT enforced — they exist so operators can stage rules ahead of the v0.2.0
# engine change. See docs/voting-architecture.md §5.
# ---------------------------------------------------------------------------
resource "consilium_quorum_policy" "dev" {
  name = "dev"

  hard_veto_voters    = [
    consilium_agent.blast_radius.name,
    consilium_agent.red_team.name,
  ]
  soft_concern_voters = [
    consilium_agent.generalist.name,
  ]

  # --- staged rules for v0.2.0 (parsed, unenforced in this release) ---------
  escalate_concern_to_veto {
    voter = "generalist"
    tool  = "cost_estimate"
    when  = "monthly_delta_usd > 5000"
  }

  escalate_concern_to_veto {
    voter = "generalist"
    tool  = "slo_impact"
    when  = "inside_change_freeze == true"
  }

  escalate_concern_to_veto {
    voter = "generalist"
    tool  = "policy_check"
    when  = "severity == 'HIGH'"
  }
}

output "parliament" {
  value = {
    speaker      = consilium_agent.speaker.name
    architect    = consilium_agent.architect.name
    hard_veto    = [consilium_agent.blast_radius.name, consilium_agent.red_team.name]
    soft_concern = [consilium_agent.generalist.name]
    policy       = consilium_quorum_policy.dev.name
  }
}
