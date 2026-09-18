"""Search context in TurboPuffer."""

import argparse
import json
from datetime import date, datetime
from typing import Any, Iterable
from sys import argv

from .tpuff import TurboPufferIndex


def _row_value(row: Any, field: str):
    """Read a field from a TurboPuffer row and normalize timestamps."""
    value = row.get(field) if isinstance(row, dict) else getattr(row, field, None)
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    return value


def results_payload(query: str, rows: Iterable[Any]) -> dict:
    """Build a stable, agent-readable search result payload."""
    results = [
        {
            "rank": rank,
            "session_id": _row_value(row, "session_id"),
            "prompt_id": _row_value(row, "prompt_id"),
            "prompt_timestamp": _row_value(row, "prompt_timestamp"),
            "project_path": _row_value(row, "project_path"),
            "transcript": _row_value(row, "transcript"),
        }
        for rank, row in enumerate(rows, start=1)
    ]
    return {"query": query, "result_count": len(results), "results": results}


def format_results(query: str, rows: Iterable[Any]) -> str:
    """Format search results as a stable, agent-readable JSON document."""
    return json.dumps(
        results_payload(query, rows),
        indent=2,
        ensure_ascii=False,
        default=str,
    )


def search(query: str):
    """Search indexed history and print agent-readable results."""
    indexer = TurboPufferIndex()
    results = indexer.context_mentioning_terms(phrase=query, top_k=5)
    print(format_results(query, results.rows or []))


def main():
    parser = argparse.ArgumentParser(description="Search indexed OpenCode history.")
    parser.add_argument("query", help="Query string to search for context.")
    args = parser.parse_args(argv[1:])
    search(query=args.query)


if __name__ == "__main__":
    main()
