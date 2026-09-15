import os from "node:os"
import path from "node:path"
import { appendFile, mkdir } from "node:fs/promises"

const telemetryFile =
  process.env.OPENCODE_TELEMETRY_FILE ??
  path.join(os.homedir(), ".local", "share", "opencode", "telemetry.jsonl")

let directoryReady
let writeQueue = Promise.resolve()

async function ensureDirectory() {
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
  const record = {
    event_type: eventType,
    timestamp: new Date().toISOString(),
    session_id: data.input?.sessionID ?? null,
    call_id: data.input?.callID ?? null,
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
      await ensureDirectory()
      await appendFile(telemetryFile, line, "utf8")
    })
    .catch((error) => {
      // Telemetry must never prevent the tool itself from running.
      console.error(`[telemetry] failed to write ${telemetryFile}:`, error)
    })

  return writeQueue
}

export const TracePlugin = async () => {
  return {
    "tool.execute.before": async (input, output) => {
      await writeEvent("tool_call", {
        input,
        output,
      })
    },

    "tool.execute.after": async (input, output) => {
      await writeEvent("tool_result", {
        input,
        output,
      })
    },
  }
}
