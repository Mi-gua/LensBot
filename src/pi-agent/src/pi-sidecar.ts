#!/usr/bin/env node
import { runPiOptimization, type JsonObject } from "./pi-session.ts";

class JsonlBridge {
  private buffer = "";
  private started = false;
  private pendingStart?: {
    resolve: (message: JsonObject) => void;
    reject: (error: Error) => void;
  };
  private pendingRequests = new Map<string, {
    resolve: (message: JsonObject) => void;
    reject: (error: Error) => void;
  }>();

  constructor() {
    process.stdin.setEncoding("utf8");
    process.stdin.on("data", (chunk: string) => this.onData(chunk));
    process.stdin.on("end", () => this.rejectAll(new Error("stdin closed")));
  }

  waitForStart(): Promise<JsonObject> {
    if (this.started) throw new Error("bridge already started");
    return new Promise((resolve, reject) => {
      this.pendingStart = { resolve, reject };
    });
  }

  requestTool(payload: JsonObject): Promise<JsonObject> {
    const requestId = `tool-${Date.now()}-${Math.random().toString(16).slice(2)}`;
    this.send({ type: "tool_request", request_id: requestId, ...payload });
    return new Promise((resolve, reject) => {
      this.pendingRequests.set(requestId, { resolve, reject });
    });
  }

  send(message: JsonObject): void {
    process.stdout.write(`${JSON.stringify(message)}\n`);
  }

  private onData(chunk: string): void {
    this.buffer += chunk;
    while (true) {
      const index = this.buffer.indexOf("\n");
      if (index < 0) return;
      const line = this.buffer.slice(0, index).replace(/\r$/, "");
      this.buffer = this.buffer.slice(index + 1);
      if (!line.trim()) continue;
      this.onMessage(JSON.parse(line));
    }
  }

  private onMessage(message: JsonObject): void {
    if (message.type === "start") {
      this.started = true;
      this.pendingStart?.resolve(message);
      this.pendingStart = undefined;
      return;
    }
    if (message.type === "tool_response") {
      const requestId = String(message.request_id || "");
      const pending = this.pendingRequests.get(requestId);
      if (!pending) return;
      this.pendingRequests.delete(requestId);
      pending.resolve(message);
    }
  }

  private rejectAll(error: Error): void {
    this.pendingStart?.reject(error);
    this.pendingStart = undefined;
    for (const pending of this.pendingRequests.values()) pending.reject(error);
    this.pendingRequests.clear();
  }
}

const bridge = new JsonlBridge();

try {
  const start = await bridge.waitForStart();
  await runPiOptimization(start, bridge);
} catch (error) {
  bridge.send({
    type: "error",
    error: error instanceof Error ? error.message : String(error),
  });
  process.exitCode = 1;
}
