from sentence_transformers import SentenceTransformer
import turbopuffer
from turbopuffer.types.row_param import RowParam
from turbopuffer.types.limit_param import LimitParam
from turbopuffer.types import NamespaceQueryResponse
import logging
import os
from typing import Iterator
from itertools import batched
from datetime import datetime, timezone


TPUF_API_KEY = os.getenv("TPUF_API_KEY")
if TPUF_API_KEY is None:
    raise RuntimeError("TPUF_API_KEY environment variable is not set.")
TPUF_NAMESPACE = os.getenv("TPUF_NAMESPACE", "opencodetrace")
logger = logging.getLogger(__name__)

model = SentenceTransformer('all-MiniLM-L6-v2')


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


def docs_batch(docs: Iterator[dict],
               last_index_time: datetime,
               batch_size: int = 100) -> Iterator[list[RowParam]]:
    """
    Yield batches of documents for indexing where the prompt_timestamp is greater than the last_index_time.
    """
    def _convert_batch(batch, embeddings) -> list[RowParam]:
        """Add a vector param, then rebuild the batch of dicts to one of rowparams."""
        converted_batch = []
        for doc, embedding in zip(batch, embeddings):
            doc['vector'] = embedding
            doc['prompt_timestamp'] = doc['prompt_timestamp'].isoformat()  # Convert datetime to ISO string
            doc['project_path'] = str(doc['project_path']) if doc['project_path'] is not None else None
            converted_batch.append(RowParam(**doc))
        return converted_batch

    filtered_docs = (doc for doc in docs if doc['prompt_timestamp'] > last_index_time)

    for batch in batched(filtered_docs, batch_size):
        all_texts = [doc['transcript'] for doc in batch]
        embeddings = model.encode(all_texts, convert_to_tensor=True).tolist()
        yield _convert_batch(batch, embeddings)


class TurboPufferIndex:

    def __init__(self):
        self.tpuf = turbopuffer.AsyncTurbopuffer(
            api_key=TPUF_API_KEY,
            region="gcp-us-central1"
        )
        ns_name = TPUF_NAMESPACE
        self.ns = self.tpuf.namespace(ns_name)
        assert self.ns is not None

    async def last_index_time(self) -> datetime:
        """Retrieve the newest doc from TurboPuffer."""
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

    async def index_docs(self,
                         docs: Iterator[dict],
                         last_index_time: datetime | None = None,
                         batch_size=100):
        """
        Index the documents into TurboPuffer.
        """
        if last_index_time is None:
            last_index_time = await self.last_index_time()
        for batch in docs_batch(docs, batch_size=batch_size,
                                last_index_time=last_index_time):
            await self.ns.write(
                upsert_rows=batch,
                distance_metric="cosine_distance",
                schema={
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
            )

        result = await self.ns.query(
            rank_by=("id", "asc"),
            limit=1,
        )
        count = result.performance.approx_namespace_size
        logger.info("Indexed %s documents into TurboPuffer.", count)

    async def search(self, phrase: str,
                     system_only: bool = False,
                     project_path: str | None = None,
                     top_k=5) -> NamespaceQueryResponse:
        """
        Query TurboPuffer for context mentioning the given phrase
        """
        logger.info(
            "Querying TurboPuffer for top %s results mentioning terms: %s",
            top_k,
            phrase,
        )
        if self.ns is None:
            raise RuntimeError("Namespace is not initialized. Please index documents first.")
        filters = []
        limit: LimitParam = {
            "total": 50,
            "per": {
                "attributes": ["project_path"],
                "limit": top_k
            }
        }
        if system_only:
            filters.append(("is_system_prompt", "Eq", True))
        if project_path is not None:
            filters.append(("project_path", "Eq", project_path))

        filter_tuple = ("And", tuple(filters)) if filters else None

        ns_results = await self.ns.query(
            rank_by=(
                "Sum",
                (
                    ("transcript", "BM25", phrase),
                    (
                        "Product",
                        10.0,   # boost phrase matches
                        ("transcript", "ContainsTokenSequence", phrase)
                    )
                )
            ),
            limit=limit,
            filters=filter_tuple if filter_tuple is not None else turbopuffer.omit,
            include_attributes=["transcript", "session_id", "prompt_id", "prompt_timestamp", "project_path"],
        )
        return ns_results
