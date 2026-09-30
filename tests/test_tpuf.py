import opencode_memory.tpuf as tpuf_module
from opencode_memory.tpuf import TurboPufferIndex, docs_batch
import pytest_asyncio
import pytest
from collections.abc import AsyncIterator
from datetime import datetime, timezone, timedelta
from typing import Any


@pytest_asyncio.fixture
async def tpuf_index() -> AsyncIterator[TurboPufferIndex]:
    test_ns_name = "test_opencode_history"
    tpuf = TurboPufferIndex(ns_name=test_ns_name)
    try:
        yield tpuf
    finally:
        try:
            await tpuf.ns.delete_all()
        finally:
            await tpuf.tpuf.close()


@pytest.fixture
def tpuf_docs() -> list[dict]:
    return [
        {
            "session_id": "session_alpha",
            "prompt_id": "prompt_alpha_system",
            "id": "session_alpha_prompt_alpha_system",
            "prompt_timestamp": datetime(2024, 1, 1, 9, 0, tzinfo=timezone.utc),
            "project_path": "/projects/alpha",
            "transcript": "System instructions for the alpha project.",
            "is_system_prompt": True,
        },
        {
            "session_id": "session_alpha",
            "prompt_id": "prompt_alpha_001",
            "id": "session_alpha_prompt_alpha_001",
            "prompt_timestamp": datetime(2024, 1, 1, 9, 1, tzinfo=timezone.utc),
            "project_path": "/projects/alpha",
            "transcript": "User: Add input validation to the signup form.",
            "is_system_prompt": False,
        },
        {
            "session_id": "session_alpha",
            "prompt_id": "prompt_alpha_002",
            "id": "session_alpha_prompt_alpha_002",
            "prompt_timestamp": datetime(2024, 1, 1, 9, 5, tzinfo=timezone.utc),
            "project_path": "/projects/alpha",
            "transcript": "User: The validation rejects valid international phone numbers.",
            "is_system_prompt": False,
        },
        {
            "session_id": "session_beta",
            "prompt_id": "prompt_beta_system",
            "id": "session_beta_prompt_beta_system",
            "prompt_timestamp": datetime(2024, 1, 2, 10, 0, tzinfo=timezone.utc),
            "project_path": "/projects/beta",
            "transcript": "System instructions for the beta project.",
            "is_system_prompt": True,
        },
        {
            "session_id": "session_beta",
            "prompt_id": "prompt_beta_001",
            "id": "session_beta_prompt_beta_001",
            "prompt_timestamp": datetime(2024, 1, 2, 10, 2, tzinfo=timezone.utc),
            "project_path": "/projects/beta",
            "transcript": "User: Find why the nightly database backup is slow.",
            "is_system_prompt": False,
        },
        {
            "session_id": "session_beta",
            "prompt_id": "prompt_beta_002",
            "id": "session_beta_prompt_beta_002",
            "prompt_timestamp": datetime(2024, 1, 2, 10, 8, tzinfo=timezone.utc),
            "project_path": "/projects/beta",
            "transcript": "Tool result: The backup is waiting on an unindexed audit query.",
            "is_system_prompt": False,
        },
        {
            "session_id": "session_gamma",
            "prompt_id": "prompt_gamma_001",
            "id": "session_gamma_prompt_gamma_001",
            "prompt_timestamp": datetime(2024, 1, 3, 11, 0, tzinfo=timezone.utc),
            "project_path": "/projects/gamma",
            "transcript": "User: Refactor the cache client to support a configurable TTL.",
            "is_system_prompt": False,
        },
        {
            "session_id": "session_gamma",
            "prompt_id": "prompt_gamma_002",
            "id": "session_gamma_prompt_gamma_002",
            "prompt_timestamp": datetime(2024, 1, 3, 11, 7, tzinfo=timezone.utc),
            "project_path": None,
            "transcript": "Assistant: Added TTL configuration and covered expiration behavior with tests.",
            "is_system_prompt": False,
        },
    ]


@pytest.mark.asyncio
async def test_indexing(tpuf_index: TurboPufferIndex, tpuf_docs: list[dict]):
    docs = tpuf_docs
    for doc in docs:
        doc["transcript_full"] = f"Full details: {doc['transcript']}"
    await tpuf_index.index_docs(docs)
    # Retrieve the doc

    for doc in docs:
        row = await tpuf_index.fetch(doc['id'])
        assert row is not None
        assert row['session_id'] == doc['session_id']
        assert row['transcript_full'] == f"Full details: {doc['transcript']}"
        assert "transcript" not in row


@pytest.mark.asyncio
async def test_indexing_after_ts(tpuf_index: TurboPufferIndex, tpuf_docs: list[dict]):
    docs = tpuf_docs
    last_index_time = datetime(2024, 1, 3, 9, 0, tzinfo=timezone.utc)
    expected_valid_index_time = last_index_time - timedelta(days=1)
    indexed_ids = {
        doc["id"] for doc in docs if doc["prompt_timestamp"] > last_index_time
    }

    await tpuf_index.index_docs(docs, last_index_time=last_index_time)
    # Retrieve the doc

    for doc in docs:
        if doc["id"] not in indexed_ids:
            continue
        row = await tpuf_index.fetch(doc['id'])
        assert row is not None
        prompt_timestamp_value = row["prompt_timestamp"]
        assert isinstance(prompt_timestamp_value, str)
        prompt_timestamp = datetime.fromisoformat(prompt_timestamp_value.replace("Z", "+00:00"))
        assert prompt_timestamp >= expected_valid_index_time


def test_docs_batch_skips_empty_transcripts(tpuf_docs: list[dict]):
    docs = [
        {
            **tpuf_docs[0],
            "transcript": "   ",
        },
        tpuf_docs[1].copy(),
    ]

    batches = list(docs_batch(docs, datetime.min.replace(tzinfo=timezone.utc)))

    assert [[row["id"] for row in batch] for batch in batches] == [[tpuf_docs[1]["id"]]]


def test_docs_batch_preserves_transcript_fields(tpuf_docs: list[dict]):
    doc = tpuf_docs[1].copy()
    doc["transcript_full"] = "full transcript"

    batch = next(docs_batch([doc], datetime.min.replace(tzinfo=timezone.utc)))

    transcript = batch[0]["transcript"]
    assert transcript == doc["transcript"]
    assert batch[0]["transcript_full"] == doc["transcript_full"]


def test_schema_embeds_transcript_but_not_full_transcript():
    index = TurboPufferIndex.__new__(TurboPufferIndex)
    schema = index._schema()

    assert schema["transcript"]["embed"]["model"] == "voyage/voyage-4-large"
    assert "full_text_search" in schema["transcript"]
    assert "embed" not in schema["transcript_full"]
    assert "full_text_search" not in schema["transcript_full"]
    assert schema["prompt_ordinal"] == {"type": "int", "filterable": True}


def test_filters_support_session_and_prompt_ordinal():
    index = TurboPufferIndex.__new__(TurboPufferIndex)

    filters = index._filters(
        system_only=False,
        project_path=None,
        session_id="session_alpha",
        prompt_ordinal=3,
    )

    assert filters == (
        "And",
        (("session_id", "Eq", "session_alpha"), ("prompt_ordinal", "Eq", 3)),
    )


def test_system_metadata_limit_is_global_and_diversified():
    index = TurboPufferIndex.__new__(TurboPufferIndex)

    assert index._limit(None, 5, system_only=True) == {
        "total": 5,
        "per": {"attributes": ["project_path"], "limit": 1},
    }


def test_non_metadata_limit_remains_per_project():
    index = TurboPufferIndex.__new__(TurboPufferIndex)

    assert index._limit(None, 5) == {
        "total": 50,
        "per": {"attributes": ["project_path"], "limit": 5},
    }


@pytest.mark.asyncio
async def test_write_batch_retries_transient_failures(monkeypatch):
    class TransientFailure(Exception):
        pass

    class Namespace:
        attempts = 0

        async def write(self, **_kwargs):
            self.attempts += 1
            if self.attempts < 3:
                raise TransientFailure()

    delays = []

    async def sleep(delay):
        delays.append(delay)

    monkeypatch.setattr(tpuf_module.turbopuffer, "InternalServerError", TransientFailure)
    monkeypatch.setattr(tpuf_module.asyncio, "sleep", sleep)

    index: Any = TurboPufferIndex.__new__(TurboPufferIndex)
    index.ns = Namespace()
    await index._write_batch([])

    assert index.ns.attempts == 3
    assert delays == [1.0, 2.0]
