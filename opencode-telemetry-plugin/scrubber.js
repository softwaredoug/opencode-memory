const SECRET_NAME = /(?:API[_-]?KEY|TOKEN|SECRET|PASSWORD|PRIVATE[_-]?KEY|AUTH|CREDENTIAL)/i
const MIN_SECRET_LENGTH = 8
const REDACTION = "<key omitted>"

function secretValues(environment) {
  return [...new Set(
    Object.entries(environment)
      .filter(([name, value]) =>
        SECRET_NAME.test(name) &&
        typeof value === "string" &&
        value.length >= MIN_SECRET_LENGTH &&
        value.trim().length > 0,
      )
      .map(([, value]) => value),
  )].sort((left, right) => right.length - left.length)
}

function scrubValue(value, secrets, seen) {
  if (typeof value === "string") {
    return secrets.reduce(
      (text, secret) => text.split(secret).join(REDACTION),
      value,
    )
  }

  if (value === null || typeof value !== "object") return value
  if (seen.has(value)) return "[Circular]"
  seen.add(value)

  if (Array.isArray(value)) {
    return value.map((item) => scrubValue(item, secrets, seen))
  }

  return Object.fromEntries(
    Object.entries(value).map(([key, item]) => [
      key,
      scrubValue(item, secrets, seen),
    ]),
  )
}

export function createScrubber(environment = process.env) {
  const secrets = secretValues(environment)
  return (value) => scrubValue(value, secrets, new WeakSet())
}
