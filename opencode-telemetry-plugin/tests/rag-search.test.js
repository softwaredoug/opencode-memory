import assert from "node:assert/strict"
import { createServer } from "node:http"
import { mkdtemp, rm } from "node:fs/promises"
import os from "node:os"
import path from "node:path"
import test from "node:test"

import { ragSearch } from "../rag-search.js"

test("posts the prompt and optional retrieval version to the daemon", async () => {
  const directory = await mkdtemp(path.join(os.tmpdir(), "opencode-rag-search-"))
  const socketPath = path.join(directory, "daemon.sock")
  const previousSocketPath = process.env.OPENCODE_HISTORY_SOCKET
  const requestBodies = []
  let requestPath
  let requestMethod
  const server = createServer(async (request, response) => {
    requestPath = request.url
    requestMethod = request.method
    let body = ""
    for await (const chunk of request) body += chunk
    const requestBody = JSON.parse(body)
    requestBodies.push(requestBody)
    response.setHeader("Content-Type", "application/json")
    response.end(JSON.stringify({
      query: requestBody.query,
      retrieval_id: "retrieval-1",
      retrieval_version: requestBody.retrieval_version ?? "bm25-v1",
      breadcrumbs: [{ id: "episode-1", transcript: "prior trace" }],
    }))
  })

  try {
    await new Promise((resolve) => server.listen(socketPath, resolve))
    process.env.OPENCODE_HISTORY_SOCKET = socketPath

    const query = "Bring back the deployment fix we used last time."
    const defaultResult = await ragSearch(query)
    const versionedResult = await ragSearch(query, "voyage-ann-diverse-v1")

    assert.equal(requestPath, "/rag-search")
    assert.equal(requestMethod, "POST")
    assert.deepEqual(requestBodies, [
      { query },
      { query, retrieval_version: "voyage-ann-diverse-v1" },
    ])
    assert.deepEqual(defaultResult.breadcrumbs, [{ id: "episode-1", transcript: "prior trace" }])
    assert.equal(defaultResult.retrieval_id, "retrieval-1")
    assert.equal(defaultResult.retrieval_version, "bm25-v1")
    assert.equal(versionedResult.retrieval_version, "voyage-ann-diverse-v1")
  } finally {
    if (previousSocketPath === undefined) delete process.env.OPENCODE_HISTORY_SOCKET
    else process.env.OPENCODE_HISTORY_SOCKET = previousSocketPath
    await new Promise((resolve, reject) => server.close((error) => error ? reject(error) : resolve()))
    await rm(directory, { recursive: true, force: true })
  }
})

test("includes sanitized FastAPI validation details on errors", async () => {
  const directory = await mkdtemp(path.join(os.tmpdir(), "opencode-rag-search-error-"))
  const socketPath = path.join(directory, "daemon.sock")
  const previousSocketPath = process.env.OPENCODE_HISTORY_SOCKET
  const server = createServer((_request, response) => {
    response.statusCode = 422
    response.setHeader("Content-Type", "application/json")
    response.end(JSON.stringify({
      detail: [{
        type: "missing",
        loc: ["body", "query"],
        msg: "Field required",
        input: "sensitive prompt contents",
      }],
    }))
  })

  try {
    await new Promise((resolve) => server.listen(socketPath, resolve))
    process.env.OPENCODE_HISTORY_SOCKET = socketPath

    await assert.rejects(
      ragSearch("query"),
      (error) => {
        assert.match(error.message, /HTTP 422: body\.query: Field required/)
        assert.doesNotMatch(error.message, /sensitive prompt contents/)
        return true
      },
    )
  } finally {
    if (previousSocketPath === undefined) delete process.env.OPENCODE_HISTORY_SOCKET
    else process.env.OPENCODE_HISTORY_SOCKET = previousSocketPath
    await new Promise((resolve, reject) => server.close((error) => error ? reject(error) : resolve()))
    await rm(directory, { recursive: true, force: true })
  }
})
