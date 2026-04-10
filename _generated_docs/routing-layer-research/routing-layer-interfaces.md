## 路由层接口设计草案（Python 视角）

本节在《routing-layer-solutions-research》中“问题拆解 P1–P4”的基础上，给出一套**面向 Python 的接口草案**，用于：

- 明确**路由层内部模块边界**（占位 / 单管寻路 / 多管协调 / JSON 映射）；
- 为后续接入 **pathfinding3d / dijkstra3d / w9-pathfinding / MSSA\*** 等算法提供**统一适配点**；
- 为将来从“普通 A\*”平滑切换到“改进 A\* / MSSA\* / PBS / CBS”保留扩展空间。

接口设计只描述**形状与职责**，不绑定具体实现。

---

### 1. 顶层入口：RouterService

```python
class RouterService(Protocol):
    def route(self, router_input: dict) -> dict:
        """
        :param router_input: 符合 router-input-protocol schema 的 JSON（已解析为 dict）
        :return: 生成层 JSON dict，符合 chemical-piping-lib Final_JSON 规范
        """
```

推荐实际实现类（示例）：

```python
@dataclass
class RouterConfig:
    voxel_size: float = 0.2
    grid_dimensions: tuple[int, int, int] = (20, 20, 20)
    origin_wc: tuple[float, float, float] = (0.0, 0.0, 0.0)
    # 是否启用多管策略（顺序 / MAPF），及其参数
    multi_line_strategy: Literal["sequential", "cbs", "pbs"] = "sequential"
    # 其他调参与开关……


class DefaultRouterService:
    def __init__(
        self,
        node_placer: "NodePlacer",
        grid_builder: "GridBuilder",
        multi_line_router: "MultiLineRouter",
        json_emitter: "JsonEmitter",
        config: RouterConfig,
    ): ...

    def route(self, router_input: dict) -> dict:
        ...
```

顶层 `route()` 内部大致流程：

1. `node_placer.place_nodes(router_input)` → 为每个 node 分配 3D 位置（wc / vc）。
2. `grid_builder.build_grid(placed_nodes, router_input)` → 得到 3D 体素网格与静态障碍。
3. `multi_line_router.route_all_lines(grid, placed_nodes, router_input, config)` → 得到每条 line 的体素路径（以及冲突消解结果）。
4. `json_emitter.emit(router_input, placed_nodes, line_paths, config)` → 生成层 JSON。

---

### 2. P1：节点 3D 占位接口（NodePlacer）

```python
@dataclass
class PlacedNode:
    node_id: str
    wc: tuple[float, float, float]
    vc: tuple[int, int, int]


class NodePlacer(Protocol):
    def place_nodes(self, router_input: dict, config: RouterConfig) -> dict[str, PlacedNode]:
        """
        :return: { node_id: PlacedNode }
        """
```

实现可从简单到复杂：

- Demo：根据 `location_2d` 做归一化投影到某层面上（固定 z）；设备/管架再加高度偏移；
- 正式版：结合设备尺寸、工艺区布局、管廊坐标等做更合理的 3D 放置。

NodePlacer **不关心寻路算法**，只负责“点放在哪里”。

---

### 3. P2：单管寻路接口（PathFinder / SingleLineRouter）

这是后续从 A\* 切到 MSSA\* 的关键抽象。

```python
@dataclass
class VoxelPath:
    line_id: str
    ordered_vc: list[tuple[int, int, int]]  # 按流向排序的体素路径


class PathFinder(Protocol):
    def find_path(
        self,
        grid: "Grid3D",
        start_vc: tuple[int, int, int],
        goal_vc: tuple[int, int, int],
        via_vc: list[tuple[int, int, int]] | None = None,
        forbidden: set[tuple[int, int, int]] | None = None,
        line_ctx: dict | None = None,
    ) -> list[tuple[int, int, int]]:
        """
        仅负责“单条线在当前障碍条件下”的曼哈顿路径。
        - grid: 含静态障碍的 3D 体素网格抽象
        - start_vc / goal_vc: 起终点体素
        - via_vc: 必经体素（按顺序），可在多次调用中拆成多段
        - forbidden: 动态禁行体素（例如已布管线或 safety margin 膨胀区）
        - line_ctx: 该 line 的上下文字段（管径、fluid_class 等），可参与代价
        """
```

**重要**：业务层只依赖 `PathFinder` 接口，**不直接依赖 pathfinding3d / dijkstra3d / MSSA\***。

示例适配器：

```python
class Pathfinding3DPathFinder:
    def __init__(self, diagonal_movement: DiagonalMovement = DiagonalMovement.never): ...
    def find_path(...): ...


class Dijkstra3DPathFinder:
    def __init__(self, use_compass: bool = True): ...
    def find_path(...): ...


class MSSAStarPathFinder:
    def find_path(...): ...
```

P2 升级时（从 A\* 换 MSSA\*），只需换注入的 PathFinder 实现。

---

### 4. P2+P3：多管线路由接口（MultiLineRouter）

`MultiLineRouter` 负责：

- 调用 `PathFinder` 完成单管路径；
- 处理**多条 line 的顺序与冲突**（“顺序 + 动态障碍” 或 PBS/CBS/w9-pathfinding）。

```python
@dataclass
class LineRouteResult:
    line_id: str
    voxel_path: list[tuple[int, int, int]] | None
    success: bool
    reason: str | None = None  # 失败原因（如 blocked, timeout 等）


class MultiLineRouter(Protocol):
    def route_all_lines(
        self,
        grid: "Grid3D",
        placed_nodes: dict[str, PlacedNode],
        router_input: dict,
        path_finder: PathFinder,
        config: RouterConfig,
    ) -> dict[str, LineRouteResult]:
        """
        :return: { line_id: LineRouteResult }
        可能存在失败的 line，需要在上游/Agent 层处理或重试。
        """
```

两种典型实现：

#### 4.1 SequentialMultiLineRouter（顺序 + 动态障碍）

```python
class SequentialMultiLineRouter:
    def __init__(self, ordering_strategy: "LineOrderingStrategy"): ...
    def route_all_lines(...): ...
```

- `ordering_strategy`：决定 line 的布线顺序（按管长、按重要性、按拓扑依赖等）；
- 内部循环：按顺序调用 `path_finder.find_path(...)`，每成功一条就把其体素路径加入 `forbidden`，下一条 line 自动避开。

#### 4.2 MapfMultiLineRouter（基于 CBS / PBS / w9-pathfinding）

```python
class MapfMultiLineRouter:
    def __init__(self, backend: Literal["w9_cbs", "pbs"] = "w9_cbs"): ...
    def route_all_lines(...): ...
```

- 对接 w9-pathfinding 的 Grid3D + CBS，或自实现 PBS/CBS；
- 需要把“多条线 + 3D 体素”映射为 MAPF 格式（agents, starts, goals, obstacles），并在 MAPF 层保证冲突消解；
- 最终仍返回每个 line 的体素路径，供 JsonEmitter 使用。

P3 升级时，只需从 `SequentialMultiLineRouter` 换成 `MapfMultiLineRouter`。

---

### 5. P2 辅助：Grid3D 抽象

**目的**：既能适配 numpy（pathfinding3d/dijkstra3d），又能适配 w9-pathfinding 或自写 MSSA\*。

```python
class Grid3D(Protocol):
    @property
    def shape(self) -> tuple[int, int, int]: ...

    def is_free(self, vc: tuple[int, int, int]) -> bool: ...

    def with_forbidden(self, forbidden: set[tuple[int, int, int]]) -> "Grid3D":
        """返回新的 Grid3D 视图，包含动态禁行体素。"""
```

实际实现可以直接包一层 numpy 数组，也可以持有多通道代价场。

---

### 6. P4：JSON 映射接口（JsonEmitter）

负责把 “图级 + 占位结果 + 每条线的体素路径” 转成生成层 JSON。

```python
class JsonEmitter(Protocol):
    def emit(
        self,
        router_input: dict,
        placed_nodes: dict[str, PlacedNode],
        line_routes: dict[str, LineRouteResult],
        config: RouterConfig,
    ) -> dict:
        """
        输出结构需符合 chemical-piping-lib Final_JSON 规范：
        - meta.voxel_grid
        - assets[]（设备几何 + ports）
        - tee_joints[]
        - segments[]（from_port/to_port + components: Pipe/Elbow/Valve/Reducer/Cap）
        """
```

典型逻辑：

1. `meta`：生成 `voxel_grid`、`generator` 等；
2. `assets`：从 nodes 中 type=Equipment 的信息 + PlacedNode 位置信息生成；
3. `tee_joints`：根据 `lines[].via_nodes` 和 line_routes 中的路径，确定三通中心体素与端口方向；
4. `segments`：对每条成功的 line：
   - 按体素路径相邻点方向分段：方向不变 → Pipe，方向改变 → Elbow；
   - 结合 line 上的阀门/变径信息插入 Valve / Reducer / Cap；
   - 写入 `from_port`/`to_port`、`spec` 等。

JsonEmitter 不关心“路径怎么来的”，只关心“路径点 + line 属性”。

---

### 7. 小结：接口与可扩展性对应关系

- **RouterService**：整个路由层的外观接口，方便被 CLI、REST、Blender 插件等调用。  
- **NodePlacer（P1）**：节点 3D 占位，可逐步从“拍平 + 固定 z”演进到“真实厂区布局”。  
- **PathFinder（P2）**：单管寻路的**唯一插拔点**，当前可用 pathfinding3d/dijkstra3d，未来可换 MSSA\* / JPS3D 等。  
- **MultiLineRouter（P3）**：多管协调的插拔点，先用 Sequential，再考虑 MAPF（w9-pathfinding CBS / PBS）。  
- **Grid3D**：屏蔽底层库的网格/代价表示差异。  
- **JsonEmitter（P4）**：唯一负责“路径 → 生成层 JSON”的模块，算法全换也不动它。

在实现时，只要业务代码始终依赖这些接口（而不是直接依赖某个具体库），就可以：

- 先用**标准 A\*** 跑通从 router-input 到 3D JSON 的闭环；
- 随后逐步对 P2/P3 的实现替换为 **MSSA\* / JPS / PBS / CBS**，而不会推倒路由层整体架构。

