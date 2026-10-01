import assert from "node:assert/strict"
import { mkdtemp, rm, writeFile } from "node:fs/promises"
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
    process.env[name] = value
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
