from pathlib import Path

from know_history.parse_telemetry import prompt_docs


FIXTURE = Path(__file__).parent / "fixtures" / "telemetry.jsonl"


def test_prompt_docs_separates_system_prompts_from_normal_prompts():
    docs = list(prompt_docs(FIXTURE))

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
    docs = list(prompt_docs(FIXTURE))
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
