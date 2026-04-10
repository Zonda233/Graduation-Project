# ADR-0005: Compatibility Re-export Layer

- Status: Accepted
- Date: 2026-03-24
- Deciders: router-layer maintainers

## Context

重构拆分后，历史 import 路径（如 `pathfinder.py`, `json_emitter.py`）可能被上游脚本依赖。
若直接删除旧入口，会产生大量非功能性破坏。

## Decision

保留兼容导出层文件，作为薄门面（re-export only）：

- `service.py`
- `pathfinder.py`
- `node_placer.py`
- `multi_line_router.py`
- `json_emitter.py`

新逻辑不写入兼容层，仅导出新实现。

## Consequences

### Positive

- 既有调用方平滑迁移；
- 重构可分阶段推进；
- 降低发布风险。

### Negative / Trade-offs

- 维护两套入口命名；
- 需要在文档中明确“兼容层非业务实现”。

## Alternatives considered

1. 一次性破坏式迁移（未选，风险高）
2. 全量自动替换上游 import（未选，跨仓库不可控）
