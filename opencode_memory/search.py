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
            "id": _row_value(row, "id"),
            "session_id": _row_value(row, "session_id"),
            "prompt_id": _row_value(row, "prompt_id"),
            "prompt_ordinal": _row_value(row, "prompt_ordinal"),
            "prompt_timestamp": _row_value(row, "prompt_timestamp"),
            "project_path": _row_value(row, "project_path"),
            "transcript": _row_value(row, "transcript"),
        }
        for rank, row in enumerate(rows, start=1)
    ]
    return {"query": query, "result_count": len(results), "results": results}


def inspect_payload(row: Any) -> dict:
    """Build a full-document payload using the untruncated transcript."""
    row_data = dict(row)
    payload = {
        "id": row_data.get("id"),
        "transcript": row_data.get("transcript_full"),
        "session_id": row_data.get("session_id"),
        "prompt_id": row_data.get("prompt_id"),
        "prompt_ordinal": row_data.get("prompt_ordinal"),
        "prompt_timestamp": row_data.get("prompt_timestamp"),
        "project_path": row_data.get("project_path"),
        "is_system_prompt": row_data.get("is_system_prompt"),
    }
    for key, value in payload.items():
        if isinstance(value, (date, datetime)):
            payload[key] = value.isoformat()
    return payload


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
    session_id: str | None = None,
    prompt_ordinal: int | None = None,
    system_metadata: bool = False,
):
    """Search indexed history through the running daemon."""
    connection = UnixSocketHTTPConnection(socket_path)
    try:
        exact_prompt = session_id is not None and prompt_ordinal is not None
        body = json.dumps({
            "query": "" if exact_prompt else query,
            "top_k": top_k,
            "project_path": project_path,
            "session_id": session_id,
            "prompt_ordinal": prompt_ordinal,
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


def inspect_doc(doc_id: str, socket_path: Path):
    """Fetch and print one complete document through the running daemon."""
    connection = UnixSocketHTTPConnection(socket_path)
    try:
        connection.request("GET", f"/inspect/{doc_id}")
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
        "--inspect",
        default=None,
        metavar="DOC_ID",
        help="Fetch one complete document by ID; cannot be combined with search options.",
    )
    parser.add_argument(
        "--socket",
        default=os.getenv("OPENCODE_HISTORY_SOCKET", str(DEFAULT_SOCKET_PATH)),
        help="Unix socket path for the history service.",
    )
    parser.add_argument("--top-k", type=int, default=5, help="Maximum results to return.")
    parser.add_argument(
        "--project-path",
        default=None,
        help="Filter results to a specific project path. Unfiltered results are capped at --top-k total, with at most 2 per project.",
    )
    parser.add_argument(
        "--session-id",
        default=None,
        help="Filter results to one OpenCode session.",
    )
    parser.add_argument(
        "--prompt-ordinal",
        type=int,
        default=None,
        help="Filter to one prompt ordinal within --session-id.",
    )
    parser.add_argument(
        "--session-metadata",
        action="store_true",
        help="Only return per-project metadata results (system prompts, AGENTS.md, project path).",
    )
    parser.add_argument(
        "search",
        nargs="?",
        default=None,
        help="Search for context",
    )
    args = parser.parse_args(argv[1:])
    if args.inspect is not None:
        if (args.top_k != 5 or args.project_path is not None
                or args.session_id is not None or args.prompt_ordinal is not None or args.session_metadata):
            parser.error("--inspect cannot be combined with a query or search options")
        inspect_doc(args.inspect, Path(args.socket).expanduser())
        return
    exact_prompt = args.session_id is not None and args.prompt_ordinal is not None
    if args.search is None and not exact_prompt:
        parser.error("a search query is required unless --inspect is used")
    if args.prompt_ordinal is not None and args.session_id is None:
        parser.error("--prompt-ordinal requires --session-id")
    search(
        query=args.search or "",
        socket_path=Path(args.socket).expanduser(),
        top_k=args.top_k,
        project_path=args.project_path,
        session_id=args.session_id,
        prompt_ordinal=args.prompt_ordinal,
        system_metadata=args.session_metadata,
    )


if __name__ == "__main__":
    main()
