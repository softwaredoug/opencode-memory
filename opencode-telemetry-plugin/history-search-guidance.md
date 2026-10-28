## Searching prior OpenCode history

Use the `search_opencode_history` CLI when prior conversations, decisions, or
solutions could help with the current task. The history daemon must be running
and the CLI must be available on `PATH`.

Search for relevant history with a concise query:

```sh
search_opencode_history --project-path "$PWD" "query about the current task"
```

Useful options:

- `--project-path PATH` limits results to a project. Omit it to search across
  projects.
- `--top-k N` changes the maximum number of results (default: 5).
- `--session-metadata` searches project metadata such as system prompts and
  `AGENTS.md` content.
- `--session-id ID --prompt-ordinal N` selects one prompt transcript in a
  session; the query is ignored for this exact selection.
- `--inspect DOC_ID` fetches the complete, untruncated transcript for a result.
  Use it by itself, without search filters.

The CLI returns JSON. Use `jq` to filter results or `grep` to search transcript
text when useful.
