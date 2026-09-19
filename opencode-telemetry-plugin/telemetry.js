import os from "node:os"
import path from "node:path"
import { appendFile, mkdir, readFile } from "node:fs/promises"

const telemetryDirectory = path.join(
  os.homedir(),
  ".local",
  "share",
  "opencode",
)
const telemetryFileOverride = process.env.OPENCODE_TELEMETRY_FILE

let directoryReady
let writeQueue = Promise.resolve()
const promptIds = new Map()
let projectMetadata = null
let hasIgnore = false

function telemetryFileFor(timestamp) {
  if (telemetryFileOverride) return telemetryFileOverride
  const date = timestamp.toISOString().slice(0, 10)
  return path.join(telemetryDirectory, `${date}-telemetry.jsonl`)
}

async function ensureDirectory(telemetryFile) {
  if (!directoryReady) {
    directoryReady = mkdir(path.dirname(telemetryFile), { recursive: true })
  }

  await directoryReady
}

function serialize(value) {
  const seen = new WeakSet()

  return JSON.stringify(value, (_key, currentValue) => {
    if (typeof currentValue === "bigint") return currentValue.toString()
    if (typeof currentValue !== "object" || currentValue === null) {
      return currentValue
    }
    if (seen.has(currentValue)) return "[Circular]"
    seen.add(currentValue)
    return currentValue
  })
}

function writeEvent(eventType, data) {
  const timestamp = new Date()
  const telemetryFile = telemetryFileFor(timestamp)
  const record = {
    event_type: eventType,
    timestamp: timestamp.toISOString(),
    session_id: data.input?.sessionID ?? null,
    call_id: data.input?.callID ?? null,
    project_metadata: projectMetadata,
    payload: data,
  }

  let line
  try {
    line = serialize(record) + "\n"
  } catch (error) {
    line = JSON.stringify({
      event_type: "telemetry.serialization_error",
      timestamp: new Date().toISOString(),
      payload: { event_type: eventType, error: String(error) },
    }) + "\n"
  }

  // Serialize writes so concurrent tool calls cannot interleave their lines.
  writeQueue = writeQueue
    .then(async () => {
      await ensureDirectory(telemetryFile)
      await appendFile(telemetryFile, line, "utf8")
    })
    .catch((error) => {
      // Telemetry must never prevent the tool itself from running.
      console.error(`[telemetry] failed to write ${telemetryFile}:`, error)
    })

  return writeQueue
}

function isAgentsFile(filePath) {
  return typeof filePath === "string" && /(?:^|[\\/])AGENTS\.md$/i.test(filePath)
}

function eventData(event) {
  return event?.properties ?? event?.data ?? {}
}

function messagePart(data) {
  return data?.part ?? data?.properties?.part ?? data
}

function sessionIdFromEvent(data) {
  return data?.sessionID ?? data?.sessionId ?? messagePart(data)?.sessionID ?? null
}

async function loadProjectMetadata(directory) {
  const projectPath = typeof directory === "string" ? directory : null
  if (!projectPath) return { path: null, agents_md: null }

  let agents_md = null
  try {
    agents_md = await readFile(path.join(projectPath, "AGENTS.md"), "utf8")
  } catch {
    // Project metadata is optional and must not affect telemetry.
  }

  return { path: projectPath, agents_md }
}


async function hasIgnoreFile(directory) {
  const projectPath = typeof directory === "string" ? directory : null
  if (!projectPath) return false;

  try {
    await readFile(path.join(projectPath, ".opencode-telemetry-ignore"), "utf8");
    return true;
  } catch {
    return false;
  }
}

export const TracePlugin = async ({ directory } = {}) => {
  hasIgnore = await hasIgnoreFile(directory)

  if (hasIgnore) return {}

  projectMetadata = await loadProjectMetadata(directory)

  return {
    "chat.message": async (input, output) => {
      const message = output.message
      const promptId = message?.id ?? input.messageID ?? null
      if (input.sessionID && promptId) promptIds.set(input.sessionID, promptId)

      await writeEvent("prompt", {
        input,
        output,
        prompt_id: promptId,
      })
    },

    "experimental.chat.system.transform": async (input, output) => {
      await writeEvent("system_prompt", {
        input,
        prompt_id: input.sessionID ? promptIds.get(input.sessionID) ?? null : null,
        system: output.system,
        system_state: projectMetadata,
      })
    },

    "tool.execute.before": async (input, output) => {
      await writeEvent("tool_call", {
        input,
        output,
        prompt_id: promptIds.get(input.sessionID) ?? null,
      })

      if (input.tool === "read" && isAgentsFile(output.args?.filePath)) {
        await writeEvent("instruction_read", {
          phase: "before",
          input,
          output,
          prompt_id: promptIds.get(input.sessionID) ?? null,
        })
      }
    },

    "tool.execute.after": async (input, output) => {
      await writeEvent("tool_result", {
        input,
        output,
        prompt_id: promptIds.get(input.sessionID) ?? null,
      })

      if (input.tool === "read" && isAgentsFile(input.args?.filePath)) {
        await writeEvent("instruction_read", {
          phase: "after",
          input,
          output,
          prompt_id: promptIds.get(input.sessionID) ?? null,
        })
      }
    },

    event: async ({ event }) => {
      if (event.type !== "message.part.updated" && event.type !== "message.updated") return

      const data = eventData(event)
      const part = messagePart(data)
      const sessionID = sessionIdFromEvent(data)
      const prompt_id = sessionID ? promptIds.get(sessionID) ?? null : null

      if (event.type === "message.part.updated") {
        const partType = part?.type
        if (partType !== "reasoning" && partType !== "text") return

        await writeEvent(partType === "reasoning" ? "reasoning" : "assistant_text", {
          event,
          prompt_id,
        })
        return
      }

      await writeEvent("message_updated", {
        event,
        prompt_id,
      })
    },
  }
}
