const HEX_DIGIT = /[0-9a-fA-F]/;

/**
 * `new URL()` never rejects a stray, truncated, or non-hex `%` escape — it
 * passes it through unchanged (e.g. `%zz`, trailing `%2`). Scan the raw input
 * the same way the server's source-URL boundary does
 * (`backend/api/run_sources.py:_client_source_url`) so both reject the same
 * malformed values instead of the browser parser silently tolerating them.
 */
function hasMalformedPercentEscape(value: string): boolean {
  for (let index = 0; index < value.length; index += 1) {
    if (value[index] !== "%") continue;
    const first = value[index + 1];
    const second = value[index + 2];
    if (!first || !second || !HEX_DIGIT.test(first) || !HEX_DIGIT.test(second)) {
      return true;
    }
  }
  return false;
}

/**
 * Normalize an absolute outbound URL only when its scheme is HTTP(S).
 * Returning the URL parser's serialization matters for CSP use: raw values
 * must never be interpolated into a policy header. Credentials (userinfo)
 * and malformed percent escapes are rejected even though the URL parser
 * accepts both, so this client boundary matches the server's safety class
 * instead of relying on browser parser tolerance.
 */
export function normalizeHttpUrl(value: unknown): string | null {
  if (typeof value !== "string" || value.length === 0 || value !== value.trim()) {
    return null;
  }
  if (hasMalformedPercentEscape(value)) return null;

  try {
    const parsed = new URL(value);
    if (parsed.protocol !== "http:" && parsed.protocol !== "https:") return null;
    if (parsed.username || parsed.password) return null;
    return parsed.href;
  } catch {
    return null;
  }
}

/**
 * Validate a backend base URL and remove its trailing slash. Credentials,
 * query strings, and fragments are rejected because appending API paths to
 * any of them is ambiguous and unsafe.
 */
export function normalizeHttpBaseUrl(value: unknown): string | null {
  const normalized = normalizeHttpUrl(value);
  if (!normalized) return null;

  const parsed = new URL(normalized);
  if (parsed.username || parsed.password || parsed.search || parsed.hash) return null;
  return normalized.replace(/\/$/, "");
}

/** Fail loudly when build/runtime configuration cannot name a safe backend. */
export function requireHttpBaseUrl(value: unknown, variableName: string): string {
  const normalized = normalizeHttpBaseUrl(value);
  if (normalized) return normalized;
  throw new Error(`${variableName} must be an absolute http:// or https:// URL without credentials, query, or fragment.`);
}
