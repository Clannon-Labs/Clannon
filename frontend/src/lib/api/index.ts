import { appConfig } from "@/config/app.config";
import type { ClannonClient } from "./client";
import { HttpClient } from "./http";
import { MockClient } from "./mock";

export type { ClannonClient } from "./client";
export * from "./types";

let instance: ClannonClient | null = null;

export function getClient(): ClannonClient {
  if (!instance) {
    instance = appConfig.apiMode === "http" ? new HttpClient() : new MockClient();
  }
  return instance;
}
