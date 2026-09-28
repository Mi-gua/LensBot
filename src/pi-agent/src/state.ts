export type OptimizationPhase =
  | "running"
  | "finished";

export type AgentVerdictStatus = "pass" | "fail" | "uncertain";

export type AgentVerdict = {
  status: AgentVerdictStatus;
  reason: string;
  stop_reason: string;
  evidence: string[];
  source: "optimization_agent";
};

export type OptimizationTool =
  | "powershell"
  | "read_file"
  | "write_file"
  | "edit_file"
  | "deeplens_adjust_structure"
  | "deeplens_curriculum"
  | "deeplens_analysis"
  | "deeplens_compare_candidates"
  | "deeplens_finetune"
  | "deeplens_inspect_checkpoint"
  | "deeplens_adjust_strategy"
  | "finish";

export type ArtifactState = {
  curriculum_json: string | null;
  candidate_json: string | null;
  candidate_zmx: string | null;
  candidate_png: string | null;
  final_json: string | null;
  final_zmx: string | null;
  final_png: string | null;
  analysis_json: string | null;
};

export type MetricsState = {
  analysis_stage: string | null;
  has_curriculum_json: boolean;
  has_candidate_json: boolean;
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
  final_verdict: AgentVerdict | null;
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
    final_verdict: null,
    artifacts: {
      curriculum_json: null,
      candidate_json: null,
      candidate_zmx: null,
      candidate_png: null,
      final_json: null,
      final_zmx: null,
      final_png: null,
      analysis_json: null,
    },
    metrics: {
      analysis_stage: null,
      has_curriculum_json: false,
      has_candidate_json: false,
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
  if (!state.allowed_tools.includes(tool)) {
    throw new Error(`${tool} is not available for the current runtime facts.`);
  }
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
    "deeplens_analysis",
    "deeplens_compare_candidates",
    "deeplens_finetune",
    "deeplens_inspect_checkpoint",
    "deeplens_adjust_strategy",
    "finish",
  ];
  return withAuxiliaryTools(tools);
}
function withAuxiliaryTools(tools: OptimizationTool[]): OptimizationTool[] {
  return ["powershell", "read_file", "write_file", "edit_file", ...tools];
}
