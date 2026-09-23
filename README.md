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
TPUF_API_KEY=<your_turbopuffer_api_key> opencode_history
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
./scripts/install.sh
```

## Extra info

### Ignore directories

Ignore directories by placing a file `opencode-telemetry-ignore` and your interactions won't be logged.
