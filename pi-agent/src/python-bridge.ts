import { spawn, type ChildProcessWithoutNullStreams } from "node:child_process";
import type { StateSnapshot, ToolResult } from "./state.ts";

export type PythonToolBridgeOptions = {
  command: string;
  args: string[];
  cwd: string;
};

export type ToolRequest = {
  tool: string;
  arguments: Record<string, unknown>;
  state: StateSnapshot;
  context?: Record<string, unknown>;
};

type PendingRequest = {
  resolve: (result: ToolResult) => void;
  reject: (error: Error) => void;
};

export class PythonToolBridge {
  private readonly child: ChildProcessWithoutNullStreams;
  private buffer = "";
  private nextRequestId = 1;
  private pending = new Map<string, PendingRequest>();
  private stderr = "";

  constructor(options: PythonToolBridgeOptions) {
    this.child = spawn(options.command, options.args, {
      cwd: options.cwd,
      env: {
        ...process.env,
        PYTHONDONTWRITEBYTECODE: "1",
      },
      stdio: ["pipe", "pipe", "pipe"],
    });
    this.child.stdout.setEncoding("utf8");
    this.child.stderr.setEncoding("utf8");
    this.child.stdout.on("data", (chunk: string) => this.onStdout(chunk));
    this.child.stderr.on("data", (chunk: string) => {
      this.stderr += chunk;
    });
    this.child.on("error", (error: Error) => this.rejectAll(error));
    this.child.on("exit", (code: number | null) => {
      if (this.pending.size > 0) {
        this.rejectAll(new Error(`Python tool server exited with code ${code}: ${this.stderr.trim()}`));
      }
    });
  }

  callTool(request: ToolRequest): Promise<ToolResult> {
    const requestId = `tool-${this.nextRequestId++}`;
    const payload = {
      type: "tool_request",
      request_id: requestId,
      tool: request.tool,
      arguments: request.arguments,
      state: request.state,
      context: request.context || {},
    };

    return new Promise((resolve, reject) => {
      this.pending.set(requestId, { resolve, reject });
      this.child.stdin.write(`${JSON.stringify(payload)}\n`, "utf8", (error: Error | null | undefined) => {
        if (!error) return;
        this.pending.delete(requestId);
        reject(error);
      });
    });
  }

  async close(): Promise<void> {
    if (this.child.exitCode !== null) return;
    this.child.stdin.end();
    await new Promise<void>((resolve) => {
      const timeout = setTimeout(() => {
        this.child.kill();
        resolve();
      }, 1000);
      this.child.once("exit", () => {
        clearTimeout(timeout);
        resolve();
      });
    });
  }

  private onStdout(chunk: string): void {
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

  private onMessage(message: unknown): void {
    if (!message || typeof message !== "object") return;
    const row = message as {
      type?: string;
      request_id?: string;
      result?: ToolResult;
      error?: string;
    };
    if (row.type !== "tool_response" || !row.request_id) return;
    const pending = this.pending.get(row.request_id);
    if (!pending) return;
    this.pending.delete(row.request_id);
    if (row.result) {
      pending.resolve(row.result);
    } else {
      pending.reject(new Error(row.error || "Python tool server returned no result."));
    }
  }

  private rejectAll(error: Error): void {
    for (const pending of this.pending.values()) {
      pending.reject(error);
    }
    this.pending.clear();
  }
}
