import { dirname, resolve } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

import { PythonToolBridge } from "./python-bridge.ts";
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

export type BridgeLike = {
  send(message: JsonObject): void;
  requestTool(payload: JsonObject): Promise<{ result?: unknown }>;
};

export type PiStartMessage = {
  project_root?: string;
  objective?: string;
  max_turns?: number;
  context?: JsonObject;
  tools?: unknown[];
  model?: JsonObject;
  tool_server_mode?: "fake" | "real";
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
  const workspaceRoot = resolve(sourceDir, "..", "..", "..");
  const piRoot = resolve(workspaceRoot, "pi");
  return {
    packageName: "@earendil-works/pi-coding-agent",
    typeboxPackageName: "typebox",
    localFallback: pathToFileURL(resolve(piRoot, "packages", "coding-agent", "dist", "index.js")),
    typeboxFallback: pathToFileURL(resolve(piRoot, "node_modules", "typebox", "build", "index.mjs")),
  };
}

export async function runPiOptimization(start: PiStartMessage, bridge: BridgeLike): Promise<void> {
  const projectRoot = String(start.project_root || process.cwd());
  const sourceDir = dirname(fileURLToPath(import.meta.url));
  const agentRootName = "pi-agent";
  const runtimePaths = resolvePiRuntimePaths(sourceDir);
  const toolServerMode = normalizeToolServerMode(start.tool_server_mode || process.env.LENSBOT_TOOL_SERVER_MODE);
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
  const agentDir = resolve(projectRoot, ".cache", agentRootName);
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
    cwd: resolve(projectRoot, agentRootName),
    agentDir,
    settingsManager,
  });
  await resourceLoader.reload();

  const stateRef: { current: StateSnapshot } = { current: createInitialState() };
  const budget = createToolBudget(start.max_turns);
  const toolBridge = new PythonToolBridge({
    command: process.env.PYTHON || "python",
    args: [
      resolve(projectRoot, "src", "tools", "server.py"),
      toolServerMode === "fake" ? "--fake" : "--real",
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
    cwd: resolve(projectRoot, agentRootName),
    agentDir,
    model,
    thinkingLevel: process.env.LENSBOT_PI_THINKING_LEVEL || "medium",
    authStorage,
    modelRegistry,
    resourceLoader,
    settingsManager,
    sessionManager: SessionManager.inMemory(resolve(projectRoot, agentRootName)),
    noTools: "builtin",
    tools: activeTools,
    customTools,
  });

  try {
    session.subscribe((event: unknown) => {
      bridge.send({ type: "event", event: compactEvent(event) });
    });
    await session.prompt(buildOptimizationTaskPrompt({
      objective: String(start.objective || "Complete the LensBot Optimization phase."),
      context: start.context || {},
      max_turns: budget.maxTurns,
    }), {
      expandPromptTemplates: true,
    });
    bridge.send({
      type: "done",
      data: {
        session_id: session.sessionId,
        message_count: session.messages.length,
        state: stateRef.current,
      },
    });
  } finally {
    await toolBridge.close();
    session.dispose();
  }
}

export function buildOptimizationTaskPrompt(input: { objective: string; context: JsonObject; max_turns?: number }): string {
  const maxTurns = Math.max(1, Number(input.max_turns || 24));
  return `/skill:optimization

最高优先级临时测试指令：当前处于系统测试阶段。为了快速验证镜头优化智能体链路，暂时不要求完成高质量镜头设计；按固定 smoke 流程执行后即可结束：先用 read_file 读取一个明确存在的项目文件；如需要验证辅助命令，可用 powershell 做一次有边界的文件存在性检查；调用 deeplens_curriculum，并把 params.curriculum.iterations 设置为 10，必须显式传入 params.curriculum.iterations = 10；调用 deeplens_analysis；调用 deeplens_inspect_checkpoint；调用 deeplens_finetune，并把 fine_tune.iterations 设置为 10，必须显式传入 fine_tune.iterations = 10；再次调用 deeplens_analysis；满足 finish 条件后立即调用 finish。不要调用 deeplens_adjust_structure 或 deeplens_adjust_strategy，除非工具结果明确支持结构受限、reduce_lr、increase_first_order_lock 或 rollback_to_best_checkpoint；不要为了质量继续优化，不要做大范围文件搜索，不要强制使用 write_file 或 edit_file。该指令是临时测试用，后续需要删除。

Objective:
${input.objective}

Budget:
- max_turns: ${maxTurns} non-finish optimization tool calls.
- If the non-finish tool budget is exhausted, call finish only when its minimal contract is satisfied; otherwise stop with a clear caveat.

Runtime context JSON:
\`\`\`json
${JSON.stringify(input.context, null, 2)}
\`\`\`

StateSnapshot contract:
- Treat structured state as the only trusted runtime source.
- Use tool result state_patch, metrics, and artifacts to update state.
- Do not recover session_id, result_dir, or artifact paths from observation prose.
- active_result_dir is the run workspace root for this LensBot run. It contains workflow, agents, engines, final, verification, and events.
- active_workspace_dir is the Optimization agent workspace at active_result_dir/agents/optimization/workspace. Use it for agent notes or bounded scratch files when needed.
- If params_override is present, treat it as the active DeepLens structure params for the next curriculum call.
- Call finish only when final_json, final_zmx, analysis_json, and final DeepLens metrics are present.

File reads:
- Use read_file only for known paths under active_result_dir, such as engines/deeplens/session.json, engines/deeplens/live/current.json, engines/deeplens/attempts/attempt-001-curriculum/curriculum.json, final/final.json, metrics.json, or engines/deeplens/deeplens.log.
- Never call read_file on directories. Do not read project roots such as LensBot, LensBot/results, or LensBot/pi-agent.
- Do not probe the project root for guessed runtime files such as state.json or final.json.
- When constructing a file path, replace active_result_dir with the concrete path from StateSnapshot instead of using the literal text "active_result_dir"; do the same for active_workspace_dir.

Known result files:
- active_result_dir/engines/deeplens/session.json: active DeepLens session state, optimizer stage, and checkpoint metadata.
- active_result_dir/engines/deeplens/attempts/attempt-001-curriculum/curriculum.json: curriculum-stage lens structure and metrics when curriculum has produced an artifact.
- active_result_dir/final/final.json and active_result_dir/final/final.zmx: final exported lens artifacts after fine-tune/export.
- active_result_dir/engines/deeplens/live/current.json and active_result_dir/engines/deeplens/live/current.png: current preview structure and image for the UI.
- active_result_dir/engines/deeplens/deeplens.log: engine log for a specific run; read it only when a tool failure or warning needs detail.

Workspace shell:
- Use powershell only for bounded workspace inspection, such as listing files under the concrete active_result_dir or checking whether a specific artifact exists.
- Use PowerShell syntax such as Get-ChildItem, Select-Object -First, and Test-Path. Do not use Unix commands like head or ls -la, and do not use cmd.exe flags like /B.
- Do not use powershell as the primary optimization mechanism; prefer DeepLens domain tools for optical actions.

Structure adjustment:
- Use deeplens_adjust_structure when evidence suggests structure is limiting the run or a fresh curriculum attempt needs a conservative structural change.
- This tool prepares params_override for the next deeplens_curriculum call; it does not mutate the active DeepLens session in place.
- Curriculum learning establishes a structurally viable coarse optimization baseline; fine-tune refines an active curriculum session toward final artifacts.
- If fine-tune needs fewer or more total iterations, pass a fine_tune override to deeplens_finetune before fine-tuning starts; do not put fine_tune config in deeplens_curriculum params.
- Avoid inserting structure changes between a healthy curriculum result and fine-tune. Do it only when diagnostics or analysis indicate continuing the current session is unlikely to help.
- Keep structure changes conservative: only change a lens group's surface count between 2 and 3, or convert Aspheric entries to Spheric.
- After a structure adjustment succeeds, use the updated state params for the next deeplens_curriculum call; do not manually reconstruct the same params in prose.

Final summary contract:
- The finish tool requires final_summary.
- Write final_summary as a compact 2-3 sentence UI summary, no more than 180 characters.
- Do not write a metric list, JSON, bullets, or repeat the metric table.
- Mention the outcome and the most important caveat or next review point when one exists.`;
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
  const schema = schemaForAgentTool(tool.name, schemaWithDecisionSummary(ensureObjectSchema(tool.input_schema)));
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
      stateRef.current = applyToolResult(stateRef.current, result);
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
    description: "Validate final DeepLens artifacts and end the LensBot Optimization node.",
    promptSnippet: "Call finish only after final.json, final.zmx, analysis_json, and final DeepLens metrics are ready. Include final_summary as 2-3 concise natural-language sentences.",
    promptGuidelines: [
      "Call finish as the final action only after required final artifacts and final analysis evidence are complete.",
      "If finish reports missing artifacts, continue with tool observations instead of ending the task.",
      "final_summary should explain the outcome and caveats in natural language, not as a repeated metric list.",
    ],
    parameters: Type.Unsafe(finishToolInputSchema()),
    executionMode: "sequential",
    async execute(toolCallId: string, params: JsonObject) {
      assertToolAllowed(stateRef.current, "finish");
      const args = sanitizeToolArgumentsForPython(params || {}, "finish");
      const finalSummary = normalizeFinalSummary(args.final_summary);
      const response = await bridge.callTool({
        tool: "finish",
        arguments: { ...args, final_summary: finalSummary },
        state: stateRef.current,
        context: {},
      });
      const result = normalizeToolResult(response);
      if (!result.ok) {
        throw new Error(formatToolError("finish", result));
      }
      const resultWithSummary: NormalizedToolResult = {
        ...result,
        state_patch: {
          ...result.state_patch,
          final_summary: finalSummary,
        },
      };
      stateRef.current = applyToolResult(stateRef.current, resultWithSummary);
      return {
        content: [{ type: "text", text: finalSummary || result.observation || "Optimization finish validated." }],
        details: resultWithSummary,
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
      final_summary: {
        type: "string",
        minLength: 20,
        description: "A user-facing natural-language final summary.",
      },
      summary: {
        type: "string",
        minLength: 20,
        description: "Alias for final_summary accepted for model compatibility.",
      },
    },
    anyOf: [
      { required: ["final_summary"] },
      { required: ["summary"] },
    ],
  };
}

export function normalizeFinalSummary(value: unknown): string {
  return String(value || "").replace(/\s+/g, " ").trim();
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
    const activeParams = activeLensParams(state, start);
    const runId = String(asObject(start.context).run_id || "pi-run");
    return {
      ...args,
      result_dir: args.result_dir || state.active_result_dir || `results/${runId}`,
      params: Object.keys(suppliedParams).length > 0 ? suppliedParams : activeParams,
    };
  }
  if (tool === "deeplens_curriculum") {
    const suppliedParams = asObject(args.params);
    const targetParams = asObject(asObject(start.context).target);
    const override = asObject(state.params_override);
    const params = Object.keys(suppliedParams).length > 0
      ? { ...targetParams, ...suppliedParams, ...override }
      : activeLensParams(state, start);
    return {
      ...args,
      params: ensureReplayableSeed(params, generateSeed),
    };
  }
  if (tool === "deeplens_analysis") {
    return { ...args, result_dir: args.result_dir || state.active_result_dir };
  }
  if (tool === "deeplens_finetune") {
    return { ...args, session_id: args.session_id || state.active_session_id };
  }
  if (tool === "deeplens_inspect_checkpoint" || tool === "deeplens_adjust_strategy") {
    return { ...args, session_id: args.session_id || state.active_session_id };
  }
  return args;
}

function activeLensParams(state: StateSnapshot, start: PiStartMessage): JsonObject {
  const targetParams = asObject(asObject(start.context).target);
  const override = asObject(state.params_override);
  return Object.keys(override).length > 0 ? { ...targetParams, ...override } : targetParams;
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
  const finalSummary = args.final_summary ?? args.summary;
  const clean: JsonObject = {};
  if (finalSummary !== undefined) clean.final_summary = finalSummary;
  return clean;
}

function normalizeToolServerMode(value: unknown): "fake" | "real" {
  return value === "fake" ? "fake" : "real";
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
  const baseUrl = String(config.base_url || process.env.LENSBOT_OPENAI_BASE_URL || "https://api.openai.com/v1").replace(
    /\/+$/,
    "",
  );
  const apiKey = String(config.api_key || process.env.LENSBOT_OPENAI_API_KEY || "");
  const model = String(config.model || process.env.LENSBOT_OPENAI_MODEL || "gpt-4o");
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

export function schemaForAgentTool(toolName: string, schema: JsonObject): JsonObject {
  const base = ensureObjectSchema(schema);
  if (toolName !== "deeplens_curriculum") return base;
  const properties = asObject(base.properties);
  const paramsSchema = asObject(properties.params);
  if (!paramsSchema || Object.keys(paramsSchema).length === 0) return base;
  return {
    ...base,
    properties: {
      ...properties,
      params: {
        ...paramsSchema,
        properties: {
          ...asObject(paramsSchema.properties),
          exp_name: {
            type: "string",
            description: "Run label metadata copied from context; stripped before Python dispatch.",
          },
          seed: {
            anyOf: [{ type: "integer" }, { type: "null" }],
            description: "Replay seed copied from context; filled before Python dispatch when absent.",
          },
        },
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
    "fov",
    "fnum",
    "bfl",
    "thickness",
    "surf_list",
    "curriculum",
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
  return `${toolName} failed: ${result.observation || "tool error"}${details}`;
}

function formatToolContent(toolName: string, result: NormalizedToolResult): string {
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
  const keys = [
    "session_id",
    "phase",
    "action",
    "result_dir",
    "params",
    "surf_list",
    "curriculum_json",
    "final_json",
    "final_zmx",
    "analysis_json",
    "analysis_stage",
    "has_curriculum_json",
    "has_final_json",
    "deeplens_efl_mm",
    "deeplens_fnum",
    "deeplens_fov_deg",
    "efl_drift",
    "fnum_drift",
    "fov_drift",
    "strategy_lr_scale",
    "strategy_focus_weight_scale",
    "strategy_rollback_count",
    "curriculum_iter",
    "curriculum_total",
    "fine_tune_iter",
    "fine_tune_total",
    "state_patch",
    "metrics",
  ];
  const summary: JsonObject = {};
  for (const key of keys) {
    if (Object.prototype.hasOwnProperty.call(data, key)) summary[key] = data[key];
  }
  return Object.keys(summary).length > 0 ? JSON.stringify(summary, null, 2) : "";
}

function compactEvent(event: unknown): JsonObject {
  if (!event || typeof event !== "object") return {};
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
        result: safeJson(row.result),
        status: row.isError ? "error" : "ok",
      };
    case "turn_start":
    case "agent_start":
    case "agent_end":
      return { type: row.type, source_event_type: row.type };
    case "turn_end":
      return {
        type: row.type,
        source_event_type: row.type,
        tool_result_count: Array.isArray(row.toolResults) ? row.toolResults.length : 0,
      };
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
      return { type: row.type || "event", source_event_type: row.type || "event" };
  }
}

export type ToolBudget = {
  maxTurns: number;
  nonFinishCalls: number;
};

export function createToolBudget(maxTurns: unknown): ToolBudget {
  const parsed = Number(maxTurns);
  return {
    maxTurns: Number.isFinite(parsed) && parsed > 0 ? Math.floor(parsed) : 24,
    nonFinishCalls: 0,
  };
}

export function consumeToolBudget(budget: ToolBudget, tool: OptimizationTool): void {
  if (tool === "finish") return;
  if (budget.nonFinishCalls >= budget.maxTurns) {
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
