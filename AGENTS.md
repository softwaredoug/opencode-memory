# Repository

In this repo are

(a) An OpenCode plugin for logging raw telemetry (for OpenCode 1.18)
(b) A python project to turn it into documents, ingest it into Turbopuffer raw memory
(c) A CLI search functionality to let OpenCode search TPuff and get back useful memories

The javascript OpenCoded plugin should be extremely lightweight with minimal complexity. It should log user mesasge ID, sessionID, and as much raw data to help us group memories tied to a user prompt and 

The meat of the project is the Python code that indexes specific memories / artifacts, and then surfaces them in a CLI.

## Plugin logging

Log to a well known location, JSONL events such as:

```
{"event_type":"prompt","session_id":"ses_1","prompt_id":"msg_1","timestamp":"2026-09-15T14:10:00.123Z","payload":{"text":"Fix the failing test"}}
{"event_type":"tool_call","session_id":"ses_1","prompt_id":"msg_1","call_id":"call_7","timestamp":"2026-09-15T14:10:01.101Z","payload":{"tool":"bash","args":{"command":"pytest"}}}
{"event_type":"tool_result","session_id":"ses_1","prompt_id":"msg_1","call_id":"call_7","timestamp":"2026-09-15T14:10:02.210Z","payload":{"output":"1 failed..."}}
```
