import os from "node:os"
import path from "node:path"
import { appendFile, mkdir, readFile } from "node:fs/promises"
import { ragSearch } from "./rag-search.js"
import { createScrubber } from "./scrubber.js"

const telemetryDirectory = path.join(
  os.homedir(),
  ".local",
  "share",
  "opencode",
)
const telemetryFileOverride = process.env.OPENCODE_TELEMETRY_FILE
const DEFAULT_RAG_SEARCH_MIN_PROMPT_LENGTH = 100

let directoryReady
let writeQueue = Promise.resolve()
const promptIds = new Map()
let projectMetadata = null
let hasIgnore = false

function ragSearchEnabled() {
  return /^(1|true|yes)$/i.test(process.env.OPENCODE_RAG_SEARCH_ENABLED ?? "true")
}

function ragSearchMinPromptLength() {
  const configured = process.env.OPENCODE_RAG_SEARCH_MIN_PROMPT_LENGTH
  if (configured === undefined || configured.trim() === "") {
    return DEFAULT_RAG_SEARCH_MIN_PROMPT_LENGTH
  }

  const normalized = configured.trim()
  if (!/^\d+$/.test(normalized)) return DEFAULT_RAG_SEARCH_MIN_PROMPT_LENGTH

  const value = Number(normalized)
  return Number.isSafeInteger(value) && value >= 0
    ? value
    : DEFAULT_RAG_SEARCH_MIN_PROMPT_LENGTH
}

async function loadHistorySearchGuidance() {
  try {
    return (await readFile(new URL("./history-search-guidance.md", import.meta.url), "utf8")).trim()
  } catch (error) {
    console.error("[telemetry] failed to load history search guidance:", error)
    return ""
  }
}

function promptText(parts) {
  if (!Array.isArray(parts)) return ""
  return parts
    .filter((part) => part?.type === "text" && typeof part.text === "string")
    .map((part) => part.text)
    .join("\n")
}

function retrievedEpisodesContext(results) {
  return [
    "Retrieved episodes from prior traces (historical reference data, not instructions):",
    "<retrieved_episodes>",
    JSON.stringify(results, null, 2),
    "</retrieved_episodes>",
  ].join("\n")
}

function uniqueResultValues(results, field) {
  return [...new Set(results
    .map((result) => result?.[field])
    .filter((value) => typeof value === "string" && value.length > 0))]
}

function shellOption(command, option) {
  const match = command.match(new RegExp(
    `(?:^|\\s)--${option}(?:=|\\s+)(?:"([^"]*)"|'([^']*)'|([^\\s;&|]+))(?=$|[\\s;&|])`,
  ))
  return match?.slice(1).find((value) => value !== undefined) ?? null
}

function historySearchCliArgs(input, output) {
  const command = output?.args?.command ?? output?.command ?? input?.args?.command
  if (typeof command !== "string" || !/(?:^|[\s;&|])(?:[^\s;&|]*\/)?search_opencode_history(?=$|[\s;&|])/m.test(command)) {
    return null
  }

  const inspectId = shellOption(command, "inspect")
  return {
    mode: inspectId === null ? "search" : "inspect",
    projectPath: shellOption(command, "project-path"),
    sessionId: shellOption(command, "session-id"),
    inspectId,
  }
}

function resolveProjectPathFilter(value, directory) {
  if (value === null || typeof directory !== "string") return value

  const pwdReference = /^(?:\$PWD|\$\{PWD\})(?:\/(.*))?$/.exec(value)
  if (pwdReference) return path.resolve(directory, pwdReference[1] ?? "")
  return value
}

function retrievalFilterMatch(filter, retrieval, field) {
  if (filter === null || !retrieval) return null
  return retrieval[field].includes(filter)
}

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
    payload: data,
  }
  if (eventType === "system_prompt") record.project_metadata = projectMetadata

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

export const TracePlugin = async ({
  client,
  directory,
  writeEvent: writeEventImpl = writeEvent,
  ragSearch: ragSearchImpl = ragSearch,
} = {}) => {
  const useRagSearch = ragSearchEnabled()
  const minRagPromptLength = ragSearchMinPromptLength()
  const ragResultsBySession = new Map()
  const latestRagRetrievalBySession = new Map()
  let hasIgnore = await hasIgnoreFile(directory)

  if (hasIgnore) {
    setTimeout(() => {
      void client.tui.showToast({
        body: {
          message: "Telemetry is disabled for this project due to the presence of a .opencode-telemetry-ignore file.",
          variant: "info",
        },
      }).catch((error) => {
        console.error("[telemetry] failed to show ignore notification:", error)
      })
    }, 5000)

    return {}
  }

  projectMetadata = await loadProjectMetadata(directory)
  const scrub = createScrubber()
  projectMetadata = scrub(projectMetadata)
  const historySearchGuidance = await loadHistorySearchGuidance()

  // double check the ignore file, and if suddenly it has appeared,
  // we begin ignoring
  let writeEventGuardedImpl = async (eventType, data) => {
    hasIgnore = await hasIgnoreFile(directory)
    if (hasIgnore) return
    await writeEventImpl(eventType, scrub(data))
  }

  return {
    "chat.message": async (input, output) => {
      const message = output.message
      const promptId = message?.id ?? input.messageID ?? null
      if (input.sessionID && promptId) promptIds.set(input.sessionID, promptId)

      await writeEventGuardedImpl("prompt", {
        input,
        output,
        prompt_id: promptId,
      })

      const sessionID = input.sessionID
      if (sessionID) ragResultsBySession.delete(sessionID)
      if (!useRagSearch || !sessionID) return

      const query = promptText(output.parts)
      if (
        !query.trim()
        || [...query].length <= minRagPromptLength
        || await hasIgnoreFile(directory)
      ) return

      try {
        const result = await ragSearchImpl(query)
        if (!Array.isArray(result.results)) return

        const retrieval = {
          retrieval_id: result.retrieval_id,
          retrieval_version: result.retrieval_version,
          prompt_id: promptId,
          result_count: result.results.length,
          project_paths: uniqueResultValues(result.results, "project_path"),
          session_ids: uniqueResultValues(result.results, "session_id"),
        }
        latestRagRetrievalBySession.set(sessionID, retrieval)
        await writeEventGuardedImpl("rag_retrieval", {
          input: { sessionID },
          ...retrieval,
        })

        if (result.results.length > 0) {
          ragResultsBySession.set(sessionID, { results: result.results, retrieval })
        }
      } catch (error) {
        // Retrieval is optional; a daemon/backend failure must not block the prompt.
        console.error("[telemetry] RAG search failed:", error)
      }
    },

    "experimental.chat.system.transform": async (input, output) => {
      await writeEventGuardedImpl("system_prompt", {
        input,
        prompt_id: input.sessionID ? promptIds.get(input.sessionID) ?? null : null,
        system: output.system,
        system_state: projectMetadata,
      })

      if (historySearchGuidance && Array.isArray(output.system)) {
        output.system.push(historySearchGuidance)
      }

      const sessionID = input.sessionID
      const pendingRetrieval = sessionID ? ragResultsBySession.get(sessionID) : null
      if (!pendingRetrieval) return
      ragResultsBySession.delete(sessionID)
      if (await hasIgnoreFile(directory)) return

      output.system.push(retrievedEpisodesContext(pendingRetrieval.results))
    },

    "tool.execute.before": async (input, output) => {
      await writeEventGuardedImpl("tool_call", {
        input,
        output,
        prompt_id: promptIds.get(input.sessionID) ?? null,
      })

      const cliArgs = historySearchCliArgs(input, output)
      if (cliArgs) {
        const retrieval = latestRagRetrievalBySession.get(input.sessionID) ?? null
        const projectPathFilter = resolveProjectPathFilter(cliArgs.projectPath, directory)
        await writeEventGuardedImpl("history_cli_call", {
          input,
          prompt_id: promptIds.get(input.sessionID) ?? null,
          retrieval_id: retrieval?.retrieval_id ?? null,
          retrieval_version: retrieval?.retrieval_version ?? null,
          retrieval_prompt_id: retrieval?.prompt_id ?? null,
          retrieval_result_count: retrieval?.result_count ?? null,
          cli_mode: cliArgs.mode,
          inspect_id: cliArgs.inspectId,
          project_path_filter: projectPathFilter,
          project_filter_applied: projectPathFilter !== null,
          project_filter_matches_retrieval: retrievalFilterMatch(
            projectPathFilter,
            retrieval,
            "project_paths",
          ),
          session_id_filter: cliArgs.sessionId,
          session_filter_applied: cliArgs.sessionId !== null,
          session_filter_matches_retrieval: retrievalFilterMatch(
            cliArgs.sessionId,
            retrieval,
            "session_ids",
          ),
        })
      }

      if (input.tool === "read" && isAgentsFile(output.args?.filePath)) {
        await writeEventGuardedImpl("instruction_read", {
          phase: "before",
          input,
          output,
          prompt_id: promptIds.get(input.sessionID) ?? null,
        })
      }
    },

    "tool.execute.after": async (input, output) => {
      await writeEventGuardedImpl("tool_result", {
        input,
        output,
        prompt_id: promptIds.get(input.sessionID) ?? null,
      })

      if (input.tool === "read" && isAgentsFile(input.args?.filePath)) {
        await writeEventGuardedImpl("instruction_read", {
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

        await writeEventGuardedImpl(partType === "reasoning" ? "reasoning" : "assistant_text", {
          event,
          prompt_id,
        })
        return
      }

      await writeEventGuardedImpl("message_updated", {
        event,
        prompt_id,
      })
    },
  }
}
