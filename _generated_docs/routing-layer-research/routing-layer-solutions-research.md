# 空间路由层（Router）方案调研报告

本文档对**空间路由层**可能的技术方案进行调研与梳理，供实现选型与分阶段开发参考。  
**目标读者**：实现路由层模块的开发者、需要评估工作量与风险的项目负责人。

**关联文档**：  

- 项目整体管线与协议：根目录 [README.md](../../README.md)、[router-input-protocol](../router-protocol/) 与 [router-protocol 设计理由](../router-protocol/pre-router-protocol-design-rationale.md)  
- 生成层输入格式：`chemical-piping-lib` 的 `Final_JSON.md`（segments / tee_joints / assets / voxel_grid）

---

## 〇、路由层问题定义（输入 / 输出 / 要解决什么）

**只有把“路由层在解什么问题”拆清楚，才能判断哪些是单管寻路、哪些是多管顺序与冲突，以及算法/库该怎么选。**

### 输入（唯一真相来源）

- **router-input-protocol JSON**（图级）：`meta`（单位、坐标语义）、`nodes[]`（设备端口、连接点、边界等，有 `id`、`type`、可选 `location_2d`，**无 3D 坐标**）、`lines[]`（每条线：`from_node`、`to_node`、可选 `via_nodes[]`、管径、等级、流体类等）、`constraints`（禁行区、最小间距等）。  
- **不包含**：体素网格、3D 坐标、已有管线几何。

### 输出（下游唯一消费格式）

- **生成层 JSON**（几何就绪）：`meta`（含 `voxel_grid`）、`materials`、`assets[]`（设备几何 + `ports[]` 的 vc/wc）、`tee_joints[]`（三通位置与连接）、`segments[]`（每段 `from_port`/`to_port` + `components[]`：Pipe、Elbow、Valve、Reducer、Cap 等，带 vc/wc）。  
- 下游 **chemical-piping-lib** 只认这份 JSON，不认“图”或“路径点”以外的中间格式。

### 路由层要解决的四个子问题（分解）


| 子问题                   | 内容                                                                                       | 对应算法/模块                            | 说明                                                                                                                                   |
| --------------------- | ---------------------------------------------------------------------------------------- | ---------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------ |
| **P1. 节点 3D 占位**      | 为每个 node 赋予 3D 位置（体素 vc 或世界 wc），以便在体素网格上定起点/终点和禁行区。                                      | 占位规则或简单布局                          | 输入只有图级；若没有 3D，需根据 `location_2d`、设备表或场景假设生成。                                                                                          |
| **P2. 单管寻路**          | 对**一条** line（from → via_nodes → to）在 3D 体素网格上找一条无碰撞、曼哈顿（6 邻接）的路径。                        | *A / 改进 A* / JPS** 等               | 这是“单根管线”的路径规划；pathfinding3d、dijkstra3d、JPS3d 等都是在解这一类问题。                                                                             |
| **P3. 多管顺序与冲突**       | 多条 line 共享同一空间时，谁先布、谁后布；后布管线不能与先布管线占同一体素（或需满足最小间距）。                                      | **顺序 + 动态障碍** 或 **PBS/CBS** 等 MAPF | 若只做“按固定顺序一条条布、已布路径写入障碍”，就是**顺序 + 动态障碍**；文献中更优的做法是 **Priority-Based Search (PBS)** 或 **Conflict-Based Search (CBS)** 等，在顺序或冲突上做搜索/消解。 |
| **P4. 路径 → 生成层 JSON** | 将每条 line 的体素路径 + 属性 转为 `segments`/`tee_joints`/`assets`（Pipe、Elbow、Valve、Reducer、Cap 等）。 | 纯映射逻辑                              | 与寻路算法解耦；输入是路径点序列 + line 的 spec/valve 等，输出是生成层协议。                                                                                     |


**重要区分**：  

- **单管寻路（P2）** 只保证“这一根管”无碰撞、曼哈顿；**多管（P3）** 才涉及“多根管之间”不打架。  
- 开源库 **pathfinding3d、dijkstra3d** 只解决 **P2**；要解决 **P3**，要么在它们之上做“顺序 + 动态障碍”，要么接入/改造 **PBS、CBS** 等多智能体寻路（见下文 § 多管策略 与 非 A* 开源库）。

### 小结：输入 / 输出 / 问题

- **输入**：图级 JSON（nodes、lines、constraints），无 3D。  
- **输出**：生成层 JSON（voxel_grid、assets、tee_joints、segments 带 vc/wc）。  
- **要解决的**：P1 占位 → P2 单管寻路（可复用 A* 库）→ **P3 多管顺序/冲突**（顺序策略或 PBS/CBS）→ P4 路径转 JSON。

---

## 一、项目上下文与路由层职责

### 1.1 在整体管线中的位置

```
校验层输出 → router-input-protocol JSON（图级）→ [ 空间路由层 ] → 生成层 JSON（几何就绪）→ chemical-piping-lib / Blender
```

### 1.2 输入/输出 JSON 与路由层适配（本项目的具体契约）

以下明确**输入长什么样、输出长什么样**，以及路由层在中间必须完成的映射；任何算法或开源库的选型都需满足这套 I/O。

**输入（router-input-protocol，图级）：**


| 输入块           | 路由层如何使用                                                                                                                                                                                                                                                       |
| ------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `meta`        | `units.length`（m/mm）→ 与生成层单位一致；`coordinate_spaces` 仅语义，3D 由路由层自定。                                                                                                                                                                                             |
| `nodes[]`     | 每个 node 有 `id`、`type`（Equipment/EquipmentPort/Junction/Boundary）、可选 `location_2d`、`equipment_ref`。**关键**：路由层须为每个 node 赋予 3D 位置（体素 `vc` 或世界 `wc`），若协议未给 3D 则需根据场景假设或 2D 抬升规则生成占位；Equipment 的端口对应 node，其 `id` 将直接作为生成层 `from_port`/`to_port`。                   |
| `lines[]`     | 每条 line：`id`、`from_node`、`to_node`、可选 `via_nodes[]`、`nominal_diameter_mm`、`spec`、`fluid_class`、`layout_type`、`valve_subtype`（Gate/Ball）、`with_flanges` 等。**路由层**：在 3D 空间中找一条从 from_node 经 via_nodes 到 to_node 的无碰撞、曼哈顿路径；路径几何 + line 属性 → 生成层 `segments` 与组件。 |
| `constraints` | `routing_rules`（min_spacing、min_clearance、max_elbows 等）→ 体素禁行或代价；`keepout_zones` → 体素障碍；`preferred_zones` → 可选代价降低。                                                                                                                                           |


**输出（生成层协议，几何就绪）：**


| 输出块            | 路由层必须生成的内容                                                                                                                                                                                                                                          |
| -------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `meta`         | `protocol_version`、`generator`（如 `router_layer_v1`）、`coordinate_system`（right_handed, Z up, meter）、`voxel_grid`（voxel_size=0.2, origin_wc, dimensions）、可选 `scene_bounds`。                                                                           |
| `materials`    | 可从 line 的 `spec` 映射到 material_id（如 mat_carbon_steel），或沿用默认列表。                                                                                                                                                                                       |
| `assets[]`     | 由 `nodes` 中 type=Equipment 的节点生成：`id`、`type`（如 Tank）、`voxel_origin`/`voxel_extent` 或 `wc_center`、`geometry`、`ports[]`（每个 port 含 `port_id`= 对应 node.id、`vc`/`wc`、`direction`、`nominal_diameter`）。                                                    |
| `tee_joints[]` | 由 line 的 `via_nodes` 产生：每个 via 对应一个 tee，`vc_center`/`wc_center`、三个 `ports`（run_a、run_b、branch）分别 `connects_to_comp` 到相应 segment 的 component。                                                                                                        |
| `segments[]`   | 每条 line 被拆成一段或多段（经 via 则多段）。每段：`id`、`from_port`/`to_port`（node_id）、`spec`（nominal_diameter、material_id、with_flanges 等）、`components[]`。**路径 → components**：相邻路径点间同向为 Pipe，转向为 Elbow(90°)；line 上标注的阀门位置插入 Valve(Gate/Ball)；变径点插入 Reducer；末端无下游插入 Cap。 |


**适配要点小结：**

- 输入没有 3D 坐标时，路由层要负责**节点 3D 占位**（例如按 location_2d 投影到平面再按层高/设备表分配 z）。
- 寻路算法输出的是**体素路径**（或可转为体素）：`[(vx,vy,vz), ...]`，再按公式 `wc = origin_wc + (vc + 0.5) * voxel_size` 得到世界坐标，填入 Pipe/Elbow 的 `vc_start`/`vc_end`、`wc_start`/`wc_end`。
- 曼哈顿约束：6 邻接寻路得到的路径天然是轴对齐折线，每一拐点对应一个 Elbow；若用 26 邻接则需后处理“拉直”为仅 90° 弯头或放弃对角。

### 1.3 路由层要解决的核心问题


| 问题           | 说明                                                                                                   |
| ------------ | ---------------------------------------------------------------------------------------------------- |
| **图→路径**     | 将每条 `line`（from_node → to_node，可选 via_nodes）转化为 3D 空间中的一条无自交、满足约束的路径（路径点序列或体素序列）。                    |
| **碰撞与禁行**    | 路径不得穿过设备包围盒、禁行区（keepout_zones）；与已有管线、结构保持最小间距（routing_rules.min_spacing_between_parallel_lines_m 等）。 |
| **几何风格**     | 工业管道常采用**曼哈顿（横平竖直）**布线：沿轴对齐的直线 + 90° 弯头，便于施工与支撑；生成层已支持 Elbow、Tee，路由层需输出与之一致的走向。                      |
| **多管线顺序与冲突** | 多条 line 共享同一空间时，存在布线顺序问题：后布管线需避开先布管线，否则会产生几何冲突。需要顺序策略或全局冲突消解。                                        |
| **与生成层对齐**   | 路径需映射为生成层的 `segments`、`tee_joints`、端口引用（from_port/to_port），并插入弯头、三通、阀门、变径、管帽等组件。                     |


---

## 二、可整合的开源库与已有方案（Python 生态）

当前项目为 **Python 脚本**，优先考虑可直接接入的库或可借鉴的工程实现；若手写 A*，需关注性能（见第四节）。

### 2.1 pathfinding3d（纯 Python，易整合）

- **来源**：PyPI [pathfinding3d](https://pypi.org/project/pathfinding3d/)，GitHub [harisankar95/pathfinding3D](https://github.com/harisankar95/pathfinding3D)。
- **能力**：3D 网格上多种寻路（A*、Dijkstra、Theta* 等）；输入为 3D numpy 数组（≤0 为障碍，>0 为可行走且可带代价）；支持**仅 6 邻接**（曼哈顿） via `DiagonalMovement.never`，与生成层 Elbow 仅 90° 一致。
- **与本项目适配**：  
  - 输入：用 `nodes` + `constraints` 构建障碍矩阵（设备/keepout 置 0），单位与 `meta.units.length` 一致。  
  - 每条 line：`from_node`/`to_node`/`via_nodes` 先映射为体素坐标 (vx,vy,vz)，再分段寻路（start→via1→…→end），得到路径点列表。  
  - 输出：路径点即体素序列，按 §1.2 转为 `segments[].components`（Pipe/Elbow）及 `tee_joints`。
- **性能**：实现为**纯 Python**，大网格（如 100×100×50）或多管线时可能较慢；适合先做**最小闭环验证**与协议联调，再视需要换用高性能实现。

```python
# 示例：6 邻接 A*，曼哈顿路径
from pathfinding3d.core.grid import Grid
from pathfinding3d.finder.a_star import AStarFinder
from pathfinding3d.core.diagonal_movement import DiagonalMovement
import numpy as np
matrix = np.ones((nx, ny, nz), dtype=np.int8)  # 障碍处置 0
grid = Grid(matrix=matrix)
finder = AStarFinder(diagonal_movement=DiagonalMovement.never)
path, _ = finder.find_path(grid.node(sx,sy,sz), grid.node(ex,ey,ez), grid)
# path 为 Node 列表，需转为 (x,y,z) 或 vc 列表再写生成层 JSON
```

### 2.2 dijkstra3d（C++ 扩展，高性能）

- **来源**：PyPI [dijkstra3d](https://pypi.org/project/dijkstra3d/)，GitHub [seung-lab/dijkstra3d](https://github.com/seung-lab/dijkstra3d)。
- **能力**：3D 体素图上的 Dijkstra/A*（`compass=True` 即用“到终点距离”启发式，等价 A*）；**6/18/26 邻接**，本项目用 `connectivity=6` 即曼哈顿；底层 C++，**性能高**（文献中 512³ 体素 A* 约 0.5s）。
- **与本项目适配**：  
  - 输入：numpy 数组 `field`（可行走为正，障碍为 0 或 inf），`source`/`target` 为 `(x,y,z)` 元组。  
  - 输出：`path` 为 `[N,3]` 的 numpy 数组，每行为体素坐标，**可直接用作 vc 序列** 转 Pipe/Elbow。
- **注意**：许可证 GPLv3+，若项目需闭源分发须考虑兼容性；仅做校内/毕设可接受。

```python
import dijkstra3d
import numpy as np
# field: 可行走为正值，障碍为 0
path = dijkstra3d.dijkstra(field, source=(sx,sy,sz), target=(ex,ey,ez), connectivity=6, compass=True)
# path.shape = (N, 3)，即 vc 列表
```

### 2.3 KBE-piping-system（参考用，非直接整合）

- **来源**：GitHub [torsteinhov/KBE-piping-system](https://github.com/torsteinhov/KBE-piping-system)。  
- **说明**：基于知识工程的管系设计，输出为 CAD（如 Siemens NX）而非本项目的 JSON；输入/输出与 router-input、生成层协议均不同。可作为**布管逻辑与规则**的参考，不适合直接当“路由层库”接入；若需可自行做一层 I/O 适配或仅借鉴思路。

### 2.4 小结：库选型与适配（仅单管寻路 P2）


| 库                 | 语言/实现    | 6 邻接曼哈顿                    | 输入→输出                          | 性能      | 适配本项目          |
| ----------------- | -------- | -------------------------- | ------------------------------ | ------- | -------------- |
| **pathfinding3d** | 纯 Python | ✅ `DiagonalMovement.never` | numpy 障碍矩阵 → Node 列表 → 自转 vc   | 小网格够用   | 适合首版闭环、联调协议    |
| **dijkstra3d**    | C++ 扩展   | ✅ `connectivity=6`         | numpy + (src,tgt) → `[N,3]` vc | 高       | 适合正式实现、大场景；GPL |
| 手写 A*             | Python   | 可控                         | 自定                             | 依赖实现与优化 | 见 §四 性能建议      |


**说明**：上表只覆盖 **P2（单管寻路）**。**P3（多管顺序与冲突）** 需要额外策略或 MAPF 类库，见下节。

---

## 2.5 多管策略：顺序 vs PBS vs CBS（对应问题 P3）

多条 line 共享体素网格时，有两种思路：

**1. 顺序 + 动态障碍（Prioritized Planning 的极简版）**

- 先定一个**管线顺序**（如按 line id、管长、拓扑依赖等），然后**按顺序**对每条 line 做单管寻路（pathfinding3d 或 dijkstra3d）；每布完一条，把该路径占用的体素（可加膨胀以满足 min_spacing）写入障碍矩阵，下一条 line 的 A* 自然避开已布管线。
- **优点**：实现简单，与现有 3D A* 库完全兼容，无需改库。  
- **缺点**：顺序一旦固定，**可能无解**（例如先布的管把后布管的必经之路堵死），或**解质量差**（管长、弯头数等）；且**不完整**——有的顺序有解、有的无解，选错顺序就失败。

**2. PBS / CBS 等 MAPF 思路（文献中更合适的做法）**

- **Priority-Based Search (PBS)**：不固定顺序，而是在**优先级顺序空间**上搜索；对每个候选顺序做“按优先级顺序的单管寻路 + 动态障碍”，发现冲突则调整优先级再试。文献指出单纯固定顺序的 Prioritized Planning 既不完整也不最优，PBS 通过搜索顺序来提升可解性与质量（*Searching with Consistent Prioritization for Multi-Agent Path Finding*, AAAI；*Prioritised Planning: Completeness, Optimality, and Complexity*, JAIR）。  
- **Conflict-Based Search (CBS)**：不先定顺序，而是先给每条管线找一条路径，若发生冲突（两管占同一体素），再在**冲突**上分支、加约束、重规划，直到得到无冲突解。Tampere 论文 *Routing Multiple Branched Pipes using Multi-Terminal Pipe Router and Conflict-Based Search* 就是把 CBS 用在多分支管线路由上：低层用 Multi-Terminal Pipe Router 单管寻路，高层用 CBS 消解冲突。

**与本项目的关系**：  

- 若只做 **Demo / 管线数少**：**顺序 + 动态障碍** 即可，顺序可用启发式（如从长到短、按依赖关系）尽量降低无解概率。  
- 若要做**多管且希望可解性/质量更好**：需要引入 **PBS 或 CBS**；但当前 **MAPF 开源库多为 2D 网格 + 时间维**（Space-Time A*），**不是 3D 体素**。3D 管道的“冲突”是两管占同一 (x,y,z)，与 2D MAPF 的 (x,y,t) 不同，因此要么：(a) 在 2D MAPF 库上做 **3D 扩展**（例如把 3D 网格压成带时间或自定义图），要么 (b) 使用支持 **3D 网格** 的 MAPF 库（见下节“非 A* 开源库”）。

---

## 2.6 非 A* 的开源库（JPS、PBS、CBS 等）

当前**标准 A*** 的 3D 库（pathfinding3d、dijkstra3d）较成熟；*改进 A、JPS、PBS、CBS** 的开源情况如下。


| 类型             | 库/项目                                                                                      | 语言           | 维度             | 说明                                                                                           |
| -------------- | ----------------------------------------------------------------------------------------- | ------------ | -------------- | -------------------------------------------------------------------------------------------- |
| **JPS 3D**     | [KumarRobotics/jps3d](https://github.com/KumarRobotics/jps3d)                             | C++          | 3D 体素          | 3D Jump Point Search，BSD-3；无官方 Python 绑定，需自写或 FFI。                                           |
| **JPS**        | [libpath](https://github.com/SanitoGonzalez/libpath)                                      | C++ + Python | 文档多写 2D        | A* + JPS，Python 可调；是否支持 3D 需查源码。                                                             |
| **PBS**        | [Jiaoyang-Li/PBS](https://github.com/Jiaoyang-Li/PBS)                                     | C++          | 2D             | PBS 原实现；Python 侧 [MAPF_Baselines](https://github.com/ArvindCar/MAPF_Baselines) 含 PBS/CBS/PP。 |
| **CBS**        | [cbs-mapf](https://pypi.org/project/cbs-mapf/)（PyPI）                                      | Python       | **2D 网格**      | 匿名 MAPF，CBS + Space-Time A*；不支持 3D。                                                          |
| **CBS / MAPF** | [w9-pathfinding](https://pypi.org/project/w9-pathfinding/)                                | Python       | **2D 与 3D 网格** | 支持 Grid3D，含 CBS、ICTS、WHCA*、HCA* 等；**是少数支持 3D 的 MAPF 库**，可评估是否用于 P3。                          |
| **CBS**        | [GavinPHR/Multi-Agent-Path-Finding](https://github.com/GavinPHR/Multi-Agent-Path-Finding) | Python       | 2D             | 使用广泛，CBS + Space-Time A*；2D。                                                                 |


**结论**：  

- **单管寻路（P2）**：除 A* 外，**JPS 3D** 有 C++ 实现（jps3d），Python 需自绑或找 binding；**MSSA*** 无现成开源，需按论文自实现。  
- **多管冲突（P3）**：**PBS/CBS** 有 Python 实现，但多为 **2D**；**w9-pathfinding** 支持 3D 网格与 CBS，若接口能与本项目“管线 = 多段路径、冲突 = 共占体素”对上，可考虑接入；否则需在 2D 库上扩展 3D 或继续用“顺序 + 动态障碍”。

---

## 三、可能的路由层方案概览（算法与文献）

以下按“算法/方法论”分类；**方案 A、B 主要对应子问题 P2（单管寻路）**，**方案 C 对应 P3（多管顺序与冲突）**，方案 D/E/F 为补充或参考。实现时可与 §二 的库结合（如用 pathfinding3d/dijkstra3d 实现“方案 A”）。

### 3.1 方案 A：经典 3D 网格 A*

**思路**：将场景离散为 3D 体素网格（与生成层 `voxel_grid` 一致），设备与禁行区标记为障碍；对每条 line 的起点/终点（及 via_nodes）映射到体素坐标，在网格上用 A* 寻路。邻接关系采用 **6 邻接**，路径自然为轴对齐折线（曼哈顿）。

**优点**：实现简单、与现有协议中 `voxel_grid` 天然一致、易做碰撞检测（体素占用）。  
**缺点**：网格粒度固定，大场景下节点多、搜索慢；未显式优化弯头数或管长；多管线需额外处理顺序与动态障碍。

**适用性**：✅ 非常适合作为**第一版最小闭环**：读入 router-input JSON → 构网 → 对每条 line 做 A*（可用 pathfinding3d 或 dijkstra3d）→ 路径转 segments/tee_joints 输出。  

**参考文献**：  

- 核电管道 3D 网格 + A*：*Research and Application of Intelligent Layout Design Algorithm for 3D Pipeline of Nuclear Power Plant*，采用 Dijkstra 大空间 + 改进 A* 局部、3D 网格划分与 AABB-OBB 碰撞检测（[RePEc](https://ideas.repec.org/a/hin/jnlmpe/5198724.html)）。

---

### 3.2 方案 B：改进 A*（多策略 A*、JPS、启发式与权重）

**思路**：在网格 A* 基础上做优化，减少扩展节点、加快搜索或改善路径质量。

- *MSSA（Multi-Search Strategy A*）**：通过“节点方向判别规则、双层域扩展、多因子启发式、动态自适应权重”等机制，在 3D 管道路由中减少盲目遍历，提高解的质量与搜索效率。  
**引用**：*Improved multi-search strategy A algorithm to solve three-dimensional pipe routing design*，Expert Systems with Applications, Vol. 240, 2024, DOI: [10.1016/j.eswa.2023.122313](https://doi.org/10.1016/j.eswa.2023.122313)；[ScienceDirect](https://www.sciencedirect.com/science/article/abs/pii/S0957417423028154)。  
- **3D Jump Point Search (JPS)**：将 2D 的 JPS 对称破缺思想扩展到 3D 体素网格，在保持路径可行的前提下显著减少搜索节点，文献报道约一个数量级的加速。  
**引用**：*Pipe-Routing and Pathfinding in 3D (Student Abstract)*，T. K. Nobes，SoCS 2023；[AAAI SoCS](https://ojs.aaai.org/index.php/SOCS/article/view/27310)，DOI: 10.1609/socs.v16i1.27310。  
- **启发式与代价**：启发式可采用曼哈顿距离；代价可包含管长、弯头数、穿越禁行区的惩罚、与 GB 50316 相关的净距惩罚等。

**优点**：在不改变 I/O 协议的前提下提升性能与路径质量，便于在“方案 A 跑通”后迭代。  
**缺点**：实现复杂度高于朴素 A*，需维护更复杂的图或跳跃规则；*JPS/MSSA 在 Python 生态中无现成 3D 管道路由库**，若采用需自实现或基于 pathfinding3d 扩展。

**适用性**：✅ 推荐作为**第二阶段优化**：先实现方案 A（含 pathfinding3d 或 dijkstra3d），再引入 JPS 或 MSSA* 类改进以应对更大场景或更多管线。

### 3.2.1 工程上能否从 A* “顺畅”换到 MSSA*？（可扩展性）

**结论**：MSSA* **不是** 标准 A* 的“同接口替换”——内部机制不同（节点方向判别、双层域扩展、多因子启发式、动态权重）。但**工程上可以做到“可插拔”**，前提是**把“单管寻路”抽象成统一接口**，这样从 A* 换到 MSSA* 只改“实现体”，不改管线流程。

**做法**：  

- 定义**单管寻路接口**，例如：`find_path(grid_3d, start_vc, end_vc, via_vc_list=None, obstacles=None) -> List[Tuple[int,int,int]]`（体素路径）。  
- **当前**：用 pathfinding3d 或 dijkstra3d 实现该接口（内部是标准 A* / Dijkstra+compass）。  
- **后续**：若实现 MSSA*（按论文自写或移植），**同一接口**，仅把“调用 pathfinding3d/dijkstra3d”换成“调用 MSSA* 实现”；**上游**（建网、多管顺序、障碍更新）和**下游**（路径→segments/tee_joints）**都不必改**。  
- **需要改动的**：只有“单管寻路”这一块的**实现**（以及可能的代价矩阵格式，若 MSSA* 需要多因子代价）；**不是**整条路由推倒重写。

**因此**：“先做普通 A*，再换改进 A*”在工程上**成立**，条件是**一开始就把 P2 封装成上述 find_path 接口**，避免在业务代码里到处写死 pathfinding3d 或 dijkstra3d 的调用。

---

### 3.3 方案 C：多智能体路径规划（MAPF）与冲突消解

**思路**：将多条管线视为多个“智能体”，在共享的 3D 空间（如体素网格）中同时或顺序寻路，用 MAPF 算法避免几何冲突。

- **Conflict-Based Search (CBS) + Multi-Terminal Pipe Router**：高层用 CBS 做冲突检测与消解，低层用“多端点管线路由”单管寻路；适合多分支、多端点的管线在共享图中的无冲突布线。  
**引用**：*Routing Multiple Branched Pipes using Multi-Terminal Pipe Router and Conflict-Based Search*，Aapo Nikkilä，Tampere University 硕士论文，2020；[Trepo](https://trepo.tuni.fi/handle/10024/122387)。  
- **顺序布线 + 动态障碍**：简单做法是规定管线顺序（如按 line id 或优先级），先布的管线占用体素或包围盒，后布的 A* 将已占用空间视为障碍；实现简单，但顺序敏感，可能得不到全局最优。与 §二 的 pathfinding3d/dijkstra3d 兼容：每布完一条 line 将路径体素写入障碍矩阵再布下一条。

**优点**：从理论上支持多管线无冲突、可结合优化目标。  
**缺点**：MAPF/CBS 实现复杂；工业管线有分支（via_nodes、三通），需与“多端点管线路由”结合，工程量大；**暂无可直接接入的 Python CBS 管道路由库**。

**适用性**：⚠️ 适合作为**多管线冲突严重时的增强**：若简单“顺序 + 动态障碍”已能满足 Demo，可暂不引入完整 MAPF；若后续需要“多管同时优化”，再考虑 CBS 或简化版冲突搜索。

---

### 3.4 方案 D：连接图 + 蚁群/进化/组合优化

**思路**：不直接在体素网格上搜，而是先构建“可通行空间”的图（如关键点、走廊、设备间隙），再在图上做多目标优化（管长、弯头数、约束违反等）。

- **3D 连接图 + 蚁群**：用 3D connection graph 表示可行走区域，蚁群或并发蚁群优化直角布线，考虑多终端分支。  
**引用**：*Branch pipe routing based on 3D connection graph and concurrent ant colony optimization algorithm*，Journal of Intelligent Manufacturing, 2018；[RePEc](https://ideas.repec.org/a/spr/joinma/v29y2018i7d10.1007_s10845-016-1203-4.html)。  
- **线性规划 + A***：在航天等领域有“加权 A* + 线性规划”评估可行性与成本的组合（如矩形截面、有限弯头目录）。

**优点**：在复杂约束、多目标下可能得到更优的工程解。  
**缺点**：连接图构建与维护复杂；与当前“体素 + 生成层 voxel_grid”的约定需要适配或转换；**与本项目 I/O 的适配工作量大**，且无现成 Python 管道路由库可直用。

**适用性**：⚠️ 可作为**远期研究方向**：当 A* 类方案在质量或规模上遇到瓶颈时，再考虑图结构 + 元启发式。

---

### 3.5 方案 E：距离场 + 代价与梯度

**思路**：将场景转为 3D 距离场（到障碍的最小距离），在满足净距的“可行区域”内做路径搜索或梯度下降式规划；可结合 A* 的代价函数（如距离场值越小代价越高）。

**优点**：便于表达“与设备/管线保持最小间距”的软约束，适合 GB 50316 类净距要求。  
**缺点**：实现与体素网格的融合需要额外开发；曼哈顿约束仍需在搜索或后处理中保证。

**适用性**：🔶 可作为**约束表达增强**：在 A* 的代价或禁行区生成中引入距离场，而不是完全替换 A*。dijkstra3d 提供 `euclidean_distance_field`，可用来生成距离场再转为 A* 的代价权重。

---

### 3.6 方案 F：商业/开源 CAD 与 KBE 工具

**思路**：使用现有管道设计软件或 KBE（知识工程）库的 API，由外部完成布线，本系统只做 I/O 转换。

- **KBE-piping-system**：GitHub [torsteinhov/KBE-piping-system](https://github.com/torsteinhov/KBE-piping-system)，基于知识工程的管系设计，输出为 CAD（如 Siemens NX），非本项目 JSON；可参考其规则与几何生成思路，**不能直接当路由层**。  
- 商业 CAD（如 PDMS、SP3D、AutoCAD Plant 3D）通常具备自动/半自动布管，但协议与接口需定制，且依赖商业许可。

**优点**：成熟、合规性好，适合最终交付或与设计院协作。  
**缺点**：协议对接与许可成本高；毕设/ Demo 更强调“自研路由层”的闭环与可扩展性。

**适用性**：🔶 适合作为**对标与参考**，或后期“混合模式”（简单场景自研 Router，复杂场景导出到专业软件）。

---

## 四、Python 性能与手写算法注意

项目为 **Python 脚本**，若采用现成库或手写 A*，需注意以下性能与实现方式。

### 4.1 优先使用带 C/C++ 扩展的库

- **dijkstra3d**：底层 C++，512³ 体素 A* 约 0.5s（见其 PyPI/README benchmark），适合生产级网格与多管线；接口为 numpy 数组 + 元组，与 §1.2 的 vc 输出直接对应。  
- **pathfinding3d**：纯 Python，适合小网格与首版闭环；大网格下若成为瓶颈，可替换为 dijkstra3d 或自写 Cython 模块。

### 4.2 若手写 A* 的优化要点

（参考 Stack Overflow、Cython 实践等常见建议：）

- **数据结构**：open 表用 **heapq**（最小堆）取当前 f 最小节点，closed 用 **set** 做 O(1) 存在判断；避免 list 线性扫描与 list.insert(0) 的回溯。  
- **热点**：通常 `neighbors()` / 可通行判断占大部分时间；若用纯 Python 仍慢，可只将**邻接枚举与代价计算**用 **Numba**（`@numba.njit`）或 **Cython** 编译，其余逻辑保留 Python。  
- **Numba 适用**：紧循环、数值分支多的代码，改造成本小。  
- **Cython 适用**：需要更复杂逻辑或与 C 库交互时，对热点函数单独写 `.pyx` 并编译。

**结论**：能直接用 **dijkstra3d** 时建议优先使用，避免重复造轮且性能有保障；若因协议或约束必须自写（例如自定义代价、JPS 等），再考虑 Numba/Cython 热点优化。

---

## 五、碰撞与几何表达（与协议、生成层一致）

- **设备与禁行区**：将 `nodes` 中设备端口的位置（若有 `location_2d` 或占位）与 `constraints.keepout_zones` 映射到 3D 包围盒或体素占用；路由时这些体素不可通行。  
- **体素网格**：与生成层 `meta.voxel_grid`（voxel_size=0.2m、dimensions、origin_wc）一致，便于直接输出 `vc`（体素坐标）与 `wc`（世界坐标）。  
- **曼哈顿路径**：6 邻接 A* 得到的路径即为轴对齐折线；每一段方向变化对应一个 90° 弯头，与生成层 Elbow 一致。  
- **三通与 via_nodes**：line 的 `via_nodes` 在路径上必须经过；对应生成层 `tee_joints` 与多条 segments 的衔接。  
- **多管线间距**：`routing_rules.min_spacing_between_parallel_lines_m` 可通过“已布管线占用体素 + 膨胀一层/多层体素”实现，或在后处理中校验并迭代重布。

---

## 六、输出到生成层格式的映射要点（与 §1.2 呼应）

- **node_id（端口级）→ from_port / to_port**：协议约定 node_id 与生成层 port_id 建议一致，路由层输出 segment 时直接使用。  
- **路径 → segments[].components**：路径点序列按顺序生成 Pipe（直段）与 Elbow（拐点）；若 line 带 `valve_subtype`，在对应位置插入 Valve(Gate/Ball)；变径点插入 Reducer 并拆段；无下游端点插入 Cap。  
- **via_nodes → tee_joints**：一条 line 经 via_nodes 时拆成多段，在 via 处生成 tee_joint，并正确填写 connects_to_comp 与 run_a/run_b/branch。  
- **meta.generator**：可填 `router_layer_v1` 或具体实现名，便于溯源。

---

## 七、推荐实现路线（分阶段）

路线按**问题分解 P1→P2→P3→P4** 组织，并显式区分“单管”与“多管”。


| 阶段                | 对应子问题    | 内容                                                                                                                           | 方案选用                                      |
| ----------------- | -------- | ---------------------------------------------------------------------------------------------------------------------------- | ----------------------------------------- |
| **1. 最小闭环**       | P1+P2+P4 | 节点 3D 占位（简单规则）→ 体素网格（设备/禁行区）→ **单管** 6 邻接 A*（pathfinding3d 或 dijkstra3d）→ 路径→segments/tee_joints/assets；可先单管线、无 via 或简单 via。 | 方案 A；**P2 封装为 find_path 接口**，便于后续换 MSSA*。 |
| **2. 多管线（顺序）**    | P3       | 确定管线顺序（line id 或启发式），**顺序 + 动态障碍**：每布完一条将路径体素（+ 膨胀）写入障碍，下一条 A* 避开。校验无几何交叉。                                                   | 方案 A + 顺序 + 动态障碍                          |
| **3. 约束与代价**      | P2 代价    | 将 fluid_class、layout_type、keepout_zones 等转为禁行或高代价；可选距离场（方案 E）。                                                               | 方案 A/E 结合                                 |
| **4. 单管寻路升级**     | P2       | 大场景/多管线时，换用 **JPS 或 MSSA***（实现同一 find_path 接口），减少扩展节点、改善路径质量。                                                                | 方案 B；**工程上只换“单管寻路”实现**。                   |
| **5. 多管策略升级（可选）** | P3       | 若顺序布线常无解或解差，再评估 **PBS / CBS**：接入 w9-pathfinding（3D+CBS）或自实现/扩展 2D MAPF 到 3D。                                                 | 方案 C                                      |


---

## 八、总结表


| 方案                       | 对应子问题 | 核心思想                 | 推荐阶段     | 备注                                       |
| ------------------------ | ----- | -------------------- | -------- | ---------------------------------------- |
| **A. 3D 网格 A***          | P2    | 体素网格 + 6 邻接 A*，曼哈顿路径 | 第一阶段必做   | 与 voxel_grid、生成层对齐；P2 封装 find_path 便于换 B |
| *B. 改进 A / JPS / MSSA*** | P2    | 减少扩展节点、多因子启发式、动态权重   | 单管升级     | 同接口替换，非推倒重写                              |
| **顺序 + 动态障碍**            | P3    | 固定管线顺序，已布路径写入障碍      | 多管首版     | 简单，但顺序敏感、不完整                             |
| **C. PBS / CBS**         | P3    | 多管无冲突、搜索顺序或冲突树       | 多管升级（可选） | 开源多 2D；w9-pathfinding 支持 3D CBS          |
| **D. 连接图 + 蚁群等**         | —     | 图上的多目标优化             | 远期可选     | 需图构建与协议适配                                |
| **E. 距离场**               | P2 代价 | 净距与软约束               | 可与 A 结合  | 作代价或禁行生成                                 |
| **F. 商业/开源 KBE**         | —     | 外部布管 + 协议转换          | 对标或混合    | 协议与许可成本                                  |


**结论**：  

- **问题要拆开**：P1 占位、**P2 单管寻路**（A* 库）、**P3 多管顺序/冲突**（顺序 + 动态障碍 或 PBS/CBS）、P4 路径→JSON。  
- **单管（P2）**：用 pathfinding3d 或 dijkstra3d 实现 **find_path** 接口；后续可**同接口**换 JPS/MSSA*，工程上顺畅。  
- **多管（P3）**：先做**顺序 + 动态障碍**；若需更好可解性/质量，再考虑 **w9-pathfinding（3D CBS）** 或 PBS 类搜索。

---

## 参考文献与链接汇总


| 类型       | 说明                                             | 链接/引用                                                                                                                                                                                    |
| -------- | ---------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **开源库**  | pathfinding3d，3D 网格 A*，纯 Python，6 邻接           | [PyPI](https://pypi.org/project/pathfinding3d/)，[GitHub](https://github.com/harisankar95/pathfinding3D)                                                                                  |
| **开源库**  | dijkstra3d，3D 体素 Dijkstra/A*，C++ 扩展，6/18/26 邻接 | [PyPI](https://pypi.org/project/dijkstra3d/)，[GitHub](https://github.com/seung-lab/dijkstra3d)                                                                                           |
| **开源库**  | w9-pathfinding，MAPF 含 CBS，支持 2D/3D 网格          | [PyPI](https://pypi.org/project/w9-pathfinding/)，[CBS 文档](https://w9-pathfinding.readthedocs.io/stable/mapf/CBS.html)                                                                    |
| **开源库**  | JPS 3D，C++，3D 体素                               | [KumarRobotics/jps3d](https://github.com/KumarRobotics/jps3d)                                                                                                                            |
| **开源库**  | PBS / CBS，Python（多 2D）                         | [MAPF_Baselines](https://github.com/ArvindCar/MAPF_Baselines)，[cbs-mapf](https://pypi.org/project/cbs-mapf/)                                                                             |
| **参考项目** | KBE-piping-system，知识工程管系设计（非 JSON 协议）          | [GitHub](https://github.com/torsteinhov/KBE-piping-system)                                                                                                                               |
| **论文**   | MSSA* 改进 A* 用于 3D 管道路由                         | Expert Systems with Applications 240 (2024), [DOI](https://doi.org/10.1016/j.eswa.2023.122313), [ScienceDirect](https://www.sciencedirect.com/science/article/abs/pii/S0957417423028154) |
| **论文**   | 3D 管道路由与 JPS 扩展                                | Nobes, *Pipe-Routing and Pathfinding in 3D*, SoCS 2023, [AAAI SoCS](https://ojs.aaai.org/index.php/SOCS/article/view/27310)                                                              |
| **学位论文** | CBS + Multi-Terminal Pipe Router 多管无冲突布线       | Nikkilä, Tampere University 2020, [Trepo](https://trepo.tuni.fi/handle/10024/122387)                                                                                                     |
| **论文**   | PBS / 一致优先的多智能体寻路                              | *Searching with Consistent Prioritization for MAPF*, AAAI；*Prioritised Planning: Completeness, Optimality, and Complexity*, JAIR                                                         |
| **论文**   | 3D 连接图 + 蚁群优化分支管线路由                            | Journal of Intelligent Manufacturing (2018), [RePEc](https://ideas.repec.org/a/spr/joinma/v29y2018i7d10.1007_s10845-016-1203-4.html)                                                     |
| **论文**   | 核电 3D 管道智能布局（Dijkstra + A* + 碰撞检测）             | [RePEc](https://ideas.repec.org/a/hin/jnlmpe/5198724.html)                                                                                                                               |


---

*本文档为当前阶段调研结论，随实现与文献补充可更新。具体算法与条文引用以正式文献与项目代码为准。*
