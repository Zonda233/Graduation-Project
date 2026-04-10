# ADR-0003: Typed Internal Flow

- Status: Accepted
- Date: 2026-03-24
- Deciders: router-layer maintainers

## Context

原始 JSON `dict` 在内部流程中到处传递，存在：

- 键名拼写错误风险；
- 隐式契约难追踪；
- 重构时静态检查价值低。

## Decision

建立“边界 dict，内部 typed”的数据策略：

- 输入边界：`RouterInputParser` 负责 `dict -> RouterInput`
- 内部流程：使用 `RouterInput/NodeSpec/LineSpec`、`PlacedNodeMap`、`LineRouteMap`
- 输出边界：`IJsonEmitter.emit(...) -> generation_json_dict`

## Consequences

### Positive

- 内部契约显式化；
- 重构安全性提高；
- IDE/类型检查价值更高。

### Negative / Trade-offs

- 解析层代码量增加；
- 需要维护 dataclass 与协议字段的一致性。

## Alternatives considered

1. 全程 `dict`（未选，维护性差）
2. 全程对象且输出不回 `dict`（未选，不符合下游协议边界）
