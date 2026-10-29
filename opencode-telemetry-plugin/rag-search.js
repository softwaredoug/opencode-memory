import http from "node:http"
import os from "node:os"
import path from "node:path"

const DEFAULT_SOCKET_PATH = path.join(
  os.homedir(),
  ".local",
  "share",
  "opencode-history",
  "service.sock",
)
const SEARCH_TIMEOUT_MS = 1000

function socketPath() {
  const configured = process.env.OPENCODE_HISTORY_SOCKET
  if (!configured) return DEFAULT_SOCKET_PATH
  if (configured === "~") return os.homedir()
  if (configured.startsWith("~/")) {
    return path.join(os.homedir(), configured.slice(2))
  }
  return configured
}

function responseErrorDetail(body) {
  try {
    const payload = JSON.parse(body)
    if (typeof payload.detail === "string") return payload.detail
    if (Array.isArray(payload.detail)) {
      return payload.detail.map((error) => {
        const location = Array.isArray(error.loc) ? error.loc.join(".") : "request"
        return `${location}: ${error.msg ?? error.type ?? "invalid value"}`
      }).join("; ")
    }
  } catch {
    // Keep a short response excerpt for non-JSON errors.
  }

  return body.slice(0, 500)
}

/** Query the daemon's RAG endpoint over its Unix-domain HTTP socket. */
export function ragSearch(query, retrievalVersion) {
  return new Promise((resolve, reject) => {
    const body = { query }
    if (typeof retrievalVersion === "string") {
      body.retrieval_version = retrievalVersion
    }

    const request = http.request(
      {
        socketPath: socketPath(),
        path: "/rag-search",
        method: "POST",
        headers: { "Content-Type": "application/json" },
      },
      (response) => {
        let body = ""
        response.setEncoding("utf8")
        response.on("data", (chunk) => { body += chunk })
        response.on("end", () => {
          if (response.statusCode < 200 || response.statusCode >= 300) {
            const detail = responseErrorDetail(body)
            reject(new Error(`RAG search returned HTTP ${response.statusCode}: ${detail}`))
            return
          }

          try {
            const result = JSON.parse(body)
            if (
              !Array.isArray(result.breadcrumbs)
              || typeof result.retrieval_id !== "string"
              || typeof result.retrieval_version !== "string"
            ) {
              throw new Error("RAG search response must contain breadcrumbs, retrieval_id, and retrieval_version")
            }
            resolve(result)
          } catch (error) {
            reject(error)
          }
        })
      },
    )

    request.setTimeout(SEARCH_TIMEOUT_MS, () => {
      request.destroy(new Error("RAG search timed out"))
    })
    request.on("error", reject)
    request.end(JSON.stringify(body))
  })
}
