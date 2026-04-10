# NodePlacer 子系统调研（体素版）

## 1. 本报告聚焦范围

本报告只讨论 **NodePlacer 子系统**，并严格以当前项目边界为前提：

- 空间表示是 **体素网格**（不是连续 CAD 几何）
- 目标是 **体素级不重叠**（粗粒度 AABB 即可）
- 重点是协议与 NodePlacer 的输入/输出契约，不展开生成层网格精碰撞

因此，我们把问题定义为：

> 在给定 router-input 协议数据下，NodePlacer 需要为每个节点（尤其是设备端口与关键连接点）生成体素坐标，并保证体素级占用不冲突、满足最基本方向/净距规则，向后续 PathFinder 输出可直接使用的 placed_nodes 与 forbidden 占用集合。


## 2. 当前实现与核心缺口（NodePlacer 维度）

当前 `SimpleNodePlacer` 的行为：

- 读取 `nodes[].location_2d`
- 映射到 `(vx, vy)`，`vz` 近似固定（少量特例）
- 输出 `PlacedNode {node_id, vc, wc, direction?}`

核心缺口：

1. **输入语义不足**
   - 只有 `location_2d`，缺少体素尺寸/占用语义，无法表达“这个节点要占几格”
2. **未建模占用**
   - 只放“点”，不放“体素盒”，无法做不重叠判定
3. **未做体素级合规**
   - 没有最小间距、keepout、可起步空间检查
4. **输出不完整**
   - 下游路由只拿到点位，拿不到“哪些体素被设备/节点占用”


## 3. NodePlacer 子系统的问题定义（输入/输出/约束）

## 3.1 输入（协议给什么）

最小可用输入应包含三类：

1. **拓扑输入（已有）**
   - `nodes[]`, `lines[]`, `constraints[]`
2. **放置提示（需扩展）**
   - 节点候选层、方向偏好、锚点偏好
3. **体素占用提示（需扩展）**
   - 每类节点对应的体素尺寸（或模板 ID）

如果不扩展协议，NodePlacer 只能继续“点放置”，无法可靠做不重叠检测。

## 3.2 输出（NodePlacer 应输出什么）

建议把 NodePlacer 输出升级为：

- `placed_nodes: Dict[node_id, PlacedNode]`
  - 至少含 `vc`, `wc`, `direction`
- `occupancy_voxels: Set[Vc]`
  - 节点/设备已占用体素（含必要膨胀）
- `placement_report`
  - 冲突列表、回退次数、未满足约束项

其中 `occupancy_voxels` 会直接并入 `Grid3D.forbidden`，这一步是与 PathFinder 的关键接口。

## 3.3 约束（NodePlacer 要满足什么）

只保留与当前项目强相关、可直接落地的体素约束：

- **非重叠约束**：任意两个对象占用体素集合不可相交
- **边界约束**：占用体素必须在网格范围内
- **最小净距约束（体素版）**：对象体素盒按 `clearance_voxels` 膨胀后不可相交
- **端口起步约束**：端口方向首步体素必须为空（如罐底先 `-Z`）
- **keepout 约束**：禁行区体素不可占用


## 4. 体素级不重叠算法（适合当前项目）

## 4.1 数据结构

- 每个待放置对象（节点或设备占位）抽象为：
  - `anchor_vc`（锚点体素）
  - `extent_voxels = (ex, ey, ez)`（占用盒尺寸）
  - `offset_rule`（盒子相对锚点的偏移）
- 将对象转为体素盒：
  - `BBoxV = [min_vc, max_vc]`（整数网格盒）

## 4.2 判定方式（粗粒度 AABB）

- 两盒相交判定（轴向分离）：
  - 若三轴均有重叠 -> 冲突
- 净距判定：
  - 先将盒子按 `clearance_voxels` 膨胀，再做相交判定

这就是你说的“体素级不重叠（粗 AABB）”，足够匹配当前 Router 阶段。

## 4.3 放置策略（先易后难）

建议 Phase-A 使用确定性启发式：

1. 根据 `location_2d` 给初值（仅作 seed，不是最终）
2. 依据约束做局部搜索（邻域平移/换层）
3. 成功则固化占用体素；失败则记录 report 并返回不可放置原因

这比直接上复杂优化器更贴合当前开发节奏。


## 5. 与协议的深度融合（核心）

你提到的关键点是对的：如果要弱化 `location_2d` 依赖，协议必须补输入语义。  
下面给出面向 NodePlacer 的最小扩展草案（向后兼容）。

## 5.1 nodes 级新增字段（建议）

- `placement_hint`（可选）
  - `seed_2d`: `{x,y}`（保留现有 `location_2d` 语义）
  - `z_layers`: `[int]`（可选层集合）
  - `anchor_policy`: `"fixed" | "near_seed" | "free"`
  - `direction_preferred`: `"+X|-X|+Y|-Y|+Z|-Z"`
- `bbox_hint`（可选）
  - `extent_voxels`: `[ex, ey, ez]`
  - `clearance_voxels`: `int`

若缺省：
- `extent_voxels` 用节点类型默认模板
- `clearance_voxels` 用全局默认值

## 5.2 constraints 级新增字段（建议）

- `constraints.spatial_rules`
  - `default_clearance_voxels`
  - `keepout_voxels` 或 `keepout_boxes`
  - `max_search_radius_voxels`

## 5.3 NodePlacer 输入输出契约（建议）

- 输入：`router_input + RouterConfig + node templates`
- 输出：
  - `placed_nodes`
  - `occupancy_voxels`
  - `placement_report`

这使 NodePlacer 成为“可独立验证”的子系统，而不是 PathFinder 的前置小工具。


## 6. 在现有管线中的准确位置

针对当前项目，推荐明确为：

1. `Input Parse`
2. `NodePlacer.place(...)` -> `placed_nodes + occupancy_voxels + report`
3. `SpatialValidator.validate(...)`（可先并入 NodePlacer 内部）
4. `GridBuilder` 把 `occupancy_voxels` 写入 `forbidden`
5. `PathFinder/MultiLineRouter`
6. `JsonEmitter`

重点：**NodePlacer 负责放置与占用，PathFinder 不再猜设备占用。**


## 7. 可用算法与库（仅保留当前相关）

## 7.1 必选（当前就能做）

- 体素 AABB 判定 + 膨胀净距（纯 Python 即可）
- 邻域搜索（BFS/环形扩展）

## 7.2 可选（后续增强）

- OR-Tools CP-SAT（离散放置求解）
  - 仅在启发式失败或场景规模大时引入

本阶段不建议引入 FCL/OBB/SAT 库，因为超出“体素粗粒度放置”需求。


## 8. 结论与下一步（NodePlacer 子系统）

结论：

- 你指出的问题成立：当前 NodePlacer 还不能满足工程可用要求。
- 近期关键不是复杂几何算法，而是建立**体素级占用语义 + 协议输入契约 + 可解释失败输出**。

建议的近期落地顺序：

1. 协议新增 `bbox_hint` / `placement_hint`（向后兼容）
2. NodePlacer 输出 `occupancy_voxels` 与 `placement_report`
3. 实现体素级 AABB 非重叠 + 膨胀净距检测
4. 将 `occupancy_voxels` 接入路由禁行体素

做到这四步后，NodePlacer 才能从“点映射工具”升级为“可验证的放置子系统”。

