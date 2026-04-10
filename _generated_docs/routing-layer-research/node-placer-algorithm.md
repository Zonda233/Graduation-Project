# NodePlacer 算法说明（当前实现）

## 目标

NodePlacer 在 Router 内负责把 `router_input.nodes` 放到体素网格，输出 `PlacedNode(vc,wc,direction)`。  
当前实现目标是：

- 支持 `location_2d` 引导放置
- 在缺少 `location_2d` 时自动给出合理拓扑布局 seed
- 做体素级粗粒度不重叠（AABB + clearance）
- 冲突时做邻域回退搜索

不做高精几何碰撞（OBB/SAT），只做体素级约束。

## 输入

- `nodes[]`
  - `location_2d`（可选）
  - `placement_hint`（可选）
    - `z_layers`
    - `anchor_policy`：`fixed | near_seed | free`
    - `direction_preferred`
  - `bbox_hint`（可选）
    - `extent_voxels: [ex,ey,ez]`
    - `clearance_voxels`
- `lines[]`
  - `from_node`/`to_node`/`via_nodes`（用于构建拓扑 seed）
- `constraints.spatial_rules`（可选）
  - `default_clearance_voxels`
  - `max_search_radius_voxels`
  - `default_z_layers`

## 输出

- `Dict[node_id, PlacedNode]`
  - `vc`: 体素锚点
  - `wc`: 体素中心世界坐标
  - `direction`: 端口方向（若有）
- `last_report`（调试）
  - 放置数量、占用体素数量、冲突/回退信息

## 算法步骤

1. **准备拓扑 fallback seed**
  - 把每条 line 展开为链：`from -> via... -> to`
  - 构建有向图并做拓扑排序
  - `x_norm` 按深度分层（左到右）
  - `y_norm` 按同层节点排序（依据前驱重心）做分支展开
2. **为每个节点确定 seed**
  - 若存在 `location_2d`：使用它（`seed_source=location_2d`）
  - 否则：用拓扑 seed（`seed_source=topology_auto`）
3. **确定方向与候选层**
  - 优先 `placement_hint.direction_preferred`
  - 若为罐出口（EquipmentPort+outlet）默认 `-Z`
  - 候选层来自 `placement_hint.z_layers` 或 `spatial_rules.default_z_layers`
4. **构建粗粒度体素盒**
  - `extent_voxels` 来自 `bbox_hint`，缺省按节点类型给默认尺寸
  - `clearance_voxels` 来自 `bbox_hint` 或全局默认
  - 占用集合 = AABB 按 clearance 膨胀后的体素集合
5. **邻域回退搜索**
  - 在 seed 周围按半径 0..R（方环）搜索可用锚点
  - `anchor_policy=fixed` 时 `R=0`
  - `anchor_policy=free` 时扩大搜索半径
  - 找到第一个不冲突且在边界内的位置即接受
6. **失败兜底**
  - 若半径内无可用位置，回退到 seed 并记录 conflict（不中断主流程）

## 为什么旧算法在无 location_2d 下表现差

旧版本对缺失 `location_2d` 统一给 `(0.5,0.5)` seed，导致所有节点从同一点扩散，布局由遍历顺序主导，容易出现“形状怪异”。  
现在改为先做拓扑 seed，再做局部冲突回退，至少能保持“源->汇方向”和“分支展开”。

## 已知限制

- 仍是启发式，不保证全局最优
- 复杂有环网络的 seed 会退化为稳定但不一定语义最优的布局
- 目前 `occupied` 只用于放置阶段，尚未回灌到 PathFinder 的 `forbidden`

## 下一步

1. 将 NodePlacer 的 `occupied_voxels` 输出接入 Grid forbidden
2. 为有环图增加专门布局策略（例如 SCC 压缩后再分层）
3. 输出 `placement_report` 到路由结果 meta/debug，便于可视化排障

