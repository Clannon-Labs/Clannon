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
        message = body.detail ?? body.message ?? message;
        code = body.code;
      } catch {
        // non-JSON error body; keep statusText
      }
      throw new ApiError(message, res.status, code);
    }
    if (res.status === 204) return undefined as T;
    return (await res.json()) as T;
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

  createRun(brief: string): Promise<{ id: string }> {
    return request(appConfig.endpoints.createRun, {
      method: "POST",
      body: JSON.stringify({ brief }),
    });
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
        const body = await res.json();
        message = body.detail ?? body.message ?? message;
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
