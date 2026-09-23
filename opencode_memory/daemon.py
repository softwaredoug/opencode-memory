"""FastAPI service for indexing and searching OpenCode history."""

import argparse
import os
import stat
from pathlib import Path
from sys import argv
import asyncio
from contextlib import asynccontextmanager
from collections.abc import AsyncGenerator

import uvicorn
from fastapi import FastAPI
from pydantic import BaseModel, Field

from .tpuf import TurboPufferIndex
from .parse_telemetry import MIN_UTC_TIMESTAMP, prompt_docs, last_modified_time
from .search import results_payload


DEFAULT_SOCKET_PATH = (
    Path.home() / ".local" / "share" / "opencode-history" / "service.sock"
)


async def reindex_loop():
    last_modified_date = None
    while True:
        try:
            modified_date = last_modified_time()
            if modified_date != last_modified_date:
                print("Detected new telemetry data. Reindexing...")
                await index_latest(force=False)
                last_modified_date = modified_date
        except Exception as e:
            print(f"Error during reindexing: {e}")
        await asyncio.sleep(60)  # Check every 60 seconds


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncGenerator[None, None]:
    del _app
    task = asyncio.create_task(reindex_loop())
    try:
        yield
    finally:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)


app = FastAPI(title="OpenCode History", lifespan=lifespan)


class IndexRequest(BaseModel):
    force: bool = False


class SearchRequest(BaseModel):
    query: str
    top_k: int = Field(default=5, ge=1, le=50)

    system_metadata: bool = Field(default=False,
                                  description="Only include session metadata in results (AGENTS.md and repo info). Otherwise include all results.")
    project_path: str | None = Field(default=None, description="Filter results to a specific project path.")


async def index_latest(force: bool = False):
    """Index the latest docs into TurboPuffer."""
    indexer = TurboPufferIndex()
    last_index_time = await indexer.last_index_time()
    if force:
        last_index_time = MIN_UTC_TIMESTAMP
        print("Force reindexing all docs into TurboPuffer.")
    else:
        print(f"Indexing telemetry after {last_index_time.isoformat()} into TurboPuffer.")
    docs = prompt_docs(last_index_time=last_index_time)
    await indexer.index_docs(docs)


@app.get("/health")
def health():
    """Report that the service is available without contacting TurboPuffer."""
    return {"ok": True}


@app.post("/index")
async def index(request: IndexRequest):
    """Index telemetry newer than the latest indexed prompt."""
    await index_latest(force=request.force)
    return {"ok": True}


@app.post("/search")
async def search(request: SearchRequest):
    """Search indexed history and return structured results."""
    indexer = TurboPufferIndex()
    response = await indexer.search(
        phrase=request.query,
        system_only=request.system_metadata,
        project_path=request.project_path,
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
    parser.add_argument(
        "--index",
        action="store_true",
        default=False,
        help="Index latest telemetry before starting the service.",
    )
    args = parser.parse_args(argv[1:])
    if args.index:
        asyncio.run(index_latest(force=False))
    socket_path = Path(args.socket).expanduser()
    socket_path.parent.mkdir(parents=True, exist_ok=True)
    if socket_path.exists():
        if not stat.S_ISSOCK(socket_path.stat().st_mode):
            raise RuntimeError(f"Refusing to replace non-socket path: {socket_path}")
        socket_path.unlink()
    uvicorn.run(app, uds=str(socket_path))


if __name__ == "__main__":
    main()
