"""
Generalist scoreboard.

Loads every HCL fixture under `concern_cases/` and `benign_cases/`, runs each
through `agents.generalist.main.deliberate()`, and reports the hit / false-alarm
rate against the expected verdicts encoded in the `.meta.yaml` sidecars.

Pass criteria (DoD for M4.11, see MVP_PLAN.md §D14):
  - concern cases: ≥ 5/5 returned `verdict == "concern"`
  - benign cases:  ≤ 2/10 returned `verdict == "concern"`

Exit code is non-zero if either threshold is missed.

Usage:
  python tests/generalist/scoreboard.py \
      [--mcp-url http://localhost:8000/mcp] [--json report.json]

Requires the stack to be up (MCP server + Neo4j + stub data):
  docker compose -f dev/docker-compose.yml up -d
  python -m kb_extensions.seed.seed_neo4j
  python -m kb_extensions.mcp_server
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import yaml

from agents.generalist.main import deliberate

HERE = Path(__file__).parent
CONCERN_DIR = HERE / "concern_cases"
BENIGN_DIR = HERE / "benign_cases"

MIN_CONCERN_HITS = 5      # out of 5
MAX_BENIGN_FALSE = 2      # out of 10


@dataclass
class CaseResult:
    case: str
    kind: str                    # "concern" | "benign"
    expected_verdict: str
    actual_verdict: str
    tools_cited: list[str]
    pass_: bool
    rationale: str


def _load_cases(directory: Path, kind: str) -> list[dict[str, Any]]:
    cases: list[dict[str, Any]] = []
    for hcl_file in sorted(directory.glob("*.tf")):
        meta_file = hcl_file.with_suffix(".meta.yaml")
        meta: dict[str, Any] = {}
        if meta_file.exists():
            meta = yaml.safe_load(meta_file.read_text()) or {}
        cases.append({
            "name": hcl_file.stem,
            "kind": kind,
            "hcl": hcl_file.read_text(),
            "expected_verdict": meta.get("expected_verdict", "approve" if kind == "benign" else "concern"),
            "resource_ids": meta.get("resource_ids", []) or [],
            "meta": meta,
        })
    return cases


def _citations_of(opinion: Any) -> list[str]:
    tools: set[str] = set()
    for c in getattr(opinion, "concerns", None) or []:
        for ref in getattr(c, "citations", None) or []:
            t = getattr(ref, "tool", None)
            if t:
                tools.add(t)
    return sorted(tools)


async def _run_one(case: dict[str, Any], mcp_url: str) -> CaseResult:
    opinion = await deliberate(
        hcl_fragment=case["hcl"],
        resource_ids=case["resource_ids"],
        mcp_url=mcp_url,
    )
    actual = getattr(opinion, "verdict", "error")
    expected = case["expected_verdict"]
    passed = actual == expected
    return CaseResult(
        case=case["name"],
        kind=case["kind"],
        expected_verdict=expected,
        actual_verdict=actual,
        tools_cited=_citations_of(opinion),
        pass_=passed,
        rationale=(getattr(opinion, "rationale", "") or "").strip(),
    )


async def _run_all(mcp_url: str) -> list[CaseResult]:
    cases = _load_cases(CONCERN_DIR, "concern") + _load_cases(BENIGN_DIR, "benign")
    if not cases:
        print("no fixtures found under tests/generalist/{concern_cases,benign_cases}", file=sys.stderr)
        return []
    return await asyncio.gather(*(_run_one(c, mcp_url) for c in cases))


def _tabulate(results: list[CaseResult]) -> str:
    rows = [
        f"{'CASE':40} {'KIND':8} {'EXPECT':10} {'ACTUAL':10} {'TOOLS':30} PASS",
        "-" * 110,
    ]
    for r in results:
        rows.append(
            f"{r.case:40} {r.kind:8} {r.expected_verdict:10} {r.actual_verdict:10} "
            f"{','.join(r.tools_cited) or '-':30} {'PASS' if r.pass_ else 'FAIL'}"
        )
    return "\n".join(rows)


def _summarise(results: list[CaseResult]) -> dict[str, Any]:
    concern = [r for r in results if r.kind == "concern"]
    benign = [r for r in results if r.kind == "benign"]
    concern_hits = sum(1 for r in concern if r.actual_verdict == "concern")
    benign_false = sum(1 for r in benign if r.actual_verdict == "concern")
    return {
        "concern_total": len(concern),
        "concern_hits": concern_hits,
        "benign_total": len(benign),
        "benign_false_alarms": benign_false,
        "passes_dod": concern_hits >= MIN_CONCERN_HITS and benign_false <= MAX_BENIGN_FALSE,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--mcp-url",
        default=os.environ.get("KB_MCP_URL", "http://localhost:8000") + "/mcp",
    )
    parser.add_argument("--json", dest="json_out", help="write a JSON report to this path")
    args = parser.parse_args()

    results = asyncio.run(_run_all(args.mcp_url))
    if not results:
        return 2

    print(_tabulate(results))
    summary = _summarise(results)
    print()
    print(
        f"concern hits: {summary['concern_hits']}/{summary['concern_total']} "
        f"(need ≥ {MIN_CONCERN_HITS})"
    )
    print(
        f"benign false alarms: {summary['benign_false_alarms']}/{summary['benign_total']} "
        f"(need ≤ {MAX_BENIGN_FALSE})"
    )
    print(f"DoD: {'PASS' if summary['passes_dod'] else 'FAIL'}")

    if args.json_out:
        Path(args.json_out).write_text(json.dumps(
            {"summary": summary, "results": [asdict(r) for r in results]},
            indent=2,
        ))

    return 0 if summary["passes_dod"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
