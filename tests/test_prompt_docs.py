from pathlib import Path
from datetime import datetime, timedelta

from know_history.parse_telemetry import prompt_docs


fixture_path = Path(__file__).parent / "fixtures"


def test_prompt_docs_separates_system_prompts_from_normal_prompts():
    docs = prompt_docs(fixture_path)
    docs = list(docs)

    system_docs = [doc for doc in docs if doc["prompt_id"].endswith("_system_prompt")]
    normal_docs = [doc for doc in docs if not doc["prompt_id"].endswith("_system_prompt")]

    assert system_docs
    assert normal_docs
    assert all(doc["id"] == f'{doc["session_id"]}_system_prompt' for doc in system_docs)
    assert any(doc["transcript"] for doc in system_docs)
    assert all("User:\n" not in (doc["transcript"] or "") for doc in system_docs)
    assert all("Assistant:\n" not in (doc["transcript"] or "") for doc in system_docs)
    assert all("_system_prompt" not in doc["prompt_id"] for doc in normal_docs)


def test_prompt_docs_loads_prompt_metadata_and_event_text():
    docs = prompt_docs(fixture_path)
    docs = list(docs)

    prompt_doc = next(
        doc
        for doc in docs
        if doc["prompt_id"] == "msg_0a62e36af001541mlNkgAAcTzO"
    )

    assert prompt_doc["session_id"] == "ses_f59d1c961ffe3epkVD17Dploo4"
    assert prompt_doc["transcript"]
    assert "User:\n" in prompt_doc["transcript"]
    assert "Assistant:\n" in prompt_doc["transcript"]
    assert "Tool call:\n" in prompt_doc["transcript"]
    assert "Tool result:\n" in prompt_doc["transcript"]
    assert "plugin/telemetry.js" in prompt_doc["transcript"]


def test_prompt_selects_for_timestamp():
    timestamp = "2026-09-17T00:00:00Z"
    ts = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
    docs = prompt_docs(fixture_path, last_index_time=ts)

    one_day_before = ts - timedelta(days=1)

    for doc in docs:
        doc_ts = doc['prompt_timestamp']
        assert doc_ts >= one_day_before


def test_prompt_with_timestamp_smaller_than_without():
    timestamp = "2026-09-17T00:00:00Z"
    ts = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
    docs = prompt_docs(fixture_path, last_index_time=ts)
    docs = list(docs)
    docs_no_ts = prompt_docs(fixture_path)
    docs_no_ts = list(docs_no_ts)

    assert len(docs) < len(docs_no_ts)


def test_prompt_docs_ignores_nonconforming_fixture_files():
    docs = list(prompt_docs(fixture_path))
    transcripts = "\n".join(doc["transcript"] for doc in docs)

    assert "CANARY_BAD_FILENAME" not in transcripts
    assert "CANARY_IGNORED_TEXT_FILE" not in transcripts
