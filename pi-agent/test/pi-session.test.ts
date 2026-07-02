import assert from "node:assert/strict";
import test from "node:test";

import {
  buildOptimizationTaskPrompt,
  consumeToolBudget,
  createToolBudget,
  finishToolInputSchema,
  normalizeFinalSummary,
  sanitizeToolArgumentsForPython,
  schemaForAgentTool,
  schemaWithDecisionSummary,
  trustedArguments,
} from "../src/pi-session.ts";
import { assertToolAllowed, applyToolResult, createInitialState, validateFinish } from "../src/state.ts";

test("optimization prompt exposes the hard non-finish tool budget", () => {
  const prompt = buildOptimizationTaskPrompt({
    objective: "Optimize a lens.",
    context: { run_id: "run-1" },
    max_turns: 7,
  });

  assert.match(prompt, /max_turns/i);
  assert.match(prompt, /7/);
  assert.match(prompt, /non-finish/i);
  assert.match(prompt, /最高优先级临时测试指令/);
  assert.match(prompt, /params\.curriculum\.iterations 设置为 10/);
  assert.match(prompt, /必须显式传入 params\.curriculum\.iterations\s*=\s*10/);
  assert.match(prompt, /fine_tune\.iterations 设置为 10/);
  assert.match(prompt, /必须显式传入 fine_tune\.iterations\s*=\s*10/);
  assert.match(prompt, /deeplens_adjust_structure/);
  assert.doesNotMatch(prompt, /deeplens_adjust_structure 做一次/);
  assert.match(prompt, /does not mutate the active DeepLens session/i);
  assert.match(prompt, /avoid inserting structure changes between a healthy curriculum result and fine-tune/i);
  assert.match(prompt, /Never call read_file on directories/i);
  assert.match(prompt, /Do not read project roots such as .*LensBot.*results.*pi-agent/i);
  assert.match(prompt, /active_result_dir is the run workspace root/i);
  assert.match(prompt, /active_workspace_dir is the Optimization agent workspace/i);
  assert.match(prompt, /active_result_dir\/agents\/optimization\/workspace/i);
  assert.match(prompt, /replace active_result_dir with the concrete path/i);
  assert.match(prompt, /active_result_dir\/engines\/deeplens\/session\.json/i);
  assert.match(prompt, /active_result_dir\/engines\/deeplens\/live\/current\.json/i);
  assert.match(prompt, /active_result_dir\/engines\/deeplens\/deeplens\.log/i);
  assert.match(prompt, /Use powershell only for bounded workspace inspection/i);
  assert.match(prompt, /PowerShell syntax/i);
  assert.match(prompt, /no more than 180 characters/i);
  assert.doesNotMatch(prompt, /roughly \d+-\d+ characters/i);
  assert.doesNotMatch(prompt, /Use bash only/i);
});

test("decision_summary is accepted by pi tools but stripped before Python dispatch", () => {
  const schema = schemaWithDecisionSummary({
    type: "object",
    additionalProperties: false,
    required: ["result_dir"],
    properties: {
      result_dir: { type: "string" },
    },
  });

  assert.equal(schema.additionalProperties, false);
  const properties = schema.properties as Record<string, { type: string }>;
  assert.ok(properties);
  assert.deepEqual(properties.decision_summary.type, "string");

  const sanitized = sanitizeToolArgumentsForPython({
    result_dir: "results/run-1",
    decision_summary: "Analyze final metrics before finish.",
  });

  assert.deepEqual(sanitized, { result_dir: "results/run-1" });

  const sanitizedFinish = sanitizeToolArgumentsForPython({
    final_summary: "Smoke test complete.",
    decision_summary: "Finish the validated pipeline.",
  }, "finish");

  assert.deepEqual(sanitizedFinish, { final_summary: "Smoke test complete." });
});

test("finish accepts summary alias and normalizes it for Python dispatch", () => {
  const schema = finishToolInputSchema();
  const properties = schema.properties as Record<string, { type: string }>;

  assert.equal(schema.additionalProperties, false);
  assert.deepEqual(properties.summary.type, "string");

  const sanitized = sanitizeToolArgumentsForPython({
    summary: "Smoke test complete with final artifacts.",
  }, "finish");

  assert.deepEqual(sanitized, { final_summary: "Smoke test complete with final artifacts." });
});

test("curriculum params keep replay seed through Python dispatch", () => {
  const schema = schemaForAgentTool("deeplens_curriculum", {
    type: "object",
    additionalProperties: false,
    required: ["params"],
    properties: {
      params: {
        type: "object",
        additionalProperties: false,
        properties: {
          foclen: { type: "number" },
        },
      },
    },
  });
  const paramsSchema = (schema.properties as Record<string, any>).params as Record<string, any>;

  assert.equal(paramsSchema.additionalProperties, false);
  assert.deepEqual(paramsSchema.properties.exp_name.type, "string");
  assert.deepEqual(paramsSchema.properties.seed.anyOf, [{ type: "integer" }, { type: "null" }]);

  const sanitized = sanitizeToolArgumentsForPython(
    {
      decision_summary: "Start curriculum from the selected seed.",
      params: {
        exp_name: "real-llm-api-smoke",
        seed: 4242,
        foclen: 85,
      },
    },
    "deeplens_curriculum",
  );

  assert.deepEqual(sanitized, { params: { exp_name: "real-llm-api-smoke", seed: 4242, foclen: 85 } });
});

test("trusted curriculum arguments fill a missing replay seed before logging and dispatch", () => {
  const args = trustedArguments(
    "deeplens_curriculum",
    {
      params: {
        seed: null,
        foclen: 85,
      },
    },
    createInitialState(),
    {
      context: {
        run_id: "run-1",
        target: {
          exp_name: "Auto lens design",
          seed: null,
          foclen: 52,
          fov: 43,
          fnum: 2.9,
          bfl: 18,
          thickness: 120,
        },
      },
    },
    () => 98765,
  );

  const params = args.params as Record<string, unknown>;
  assert.equal(params.seed, 98765);
  assert.equal(params.foclen, 85);
});

test("trusted finetune arguments use active session when omitted", () => {
  const state = applyToolResult(createInitialState(), {
    ok: true,
    observation: "curriculum done",
    state_patch: { active_session_id: "session-1" },
  });

  const args = trustedArguments(
    "deeplens_finetune",
    {},
    state,
    { context: { run_id: "run-1", target: {} } },
  );

  assert.deepEqual(args, { session_id: "session-1" });
});

test("finish does not impose a final summary length limit", () => {
  const schema = finishToolInputSchema();
  const finalSummarySchema = (schema.properties as Record<string, any>).final_summary as Record<string, any>;
  const verboseSummary = "Smoke test validated the complete pipeline end-to-end. All final artifacts exported successfully; reduced iteration count means optical quality is not representative of full optimization.";

  assert.equal(verboseSummary.length, 187);
  assert.equal(finalSummarySchema.maxLength, undefined);

  const normalized = normalizeFinalSummary(verboseSummary);

  assert.equal(normalized, verboseSummary);
});

test("state snapshot derives the active optimization workspace directory", () => {
  const initial = createInitialState();

  assert.equal(initial.active_workspace_dir, null);

  const next = applyToolResult(initial, {
    ok: true,
    observation: "workspace bound",
    state_patch: { active_result_dir: "results/run-1" },
  });

  assert.equal(next.active_workspace_dir, "results/run-1/agents/optimization/workspace");
});

test("state starts as running facts plus structurally valid tools", () => {
  const initial = createInitialState();

  assert.equal(initial.phase, "running");
  assert.ok(initial.allowed_tools.includes("deeplens_adjust_structure"));
  assert.ok(initial.allowed_tools.includes("deeplens_curriculum"));
  assert.equal(initial.allowed_tools.includes("deeplens_analysis"), false);
  assert.equal(initial.allowed_tools.includes("deeplens_finetune"), false);
  assert.equal(initial.allowed_tools.includes("finish"), false);
});

test("invalid tool calls are guarded by missing runtime facts", () => {
  const initial = createInitialState();

  assert.throws(() => assertToolAllowed(initial, "deeplens_analysis"), /active_result_dir/);
  assert.throws(() => assertToolAllowed(initial, "deeplens_finetune"), /active_session_id/);
  assert.throws(() => assertToolAllowed(initial, "deeplens_inspect_checkpoint"), /active_session_id/);
  assert.throws(() => assertToolAllowed(initial, "deeplens_adjust_strategy"), /active_session_id/);
});

test("dynamic tools derive structural availability without forcing a linear script", () => {
  const initial = createInitialState();

  const afterCurriculum = applyToolResult(initial, {
    ok: true,
    observation: "curriculum done",
    state_patch: {
      active_session_id: "session-1",
      active_result_dir: "results/run-1",
      artifacts: { curriculum_json: "results/run-1/engines/deeplens/attempts/attempt-001-curriculum/curriculum.json" },
    },
  });

  assert.equal(afterCurriculum.phase, "running");
  assert.ok(afterCurriculum.allowed_tools.includes("deeplens_adjust_structure"));
  assert.ok(afterCurriculum.allowed_tools.includes("deeplens_curriculum"));
  assert.ok(afterCurriculum.allowed_tools.includes("deeplens_analysis"));
  assert.ok(afterCurriculum.allowed_tools.includes("deeplens_finetune"));
  assert.ok(afterCurriculum.allowed_tools.includes("deeplens_inspect_checkpoint"));
  assert.ok(afterCurriculum.allowed_tools.includes("deeplens_adjust_strategy"));
  assert.equal(afterCurriculum.allowed_tools.includes("finish"), false);
});

test("auxiliary workspace tools stay available to optimization", () => {
  const initial = createInitialState();
  const auxiliaryTools = ["powershell", "read_file", "write_file", "edit_file"];

  for (const tool of auxiliaryTools) {
    assert.ok(initial.allowed_tools.includes(tool as never), `${tool} should be available initially`);
  }

  const afterFinalAnalysis = applyToolResult(initial, {
    ok: true,
    observation: "final analysis done",
    state_patch: {
      active_session_id: "session-1",
      active_result_dir: "results/run-1",
      artifacts: {
        curriculum_json: "results/run-1/engines/deeplens/attempts/attempt-001-curriculum/curriculum.json",
        final_json: "results/run-1/final/final.json",
        final_zmx: "results/run-1/final/final.zmx",
        analysis_json: "results/run-1/final/final.json",
      },
      metrics: {
        analysis_stage: "final",
        has_final_json: true,
      },
    },
  });

  for (const tool of auxiliaryTools) {
    assert.ok(afterFinalAnalysis.allowed_tools.includes(tool as never), `${tool} should remain available`);
  }
});

test("final contract is structural and does not depend on old analysis phases", () => {
  const initial = createInitialState();
  const readyToFinish = applyToolResult(initial, {
    ok: true,
    observation: "final analysis done",
    state_patch: {
      active_session_id: "session-1",
      active_result_dir: "results/run-1",
      artifacts: {
        final_json: "results/run-1/final/final.json",
        final_zmx: "results/run-1/final/final.zmx",
        analysis_json: "results/run-1/final/final.json",
      },
      metrics: {
        analysis_stage: "final",
        has_final_json: true,
      },
    },
  });

  assert.equal(readyToFinish.phase, "running");
  assert.ok(readyToFinish.allowed_tools.includes("finish"));
  assert.ok(readyToFinish.allowed_tools.includes("deeplens_analysis"));
  assert.ok(readyToFinish.allowed_tools.includes("deeplens_finetune"));
  assert.doesNotThrow(() => validateFinish(readyToFinish));
  assert.doesNotThrow(() => assertToolAllowed(readyToFinish, "finish"));

  const finished = applyToolResult(readyToFinish, {
    ok: true,
    observation: "finish validated",
    state_patch: { phase: "finished" },
  });

  assert.equal(finished.phase, "finished");
  assert.deepEqual(finished.allowed_tools, []);
});

test("finish requires final artifacts plus final analysis evidence", () => {
  const initial = createInitialState();
  const artifactsOnly = applyToolResult(initial, {
    ok: true,
    observation: "final artifacts exported",
    state_patch: {
      artifacts: {
        final_json: "results/run-1/final/final.json",
        final_zmx: "results/run-1/final/final.zmx",
        analysis_json: "results/run-1/final/final.json",
      },
    },
  });

  assert.throws(() => validateFinish(artifactsOnly), /final DeepLens metrics/);
  assert.equal(artifactsOnly.allowed_tools.includes("finish"), false);

  const metricsWithoutAnalysisArtifact = applyToolResult(initial, {
    ok: true,
    observation: "final metrics reported",
    state_patch: {
      artifacts: {
        final_json: "results/run-1/final/final.json",
        final_zmx: "results/run-1/final/final.zmx",
      },
      metrics: {
        analysis_stage: "final",
        has_final_json: true,
      },
    },
  });

  assert.throws(() => validateFinish(metricsWithoutAnalysisArtifact), /analysis_json/);
  assert.equal(metricsWithoutAnalysisArtifact.allowed_tools.includes("finish"), false);
});

test("state snapshot keeps adjusted structure params for later curriculum", () => {
  const initial = createInitialState();
  const params = {
    foclen: 50,
    fov: 35,
    fnum: 2.8,
    bfl: 18,
    thickness: 80,
    surf_list: [["Spheric", "Spheric"], ["Aperture"], ["Spheric", "Spheric"]],
  };

  const next = applyToolResult(initial, {
    ok: true,
    observation: "structure adjusted",
    state_patch: { params_override: params },
  });

  assert.deepEqual(next.params_override, params);
});

test("trusted structure adjustment arguments include active result dir for preview refresh", () => {
  const state = applyToolResult(createInitialState(), {
    ok: true,
    observation: "curriculum done",
    state_patch: {
      active_result_dir: "results/run-1",
    },
  });

  const args = trustedArguments(
    "deeplens_adjust_structure",
    {
      action: "convert_aspheric_to_spheric",
      params: {
        foclen: 50,
        surf_list: [["Spheric", "Aspheric"], ["Aperture"], ["Spheric", "Spheric"]],
      },
    },
    state,
    { context: { run_id: "run-1", target: {} } },
  );

  assert.equal(args.result_dir, "results/run-1");
});

test("hard budget counts non-finish tools and exempts finish", () => {
  const budget = createToolBudget(2);

  consumeToolBudget(budget, "deeplens_curriculum");
  consumeToolBudget(budget, "deeplens_analysis");

  assert.throws(() => consumeToolBudget(budget, "deeplens_finetune"), /max_turns=2/);
  assert.doesNotThrow(() => consumeToolBudget(budget, "finish"));
});
