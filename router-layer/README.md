# 空间路由层（Router Layer）

本模块将**图级**的 router-input-protocol JSON 转为**几何就绪**的生成层 JSON，供 `chemical-piping-lib` 在 Blender 中构建三维管道场景。

## 输入与输出

| 项目 | 说明 |
|------|------|
| **输入** | [router-input-protocol](router-input-protocol/) 定义的 JSON：`nodes`（设备端口、连接点等）、`lines`（管线 from/to/via_nodes）、`constraints`。**图级，无 3D 体积或设备几何**。 |
| **输出** | 生成层协议 JSON：`meta.voxel_grid`、`assets`、`tee_joints`、`segments`（含 Pipe/Elbow 等 components），可直接被 chemical-piping-lib 消费。 |

## 路由层完整管线（现状）

1. **Input Parse/Normalize**：读取并规范化 router-input JSON。
2. **Node Placement（当前偏弱）**：`SimpleNodePlacer` 按 `location_2d` 放置到网格；设备端口做少量方向规则（如罐底先 -Z）。
3. **Grid Build**：按 `RouterConfig` 初始化体素网格。
4. **Multi-line Routing**：顺序 A* 逐线寻路，已铺路径写入禁行集（共享节点可复用）。
5. **Topology Emit**：按 `via_nodes` 生成 `tee_joints` 并拆分 `segments`。
6. **Geometry Fitting**：对 Elbow/Tee 邻接 Pipe 端点做几何裁剪（避免重叠/穿插）。
7. **Schema Validation（测试脚本）**：输出 generation JSON 并对 protocol schema 校验。

> 关键缺口：当前缺少独立的 **Spatial Validation** 阶段（包围盒重叠检测、净距检测、合规性检测）。这也是 NodePlacer 目前“不够格”的主要原因。

## 架构重构（已完成）

- 重构目标：按“组件化 + 依赖注入 + 强类型数据模型”组织 Router。
- 当前架构状态：
  - `RouterInputModels.py`：路由输入 dataclass 模型（Node/Line/Constraints）
  - `RouterInputParser.py`：JSON(dict) 到 dataclass 的边界解析器
  - `INodePlacer.py` / `SimpleNodePlacer.py`
  - `IPathFinder.py` / `ClearanceAwareShortestPathFinder.py`（`AStarPathFinder.py` 兼容别名）
  - `IMultiLineRouter.py` / `SequentialMultiLineRouter.py` / `MapfMultiLineRouter.py`
  - `IRouterService.py` / `DefaultRouterService.py` / `MapfRouterService.py`
- 兼容层文件（如 `service.py`、`pathfinder.py`、`multi_line_router.py`、`node_placer.py`）目前仅做导出转发，保证旧导入路径可用。
- JSON 发射已拆分为一类一文件；`json_emitter.py` 仅作兼容 re-export：
  - `IJsonEmitter.py`、`MinimalJsonEmitter.py`、`SchemaCompliantJsonEmitter.py`、`FullJsonEmitter.py`
  - `GenerationMetaBuilder.py`、`VoxelGeometryMaps.py`、`GenerationPathComponentConverter.py`
  - `PipeAndTeeGeometryTrimmer.py`、`SegmentsAndTeesAssembler.py`、`PlaceholderTankAssetBuilder.py`、`SchemaDefaultMaterials.py`
- 实现类均已显式继承接口（`I*`），并保持依赖注入风格（通过 `DefaultRouterService` 组装）。
- 业务流程内部不再使用 `dict` 传递参数：`RouterInputParser` 之后全程使用 dataclass；`dict` 仅保留在输入/输出 JSON 边界。

## 软件架构文档

- 维护文档：`ARCHITECTURE.md`
- 架构决策记录（ADR）：`adr/README.md`
- 内容包括：模块职责、依赖关系、数据流、扩展点、测试与变更约束，以及可追踪的架构决策历史。

## 位置与体积从哪里来？

- **输入协议中不包含**：设备的 3D 尺寸、体积、包围盒；只有节点 ID、类型、可选的 `location_2d`（归一化或图纸坐标）和 `equipment_ref`。
- **输入协议可选增强字段**：`nodes[].placement_hint`、`nodes[].bbox_hint`、`constraints.spatial_rules`，用于体素级放置与粗粒度占用检查。
- **路由层当前做法**：
  - **节点 3D 位置**：`SimpleNodePlacer` 使用 `location_2d` 作为 seed；若缺失，则使用拓扑自动布局（按 line 深度分层 + 分支展开）生成 seed，并结合 `placement_hint`、`bbox_hint` 与 `constraints.spatial_rules` 做体素级冲突回退；保证粗粒度不重叠（体素AABB）后输出锚点 vc。
  - **设备（罐子等）**：输入中若有 `EquipmentPort` 且带 `equipment_ref`（如 `tank_01`），但**没有**对应的 `type=Equipment` 节点时，输出阶段会为每个这样的 `equipment_ref` 生成一个**占位 Tank**（小尺寸立式罐，端口在罐底 -Z），以便生成层能画出罐体并与管线连接。占位罐的尺寸与位置由端口位置反推，**非输入协议给定**。
- 若上游（感知/校验层）将来提供设备的 3D 包围盒或几何，可扩展 NodePlacer / JsonEmitter 使用这些信息，替代当前占位逻辑。

## 多管线与共享节点

- 当前为**顺序 A\***：按 `lines` 顺序逐条寻路，已布路径体素写入“禁行”集合。
- **共享节点**（如三通 `via_nodes`）会从禁行集合中排除，否则后布管线无法以该点作为起点/终点，导致只出现一根管。详见 `pathfinder.py` 中对 start/goal/via 的排除逻辑。

## 几何裁剪约定（弯头/三通）

- 路由输出现在会对 `segments.components` 做**几何裁剪**，避免“直管伸进弯头/三通实体”：
  - **Elbow 邻接 Pipe 裁剪**：相邻直管端点不再落在体素拐点，而是落在弯头切点；输出 `Elbow.bend_radius_m`，并按 `bend_radius_m + elbow_overlap_m` 裁剪前后直管。
  - **Tee 邻接 Pipe 裁剪**：连接到 `tee_*_run_a/run_b/branch` 的直管端点不再落在 tee 中心，而是落在 tee 三个端口的几何位置（偏移由 `tee_run_half_length_factor` / `tee_branch_half_length_factor` 控制）。
- 说明：`vc_*` 仍用于拓扑/调试，实际几何拼接以 `wc_*` 为准；因此出现 “`wc_start/wc_end` 与 `vc_start/vc_end` 不完全重合” 是预期行为。
- 上述裁剪参数均已配置化，定义在 `RouterConfig`：`elbow_overlap_m`、`tee_run_half_length_factor`、`tee_branch_half_length_factor`。

## 目录与运行测试

| 路径 | 说明 |
|------|------|
| `router-input-protocol/` | 进入 Router 前的协议定义与示例 JSON。 |
| `tests/test_router_to_generation.py` | 测试脚本：读入示例 → 路由 → 写出生成层 JSON → Schema 校验；并输出 Blender 用代码片段。 |
| `output/` | 测试生成的 JSON 输出目录（可加入 .gitignore）。 |

在**项目根目录**执行：

```bash
python router-layer/tests/test_router_to_generation.py
```

会生成 `router-layer/output/router_output_cooling_water.json`，并通过 chemical-piping-lib 的 `protocol_v1.json` 校验。

复杂样例可执行：

```bash
python router-layer/tests/test_router_to_generation.py --input router-layer/router-input-protocol/examples/complex_cooling_water.json --output router-layer/output/router_output_complex_cooling_water.json
```

## 参考

- 协议与设计理由：`router-input-protocol/README.md`、`_generated_docs/router-protocol/`
- 路由方案与接口：`_generated_docs/routing-layer-research/`
- 路由层架构：`ARCHITECTURE.md`
- 生成层协议：`chemical-piping-lib` 的 `doc/Final_JSON.md`
