from sentence_transformers import SentenceTransformer
import turbopuffer
from turbopuffer.types.row_param import RowParam
from tubropuffer.types import NamespaceQueryResponse
import os
from typing import Iterator
from itertools import batched

from .parse_telemetry import prompt_docs


TPUF_API_KEY = os.getenv("TPUF_API_KEY")

model = SentenceTransformer('all-MiniLM-L6-v2')


def ns_exists(tpuf, ns_name, expected_count=1):
    ns = tpuf.namespace(ns_name)
    try:
        metadata = ns.metadata()
        if metadata.approx_row_count < expected_count:
            print(f"Namespace {ns_name} exists but has fewer rows ({metadata.approx_row_count}) than expected ({expected_count}).")
            return False
    except turbopuffer.NotFoundError:
        return False
    return True


def docs_batch(docs: Iterator[dict], batch_size=100) -> Iterator[list[RowParam]]:
    """
    Yield batches of documents for indexing.
    """
    def _convert_batch(batch, embeddings) -> list[RowParam]:
        """Add a vector param, then rebuild the batch of dicts to one of rowparams."""
        converted_batch = []
        for doc, embedding in zip(batch, embeddings):
            doc['vector'] = embedding
            doc['prompt_timestamp'] = doc['prompt_timestamp'].isoformat()  # Convert datetime to ISO string
            converted_batch.append(RowParam(**doc))
        return converted_batch

    for batch in batched(docs, batch_size):
        all_texts = [doc['transcript'] for doc in batch]
        embeddings = model.encode(all_texts, convert_to_tensor=True).tolist()
        yield _convert_batch(batch, embeddings)


class TurboPufferIndex:

    def __init__(self):
        self.tpuf = turbopuffer.Turbopuffer(
            api_key=TPUF_API_KEY,
            region="gcp-us-central1"
        )
        self.ns = None

    def index_docs(self, docs: Iterator[dict], force=False, batch_size=100):
        """
        Index the documents into TurboPuffer.
        """
        ns_name = "opencodetrace"
        self.ns = self.tpuf.namespace(ns_name)
        if not ns_exists(self.tpuf, ns_name) or force:
            for batch in docs_batch(docs, batch_size=batch_size):
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
                        "prompt_id": {
                            "type": "string",
                            "filterable": True
                        },
                        "prompt_timestamp": {
                            "type": "datetime",
                            "filterable": True
                        }
                    }
                )

            result = self.ns.query(
                rank_by=("id", "asc"),
                limit=1,
            )
            count = result.performance.approx_namespace_size
            print(f"Indexed {count} documents into TurboPuffer.")

    def context_mentioning_terms(self, phrase: list[str], top_k=5) -> NamespaceQueryResponse:
        """
        Query TurboPuffer for context mentioning the given phrase
        """
        print(f"Querying TurboPuffer for top {top_k} results mentioning terms: {phrase}")
        if self.ns is None:
            raise RuntimeError("Namespace is not initialized. Please index documents first.")
        ns_results = self.ns.query(
            rank_by=(
                "Sum",
                (
                    ("transcript", "BM25", phrase),
                )
            ),
            top_k=top_k,
            include_attributes=["content"],
            filters=(
                "Or", (
                    ("transcript", "ContainsTokenSequence", phrase),
                ),
            )
        )
        return ns_results


def index_docs(force=False, batch_size=100):
    """
    Index the prompt documents into TurboPuffer.
    """
    indexer = TurboPufferIndex()
    indexer.index_docs(docs=prompt_docs(), force=force, batch_size=batch_size)
