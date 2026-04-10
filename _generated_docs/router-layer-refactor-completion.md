# Router Layer Refactor Completion Note

## Status

The router-layer refactor is considered complete for the current scope.

## What is completed

- one primary class per file across core router modules;
- compatibility re-export files kept for legacy imports;
- explicit interface inheritance added for concrete implementations:
  - `SimpleNodePlacer(INodePlacer)`
  - `AStarPathFinder(IPathFinder)`
  - `SequentialMultiLineRouter(IMultiLineRouter)`
  - `MapfMultiLineRouter(IMultiLineRouter)`
  - `DefaultRouterService(IRouterService)`
  - `MapfRouterService(IRouterService)`
  - `MinimalJsonEmitter(IJsonEmitter)`
  - `SchemaCompliantJsonEmitter(IJsonEmitter)`
  - `FullJsonEmitter(IJsonEmitter)`
- input parsing boundary established:
  - raw JSON dict -> `RouterInputParser` -> typed dataclasses
- internal data flow typed end-to-end:
  - placement/routing/emission use dataclasses and typed maps
- JSON emitter subsystem split into dedicated classes:
  - interfaces, emitters, geometry maps, component conversion, tee assembly, placeholder asset builder
- integration tests pass with schema validation.

## Remaining intentional placeholders

- `MapfMultiLineRouter` and `MapfRouterService` are placeholders for future MAPF implementation.
- `FullJsonEmitter` is a placeholder for full protocol coverage.
- dedicated spatial compliance/validation stage is not implemented yet.

## Architecture document

- Canonical architecture document: `router-layer/ARCHITECTURE.md`.
