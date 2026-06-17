import { appConfig } from "@/config/app.config";
import type { OAuthProvider } from "@/config/site.config";
import type { PlanId } from "@/config/plans";
import type { ClannonClient } from "./client";
import {
  ApiError,
  type Credentials,
  type LayerModelConfig,
  type MemoryEntry,
  type RemoteConfig,
  type Run,
  type RunEvent,
  type RunSummary,
  type SignupInput,
  type UsageSummary,
  type User,
} from "./types";

function url(endpoint: string, params?: Record<string, string>): string {
  let path = endpoint;
  if (params) {
    for (const [key, value] of Object.entries(params)) {
      path = path.replace(`:${key}`, encodeURIComponent(value));
    }
  }
  return `${appConfig.apiBaseUrl}${path}`;
}

/**
 * FastAPI's `detail` is a string for HTTPException but an ARRAY of
 * error objects for Pydantic validation (422) — coerce both to prose,
 * never let an object reach Error's message (it renders "[object Object]").
 */
function errorMessage(body: unknown, fallback: string): string {
  if (typeof body !== "object" || body === null) return fallback;
  const detail = (body as { detail?: unknown; message?: unknown }).detail
    ?? (body as { message?: unknown }).message;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    const msgs = detail
      .map((d) => (typeof d?.msg === "string" ? d.msg : null))
      .filter(Boolean);
    if (msgs.length) return msgs.join(" · ");
  }
  return fallback;
}

async function request<T>(
  endpoint: string,
  init: RequestInit & { params?: Record<string, string> } = {},
): Promise<T> {
  const { params, ...rest } = init;
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), appConfig.http.timeoutMs);
  try {
    const res = await fetch(url(endpoint, params), {
      credentials: appConfig.http.credentials,
      signal: init.signal ?? controller.signal,
      ...rest,
      headers: {
        "Content-Type": "application/json",
        ...rest.headers,
      },
    });
    if (!res.ok) {
      let message = res.statusText;
      let code: string | undefined;
      try {
        const body = await res.json();
        message = errorMessage(body, message);
        code = body.code;
      } catch {
        // non-JSON error body; keep statusText
      }
      throw new ApiError(message, res.status, code);
    }
    if (res.status === 204) return undefined as T;
    return (await res.json()) as T;
  } catch (e) {
    if (e instanceof ApiError) throw e;
    // a caller-initiated abort is intentional — let it propagate untouched
    if (init.signal?.aborted) throw e;
    // offline / DNS / refused → bare TypeError; timeout → AbortError.
    // Map both to messages a user can act on.
    throw new ApiError(
      controller.signal.aborted
        ? "The server took too long to respond — try again."
        : "Can't reach the server — check your connection and try again.",
      0,
    );
  } finally {
    clearTimeout(timeout);
  }
}

/**
 * Talks to the real backend — the Vraksha engine — defined in app.config.ts.
 * Auth is cookie-based (httpOnly, set by the backend) — no tokens
 * are ever stored in JS-accessible storage.
 */
export class HttpClient implements ClannonClient {
  async getRemoteConfig(): Promise<RemoteConfig | null> {
    try {
      return await request<RemoteConfig>(appConfig.endpoints.config);
    } catch {
      // Backend doesn't serve /config (or is unreachable) — fall back
      // to the local defaults rather than breaking the page.
      return null;
    }
  }

  login(input: Credentials): Promise<User> {
    return request(appConfig.endpoints.login, {
      method: "POST",
      body: JSON.stringify(input),
    });
  }

  signup(input: SignupInput): Promise<User> {
    return request(appConfig.endpoints.signup, {
      method: "POST",
      body: JSON.stringify(input),
    });
  }

  loginWithProvider(provider: OAuthProvider): Promise<User> {
    // Full-page navigation: the backend owns the OAuth handshake and
    // returns with an httpOnly cookie. The promise never settles —
    // the page unloads first.
    window.location.assign(url(appConfig.endpoints.oauthStart, { provider }));
    return new Promise<User>(() => {});
  }

  async logout(): Promise<void> {
    await request(appConfig.endpoints.logout, { method: "POST" });
  }

  async me(): Promise<User | null> {
    try {
      return await request<User>(appConfig.endpoints.me);
    } catch (e) {
      if (e instanceof ApiError && e.status === 401) return null;
      throw e;
    }
  }

  listRuns(): Promise<RunSummary[]> {
    return request(appConfig.endpoints.runs);
  }

  getRun(id: string): Promise<Run> {
    return request(appConfig.endpoints.run, { params: { id } });
  }

  async createRun(
    brief: string,
    files: File[] = [],
    models: Record<string, string> = {},
  ): Promise<{ id: string }> {
    // multipart now (was JSON): brief + repeated "files" field. Let the
    // browser set the multipart boundary — the json request() helper can't.
    const form = new FormData();
    form.append("brief", brief);
    for (const f of files) form.append("files", f, f.name); // field name MUST be "files"
    if (Object.keys(models).length) form.append("models", JSON.stringify(models)); // per-session overrides
    const res = await fetch(url(appConfig.endpoints.createRun), {
      method: "POST",
      credentials: appConfig.http.credentials,
      body: form,
    });
    if (!res.ok) {
      let message = res.statusText;
      try {
        message = errorMessage(await res.json(), message);
      } catch {
        // non-JSON error body
      }
      throw new ApiError(message, res.status); // 422 detail names the rejected file
    }
    return (await res.json()) as { id: string };
  }

  async downloadArtifact(runId: string, name: string): Promise<Blob> {
    // fetch-blob, not a bare <a download>: the backend is a different origin
    // and auth is a cookie — credentials:"include" reliably authenticates.
    const res = await fetch(url(appConfig.endpoints.runArtifact, { id: runId, name }), {
      credentials: appConfig.http.credentials,
    });
    if (!res.ok) throw new ApiError(`Download failed: ${res.statusText}`, res.status);
    return res.blob();
  }

  async setRunFeedback(
    id: string,
    rating: "up" | "down" | null,
    comment?: string,
  ): Promise<void> {
    await request(appConfig.endpoints.runFeedback, {
      method: "POST",
      params: { id },
      body: JSON.stringify({ rating, comment: comment ?? null }),
    });
  }

  async createFollowUp(
    id: string,
    brief: string,
    files: File[] = [],
    models: Record<string, string> = {},
  ): Promise<{ id: string }> {
    // multipart now (was JSON): brief + repeated "files", mirroring createRun.
    const form = new FormData();
    form.append("brief", brief);
    for (const f of files) form.append("files", f, f.name); // field name MUST be "files"
    if (Object.keys(models).length) form.append("models", JSON.stringify(models)); // per-session overrides
    const res = await fetch(url(appConfig.endpoints.runFollowUp, { id }), {
      method: "POST",
      credentials: appConfig.http.credentials,
      body: form,
    });
    if (!res.ok) {
      let message = res.statusText;
      try {
        message = errorMessage(await res.json(), message);
      } catch {
        // non-JSON error body
      }
      throw new ApiError(message, res.status); // 422 detail names the rejected file
    }
    return (await res.json()) as { id: string };
  }

  getRunThread(id: string): Promise<Run[]> {
    return request(appConfig.endpoints.runThread, { params: { id } });
  }

  async deleteSession(sessionId: string): Promise<void> {
    await request(appConfig.endpoints.session, {
      method: "DELETE",
      params: { id: sessionId },
    });
  }

  async cancelRun(id: string): Promise<void> {
    // 200 {status:"cancelling"} on a live run, 204 on an already-terminal one —
    // both fine; the authoritative `cancelled` lands over the stream.
    await request(appConfig.endpoints.runCancel, { method: "POST", params: { id } });
  }

  /**
   * Consumes the backend's Server-Sent Events stream. Each `data:`
   * line is one JSON-encoded RunEvent.
   */
  async *streamRun(id: string, signal: AbortSignal): AsyncGenerator<RunEvent> {
    const res = await fetch(url(appConfig.endpoints.runStream, { id }), {
      credentials: appConfig.http.credentials,
      headers: { Accept: "text/event-stream" },
      signal,
    });
    if (!res.ok || !res.body) {
      throw new ApiError(`Stream failed: ${res.statusText}`, res.status);
    }

    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    try {
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        // SSE messages are separated by a blank line
        const messages = buffer.split("\n\n");
        buffer = messages.pop() ?? "";
        for (const message of messages) {
          for (const line of message.split("\n")) {
            if (!line.startsWith("data:")) continue;
            const payload = line.slice(5).trim();
            if (!payload || payload === "[DONE]") continue;
            try {
              yield JSON.parse(payload) as RunEvent;
            } catch {
              // skip malformed frames rather than killing the stream
            }
          }
        }
      }
    } finally {
      reader.releaseLock();
    }
  }

  listMemory(): Promise<MemoryEntry[]> {
    return request(appConfig.endpoints.memory);
  }

  saveMemoryEntry(
    entry: Pick<MemoryEntry, "tier" | "title" | "content"> & { id?: string },
  ): Promise<MemoryEntry> {
    if (entry.id) {
      return request(appConfig.endpoints.memoryEntry, {
        method: "PUT",
        params: { id: entry.id },
        body: JSON.stringify(entry),
      });
    }
    return request(appConfig.endpoints.memory, {
      method: "POST",
      body: JSON.stringify(entry),
    });
  }

  async uploadMemoryFiles(files: File[]): Promise<MemoryEntry[]> {
    // multipart: build FormData and let the browser set the boundary
    // header (the json request() helper would corrupt it)
    const form = new FormData();
    for (const file of files) form.append("files", file, file.name);
    const res = await fetch(url(appConfig.endpoints.memoryUpload), {
      method: "POST",
      credentials: appConfig.http.credentials,
      body: form,
    });
    if (!res.ok) {
      let message = res.statusText;
      try {
        message = errorMessage(await res.json(), message);
      } catch {
        // non-JSON error body
      }
      throw new ApiError(message, res.status);
    }
    return (await res.json()) as MemoryEntry[];
  }

  async deleteMemoryEntry(id: string): Promise<void> {
    await request(appConfig.endpoints.memoryEntry, {
      method: "DELETE",
      params: { id },
    });
  }

  startCheckout(planId: PlanId): Promise<{ url?: string }> {
    return request(appConfig.endpoints.checkout, {
      method: "POST",
      body: JSON.stringify({ planId }),
    });
  }

  openBillingPortal(): Promise<{ url?: string }> {
    return request(appConfig.endpoints.billingPortal, { method: "POST" });
  }

  getUsage(): Promise<UsageSummary> {
    return request(appConfig.endpoints.usage);
  }

  getModelConfig(): Promise<LayerModelConfig[]> {
    return request(appConfig.endpoints.modelConfig);
  }

  async setModelLayer(layer: string, model: string): Promise<void> {
    await request(appConfig.endpoints.modelConfig, {
      method: "PUT",
      body: JSON.stringify({ layer, model }),
    });
  }
}
