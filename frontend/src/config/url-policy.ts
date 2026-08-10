/**
 * Normalize an absolute outbound URL only when its scheme is HTTP(S).
 * Returning the URL parser's serialization matters for CSP use: raw values
 * must never be interpolated into a policy header.
 */
export function normalizeHttpUrl(value: unknown): string | null {
  if (typeof value !== "string" || value.length === 0 || value !== value.trim()) {
    return null;
  }

  try {
    const parsed = new URL(value);
    if (parsed.protocol !== "http:" && parsed.protocol !== "https:") return null;
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
