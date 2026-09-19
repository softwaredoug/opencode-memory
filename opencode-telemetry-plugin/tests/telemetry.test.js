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
  const toasts = []

  try {
    await writeFile(path.join(directory, ".opencode-telemetry-ignore"), "\n")
    await TracePlugin({
      directory,
      client: mockClient(async (toast) => toasts.push(toast)),
    })

    assert.deepEqual(toasts, [{
      body: {
        message: "Telemetry is disabled for this project due to the presence of a .opencode-telemetry-ignore file.",
        variant: "info",
      },
    }])
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
