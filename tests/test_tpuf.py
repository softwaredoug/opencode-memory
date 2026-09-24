from opencode_memory.tpuf import TurboPufferIndex
import pytest_asyncio
import pytest
from collections.abc import AsyncIterator
from datetime import datetime, timezone


@pytest_asyncio.fixture
async def tpuf_index() -> AsyncIterator[TurboPufferIndex]:
    test_ns_name = "test_opencode_history"
    tpuf = TurboPufferIndex(ns_name=test_ns_name)
    yield tpuf
    await tpuf.ns.delete_all()


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
    await tpuf_index.index_docs(docs)
    # Retrieve the doc

    for doc in docs:
        row = await tpuf_index.fetch(doc['id'])
        assert row is not None
        assert row['session_id'] == doc['session_id']
