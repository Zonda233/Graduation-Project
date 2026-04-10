# ADR-0002: Interface And Dependency Injection Style

- Status: Accepted
- Date: 2026-03-24
- Deciders: router-layer maintainers

## Context

路由流程包含可替换算法（placer/pathfinder/multi-line/emitter）。
如果直接在业务流程里硬编码具体类，将导致：

- 算法替换需要修改 orchestrator；
- 测试时难以注入替身实现；
- 架构约束只停留在约定层面。

## Decision

采用 `I*` 接口 + 显式继承 + 服务层依赖注入：

- `INodePlacer` / `IPathFinder` / `IMultiLineRouter` / `IJsonEmitter` / `IRouterService`
- 具体类显式实现对应接口；
- `DefaultRouterService` 通过 dataclass 字段注入依赖。

## Consequences

### Positive

- 算法替换无需改主流程；
- 单测可注入 mock/stub；
- 架构阅读时可直接识别多态点。

### Negative / Trade-offs

- 需要维护接口与实现的同步；
- 新人需要理解 DI 组装方式。

## Alternatives considered

1. 仅用 duck typing（未选，可读性与治理强度不足）
2. 直接硬编码具体实现（未选，扩展性差）
