import asyncio
import json
from uuid import uuid4

from fastapi.testclient import TestClient
import pytest
import turbopuffer

import opencode_memory.daemon as daemon
from opencode_memory.tpuf import TurboPufferIndex


@pytest.fixture
def telemetry_path(tmp_path):
    telemetry_path = tmp_path / "telemetry"
    telemetry_path.mkdir()
    telemetry_file = telemetry_path / "2026-09-19-telemetry.jsonl"
    events = [
        {
            "event_type": "system_prompt",
            "timestamp": "2026-09-19T10:00:00.000Z",
            "session_id": "session_test",
            "project_metadata": {"path": "/tmp/test-project", "agents_md": "Test project"},
            "payload": {
                "input": {"sessionID": "session_test"},
                "output": {"message": {"id": "system"}, "parts": [{"text": "System"}]},
            },
        },
        {
            "event_type": "prompt",
            "timestamp": "2026-09-19T10:00:01.000Z",
            "session_id": "session_test",
            "payload": {
                "input": {"sessionID": "session_test"},
                "output": {
                    "message": {"id": "prompt_test"},
                    "parts": [{"text": "Find the distinctive fixture phrase"}],
                },
            },
        },
    ]
    telemetry_file.write_text("\n".join(json.dumps(event) for event in events) + "\n")
    return telemetry_path


def test_index_then_search_fixture_telemetry(telemetry_path, monkeypatch):
    namespace = f"test_daemon_{uuid4().hex}"
    indexes = []

    async def no_reindex_loop():
        await asyncio.Event().wait()

    monkeypatch.setenv(daemon.TELEMETRY_PATH_ENV, str(telemetry_path))

    def make_index():
        index = TurboPufferIndex(ns_name=namespace)
        indexes.append(index)
        return index

    monkeypatch.setattr(
        daemon,
        "TurboPufferIndex",
        make_index,
    )
    monkeypatch.setattr(daemon, "reindex_loop", no_reindex_loop)

    try:
        with TestClient(daemon.app) as client:
            try:
                index_response = client.post("/index", json={})
                search_response = client.post(
                    "/search",
                    json={"query": "distinctive fixture phrase", "top_k": 5},
                )

                assert index_response.status_code == 200
                assert index_response.json() == {"ok": True}
                assert search_response.status_code == 200
                result = search_response.json()
                assert result["result_count"] >= 1
                assert any(
                    item["id"] == "session_test_prompt_test"
                    and item["session_id"] == "session_test"
                    and "distinctive fixture phrase" in item["transcript"]
                    for item in result["results"]
                )
                session_search = client.post(
                    "/search",
                    json={
                        "session_id": "session_test",
                        "prompt_ordinal": 0,
                    },
                )
                assert session_search.status_code == 200
                assert session_search.json()["result_count"] == 1
                assert session_search.json()["query"] == ""

                invalid_search = client.post(
                    "/search",
                    json={"query": "anything", "prompt_ordinal": 0},
                )
                assert invalid_search.status_code == 422
                inspect_response = client.get("/inspect/session_test_prompt_test")
                assert inspect_response.status_code == 200
                inspected = inspect_response.json()
                assert inspected["id"] == "session_test_prompt_test"
                assert inspected["transcript"] == "User: Find the distinctive fixture phrase"
                assert "transcript_full" not in inspected
            finally:
                async def close_indexes():
                    for index in indexes:
                        await index.tpuf.close()

                portal = client.portal
                assert portal is not None
                portal.call(close_indexes)
    finally:
        async def delete_namespace():
            cleanup_index = TurboPufferIndex(ns_name=namespace)
            try:
                await cleanup_index.ns.delete_all()
            except turbopuffer.NotFoundError:
                pass
            finally:
                await cleanup_index.tpuf.close()

        asyncio.run(delete_namespace())
