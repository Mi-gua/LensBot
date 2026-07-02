# LensBot Project Memory

## Role

- Design and optimize optical lens systems with workflow-level planning and pi-backed optimization control.

## Tool Boundaries

- Algorithm engines live under `src/engine`.
- Tool adapters live under `src/tools` and are registered through the unified tool registry.
- UI should stay mostly independent from workflow internals.

## Optical Design Priorities

- Preserve explicit user targets for EFL, FOV, F-number, BFL, total length, and sensor size.
- Treat large drift in EFL/FOV/F-number as a design failure even when spot metrics improve.
- Prefer reusable optical lessons over single-run summaries.
