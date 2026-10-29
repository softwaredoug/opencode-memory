# OpenCode Agent Memory w/ Turbopuffer

This repo indexes your OpenCode telemetry as memories into Turbopuffer.

## How it works

Agent memories exist as a hierarchy of information

* Projects: a specific project being worked on in the agent
* Sessions: every chat turn of an OpenCode session
* Prompts: a transcript of a single user message interaction with an agent

In this repo, a single document in Turbopuffer corresponds to a prompt.

The search CLI allows selecting project-path, analyzing just projects, or getting deep into
specific interactions with the agent.

## Running

The daemon acts as a service to search and keep the index up to date.

Then to run the memory daemon, run:

```bash
TURBOPUFFER_API_KEY=<your_turbopuffer_api_key> opencode_history
```

Now tell your agent to use this CLI to search

```
search_opencode_history --project-path "/Users/doug/ws/opencode-plugin" neovim
```

```
search_opencode_history --project-path "/Users/doug/ws/opencode-plugin" neovim
{
  "query": "neovim",
  "result_count": 2,
  "results": [
    {
      "rank": 1,
      "session_id": "ses_f3b983dfbffei7Fo6nz6rrDJ7Q",
      "prompt_id": "msg_0c47738cf001xCM0vF2naHBiwp",
      "prompt_timestamp": "2026-09-21T14:55:42.801000000Z",
      "project_path": "/Users/doug/ws/opencode-plugin",
      "transcript": "User:\nYou can see how neovim in configured in .nvimrc, does that help you diagnose the difference?

Assistant: I’ll inspect the repository and home Neovim configuration for the active Python LSP, Pyright/BasedPyright version, and diagnostic settin
gs, then compare those with the project command.\n\nTool result:\n/Users/doug/ws/opencode-plugin/.nvimrc\n\nTool result:\nNo files found

Tool result:\n<path>/Users/doug/ws/opencode-plugin/.nvimrc</path>\n<type>file</type>\n<content>\n1: \" Run Python linting and type c
hecking through the uv project environment.\n2: let g:ale_linters = {'python': ['flake8', 'pyright']}\n3: let g:ale_python_flake8_auto_u
```

## Installation

Installs opencode plugin, a daemon, and a search CLI

```bash
make install
```

The plugin appends the editable guidance in
`~/.config/opencode/plugins/history-search-guidance.md` to each system prompt.
Edit that installed file to customize the instructions, then restart OpenCode
for the changes to take effect. If you use a custom OpenCode config directory,
the file is installed under `$OPENCODE_CONFIG_DIR/plugins/` instead.

## Experimental RAG retrieval

For user prompts longer than 100 characters by default, the plugin can request
prior episodes from the daemon's `POST /rag-search` endpoint. It sends only
`{"query": "<user prompt>"}` over the daemon's Unix socket and uses a
TurboPuffer BM25 search over transcript text. The active variant is
`bm25-v1`, selected by `ACTIVE_RAG_VARIANT` in `opencode_memory/daemon.py`;
`voyage-ann-diverse-v1` remains available as an alternative. Socket clients may
include an optional `retrieval_version` in the request JSON to select either
variant; if omitted, the daemon uses the active variant.
The response contains `{"breadcrumbs": [...]}`, with no more than two results
per project and one per session. The plugin adds non-empty breadcrumbs to the
system context. Responses include a per-response `retrieval_id` and a stable
strategy `retrieval_version` matching the active variant. The plugin logs
`rag_retrieval` and `history_cli_call` telemetry events, associating history
CLI calls with the latest RAG response in that session and recording whether
project/session filters match its results. CLI events represent tool-call
attempts and are stored as raw telemetry, not appended to indexed transcripts.
Search is enabled by default; set
`OPENCODE_RAG_SEARCH_ENABLED=false` in the environment used to start OpenCode
to disable it. Set `OPENCODE_RAG_SEARCH_MIN_PROMPT_LENGTH` to change the
character threshold. Retrieval errors are ignored so prompts continue
normally.

## Testing

Run the Python and OpenCode plugin test suites with:

```bash
make test
```

## Extra info

### Ignore directories

Ignore directories by placing a file `opencode-telemetry-ignore` and your interactions won't be logged.
