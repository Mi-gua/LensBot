type JsonObject = Record<string, unknown>;

const EFFORT_STAGES = ["curriculum", "fine_tune"] as const;
const EFFORT_KEYS = ["iterations", "test_per_iter", "num_ring", "num_arm", "spp"] as const;

export function resolveExecutionParams(context: JsonObject, ...changes: JsonObject[]): JsonObject {
  const baseline = objectValue(context.execution_params);
  const contract = objectValue(context.design_contract);
  const merged = mergeParams(baseline, ...changes);
  const protectedKeys = Array.isArray(contract.protected_parameter_keys)
    ? contract.protected_parameter_keys.map(String)
    : ["foclen", "imgh", "fov", "fnum"];

  for (const key of protectedKeys) {
    if (Object.hasOwn(baseline, key)) merged[key] = baseline[key];
  }

  if (Object.hasOwn(baseline, "_meta")) {
    const metadata = objectValue(baseline._meta);
    const budgetSources = { ...objectValue(metadata.budget_sources) };
    for (const stage of EFFORT_STAGES) {
      if (effortChanged(objectValue(merged[stage]), objectValue(baseline[stage]))) {
        budgetSources[stage] = "adaptive";
      }
    }
    merged._meta = { ...metadata, budget_sources: budgetSources };
  }
  return merged;
}

function mergeParams(...layers: JsonObject[]): JsonObject {
  const merged = Object.assign({}, ...layers);
  for (const stage of EFFORT_STAGES) {
    const stageLayers = layers.map((layer) => objectValue(layer[stage]));
    if (stageLayers.some((layer) => Object.keys(layer).length > 0)) {
      merged[stage] = Object.assign({}, ...stageLayers);
    }
  }
  return merged;
}

function effortChanged(proposed: JsonObject, baseline: JsonObject): boolean {
  return EFFORT_KEYS.some((key) => Object.hasOwn(proposed, key) && proposed[key] !== baseline[key]);
}

function objectValue(value: unknown): JsonObject {
  return value && typeof value === "object" && !Array.isArray(value) ? value as JsonObject : {};
}
