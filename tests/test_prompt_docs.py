from pathlib import Path
from datetime import datetime, timedelta
import pytest
from tempfile import TemporaryDirectory
import json

from opencode_memory.parse_telemetry import prompt_docs, truncate


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
    assert prompt_doc["transcript_full"]
    assert "User: " in prompt_doc["transcript"]
    assert "Assistant: " in prompt_doc["transcript"]
    assert "Tool call: " in prompt_doc["transcript"]
    assert "Tool result: " in prompt_doc["transcript"]
    assert prompt_doc["transcript"].startswith("User: OK tell me about this repo\n\n")
    assert "git status --short" in prompt_doc["transcript"]
    assert "... <truncated>" in prompt_doc["transcript"]
    assert "plugin/telemetry.js" in prompt_doc["transcript_full"]


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


@pytest.fixture
def interleaved_telemetry():
    with TemporaryDirectory() as temp_dir:
        temp_dir = Path(temp_dir)
        interleaved = [
            {
                "event_type": "system_prompt",
                "timestamp": "2026-09-19T10:00:00.000Z",
                "session_id": "ses_A",
                "project_metadata": {"path": "/tmp/project-a", "agents_md": "AGENTSMD content A"},
                "payload": {
                    "input": {"sessionID": "ses_A"},
                    "output": {
                        "message": {"id": "msg_A1"},
                        "parts": [{"text": "Prompt A"}],
                    },
                },
            },
            {
                "event_type": "system_prompt",
                "timestamp": "2026-09-19T10:00:00.000Z",
                "session_id": "ses_B",
                "project_metadata": {"path": "/tmp/project-b", "agents_md": "AGENTSMD content B"},
                "payload": {
                    "input": {"sessionID": "ses_B"},
                    "output": {
                        "message": {"id": "msg_B1"},
                        "parts": [{"text": "Prompt B"}],
                    },
                },
            },
            {
                "event_type": "prompt",
                "timestamp": "2026-09-19T10:00:00.000Z",
                "session_id": "ses_A",
                "payload": {
                    "input": {"sessionID": "ses_A"},
                    "output": {
                        "message": {"id": "msg_A1"},
                        "parts": [{"text": "Prompt A"}],
                    },
                },
            },
            {
                "event_type": "prompt",
                "timestamp": "2026-09-19T10:00:01.000Z",
                "session_id": "ses_B",
                "payload": {
                    "input": {"sessionID": "ses_B"},
                    "output": {
                        "message": {"id": "msg_B1"},
                        "parts": [{"text": "Prompt B"}],
                    },
                },
            },
            {
                "event_type": "tool_result",
                "timestamp": "2026-09-19T10:00:02.000Z",
                "session_id": "ses_A",
                "payload": {
                    "input": {"sessionID": "ses_A", "tool": "bash"},
                    "output": {"output": "Result A"},
                },
            },
            {
                "event_type": "tool_result",
                "timestamp": "2026-09-19T10:00:03.000Z",
                "session_id": "ses_B",
                "payload": {
                    "input": {"sessionID": "ses_B", "tool": "bash"},
                    "output": {"output": "Result B"},
                },
            },
        ]
        telemetry_file = temp_dir / "2026-09-19-telemetry.jsonl"
        with telemetry_file.open("w") as f:
            for event in interleaved:
                f.write(json.dumps(event) + "\n")
        yield temp_dir


def test_interleaved_assigns_prompt_id_correctly(interleaved_telemetry):
    docs = list(prompt_docs(interleaved_telemetry))
    assert docs[0]['prompt_id'] == 'ses_A_system_prompt'
    assert docs[1]['prompt_id'] == 'ses_B_system_prompt'


def test_project_path_assigned_correctly(interleaved_telemetry):
    docs = list(prompt_docs(interleaved_telemetry))
    assert docs[0]['project_path'] == Path('/tmp/project-a')
    assert docs[1]['project_path'] == Path('/tmp/project-b')


@pytest.fixture
def conversational_telemetry():
    with TemporaryDirectory() as temp_dir:
        temp_dir = Path(temp_dir)
        events = [
            {
                "event_type": "system_prompt",
                "timestamp": "2026-09-19T10:00:00.000Z",
                "session_id": "ses_conversation",
                "project_metadata": {"path": "/tmp/project", "agents_md": "metadata"},
                "payload": {
                    "input": {"sessionID": "ses_conversation"},
                    "output": {"message": {"id": "system"}, "parts": [{"text": "System"}]},
                },
            },
            {
                "event_type": "prompt",
                "timestamp": "2026-09-19T10:00:01.000Z",
                "session_id": "ses_conversation",
                "payload": {
                    "input": {"sessionID": "ses_conversation"},
                    "output": {
                        "message": {"id": "prompt_one"},
                        "parts": [{"text": "First question"}],
                    },
                },
            },
            {
                "event_type": "assistant_text",
                "timestamp": "2026-09-19T10:00:02.000Z",
                "payload": {
                    "event": {
                        "properties": {
                            "sessionID": "ses_conversation",
                            "part": {"messageID": "assistant_one", "text": "First draft " + "x" * 40},
                        },
                    },
                },
            },
            {
                "event_type": "assistant_text",
                "timestamp": "2026-09-19T10:00:03.000Z",
                "payload": {
                    "event": {
                        "properties": {
                            "sessionID": "ses_conversation",
                            "part": {"messageID": "assistant_one", "text": "Final answer"},
                        },
                    },
                },
            },
            {
                "event_type": "tool_result",
                "timestamp": "2026-09-19T10:00:04.000Z",
                "payload": {
                    "input": {"sessionID": "ses_conversation"},
                    "output": {"output": "Tool output"},
                },
            },
            {
                "event_type": "tool_result",
                "timestamp": "2026-09-19T10:00:04.500Z",
                "payload": {
                    "input": {"sessionID": "ses_conversation"},
                    "output": {"output": "Continued tool output"},
                },
            },
            {
                "event_type": "prompt",
                "timestamp": "2026-09-19T10:00:05.000Z",
                "session_id": "ses_conversation",
                "payload": {
                    "input": {"sessionID": "ses_conversation"},
                    "output": {
                        "message": {"id": "prompt_two"},
                        "parts": [{"text": "Second question"}],
                    },
                },
            },
            {
                "event_type": "assistant_text",
                "timestamp": "2026-09-19T10:00:06.000Z",
                "payload": {
                    "event": {
                        "properties": {
                            "sessionID": "ses_conversation",
                            "part": {"messageID": "assistant_two", "text": "Second answer"},
                        },
                    },
                },
            },
        ]
        telemetry_file = temp_dir / "2026-09-19-telemetry.jsonl"
        with telemetry_file.open("w") as output:
            for event in events:
                output.write(json.dumps(event) + "\n")
        yield temp_dir


def test_conversational_entries_group_prompt_and_assistant_text(conversational_telemetry):
    docs = list(prompt_docs(conversational_telemetry))
    normal_docs = {
        doc["prompt_id"]: doc["transcript"]
        for doc in docs
        if not doc["prompt_id"].endswith("_system_prompt")
    }
    transcripts = {
        doc["prompt_id"]: doc["transcript_full"]
        for doc in docs
        if not doc["prompt_id"].endswith("_system_prompt")
    }

    assert normal_docs["prompt_one"].startswith("User: First question\n\nAssistant: First draft ")
    assert "Assistant: First draft " + "x" * 40 in normal_docs["prompt_one"]
    assert "Assistant: First draft xxxxxxxxxxxxxxxxxxxxxxxxxxxx... <truncated>" not in normal_docs["prompt_one"]
    assert normal_docs["prompt_one"].endswith("Tool result: Tool output")
    assert "Continued tool output" not in normal_docs["prompt_one"]
    assert normal_docs["prompt_two"] == "User: Second question\n\nAssistant: Second answer"
    assert "x" * 40 in transcripts["prompt_one"]
    assert "Continued tool output" in transcripts["prompt_one"]
    assert "... <truncated>" not in transcripts["prompt_one"]


def test_truncate_marks_only_text_over_limit():
    assert truncate("short", max_chars=5) == "short"
    assert truncate("123456", max_chars=5) == "12345... <truncated>"
