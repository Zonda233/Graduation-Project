# Router Layer Architecture

## 1. Document purpose

本文档是 `router-layer` 的系统架构说明，面向三类读者：

- 开发者：理解模块边界与扩展点；
- 维护者：控制重构时的依赖方向与回归风险；
- 算法迭代者：在不破坏协议契约的前提下替换放置/寻路策略。

文档范围仅覆盖 `router-layer`，不覆盖 `chemical-piping-lib` 内部实现。

相关工程化文档：

- ADR 索引：`adr/README.md`
- ADR 模板：`adr/0000-template.md`

## 2. System context (C4 Level 1)

`router-layer` 位于“协议输入”与“几何生成”之间：

- 上游：`router-input-protocol` JSON（图级语义，弱几何）
- 下游：`chemical-piping-lib` generation JSON（几何可消费）
- 外部工具：测试脚本与 Blender 运行时仅消费输出，不参与核心算法

职责边界：

- 本层负责：节点放置、体素路由、分段/三通拓扑构建、几何裁剪参数化输出；
- 本层不负责：真实设备几何建模、全量工程规范审查、渲染构建。

## 3. Container/component view (C4 Level 2/3)

### 3.1 Core orchestrator

- `DefaultRouterService`（实现 `IRouterService`）
  - 编排完整 pipeline；
  - 注入 parser / placer / pathfinder / multi-line router / emitter；
  - 对外唯一稳定入口：`route(router_input_dict) -> generation_json_dict`。

### 3.2 Input boundary and typed model

- `RouterInputParser`
  - 边界解析：`dict -> RouterInput`；
  - 兼容缺省字段与类型兜底。
- `RouterInputModels`
  - 内部强类型数据结构：`RouterInput`, `NodeSpec`, `LineSpec`, `ConstraintsSpec` 等。

### 3.3 Spatial planning components

- `SimpleNodePlacer`（实现 `INodePlacer`）
  - 优先 `location_2d`，否则拓扑种子布局；
  - 结合 `placement_hint` / `bbox_hint` / `spatial_rules` 做 anchor 搜索与冲突回退。
- `ClearanceAwareShortestPathFinder`（实现 `IPathFinder`）
  - 最短路优先；
  - 同长度路径按净距（离已占用体素）最大化做 tie-break；
  - 支持端点首步/末步方向约束。
- `SequentialMultiLineRouter`（实现 `IMultiLineRouter`）
  - 按 `lines` 顺序逐条路由；
  - 已路由体素进入 `forbidden`，支持 safety margin 膨胀。

### 3.4 Emission components

- `SchemaCompliantJsonEmitter`（实现 `IJsonEmitter`）
  - 面向 schema 合规输出（当前主用）。
- `MinimalJsonEmitter`
  - 轻量调试输出。
- `FullJsonEmitter`
  - 占位，未来覆盖完整构件类型。

辅助组件：

- `SegmentsAndTeesAssembler`：via 节点拆段 + `tee_joints` 组装；
- `GenerationPathComponentConverter`：voxel path -> Pipe/Elbow；
- `PipeAndTeeGeometryTrimmer`：Elbow/Tee 邻接端点裁剪；
- `PlaceholderTankAssetBuilder`：缺失 equipment 时生成占位 Tank；
- `GenerationMetaBuilder` / `SchemaDefaultMaterials` / `VoxelGeometryMaps`：协议元数据与几何映射。

### 3.5 Compatibility layer

- `service.py`, `pathfinder.py`, `node_placer.py`, `multi_line_router.py`, `json_emitter.py`
  - 仅 re-export；
  - 用于兼容历史 import 路径。

## 4. Runtime view (sequence)

一次 `DefaultRouterService.route(...)` 的运行时序：

1. `RouterInputParser.parse(raw_dict)` 生成 `RouterInput`；
2. `INodePlacer.place_nodes(...)` 生成 `PlacedNodeMap`；
3. 构建 `Grid3D`；
4. `IMultiLineRouter.route_all_lines(...)` 生成 `LineRouteMap`；
5. `IJsonEmitter.emit(...)` 生成 generation JSON；
6. 返回给调用方（测试脚本可再做 schema 校验）。

失败语义：

- 单条 line 无路径：`LineRouteResult(success=False, reason="no_path_found")`；
- emitter 仍可输出成功路由的线段，整体不中断（当前策略）。

## 5. Data architecture and contracts

### 5.1 Boundary contracts

- 输入边界：`dict`（JSON）；
- 输出边界：`dict`（JSON）。

### 5.2 Internal contracts

- parser 之后禁止使用业务 `dict` 贯穿算法；
- 内部在 placer/router/emitter 间传递 dataclass 与 typed map：
  - `RouterInput`
  - `PlacedNodeMap`
  - `LineRouteMap`

### 5.3 Coordinate contracts

- voxel 坐标：`vc = (x, y, z)`，整数栅格；
- world 坐标：`wc` 由 `origin_wc + (vc + 0.5) * voxel_size` 映射；
- 几何拼接以 `wc` 为准，`vc` 用于拓扑/调试。

## 6. Key architecture decisions (ADR)

- [ADR-0001 One Class Per File](adr/0001-one-class-per-file.md) — Accepted
- [ADR-0002 Interface And Dependency Injection Style](adr/0002-interface-and-di-style.md) — Accepted
- [ADR-0003 Typed Internal Flow](adr/0003-typed-internal-flow.md) — Accepted
- [ADR-0004 Shortest Path With Clearance Tie-break](adr/0004-shortest-with-clearance-tiebreak.md) — Accepted
- [ADR-0005 Compatibility Re-export Layer](adr/0005-compatibility-reexport-layer.md) — Accepted

## 7. Quality attributes

### 7.1 Correctness

- 最短路主目标严格保持；
- 输出需满足 `protocol_v1.json` schema。

### 7.2 Maintainability

- 模块边界清晰；
- 依赖单向；
- 算法文档内嵌关键实现文件。

### 7.3 Extensibility

- 可替换节点放置、寻路、多线策略、发射器；
- 服务层通过依赖注入组合策略。

### 7.4 Performance

- 当前以可解释性和确定性优先；
- 大图场景可演进为 MAPF/CBS、增量重路由、并行寻路。

## 8. Configuration architecture

`RouterConfig` 是当前唯一运行时配置聚合：

- 网格：`voxel_size`, `grid_dimensions`, `origin_wc`
- 路由：`multi_line_strategy`, `safety_margin_voxels`
- 几何：`elbow_overlap_m`, `tee_run_half_length_factor`, `tee_branch_half_length_factor`

配置原则：

- 参数只放在 `RouterConfig`；
- 算法实现不直接读取环境变量或全局状态。

## 9. Risks and technical debt

- 尚无独立 spatial validation stage（净距/合规单独校验）；
- MAPF 路由器仍为占位实现；
- `FullJsonEmitter` 未覆盖阀门/变径/端帽全语义。

## 10. Verification strategy

基线回归：

- `tests/test_router_to_generation.py`（sample / minimal / complex）
- schema 校验：`chemical_piping_lib/schema/protocol_v1.json`

架构改动最小验收：

1. lints 无新错误；
2. sample 路由与 schema 通过；
3. 兼容导入路径不破坏（旧 import 可用）。

## 11. Evolution roadmap

短期：

- 增加 spatial validation 组件并接入 pipeline；
- 将 node placement 质量指标纳入报告（拥挤度/最小净距）。

中期：

- 实现 `MapfMultiLineRouter`（CBS/PBS）；
- 完成 `FullJsonEmitter` 全构件输出。

长期：

- 形成规则引擎与路由代价模型联动（规范驱动布管）。

## 12. Architecture governance

- 新架构决策必须新增 ADR，而不是直接改历史 ADR。
- 若决策发生替代，新增 superseding ADR 并在索引标注状态。
- 合并前检查：
  1. `ARCHITECTURE.md` 是否需要更新；
  2. ADR 索引状态是否一致；
  3. 核心回归（sample + schema）是否通过。
