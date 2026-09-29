import asyncio
import turbopuffer
from turbopuffer.types.row_param import RowParam
from turbopuffer.types.limit_param import LimitParam
from turbopuffer.types import Row
from turbopuffer.types.namespace_multi_query_response import Result
import logging
from collections.abc import Iterable
import os
from typing import Iterator
from itertools import batched
from datetime import datetime, timezone


TURBOPUFFER_API_KEY = os.getenv("TURBOPUFFER_API_KEY")
if TURBOPUFFER_API_KEY is None:
    raise RuntimeError("TURBOPUFFER_API_KEY environment variable is not set.")
DEFAULT_TPUF_NAMESPACE = os.getenv("TPUF_NAMESPACE", "opencodetrace")
VOYAGE_MODEL = "voyage/voyage-4-large"
INDEX_MAX_RETRIES = 3
INDEX_RETRY_BASE_SECONDS = 1.0
MAX_TRANSCRIPT_CHARS = 4000


logger = logging.getLogger(__name__)


def ns_exists(tpuf, ns_name, expected_count=1):
    ns = tpuf.namespace(ns_name)
    try:
        metadata = ns.metadata()
        if metadata.approx_row_count < expected_count:
            logger.warning(
                "Namespace %s exists but has fewer rows (%s) than expected (%s).",
                ns_name,
                metadata.approx_row_count,
                expected_count,
            )
            return False
    except turbopuffer.NotFoundError:
        return False
    return True


def docs_batch(docs: Iterable[dict],
               last_index_time: datetime,
               batch_size: int = 30) -> Iterator[list[RowParam]]:
    """
    Yield batches of documents for indexing where the prompt_timestamp is greater than the last_index_time.
    """
    def _convert_batch(batch) -> list[RowParam]:
        """Convert a batch of documents to row parameters."""
        converted_batch = []
        for doc in batch:
            doc = doc.copy()
            doc['transcript_embedding_text'] = doc['transcript'][:MAX_TRANSCRIPT_CHARS]
            doc['prompt_timestamp'] = doc['prompt_timestamp'].isoformat()  # Convert datetime to ISO string
            doc['project_path'] = str(doc['project_path']) if doc['project_path'] is not None else None
            converted_batch.append(RowParam(**doc))
        return converted_batch

    filtered_docs = (
        doc for doc in docs
        if doc['prompt_timestamp'] > last_index_time
        and isinstance(doc.get('transcript'), str)
        and doc['transcript'].strip()
    )

    for batch in batched(filtered_docs, batch_size):
        yield _convert_batch(batch)


class TurboPufferIndex:

    def __init__(self, ns_name: str = DEFAULT_TPUF_NAMESPACE):
        self.tpuf = turbopuffer.AsyncTurbopuffer(
            api_key=TURBOPUFFER_API_KEY,
            region="gcp-us-central1"
        )
        self.ns = self.tpuf.namespace(ns_name)

    async def last_index_time(self) -> datetime:
        """Retrieve the newest doc from TurboPuffer."""
        if not await self.ns.exists():
            return datetime.min.replace(tzinfo=timezone.utc)
        result = await self.ns.query(
            rank_by=("prompt_timestamp", "desc"),
            limit=1,
            include_attributes=["prompt_timestamp"],
            consistency={"level": "strong"}
        )
        results = result.rows
        if results:
            ts_string = results[0].prompt_timestamp
            assert isinstance(ts_string, str)
            ts_string = ts_string.replace("Z", "+00:00")
            ts = datetime.fromisoformat(ts_string)
            return ts
        else:
            return datetime.min.replace(tzinfo=timezone.utc)

    def _schema(self) -> dict:
        schema = {
            "transcript": {
                "type": "string",
                "full_text_search": {
                    "tokenizer": "word_v4",
                    "language": "english",
                    "stemming": True,
                    "remove_stopwords": False,
                    "case_sensitive": False
                },
                "filterable": False
            },
            "transcript_embedding_text": {
                "type": "string",
                "embed": {"model": VOYAGE_MODEL},
                "filterable": False
            },
            "session_id": {
                "type": "string",
                "filterable": True
            },
            "project_path": {
                "type": "string",
                "filterable": True
            },
            "prompt_id": {
                "type": "string",
                "filterable": True
            },
            "prompt_timestamp": {
                "type": "datetime",
                "filterable": True
            },
            "is_system_prompt": {
                "type": "bool",
                "filterable": True
            }
        }
        return schema

    async def _write_batch(self, batch: list[RowParam]) -> None:
        """Write a batch, retrying transient embedding/service failures."""
        for attempt in range(INDEX_MAX_RETRIES + 1):
            try:
                await self.ns.write(
                    upsert_rows=batch,
                    distance_metric="cosine_distance",
                    schema=self._schema()
                )
                return
            except (turbopuffer.RateLimitError, turbopuffer.InternalServerError):
                if attempt == INDEX_MAX_RETRIES:
                    raise
                delay = INDEX_RETRY_BASE_SECONDS * (2 ** attempt)
                logger.warning(
                    "Transient TurboPuffer write failure; retrying in %.1f seconds (attempt %s/%s).",
                    delay,
                    attempt + 1,
                    INDEX_MAX_RETRIES,
                )
                await asyncio.sleep(delay)

    async def index_docs(self,
                         docs: Iterable[dict],
                         last_index_time: datetime | None = None,
                         batch_size=30):
        """
        Index the documents into TurboPuffer.
        """
        if last_index_time is None:
            last_index_time = await self.last_index_time()
        for batch in docs_batch(docs,
                                batch_size=batch_size,
                                last_index_time=last_index_time):
            print(f"Indexing batch of {len(batch)} docs into TurboPuffer...")
            await self._write_batch(batch)

        result = await self.ns.query(
            rank_by=("id", "asc"),
            limit=1,
        )
        count = result.performance.approx_namespace_size
        logger.info("Indexed %s documents into TurboPuffer.", count)

    async def fetch(self, doc_id: str) -> Row | None:
        if self.ns is None:
            raise RuntimeError("Namespace is not initialized. Please index documents first.")

        result = await self.ns.query(
            filters=("id", "Eq", doc_id),
            rank_by=("id", "asc"),
            limit=1,
            include_attributes=True,
        )

        return result.rows[0] if result.rows else None

    def _filters(self, system_only: bool, project_path: str | None) -> tuple | None:
        filters = []
        if system_only:
            filters.append(("is_system_prompt", "Eq", True))
        if project_path is not None:
            filters.append(("project_path", "Eq", project_path))
        filter_tuple = ("And", tuple(filters)) if filters else None
        return filter_tuple

    def _limit(self, project_path: str | None, top_k: int) -> LimitParam:
        limit: LimitParam = {
            "total": 50 if project_path is None else top_k,
            "per": {
                "attributes": ["project_path"],
                "limit": top_k
            }
        }
        return limit

    async def search(self,
                     query: str,
                     system_only: bool = False,
                     project_path: str | None = None,
                     top_k=5) -> Result:
        """Search history with BM25 and Voyage embeddings fused by RRF."""
        logger.info(
            "Querying TurboPuffer with BM25 and %s for top %s results: %s",
            VOYAGE_MODEL,
            top_k,
            query,
        )
        if self.ns is None:
            raise RuntimeError("Namespace is not initialized. Please index documents first.")
        filters = self._filters(system_only, project_path)
        result = await self.ns.multi_query(
            queries=[
                {
                    "rank_by": ("transcript", "BM25", query),
                    "limit": self._limit(project_path, top_k),
                    "filters": filters if filters is not None else turbopuffer.omit,
                    "include_attributes": ["id", "transcript", "session_id", "prompt_id", "prompt_timestamp", "project_path"],
                },
                {
                    "rank_by": ("transcript_embedding_text", "ANN", ("Embed", query)),
                    "limit": self._limit(project_path, top_k),
                    "filters": filters if filters is not None else turbopuffer.omit,
                    "include_attributes": ["id", "transcript", "session_id", "prompt_id", "prompt_timestamp", "project_path"],
                },
            ],
            rerank_by=("RRF",),
        )
        return result.results[0]
