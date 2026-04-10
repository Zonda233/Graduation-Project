# ADR-0001: One Class Per File

- Status: Accepted
- Date: 2026-03-24
- Deciders: router-layer maintainers

## Context

早期实现将多种职责塞在单文件中，导致：

- 变更影响面大；
- 代码审查难以定位责任边界；
- 接口替换（例如 pathfinder/placer）成本高。

## Decision

在 `router-layer` 中采用“一主类一文件”规则：

- 每个业务类使用同名文件；
- 仅允许紧密关联的 dataclass 与该主类同文件；
- 跨模块公共能力抽成独立 helper 类文件。

## Consequences

### Positive

- 模块边界明确，替换成本低；
- 导航与审查效率显著提升；
- 便于接口驱动重构。

### Negative / Trade-offs

- 文件数量增加；
- 需要额外维护导出层与文档索引。

## Alternatives considered

1. 按“功能域”打包多类同文件（未选，职责仍易混杂）
2. 保持大文件并靠注释分区（未选，工程可维护性不足）
