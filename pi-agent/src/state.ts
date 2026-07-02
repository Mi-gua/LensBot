export type OptimizationPhase =
  | "running"
  | "finished";

export type OptimizationTool =
  | "powershell"
  | "read_file"
  | "write_file"
  | "edit_file"
  | "deeplens_adjust_structure"
  | "deeplens_curriculum"
  | "deeplens_analysis"
  | "deeplens_finetune"
  | "deeplens_inspect_checkpoint"
  | "deeplens_adjust_strategy"
  | "finish";

export type ArtifactState = {
  curriculum_json: string | null;
  final_json: string | null;
  final_zmx: string | null;
  analysis_json: string | null;
};

export type MetricsState = {
  analysis_stage: string | null;
  has_curriculum_json: boolean;
  has_final_json: boolean;
  [key: string]: unknown;
};

export type ParamsOverride = Record<string, unknown>;

export type StateSnapshot = {
  phase: OptimizationPhase;
  active_seed_id: string | null;
  active_session_id: string | null;
  active_result_dir: string | null;
  active_workspace_dir: string | null;
  params_override: ParamsOverride | null;
  final_summary: string | null;
  artifacts: ArtifactState;
  metrics: MetricsState;
  allowed_tools: OptimizationTool[];
  warnings: string[];
};

export type StatePatch = Partial<
  Omit<StateSnapshot, "artifacts" | "metrics" | "allowed_tools" | "warnings">
> & {
  artifacts?: Partial<ArtifactState>;
  metrics?: Partial<MetricsState>;
  warnings?: string[];
};

export type ToolArtifact = {
  path: string;
  kind?: string;
  label?: string;
  source?: string;
  role?: string;
  stage?: string;
  preview?: boolean;
  order?: number;
  metadata?: Record<string, unknown>;
};

export type ToolResult = {
  ok: boolean;
  observation: string;
  state_patch?: StatePatch;
  metrics?: Partial<MetricsState>;
  artifacts?: ToolArtifact[];
  error?: unknown;
};

export function createInitialState(): StateSnapshot {
  return withAllowedTools({
    phase: "running",
    active_seed_id: null,
    active_session_id: null,
    active_result_dir: null,
    active_workspace_dir: null,
    params_override: null,
    final_summary: null,
    artifacts: {
      curriculum_json: null,
      final_json: null,
      final_zmx: null,
      analysis_json: null,
    },
    metrics: {
      analysis_stage: null,
      has_curriculum_json: false,
      has_final_json: false,
    },
    allowed_tools: [],
    warnings: [],
  });
}

export function applyToolResult(state: StateSnapshot, result: ToolResult): StateSnapshot {
  const patch = result.state_patch ?? {};
  const next: StateSnapshot = {
    ...state,
    ...patch,
    artifacts: {
      ...state.artifacts,
      ...(patch.artifacts ?? {}),
    },
    metrics: {
      ...state.metrics,
      ...(patch.metrics ?? {}),
      ...(result.metrics ?? {}),
    },
    warnings: [
      ...state.warnings,
      ...(patch.warnings ?? []),
    ],
    allowed_tools: [],
  };
  if (!next.active_workspace_dir && next.active_result_dir) {
    next.active_workspace_dir = `${next.active_result_dir.replace(/[\\/]+$/, "")}/agents/optimization/workspace`;
  }

  return withAllowedTools(next);
}

export function assertToolAllowed(state: StateSnapshot, tool: OptimizationTool): void {
  if (state.phase === "finished") {
    throw new Error(`${tool} is not available after finish.`);
  }
  if (tool === "deeplens_analysis" && !state.active_result_dir) {
    throw new Error("deeplens_analysis requires active_result_dir from a prior tool result.");
  }
  if (tool === "deeplens_finetune" && !state.active_session_id) {
    throw new Error("deeplens_finetune requires active_session_id from a prior tool result.");
  }
  if ((tool === "deeplens_inspect_checkpoint" || tool === "deeplens_adjust_strategy") && !state.active_session_id) {
    throw new Error(`${tool} requires active_session_id from a prior tool result.`);
  }
  if (tool === "finish") {
    validateFinish(state);
    return;
  }
  if (!state.allowed_tools.includes(tool)) {
    throw new Error(`${tool} is not available for the current runtime facts.`);
  }
}

export function validateFinish(state: StateSnapshot): { ok: true; observation: string } {
  const missing: string[] = [];
  if (!state.artifacts.final_json) missing.push("final_json");
  if (!state.artifacts.final_zmx) missing.push("final_zmx");
  if (!state.artifacts.analysis_json) missing.push("analysis_json");
  if (missing.length > 0) {
    throw new Error(`finish requires ${missing.join(", ")}.`);
  }
  if (state.metrics.analysis_stage !== "final" || state.metrics.has_final_json !== true) {
    throw new Error("finish requires final DeepLens metrics.");
  }
  return { ok: true, observation: "Optimization finish validated." };
}

function withAllowedTools(state: StateSnapshot): StateSnapshot {
  return {
    ...state,
    allowed_tools: allowedToolsFor(state),
  };
}

function allowedToolsFor(state: StateSnapshot): OptimizationTool[] {
  if (state.phase === "finished") return [];

  const tools: OptimizationTool[] = [
    "deeplens_adjust_structure",
    "deeplens_curriculum",
  ];
  if (canAnalyze(state)) tools.push("deeplens_analysis");
  if (canFineTune(state)) tools.push("deeplens_finetune");
  if (canInspectCheckpoint(state)) tools.push("deeplens_inspect_checkpoint");
  if (canAdjustStrategy(state)) tools.push("deeplens_adjust_strategy");
  if (canFinish(state)) tools.push("finish");
  return withAuxiliaryTools(tools);
}

export function canAnalyze(state: StateSnapshot): boolean {
  return state.phase === "running" && Boolean(state.active_result_dir);
}

export function canFineTune(state: StateSnapshot): boolean {
  return state.phase === "running" && Boolean(state.active_session_id);
}

export function canInspectCheckpoint(state: StateSnapshot): boolean {
  return state.phase === "running" && Boolean(state.active_session_id);
}

export function canAdjustStrategy(state: StateSnapshot): boolean {
  return state.phase === "running" && Boolean(state.active_session_id);
}

export function canFinish(state: StateSnapshot): boolean {
  try {
    validateFinish(state);
    return true;
  } catch (_error) {
    return false;
  }
}

function withAuxiliaryTools(tools: OptimizationTool[]): OptimizationTool[] {
  return ["powershell", "read_file", "write_file", "edit_file", ...tools];
}
