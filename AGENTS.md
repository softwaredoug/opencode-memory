# Repository

This repo organizes OpenCode telemetry into transcripts that can be searched.

Roughly sketched out

(a) An OpenCode plugin for logging raw telemetry (for OpenCode 1.18)
(b) Python code to turn it into documents to be searched
(c) A daemon service that indexes / searches
(d) CLIs that interact with the daemon to search, etc on behalf of agents

The javascript OpenCoded plugin should be extremely lightweight with minimal complexity. It should log user mesasge ID, sessionID, and as much raw data to help us group memories tied to a user prompt and 

The meat of the project is the Python code that indexes specific memories / artifacts, and then surfaces them in a CLI.

## Development practices

This is mostly a python repo, using uv for packaage management

### Testing

We test at three levels

* unit tests - tests of specific individual components
* e2e tests - tests up to the API boundary, with the exception of Turbopuffer stays within the boundary

## Turbopuffer

Be sure when asked about Turbopuffer (TPuf) to search the latest documentation, as the project evolves fast, and your knowledge may be out of date.

### Tests
- TPuf tests should index actual data into Turbopuffer and should not mock the backend
- You should then confirm the expected behavior

## Daemon service

The Daemon service runs a FastAPI service 

### Tests

- It should be tested e2e via FastAPI's TestClient
- It should use pytest fixtures that write to temp files for telemetry

## Schema structure

The structure of the schema follows a hierarical strategy, allowing the caller to select historical traces at different levels of granularity

### What type of document do we index

We index individual *transcripts* as the primary document.

A transcript is a single user message, the agents responses, and the intermediate tool calls / their outputs. Transcripts truncate tool call / tool output when they exceed a certain size. We also index a transcript with system prompt information at the start of every session.

The attributes on the document allow filtering depending on the level of granularity desired:

- project_path - the path to the project being worked on
- session_id - an agent session (ie one ongoing context window being worked on / chatted with, usually to complete a specific task)
- prompt_id - the id of the individual prompt / transcript
- id - the doc_id, a unique identifier for this document in turbopuffer
- transcript - the transcript (though with certain parts truncated / summarized). This is what's embedded or indexed.
- transcript_full - the transcript, not truncated
- is_system_prompt - whether this indexed prompted is a system prompt (then the transcript is the AGENTS.md)


### How the schema is used to explore history

The search tool exposes many of the attributes for filtering the result set, ie

`project_path`, `session_id`, `is_system_prompt`, etc

In addition, to get the full, unadulterated transcript for a prompt, the user can call

--inspect <id>

Additionally a query can be passed unless the selection chooses a single prompt. In which case the query is ignored.


### Users should use `jq` and `grep` to further search, if available 

The output of the search tool is JSON, so users can use `jq` to further filter the results, or `grep` to search for specific strings in the transcript.
