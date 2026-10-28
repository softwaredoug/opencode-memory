import assert from "node:assert/strict"
import { mkdtemp, readFile, rm, writeFile } from "node:fs/promises"
import os from "node:os"
import path from "node:path"
import test from "node:test"

import { TracePlugin } from "../telemetry.js"

function mockClient(toast = async () => {}) {
  return {
    tui: {
      showToast: toast,
    },
  }
}

async function capturePluginEvents(options = {}) {
  const events = []
  const plugin = await TracePlugin({
    ...options,
    writeEvent: async (eventType, data) => {
      events.push({ eventType, data })
    },
  })
  return { events, plugin }
}

async function withEnvironment(values, callback) {
  const previous = new Map()
  for (const [name, value] of Object.entries(values)) {
    previous.set(name, process.env[name])
    if (value === null) delete process.env[name]
    else process.env[name] = value
  }

  try {
    return await callback()
  } finally {
    for (const [name, value] of previous) {
      if (value === undefined) delete process.env[name]
      else process.env[name] = value
    }
  }
}

test("ignore marker disables telemetry hooks", async () => {
  const directory = await mkdtemp(path.join(os.tmpdir(), "opencode-telemetry-"))

  try {
    await writeFile(path.join(directory, ".opencode-telemetry-ignore"), "\n")
    assert.deepEqual(await TracePlugin({ directory, client: mockClient() }), {})
  } finally {
    await rm(directory, { recursive: true, force: true })
  }
})

test("ignore marker emits a startup toast", async () => {
  const directory = await mkdtemp(path.join(os.tmpdir(), "opencode-telemetry-"))
  let toastCalled = false
  let resolveToast
  const toastShown = new Promise((resolve) => { resolveToast = resolve })

  try {
    await writeFile(path.join(directory, ".opencode-telemetry-ignore"), "\n")
    await TracePlugin({
      directory,
      client: mockClient(async () => {
        toastCalled = true
        resolveToast()
      }),
    })
    await toastShown

    assert.ok(toastCalled)
  } finally {
    await rm(directory, { recursive: true, force: true })
  }
})

test("ignore marker does not write anywhere", async () => {
  const directory = await mkdtemp(path.join(os.tmpdir(), "opencode-telemetry-"))
  let calls = 0

  try {
    const plugin = await TracePlugin({
      directory,
      client: mockClient(),
      writeEvent: async () => { calls++; },
    })
    await writeFile(path.join(directory, ".opencode-telemetry-ignore"), "\n")

    const functionsToCheck = ["chat.message", "experimental.chat.system.transform", "tool.execute.before",
                              "tool.execute.after"]
    for (const fn of functionsToCheck) {
      assert.ok(plugin[fn])
      await plugin[fn]({}, {})
    }
    assert.equal(calls, 0)
  } finally {
    await rm(directory, { recursive: true, force: true })
  }
})

test("calls all with no ignore file", async () => {
  const directory = await mkdtemp(path.join(os.tmpdir(), "opencode-telemetry-"))
  let calls = 0

  try {
    const plugin = await TracePlugin({ directory, writeEvent: async () => { calls++; } })

    const functionsToCheck = ["chat.message", "experimental.chat.system.transform", "tool.execute.before",
                              "tool.execute.after"]
    for (const fn of functionsToCheck) {
      assert.ok(plugin[fn])
      await plugin[fn]({}, {})
    }
    assert.equal(calls, 4)
  } finally {
    await rm(directory, { recursive: true, force: true })
  }
})

test("RAG search can be disabled with its feature flag", async () => {
  await withEnvironment({ OPENCODE_RAG_SEARCH_ENABLED: "false" }, async () => {
    let calls = 0
    const plugin = await TracePlugin({
      writeEvent: async () => {},
      ragSearch: async () => { calls++; return { results: [] } },
    })

    await plugin["chat.message"](
      { sessionID: "session-rag-disabled" },
      { message: { id: "prompt-rag-disabled" }, parts: [{ type: "text", text: "prompt" }] },
    )

    assert.equal(calls, 0)
  })
})

test("RAG search defaults on for prompts longer than 100 characters", async () => {
  await withEnvironment({
    OPENCODE_RAG_SEARCH_ENABLED: null,
    OPENCODE_RAG_SEARCH_MIN_PROMPT_LENGTH: null,
  }, async () => {
    const queries = []
    const plugin = await TracePlugin({
      writeEvent: async () => {},
      ragSearch: async (query) => { queries.push(query); return { results: [] } },
    })

    await plugin["chat.message"](
      { sessionID: "session-rag-100" },
      { message: { id: "prompt-rag-100" }, parts: [{ type: "text", text: "x".repeat(100) }] },
    )
    assert.deepEqual(queries, [])

    const longPrompt = "x".repeat(101)
    await plugin["chat.message"](
      { sessionID: "session-rag-101" },
      { message: { id: "prompt-rag-101" }, parts: [{ type: "text", text: longPrompt }] },
    )

    assert.deepEqual(queries, [longPrompt])
  })
})

test("RAG search prompt-length threshold can be overridden", async () => {
  await withEnvironment({
    OPENCODE_RAG_SEARCH_ENABLED: "true",
    OPENCODE_RAG_SEARCH_MIN_PROMPT_LENGTH: "4",
  }, async () => {
    const queries = []
    const plugin = await TracePlugin({
      writeEvent: async () => {},
      ragSearch: async (query) => { queries.push(query); return { results: [] } },
    })

    await plugin["chat.message"](
      { sessionID: "session-rag-override-4" },
      { message: { id: "prompt-rag-override-4" }, parts: [{ type: "text", text: "four" }] },
    )
    assert.deepEqual(queries, [])

    await plugin["chat.message"](
      { sessionID: "session-rag-override-5" },
      { message: { id: "prompt-rag-override-5" }, parts: [{ type: "text", text: "fives" }] },
    )
    assert.deepEqual(queries, ["fives"])
  })
})

test("invalid RAG prompt-length threshold falls back to 100 characters", async () => {
  await withEnvironment({
    OPENCODE_RAG_SEARCH_ENABLED: "true",
    OPENCODE_RAG_SEARCH_MIN_PROMPT_LENGTH: "invalid",
  }, async () => {
    const queries = []
    const plugin = await TracePlugin({
      writeEvent: async () => {},
      ragSearch: async (query) => { queries.push(query); return { results: [] } },
    })

    await plugin["chat.message"](
      { sessionID: "session-rag-invalid-100" },
      { message: { id: "prompt-rag-invalid-100" }, parts: [{ type: "text", text: "x".repeat(100) }] },
    )
    assert.deepEqual(queries, [])

    const longPrompt = "x".repeat(101)
    await plugin["chat.message"](
      { sessionID: "session-rag-invalid-101" },
      { message: { id: "prompt-rag-invalid-101" }, parts: [{ type: "text", text: longPrompt }] },
    )
    assert.deepEqual(queries, [longPrompt])
  })
})

test("RAG search sends the prompt and adds returned episodes to system context", async () => {
  const query = "Use the same queue strategy as before? Include prior decisions, implementation details, and relevant examples."
  const episodes = [{
    id: "session_old_prompt_old",
    project_path: "/project/rag",
    session_id: "session-old",
    transcript: "User: We used a bounded queue.\nAssistant: ...",
  }]

  await withEnvironment({ OPENCODE_RAG_SEARCH_ENABLED: "true" }, async () => {
    const queries = []
    const recordedEvents = []
    const plugin = await TracePlugin({
      directory: "/project/rag",
      writeEvent: async (eventType, data) => {
        recordedEvents.push({ eventType, data: structuredClone(data) })
      },
      ragSearch: async (value) => {
        queries.push(value)
        return {
          query: value,
          retrieval_id: "retrieval-rag-1",
          retrieval_version: "seed-v1",
          result_count: episodes.length,
          results: episodes,
        }
      },
    })

    await plugin["chat.message"](
      { sessionID: "session-rag", messageID: "prompt-rag" },
      { message: { id: "prompt-rag" }, parts: [{ type: "text", text: query }] },
    )
    const output = { system: ["Existing system prompt"] }
    await plugin["experimental.chat.system.transform"](
      { sessionID: "session-rag", model: {} },
      output,
    )

    assert.deepEqual(queries, [query])
    assert.equal(output.system.length, 3)
    assert.ok(output.system[1].includes("search_opencode_history"))
    assert.ok(output.system[2].includes("<retrieved_episodes>"))
    assert.ok(output.system[2].includes("session_old_prompt_old"))
    assert.ok(output.system[2].includes("bounded queue"))

    const systemPromptEvent = recordedEvents.find((event) => event.eventType === "system_prompt")
    assert.ok(systemPromptEvent)
    assert.ok(!JSON.stringify(systemPromptEvent.data.system).includes("<retrieved_episodes>"))
    assert.ok(!JSON.stringify(systemPromptEvent.data.system).includes("session_old_prompt_old"))
    assert.ok(!JSON.stringify(systemPromptEvent.data.system).includes("search_opencode_history"))

    const retrievalEvent = recordedEvents.find((event) => event.eventType === "rag_retrieval")
    assert.ok(retrievalEvent)
    assert.equal(retrievalEvent.data.retrieval_id, "retrieval-rag-1")
    assert.equal(retrievalEvent.data.retrieval_version, "seed-v1")
    assert.equal(retrievalEvent.data.result_count, 1)
    assert.deepEqual(retrievalEvent.data.project_paths, ["/project/rag"])
    assert.deepEqual(retrievalEvent.data.session_ids, ["session-old"])

    await plugin["tool.execute.before"](
      { sessionID: "session-rag", tool: "bash", callID: "call-history-cli" },
      {
        args: {
          command: 'search_opencode_history --project-path "$PWD" --session-id session-old queue',
        },
      },
    )
    const cliCall = recordedEvents.find((event) => event.eventType === "history_cli_call")
    assert.ok(cliCall)
    assert.equal(cliCall.data.retrieval_id, "retrieval-rag-1")
    assert.equal(cliCall.data.retrieval_version, "seed-v1")
    assert.equal(cliCall.data.retrieval_prompt_id, "prompt-rag")
    assert.equal(cliCall.data.project_path_filter, "/project/rag")
    assert.equal(cliCall.data.project_filter_matches_retrieval, true)
    assert.equal(cliCall.data.session_filter_matches_retrieval, true)

    await plugin["tool.execute.before"](
      { sessionID: "session-rag", tool: "bash", callID: "call-history-cli-miss" },
      {
        args: {
          command: "search_opencode_history --project-path /other/project --session-id other-session query",
        },
      },
    )
    const cliCalls = recordedEvents.filter((event) => event.eventType === "history_cli_call")
    assert.equal(cliCalls.length, 2)
    assert.deepEqual(cliCalls.map((event) => event.data.retrieval_id), [
      "retrieval-rag-1",
      "retrieval-rag-1",
    ])
    assert.equal(cliCalls[1].data.project_filter_matches_retrieval, false)
    assert.equal(cliCalls[1].data.session_filter_matches_retrieval, false)
  })
})

test("writes full AGENTS.md metadata only on system prompts", async () => {
  const directory = await mkdtemp(path.join(os.tmpdir(), "opencode-telemetry-metadata-"))
  const telemetryFile = path.join(directory, "telemetry.jsonl")
  const agentsMd = "# Project instructions\n\nKeep this content on the system prompt only.\n"
  const previousTelemetryFile = process.env.OPENCODE_TELEMETRY_FILE
  const previousRagSearchFlag = process.env.OPENCODE_RAG_SEARCH_ENABLED

  try {
    await writeFile(path.join(directory, "AGENTS.md"), agentsMd)
    process.env.OPENCODE_TELEMETRY_FILE = telemetryFile
    process.env.OPENCODE_RAG_SEARCH_ENABLED = "false"

    const { TracePlugin: FreshTracePlugin } = await import(
      `../telemetry.js?metadata-test=${Date.now()}`
    )
    const plugin = await FreshTracePlugin({ directory })

    await plugin["chat.message"](
      { sessionID: "session-metadata" },
      { message: { id: "prompt-metadata" } },
    )
    await plugin["experimental.chat.system.transform"](
      { sessionID: "session-metadata" },
      { system: ["system instructions"] },
    )
    await plugin["tool.execute.before"](
      { sessionID: "session-metadata", tool: "bash", callID: "call-metadata" },
      { args: { command: "printf test" } },
    )

    const records = (await readFile(telemetryFile, "utf8"))
      .trim()
      .split("\n")
      .map((line) => JSON.parse(line))
    const systemRecord = records.find((record) => record.event_type === "system_prompt")
    const otherRecords = records.filter((record) => record.event_type !== "system_prompt")

    assert.equal(systemRecord.project_metadata.agents_md, agentsMd)
    assert.ok(otherRecords.length > 0)
    assert.ok(otherRecords.every((record) => record.project_metadata?.agents_md !== agentsMd))
  } finally {
    if (previousTelemetryFile === undefined) delete process.env.OPENCODE_TELEMETRY_FILE
    else process.env.OPENCODE_TELEMETRY_FILE = previousTelemetryFile
    if (previousRagSearchFlag === undefined) delete process.env.OPENCODE_RAG_SEARCH_ENABLED
    else process.env.OPENCODE_RAG_SEARCH_ENABLED = previousRagSearchFlag
    await rm(directory, { recursive: true, force: true })
  }
})

test("redacts API keys from nested tool payloads", async () => {
  const secret = "sk-test-api-key-123456789"

  await withEnvironment({ TEST_API_KEY: secret }, async () => {
    const { events, plugin } = await capturePluginEvents()
    await plugin["tool.execute.after"](
      { sessionID: "session-redaction", tool: "bash", callID: "call-redaction" },
      { output: { nested: { result: `received ${secret}` } } },
    )

    const serialized = JSON.stringify(events)
    assert.ok(serialized.includes("<key omitted>"))
    assert.ok(!serialized.includes(secret))
  })
})

test("redacts supported credential environment variable patterns", async () => {
  const credentials = {
    TEST_API_KEY: "api-key-value-123456",
    TEST_TOKEN: "token-value-123456",
    TEST_SECRET: "secret-value-123456",
    TEST_PASSWORD: "password-value-123456",
    TEST_PRIVATE_KEY: "private-key-value-123456",
    TEST_AUTH_TOKEN: "auth-token-value-123456",
  }

  await withEnvironment(credentials, async () => {
    const { events, plugin } = await capturePluginEvents()
    const input = Object.values(credentials).join(" | ")
    await plugin["tool.execute.after"](
      { sessionID: "session-patterns", tool: "bash", callID: "call-patterns" },
      { output: input },
    )

    const serialized = JSON.stringify(events)
    for (const secret of Object.values(credentials)) {
      assert.ok(!serialized.includes(secret))
    }
  })
})

test("redacts repeated and overlapping secret values", async () => {
  const shortSecret = "overlap-secret-123456"
  const longSecret = `${shortSecret}-expanded`

  await withEnvironment({ TEST_API_KEY: shortSecret, TEST_TOKEN: longSecret }, async () => {
    const { events, plugin } = await capturePluginEvents()
    await plugin["tool.execute.after"](
      { sessionID: "session-overlap", tool: "bash", callID: "call-overlap" },
      { output: `${longSecret} ${shortSecret} ${longSecret}` },
    )

    const serialized = JSON.stringify(events)
    assert.ok(!serialized.includes(shortSecret))
    assert.ok(!serialized.includes(longSecret))
  })
})

test("does not redact non-secret environment variables", async () => {
  const value = "project-name-value-123456"

  await withEnvironment({ TEST_PROJECT_NAME: value }, async () => {
    const { events, plugin } = await capturePluginEvents()
    await plugin["tool.execute.after"](
      { sessionID: "session-non-secret", tool: "bash", callID: "call-non-secret" },
      { output: value },
    )

    assert.ok(JSON.stringify(events).includes(value))
  })
})

test("redacts secrets from assistant text and project metadata", async () => {
  const directory = await mkdtemp(path.join(os.tmpdir(), "opencode-telemetry-redaction-"))
  const secret = "agents-secret-value-123456"

  try {
    await writeFile(path.join(directory, "AGENTS.md"), `Use ${secret} only for testing.\n`)
    await withEnvironment({ TEST_AGENTS_TOKEN: secret }, async () => {
      const { events, plugin } = await capturePluginEvents({ directory })
      await plugin.event({
        event: {
          type: "message.part.updated",
          properties: {
            sessionID: "session-metadata",
            part: { type: "text", text: `Assistant repeated ${secret}` },
          },
        },
      })

      const serialized = JSON.stringify(events)
      assert.ok(!serialized.includes(secret))
      assert.ok(serialized.includes("<key omitted>"))
    })
  } finally {
    await rm(directory, { recursive: true, force: true })
  }
})
