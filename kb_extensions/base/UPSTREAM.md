# Upstream: aws-hashi-knowledge-base

Vendored from https://github.com/ChrisAdkin8/aws-hashi-knowledge-base (mcp/ directory, depth-1 snapshot).

## What's here

| File | Purpose |
|---|---|
| `server.py` | Upstream FastMCP server — Kendra semantic search + Neptune graph |
| `test_server.py` | Upstream smoke tests (requires AWS credentials + Kendra index) |
| `requirements.txt` | Upstream Python deps (`mcp`, `boto3`, `requests`) |

## Relationship to Consilium

`kb_extensions/mcp_server.py` is the Consilium-specific MCP server.  
It exposes the **same three-tool contract** (`semantic_search`, `blast_radius`, `security_posture`) but uses a local corpus + Neo4j instead of Kendra + Neptune.

The upstream server is kept here as a reference for the production Kendra/Neptune backend.
To run the upstream server in production (post-MVP), set `AWS_KENDRA_INDEX_ID`, `AWS_REGION`,
and optionally `NEPTUNE_ENDPOINT`, then `python -m kb_extensions.base.server`.
