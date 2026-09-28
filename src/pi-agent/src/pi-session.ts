import { dirname, resolve } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

import { PythonToolBridge } from "./python-bridge.ts";
import { resolveExecutionParams } from "./execution-params.ts";
import {
  applyToolResult,
  assertToolAllowed,
  createInitialState,
  type OptimizationTool,
  type StateSnapshot,
  type ToolArtifact,
  type ToolResult,
} from "./state.ts";

export type JsonObject = Record<string, unknown>;
export { resolveExecutionParams } from "./execution-params.ts";

export const RECOMMENDED_REVIEW_TURNS = 50;

export type BridgeLike = {
  send(message: JsonObject): void;
  requestTool(payload: JsonObject): Promise<{ result?: unknown }>;
};

export type PiStartMessage = {
  project_root?: string;
  objective?: string;
  max_turns?: number | null;
  context?: JsonObject;
  tools?: unknown[];
  model?: JsonObject;
};

export type NormalizedToolResult = {
  ok: boolean;
  observation: string;
  data: unknown;
  state_patch: JsonObject;
  metrics: JsonObject;
  artifacts: ToolArtifact[];
  error: unknown;
  metadata: JsonObject;
} & ToolResult;

export function resolvePiRuntimePaths(sourceDir: string): {
  packageName: string;
  typeboxPackageName: string;
  localFallback: URL;
  typeboxFallback: URL;
} {
  const workspaceRoot = resolve(sourceDir, "..", "..", "..", "..");
  const piRoot = resolve(workspaceRoot, "pi");
  return {
    packageName: "@earendil-works/pi-coding-agent",
    typeboxPackageName: "typebox",
    localFallback: pathToFileURL(resolve(piRoot, "packages", "coding-agent", "dist", "index.js")),
    typeboxFallback: pathToFileURL(resolve(piRoot, "node_modules", "typebox", "build", "index.mjs")),
  };
}

export async function runPiOptimization(start: PiStartMessage, bridge: BridgeLike): Promise<void> {
  const projectRoot = resolve(String(start.project_root || process.cwd()));
  const sourceDir = dirname(fileURLToPath(import.meta.url));
  const runtimePaths = resolvePiRuntimePaths(sourceDir);
  const piAgentRoot = resolve(projectRoot, "src", "pi-agent");
  const agentDir = resolve(projectRoot, ".cache", "pi-agent");
  const {
    AuthStorage,
    createAgentSession,
    DefaultResourceLoader,
    defineTool,
    ModelRegistry,
    SessionManager,
    SettingsManager,
  } = await importPiCodingAgent(runtimePaths) as Record<string, any>;
  const { Type } = await importTypebox(runtimePaths) as Record<string, any>;

  const modelConfig = normalizeModelConfig(start.model || {});
  const provider = "lensbot-openai";
  const model = {
    id: modelConfig.model,
    name: modelConfig.model,
    provider,
    api: "openai-completions",
    baseUrl: modelConfig.baseUrl,
    reasoning: false,
    input: ["text"],
    cost: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0 },
    contextWindow: numberFromEnv("LENSBOT_PI_CONTEXT_WINDOW", 128000),
    maxTokens: numberFromEnv("LENSBOT_PI_MAX_TOKENS", 8192),
  };

  const authStorage = AuthStorage.create(resolve(agentDir, "auth.json"));
  authStorage.setRuntimeApiKey(provider, modelConfig.apiKey);
  const modelRegistry = ModelRegistry.inMemory(authStorage);
  const settingsManager = SettingsManager.inMemory({
    retry: { enabled: true, maxRetries: 2 },
    compaction: { enabled: true },
  });
  const resourceLoader = new DefaultResourceLoader({
    cwd: projectRoot,
    agentDir,
    systemPrompt: resolve(piAgentRoot, "SYSTEM.md"),
    additionalSkillPaths: [resolve(piAgentRoot, "skills")],
    settingsManager,
  });
  await resourceLoader.reload();

  const stateRef: { current: StateSnapshot } = { current: createInitialState() };
  const budget = createToolBudget(start.max_turns);
  const toolBridge = new PythonToolBridge({
    command: process.env.PYTHON || "python",
    args: [
      resolve(projectRoot, "src", "tools", "server.py"),
      "--project-root",
      projectRoot,
    ],
    cwd: projectRoot,
  });

  const customTools = [
    ...normalizeTools(start.tools).map((tool) => createBridgeTool(tool, toolBridge, defineTool, Type, stateRef, start, budget)),
    createFinishTool(toolBridge, defineTool, Type, stateRef),
  ];
  const activeTools = customTools.map((tool) => (tool as { name: string }).name);
  const { session } = await createAgentSession({
    cwd: projectRoot,
    agentDir,
    model,
    thinkingLevel: process.env.LENSBOT_PI_THINKING_LEVEL || "medium",
    authStorage,
    modelRegistry,
    resourceLoader,
    settingsManager,
    sessionManager: SessionManager.inMemory(piAgentRoot),
    noTools: "builtin",
    tools: activeTools,
    customTools,
  });

  try {
    session.subscribe((event: unknown) => {
      const compact = compactEvent(event);
      if (compact?.type === "tool_execution_end") compact.state = stateRef.current;
      if (compact) bridge.send({ type: "event", event: compact });
    });
    await session.prompt(buildOptimizationTaskPrompt({
      project_root: projectRoot,
      objective: String(start.objective || "Complete the LensBot Optimization phase."),
      context: start.context || {},
      max_turns: budget.maxTurns,
    }), { expandPromptTemplates: true });
    const lastAssistant = [...session.messages].reverse().find((message: any) => message.role === "assistant");
    const error = stateRef.current.phase === "finished" ? "" :
      lastAssistant?.errorMessage || "Optimization session returned without finish.";
    bridge.send({
      type: "done",
      data: {
        session_id: session.sessionId,
        message_count: session.messages.length,
        state: stateRef.current,
        error,
      },
    });
  } finally {
    await toolBridge.close();
    session.dispose();
  }
}

export function buildOptimizationTaskPrompt(input: { project_root: string; objective: string; context: JsonObject; max_turns?: number | null }): string {
  const explicitLimit = normalizeMaxTurns(input.max_turns);
  const effortPolicy = asObject(input.context.effort_policy);
  const reviewPoint = Number(effortPolicy.recommended_review_point || RECOMMENDED_REVIEW_TURNS);
  const budgetText = explicitLimit === null
    ? `- No user-specified tool-call limit is active. The ${reviewPoint} call value is a general review point, not a target or authorization to keep working.\n- Choose effort adaptively from uncertainty, observed progress, and the value of the next experiment.`
    : `- The user supplied a hard limit of ${explicitLimit} non-finish tool calls.\n- If it is exhausted, finish only when the artifact/evidence contract is satisfied; otherwise fail honestly.`;
  // Pi separates the skill name from its arguments with a literal space.
  return `/skill:optimization Follow the LensBot Optimization system prompt and the optimization skill.

Workspace root: ${JSON.stringify(input.project_root)}
Resolve relative file and command paths against this root. Keep all agent-issued
file operations and command execution inside it, including command working
directories and paths accessed by scripts. Use the supplied domain tools for
configured engine execution.

The runtime context below is the completed Intake/Seeding handoff. Use
design_contract, execution_params, and initial_structures as the basis for a
brief optical assessment before initialization. Compare relevant candidate
tradeoffs, identify the main risk, and explain the intended first experiment.
Use targeted reference reading or tools when a missing fact would affect that
decision, then begin curriculum when the starting choice is sufficiently
supported. Memory supplies historical guidance only. Reuse the supplied context
rather than rediscovering it through directory scans or historical-run audits.
If a required field is missing or contradictory, identify that specific blocker.

Objective:
${input.objective}

Effort policy:
${budgetText}
- A suggested stage iteration count is a starting hypothesis, not a requirement. State what a repeated expensive run will test.
- Stopping because effort is no longer worthwhile is not the same as an optical pass.

Runtime context JSON:
\`\`\`json
${JSON.stringify(input.context, null, 2)}
\`\`\``;
}

export function normalizeToolResult(value: unknown): NormalizedToolResult {
  if (!value || typeof value !== "object") {
    return {
      ok: false,
      observation: "Tool bridge returned an invalid result.",
      data: value,
      state_patch: {},
      metrics: {},
      artifacts: [],
      error: undefined,
      metadata: {},
    };
  }
  const result = value as JsonObject;
  return {
    ok: Boolean(result.ok),
    observation: String(result.observation || result.message || ""),
    data: result.data,
    state_patch: asObject(result.state_patch),
    metrics: asObject(result.metrics),
    artifacts: Array.isArray(result.artifacts) ? result.artifacts.filter(isToolArtifact) : [],
    error: result.error,
    metadata: asObject(result.metadata),
  };
}

function createBridgeTool(
  tool: NormalizedToolDefinition,
  bridge: PythonToolBridge,
  defineTool: Callable,
  Type: TypeboxLike,
  stateRef: { current: StateSnapshot },
  start: PiStartMessage,
  budget: ToolBudget,
): unknown {
  const schema = schemaWithDecisionSummary(ensureObjectSchema(tool.input_schema));
  return defineTool({
    name: tool.name,
    label: tool.label || tool.name,
    description: tool.description || tool.name,
    promptSnippet: tool.prompt_snippet || tool.description || tool.name,
    parameters: Type.Unsafe(schema),
    executionMode: "sequential",
    async execute(toolCallId: string, params: JsonObject) {
      const toolName = tool.name as OptimizationTool;
      const args = trustedArguments(toolName, params || {}, stateRef.current, start);
      assertToolAllowed(stateRef.current, toolName);
      consumeToolBudget(budget, toolName);
      const response = await bridge.callTool({
        tool: tool.name,
        arguments: args,
        state: stateRef.current,
        context: start.context || {},
      });
      const result = normalizeToolResult(response);
      if (!result.ok) {
        throw new Error(formatToolError(tool.name, result));
      }
      const baseState = toolName === "deeplens_curriculum" ? createInitialState() : stateRef.current;
      stateRef.current = applyToolResult(baseState, result);
      return {
        content: [{ type: "text", text: formatToolContent(tool.name, result) }],
        details: result,
      };
    },
  });
}

function createFinishTool(
  bridge: PythonToolBridge,
  defineTool: Callable,
  Type: TypeboxLike,
  stateRef: { current: StateSnapshot },
): unknown {
  return defineTool({
    name: "finish",
    label: "Finish",
    description: "Validate chosen DeepLens artifacts, promote a candidate when needed, and end the LensBot Optimization node.",
    promptSnippet: "Call finish only after a chosen candidate or final lens has analysis evidence. Submit optical status and reason, an independent stop_reason, and evidence keys.",
    promptGuidelines: [
      "Call finish as the final action only after a chosen candidate or final lens has analysis evidence.",
      "If finish reports missing artifacts, continue with tool observations instead of ending the task.",
      "You judge optical quality. Python validates artifacts, matching analysis and evidence, and rejects pass for measured violations of explicit user constraints; missing tolerances do not create automatic thresholds.",
      "verdict.reason should concisely explain the outcome and decisive caveats without repeating a raw metric list.",
      "verdict.stop_reason should explain why optimization stops now, independently of whether the lens passes, fails, or remains uncertain.",
    ],
    parameters: Type.Unsafe(finishToolInputSchema()),
    executionMode: "sequential",
    async execute(toolCallId: string, params: JsonObject) {
      assertToolAllowed(stateRef.current, "finish");
      const args = sanitizeToolArgumentsForPython(params || {}, "finish");
      const response = await bridge.callTool({
        tool: "finish",
        arguments: args,
        state: stateRef.current,
        context: {},
      });
      const result = normalizeToolResult(response);
      if (!result.ok) {
        throw new Error(formatToolError("finish", result));
      }
      stateRef.current = applyToolResult(stateRef.current, result);
      return {
        content: [{ type: "text", text: stateRef.current.final_verdict?.reason || result.observation }],
        details: result,
        terminate: true,
      };
    },
  });
}

export function finishToolInputSchema(): JsonObject {
  return {
    type: "object",
    additionalProperties: false,
    properties: {
      verdict: {
        type: "object",
        additionalProperties: false,
        properties: {
          status: {
            type: "string",
            enum: ["pass", "fail", "uncertain"],
            description: "The Agent's optical judgment based on the prompt and observed evidence.",
          },
          reason: {
            type: "string",
            minLength: 20,
            description: "A concise outcome and caveat summary; do not repeat the full metric list.",
          },
          stop_reason: {
            type: "string",
            minLength: 12,
            description: "Why optimization stops now; keep this independent from the optical status.",
          },
          evidence: {
            type: "array",
            items: { type: "string", minLength: 1 },
            minItems: 1,
            maxItems: 8,
            uniqueItems: true,
            description: "Metric or artifact keys that directly support the verdict.",
          },
        },
        required: ["status", "reason", "stop_reason", "evidence"],
      },
    },
    required: ["verdict"],
  };
}



export function trustedArguments(
  tool: OptimizationTool,
  args: JsonObject,
  state: StateSnapshot,
  start: PiStartMessage,
  generateSeed: () => number = randomReplaySeed,
): Record<string, unknown> {
  args = sanitizeToolArgumentsForPython(args, tool);
  if (tool === "deeplens_adjust_structure") {
    const suppliedParams = asObject(args.params);
    const runId = String(asObject(start.context).run_id || "pi-run");
    return {
      ...args,
      result_dir: args.result_dir || state.active_result_dir || `results/${runId}`,
      params: resolveExecutionParams(asObject(start.context), asObject(state.params_override), suppliedParams),
    };
  }
  if (tool === "deeplens_curriculum") {
    const suppliedParams = asObject(args.params);
    const params = resolveExecutionParams(asObject(start.context), asObject(state.params_override), suppliedParams);
    return {
      ...args,
      params: ensureReplayableSeed(params, generateSeed),
    };
  }
  if (tool === "deeplens_analysis") {
    return {
      ...args,
      result_dir: args.result_dir || state.active_result_dir,
      lens_json: args.lens_json || bestLensArtifact(state),
    };
  }
  if (tool === "deeplens_finetune") {
    const activeSessionId = state.active_session_id;
    const hasLiveSession = Boolean(activeSessionId);
    const fallbackLens = !hasLiveSession && !args.lens_json ? bestLensArtifact(state) : undefined;
    const lensJson = args.lens_json || fallbackLens;
    return {
      session_id: activeSessionId,
      result_dir: args.result_dir || state.active_result_dir,
      ...(lensJson ? { lens_json: lensJson } : {}),
      ...(args.fine_tune ? { fine_tune: args.fine_tune } : {}),
    };
  }
  if (tool === "deeplens_inspect_checkpoint" || tool === "deeplens_adjust_strategy") {
    return {
      ...args,
      session_id: args.session_id || state.active_session_id,
      result_dir: args.result_dir || state.active_result_dir,
      lens_json: args.lens_json || bestLensArtifact(state),
    };
  }
  return args;
}

function bestLensArtifact(state: StateSnapshot): string | undefined {
  return state.artifacts.candidate_json || state.artifacts.final_json || state.artifacts.curriculum_json || undefined;
}

export function sanitizeToolArgumentsForPython(args: JsonObject, tool?: string): JsonObject {
  const sanitized = stripDecisionSummary(args);
  if (tool === "finish") {
    return normalizeFinishArguments(sanitized);
  }
  if (tool === "deeplens_curriculum") {
    return sanitizeCurriculumArguments(sanitized);
  }
  return sanitized;
}

function normalizeFinishArguments(args: JsonObject): JsonObject {
  return args.verdict === undefined ? {} : { verdict: args.verdict };
}

type Callable = (definition: JsonObject) => unknown;
type TypeboxLike = {
  Object(shape: JsonObject): unknown;
  Unsafe(schema: JsonObject): unknown;
};

type NormalizedToolDefinition = {
  name: string;
  label: string;
  description: string;
  input_schema: JsonObject;
  output_schema: JsonObject;
  prompt_snippet?: string;
};

function normalizeModelConfig(config: JsonObject): { baseUrl: string; apiKey: string; model: string } {
  const baseUrl = String(config.base_url || process.env.LENSBOT_OPENAI_BASE_URL || "https://api.deepseek.com").replace(
    /\/+$/,
    "",
  );
  const apiKey = String(config.api_key || process.env.LENSBOT_OPENAI_API_KEY || "");
  const model = String(config.model || process.env.LENSBOT_OPENAI_MODEL || "deepseek-flash");
  if (!apiKey) {
    throw new Error("LENSBOT_OPENAI_API_KEY is required for pi optimization.");
  }
  return { baseUrl, apiKey, model };
}

function normalizeTools(value: unknown): NormalizedToolDefinition[] {
  if (!Array.isArray(value)) return [];
  return value
    .filter((tool): tool is JsonObject => Boolean(tool && typeof tool === "object" && !Array.isArray(tool) && "name" in tool))
    .map((tool) => ({
      name: String(tool.name),
      label: String(tool.label || tool.name),
      description: String(tool.description || tool.name),
      input_schema: asObject(tool.input_schema || asObject(tool.schema).input),
      output_schema: asObject(tool.output_schema || asObject(tool.schema).output),
      prompt_snippet: String(asObject(asObject(tool.metadata).pi).prompt_snippet || ""),
    }));
}

function ensureObjectSchema(schema: JsonObject): JsonObject {
  if (!schema || typeof schema !== "object" || Array.isArray(schema)) {
    return { type: "object", properties: {}, additionalProperties: false };
  }
  if (!schema.type) {
    return { type: "object", properties: {}, additionalProperties: true, ...schema };
  }
  return schema;
}

export function schemaWithDecisionSummary(schema: JsonObject): JsonObject {
  const base = ensureObjectSchema(schema);
  const properties = asObject(base.properties);
  return {
    ...base,
    properties: {
      ...properties,
      decision_summary: {
        type: "string",
        description: "User-visible decision summary for the trace; stripped before Python tool dispatch.",
      },
    },
  };
}

function sanitizeCurriculumArguments(args: JsonObject): JsonObject {
  const params = asObject(args.params);
  if (Object.keys(params).length === 0) return args;
  const allowed = new Set([
    "exp_name",
    "seed",
    "foclen",
    "imgh",
    "fov",
    "fnum",
    "bfl",
    "thickness",
    "surf_list",
    "curriculum",
    "fine_tune",
    "_meta",
  ]);
  const cleanParams: JsonObject = {};
  for (const [key, value] of Object.entries(params)) {
    if (allowed.has(key)) cleanParams[key] = value;
  }
  return { ...args, params: cleanParams };
}

export function ensureReplayableSeed(params: JsonObject, generateSeed: () => number = randomReplaySeed): JsonObject {
  const seed = params.seed;
  if (typeof seed === "number" && Number.isInteger(seed)) {
    return params;
  }
  return { ...params, seed: generateSeed() };
}

function randomReplaySeed(): number {
  return Math.floor(Math.random() * 100001);
}

function formatToolError(toolName: string, result: NormalizedToolResult): string {
  const details = result.error ? ` ${JSON.stringify(result.error)}` : "";
  return `${toolName} failed: ${formatToolContent(toolName, result)}${details}`;
}

export function formatToolContent(toolName: string, result: NormalizedToolResult): string {
  const observation = result.observation || `${toolName} completed.`;
  const summary = summarizeToolData({
    ...(asObject(result.data)),
    state_patch: result.state_patch,
    metrics: result.metrics,
  });
  if (!summary) return observation;
  return `${observation}\nTool data summary:\n${summary}`;
}

function summarizeToolData(data: JsonObject): string {
  // Preserve schema-defined evidence for the agent while bounding context use.
  const text = JSON.stringify(data, null, 2);
  const limit = 32000;
  return text.length <= limit ? text : `${text.slice(0, limit)}\n[Tool data truncated at ${limit} characters; request a narrower query or a subsequent file page.]`;
}

export function compactEvent(event: unknown): JsonObject | null {
  if (!event || typeof event !== "object") return null;
  const row = event as JsonObject;
  switch (row.type) {
    case "tool_execution_start":
      const startArgs = asObject(row.args);
      return {
        type: row.type,
        source_event_type: row.type,
        tool_call_id: row.toolCallId,
        tool_name: row.toolName,
        args: stripDecisionSummary(startArgs),
        decision_summary: stringValue(startArgs.decision_summary),
        thought: stringValue(startArgs.decision_summary),
        status: "running",
      };
    case "tool_execution_update":
      return {
        type: row.type,
        source_event_type: row.type,
        tool_call_id: row.toolCallId,
        tool_name: row.toolName,
        args: stripDecisionSummary(asObject(row.args)),
        partial_result: safeJson(row.partialResult),
        status: "running",
      };
    case "tool_execution_end":
      return {
        type: row.type,
        source_event_type: row.type,
        tool_call_id: row.toolCallId,
        tool_name: row.toolName,
        is_error: Boolean(row.isError),
        result: compactToolResultForTrace(row.result),
        status: row.isError ? "error" : "ok",
      };
    case "turn_start":
      return { type: row.type, source_event_type: row.type };
    case "turn_end": {
      const turnMessage = asObject(row.message);
      return {
        type: row.type,
        source_event_type: row.type,
        turn_index: row.turnIndex,
        tool_result_count: Array.isArray(row.toolResults) ? row.toolResults.length : 0,
        usage: safeJson(turnMessage.usage),
      };
    }
    case "message_update": {
      const update = asObject(row.assistantMessageEvent);
      const updateType = String(update.type || "");
      const contentType = updateType.includes("_") ? updateType.split("_")[0] : updateType;
      return {
        type: row.type,
        source_event_type: row.type,
        update_type: updateType,
        assistant_event_type: updateType,
        content_type: contentType || undefined,
        content_index: update.contentIndex,
        delta: updateType === "text_delta" ? update.delta : undefined,
        delta_length: typeof update.delta === "string" ? update.delta.length : undefined,
        tool_call_id: update.id,
        tool_name: update.toolName,
        stop_reason: update.reason,
      };
    }
    default:
      return null;
  }
}

export type ToolBudget = {
  maxTurns: number | null;
  nonFinishCalls: number;
};

export function createToolBudget(maxTurns: unknown): ToolBudget {
  return {
    maxTurns: normalizeMaxTurns(maxTurns),
    nonFinishCalls: 0,
  };
}

function compactToolResultForTrace(value: unknown): JsonObject {
  const result = asObject(safeJson(value));
  const details = asObject(result.details);
  const compactDetails: JsonObject = {};
  for (const key of ["ok", "observation", "state_patch", "metrics", "artifacts", "error", "metadata"]) {
    if (Object.prototype.hasOwnProperty.call(details, key)) compactDetails[key] = details[key];
  }
  return Object.keys(compactDetails).length > 0 ? { details: compactDetails } : {
    observation: result.observation || result.message || (Array.isArray(result.content)
      ? result.content.map((block) => asObject(block)).filter((block) => block.type === "text")
        .map((block) => stringValue(block.text)).filter(Boolean).join("\n")
      : undefined),
  };
}

function normalizeMaxTurns(value: unknown): number | null {
  if (value === undefined || value === null || value === "") return null;
  const parsed = Number(value);
  return Number.isFinite(parsed) && parsed > 0
    ? Math.floor(parsed)
    : null;
}

export function consumeToolBudget(budget: ToolBudget, tool: OptimizationTool): void {
  if (tool === "finish") return;
  if (budget.maxTurns !== null && budget.nonFinishCalls >= budget.maxTurns) {
    throw new Error(`Optimization tool budget exceeded: max_turns=${budget.maxTurns} non-finish tool calls.`);
  }
  budget.nonFinishCalls += 1;
}

function stripDecisionSummary(args: JsonObject): JsonObject {
  const clean: JsonObject = {};
  for (const [key, value] of Object.entries(args || {})) {
    if (key !== "decision_summary") clean[key] = value;
  }
  return clean;
}

function stringValue(value: unknown): string | undefined {
  return typeof value === "string" && value.trim() ? value : undefined;
}

function safeJson(value: unknown): unknown {
  return JSON.parse(JSON.stringify(value, (_key, item) => {
    if (item instanceof Error) return { name: item.name, message: item.message };
    return item;
  }));
}

function asObject(value: unknown): JsonObject {
  return value && typeof value === "object" && !Array.isArray(value) ? value as JsonObject : {};
}

function isObject(value: unknown): value is JsonObject {
  return Boolean(value && typeof value === "object" && !Array.isArray(value));
}

function isToolArtifact(value: unknown): value is ToolArtifact {
  return isObject(value) && typeof value.path === "string";
}

function numberFromEnv(name: string, fallback: number): number {
  const value = Number(process.env[name]);
  return Number.isFinite(value) && value > 0 ? value : fallback;
}

async function importPiCodingAgent(paths = resolvePiRuntimePaths(dirname(fileURLToPath(import.meta.url)))): Promise<JsonObject> {
  try {
    return await import(paths.packageName);
  } catch (_error) {
    return await import(paths.localFallback.href);
  }
}

async function importTypebox(paths = resolvePiRuntimePaths(dirname(fileURLToPath(import.meta.url)))): Promise<JsonObject> {
  try {
    return await import(paths.typeboxPackageName);
  } catch (_error) {
    return await import(paths.typeboxFallback.href);
  }
}
