"""Search context in TurboPuffer."""

import argparse
import http.client
import json
from datetime import date, datetime
import os
from pathlib import Path
import socket
from typing import Any, Iterable
from sys import argv

DEFAULT_SOCKET_PATH = (
    Path.home() / ".local" / "share" / "opencode-history" / "service.sock"
)


class UnixSocketHTTPConnection(http.client.HTTPConnection):
    """HTTP connection that transports requests over a Unix socket."""

    def __init__(self, socket_path: Path):
        super().__init__("localhost")
        self.socket_path = socket_path

    def connect(self):
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        if isinstance(self.timeout, (int, float)):
            self.sock.settimeout(self.timeout)
        self.sock.connect(str(self.socket_path))


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


def search(
    query: str,
    socket_path: Path,
    top_k: int = 5,
    project_path: str | None = None,
    system_metadata: bool = False,
):
    """Search indexed history through the running daemon."""
    connection = UnixSocketHTTPConnection(socket_path)
    try:
        body = json.dumps({
            "query": query,
            "top_k": top_k,
            "project_path": project_path,
            "system_metadata": system_metadata,
        })
        connection.request(
            "POST",
            "/search",
            body=body,
            headers={"Content-Type": "application/json"},
        )
        response = connection.getresponse()
        response_body = response.read().decode("utf-8")
    finally:
        connection.close()

    result = json.loads(response_body)
    if response.status >= 400:
        raise RuntimeError(result.get("detail", response_body))
    print(json.dumps(result, indent=2, ensure_ascii=False, default=str))


def main():
    parser = argparse.ArgumentParser(description="Search indexed OpenCode history.")
    # parser.add_argument("query", help="Query string to search for context.")
    parser.add_argument(
        "--socket",
        default=os.getenv("OPENCODE_HISTORY_SOCKET", str(DEFAULT_SOCKET_PATH)),
        help="Unix socket path for the history service.",
    )
    parser.add_argument("--top-k", type=int, default=5, help="Maximum results to return.")
    parser.add_argument(
        "--project-path",
        default=None,
        help="Filter results to a specific project path. If not specified, will give top K per project to give you an overview",
    )
    parser.add_argument(
        "--system-metadata",
        action="store_true",
        help="Only return per-project metadata results (system prompts, AGENTS.md, project path).",
    )
    parser.add_argument(
        "keyword-search",
        nargs="?",
        default=None,
        help="Keyword search to search for",
    )
    args = parser.parse_args(argv[1:])
    search(
        query=args.query,
        socket_path=Path(args.socket).expanduser(),
        top_k=args.top_k,
        project_path=args.project_path,
        system_metadata=args.system_metadata,
    )


if __name__ == "__main__":
    main()
