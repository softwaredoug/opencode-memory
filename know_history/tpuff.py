from sentence_transformers import SentenceTransformer
import turbopuffer
from turbopuffer.types.row_param import RowParam
from turbopuffer.types import NamespaceQueryResponse
import logging
import os
from typing import Iterator
from itertools import batched
from datetime import datetime, timezone


TPUF_API_KEY = os.getenv("TPUF_API_KEY")
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
            converted_batch.append(RowParam(**doc))
        return converted_batch

    filtered_docs = (doc for doc in docs if doc['prompt_timestamp'] > last_index_time)

    for batch in batched(filtered_docs, batch_size):
        all_texts = [doc['transcript'] for doc in batch]
        embeddings = model.encode(all_texts, convert_to_tensor=True).tolist()
        yield _convert_batch(batch, embeddings)


class TurboPufferIndex:

    def __init__(self):
        self.tpuf = turbopuffer.Turbopuffer(
            api_key=TPUF_API_KEY,
            region="gcp-us-central1"
        )
        ns_name = "opencodetrace"
        self.ns = self.tpuf.namespace(ns_name)
        assert self.ns is not None

    def last_index_time(self) -> datetime:
        """Retrieve the newest doc from TurboPuffer."""
        result = self.ns.query(
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

    def index_docs(self,
                   docs: Iterator[dict],
                   last_index_time: datetime | None = None,
                   batch_size=100):
        """
        Index the documents into TurboPuffer.
        """
        if last_index_time is None:
            last_index_time = self.last_index_time()
        for batch in docs_batch(docs, batch_size=batch_size,
                                last_index_time=last_index_time):
            self.ns.write(
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

        result = self.ns.query(
            rank_by=("id", "asc"),
            limit=1,
        )
        count = result.performance.approx_namespace_size
        logger.info("Indexed %s documents into TurboPuffer.", count)

    def context_mentioning_terms(self, phrase: str, top_k=5) -> NamespaceQueryResponse:
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
        ns_results = self.ns.query(
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
            top_k=top_k,
            include_attributes=["transcript", "session_id", "prompt_id", "prompt_timestamp", "project_path"],
        )
        return ns_results
