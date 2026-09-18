"""FastAPI service for indexing and searching OpenCode history."""

import argparse
import os
import stat
from pathlib import Path
from sys import argv

import uvicorn
from fastapi import FastAPI
from pydantic import BaseModel, Field

from .tpuff import TurboPufferIndex
from .parse_telemetry import MIN_UTC_TIMESTAMP, prompt_docs
from .search import results_payload


DEFAULT_SOCKET_PATH = (
    Path.home() / ".local" / "share" / "opencode-history" / "service.sock"
)

app = FastAPI(title="OpenCode History")


class IndexRequest(BaseModel):
    force: bool = False


class SearchRequest(BaseModel):
    query: str
    top_k: int = Field(default=5, ge=1, le=50)


def index_latest(force: bool = False):
    """Index the latest docs into TurboPuffer."""
    indexer = TurboPufferIndex()
    last_index_time = indexer.last_index_time()
    if force:
        last_index_time = MIN_UTC_TIMESTAMP
        print("Force reindexing all docs into TurboPuffer.")
    else:
        print(f"Indexing telemetry after {last_index_time.isoformat()} into TurboPuffer.")
    docs = prompt_docs(last_index_time=last_index_time)
    indexer.index_docs(docs)


@app.get("/health")
def health():
    """Report that the service is available without contacting TurboPuffer."""
    return {"ok": True}


@app.post("/index")
def index(request: IndexRequest):
    """Index telemetry newer than the latest indexed prompt."""
    index_latest(force=request.force)
    return {"ok": True}


@app.post("/search")
def search(request: SearchRequest):
    """Search indexed history and return structured results."""
    indexer = TurboPufferIndex()
    response = indexer.context_mentioning_terms(
        phrase=request.query,
        top_k=request.top_k,
    )
    return results_payload(request.query, response.rows or [])


def main():
    parser = argparse.ArgumentParser(description="Run the OpenCode history service.")
    parser.add_argument(
        "--socket",
        default=os.getenv("OPENCODE_HISTORY_SOCKET", str(DEFAULT_SOCKET_PATH)),
        help="Unix socket path for the service.",
    )
    args = parser.parse_args(argv[1:])
    socket_path = Path(args.socket).expanduser()
    socket_path.parent.mkdir(parents=True, exist_ok=True)
    if socket_path.exists():
        if not stat.S_ISSOCK(socket_path.stat().st_mode):
            raise RuntimeError(f"Refusing to replace non-socket path: {socket_path}")
        socket_path.unlink()
    uvicorn.run(app, uds=str(socket_path))


if __name__ == "__main__":
    main()
