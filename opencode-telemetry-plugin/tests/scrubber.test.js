import assert from "node:assert/strict"
import test from "node:test"

import { createScrubber } from "../scrubber.js"

test("scrubs credential values recursively and handles overlaps", () => {
  const shortSecret = "overlap-secret-123456"
  const longSecret = `${shortSecret}-expanded`
  const scrub = createScrubber({
    TEST_API_KEY: shortSecret,
    TEST_TOKEN: longSecret,
    TEST_PROJECT_NAME: "keep-this-value",
  })

  const result = scrub({
    message: `${longSecret} ${shortSecret}`,
    nested: [{ value: longSecret }],
    project: "keep-this-value",
  })

  assert.deepEqual(result, {
    message: "<key omitted> <key omitted>",
    nested: [{ value: "<key omitted>" }],
    project: "keep-this-value",
  })
})

test("scrubber replaces circular references without throwing", () => {
  const value = { secret: "secret-value-123456" }
  value.self = value

  const scrub = createScrubber({ TEST_SECRET: value.secret })
  const result = scrub(value)

  assert.equal(result.secret, "<key omitted>")
  assert.equal(result.self, "[Circular]")
})
