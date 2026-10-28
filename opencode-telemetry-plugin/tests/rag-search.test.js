import assert from "node:assert/strict"
import { createServer } from "node:http"
import { mkdtemp, rm } from "node:fs/promises"
import os from "node:os"
import path from "node:path"
import test from "node:test"

import { ragSearch } from "../rag-search.js"

test("posts only the prompt to the daemon's rag-search endpoint", async () => {
  const directory = await mkdtemp(path.join(os.tmpdir(), "opencode-rag-search-"))
  const socketPath = path.join(directory, "daemon.sock")
  const previousSocketPath = process.env.OPENCODE_HISTORY_SOCKET
  let requestBody
  let requestPath
  let requestMethod
  const server = createServer(async (request, response) => {
    requestPath = request.url
    requestMethod = request.method
    let body = ""
    for await (const chunk of request) body += chunk
    requestBody = JSON.parse(body)
    response.setHeader("Content-Type", "application/json")
    response.end(JSON.stringify({
      query: requestBody.query,
      retrieval_id: "retrieval-1",
      retrieval_version: "seed-v1",
      breadcrumbs: [{ id: "episode-1", transcript: "prior trace" }],
    }))
  })

  try {
    await new Promise((resolve) => server.listen(socketPath, resolve))
    process.env.OPENCODE_HISTORY_SOCKET = socketPath

    const query = "Bring back the deployment fix we used last time."
    const result = await ragSearch(query)

    assert.equal(requestPath, "/rag-search")
    assert.equal(requestMethod, "POST")
    assert.deepEqual(requestBody, { query })
    assert.deepEqual(result.breadcrumbs, [{ id: "episode-1", transcript: "prior trace" }])
    assert.equal(result.retrieval_id, "retrieval-1")
    assert.equal(result.retrieval_version, "seed-v1")
  } finally {
    if (previousSocketPath === undefined) delete process.env.OPENCODE_HISTORY_SOCKET
    else process.env.OPENCODE_HISTORY_SOCKET = previousSocketPath
    await new Promise((resolve, reject) => server.close((error) => error ? reject(error) : resolve()))
    await rm(directory, { recursive: true, force: true })
  }
})
