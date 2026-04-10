# ADR-0004: Shortest Path With Clearance Tie-break

- Status: Accepted
- Date: 2026-03-24
- Deciders: router-layer maintainers

## Context

在 3D 体素网格中，常出现多条“同样最短”的路径。传统 A* 对并列方案的选择依赖遍历顺序，
会生成“过于贴近已有管线”的路径，视觉与工程净距都不理想。

## Decision

采用两阶段优化：

1. 保持最短路为硬目标（不增加路径长度）；
2. 在最短路集合中，按净距做词典序最大化：
   - 先最大化路径上的最小净距；
   - 再最大化净距累计值。

实现落地于 `ClearanceAwareShortestPathFinder.py`。

## Consequences

### Positive

- 不牺牲最短长度；
- 同代价下自动偏好“更远离已铺管线”的路线；
- 结果更稳定、可解释。

### Negative / Trade-offs

- 相比单次 A* 多了若干 BFS 与 DP 过程；
- 代码复杂度上升，需要算法文档配套维护。

## Alternatives considered

1. 直接给 A* 增加软权重（未选，可能破坏最短性）
2. 仅调邻居遍历顺序（未选，不稳定且不可解释）
