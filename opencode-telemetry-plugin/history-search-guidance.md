## Searching prior OpenCode history

Use the `search_opencode_history` CLI when prior conversations, decisions, or
solutions could help with the current task. The history daemon must be running
and the CLI must be available on `PATH`.

For prompts longer than 100 characters by default, the plugin may request
history breadcrumbs. Any results are added directly to the system context in a
`<retrieved_episodes>` block. Use relevant details or document IDs from those
breadcrumbs to explore further with a focused CLI search or `--inspect DOC_ID`.
The threshold can be changed with `OPENCODE_RAG_SEARCH_MIN_PROMPT_LENGTH`.

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
