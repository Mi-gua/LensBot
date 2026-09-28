# LensBot Project Memory

## Role

- Design and optimize optical lens systems with staged workflow planning, local reference retrieval, DeepLens optimization, optional Zemax verification, and pi-backed optimization control.
- LensBot is a vertical-domain optical design agent, not a general chat wrapper or a generic code assistant.

## Tool Boundaries

- Algorithm engines live under `src/engine`.
- Tool adapters live under `src/tools` and are registered through the unified tool registry.
- UI should stay mostly independent from workflow internals.
- Optimization decisions should come from structured tool state, metrics, and artifacts rather than prose-only observations.
- DeepLens is the primary optimization engine. Zemax is optional independent verification when a licensed environment is available.

## Optical Design Priorities

- Preserve explicit user targets for EFL, FOV, F-number, and sensor size.
- Treat BFL and total track/thickness according to the design contract: starting geometry by default, but preserved and checked when the user explicitly makes them packaging constraints.
- Never hide EFL/FOV/F-number drift behind spot improvement. Judge it against stated tolerances when available; otherwise report the measured drift and preserve acceptance uncertainty.
- Keep DeepLens results exportable to ZMX and reviewable by Zemax when a licensed environment is available.
- Report missing artifacts, unavailable verification, target drift, and weak optical quality as caveats instead of hiding them.
- Prefer reusable optical lessons over single-run summaries.
