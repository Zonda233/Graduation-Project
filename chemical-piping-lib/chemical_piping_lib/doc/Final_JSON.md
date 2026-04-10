# 生成层输入 JSON 协议规范

**版本：** `1.0.0`
**适用模块：** `chemical_piping_lib`（生成层）
**上游来源：** 路由层（空间路由 A* 算法输出）

---

## 目录

1. [总体结构](#1-总体结构)
2. [meta 块](#2-meta-块)
3. [materials 块](#3-materials-块)
4. [assets 块（大型设备）](#4-assets-块大型设备)
5. [tee_joints 块（三通节点）](#5-tee_joints-块三通节点)
6. [segments 块（管线段）](#6-segments-块管线段)
7. [枚举值速查表](#7-枚举值速查表)
8. [完整示例](#8-完整示例)
9. [设计约定](#9-设计约定)

---

## 1. 总体结构

```json
{
  "meta":       { ... },
  "materials":  [ ... ],
  "assets":     [ ... ],
  "tee_joints": [ ... ],
  "segments":   [ ... ]
}
```


| 顶层字段         | 类型     | 必需  | 说明                            |
| ------------ | ------ | --- | ----------------------------- |
| `meta`       | object | ✅   | 协议版本、坐标系、体素网格基础参数             |
| `materials`  | array  | ✅   | 材质定义库，被其他块通过 `material_id` 引用 |
| `assets`     | array  | ✅   | 大型独立设备（储罐等），可为空数组             |
| `tee_joints` | array  | ✅   | 三通连接节点，可为空数组                  |
| `segments`   | array  | ✅   | 管线段，每段包含有序的管件序列               |


> **核心约定：** 所有对象间通过 `id` 字符串引用，不允许嵌套实体定义。所有 `id` 在整份 JSON 中必须全局唯一。

---

## 2. `meta` 块

```json
"meta": {
  "protocol_version": "1.0.0",
  "generator":        "router_layer_v1",
  "timestamp":        "2026-03-05T10:00:00Z",
  "coordinate_system": {
    "type":     "right_handed",
    "up_axis":  "Z",
    "unit":     "meter"
  },
  "voxel_grid": {
    "voxel_size":   0.2,
    "origin_wc":    [0.0, 0.0, 0.0],
    "dimensions":   [20, 20, 20]
  },
  "scene_bounds": {
    "min_wc": [0.0, 0.0, 0.0],
    "max_wc": [4.0, 4.0, 4.0]
  }
}
```


| 字段                          | 类型        | 必需  | 说明                          |
| --------------------------- | --------- | --- | --------------------------- |
| `protocol_version`          | string    | ✅   | 语义版本号，生成层用于兼容性检查            |
| `generator`                 | string    | ❌   | 上游模块标识，用于调试溯源               |
| `timestamp`                 | string    | ❌   | ISO 8601 格式                 |
| `coordinate_system.type`    | string    | ✅   | 固定值 `"right_handed"`        |
| `coordinate_system.up_axis` | string    | ✅   | 固定值 `"Z"`，与 Blender 默认一致    |
| `coordinate_system.unit`    | string    | ✅   | 固定值 `"meter"`               |
| `voxel_grid.voxel_size`     | float     | ✅   | 体素边长（米），本项目固定 `0.2`         |
| `voxel_grid.origin_wc`      | [float×3] | ✅   | 体素坐标 `[0,0,0]` 对应的世界坐标      |
| `voxel_grid.dimensions`     | [int×3]   | ✅   | 网格尺寸（格数），本项目固定 `[20,20,20]` |
| `scene_bounds`              | object    | ❌   | 场景包围盒，供生成层做越界检查             |


**坐标转换公式：**

```
体素坐标 vc = [vx, vy, vz]（整数）
世界坐标 wc = origin_wc + (vc + 0.5) × voxel_size
             即体素中心点的世界坐标
```

---

## 3. `materials` 块

```json
"materials": [
  {
    "id":           "mat_carbon_steel",
    "display_name": "碳钢",
    "visual": {
      "base_color": [0.4, 0.4, 0.45, 1.0],
      "metallic":   0.9,
      "roughness":  0.4
    }
  }
]
```


| 字段                  | 类型        | 必需  | 说明                                                 |
| ------------------- | --------- | --- | -------------------------------------------------- |
| `id`                | string    | ✅   | 全局唯一，被其他块通过 `material_id` 引用                       |
| `display_name`      | string    | ❌   | 在 Blender 材质列表中显示的名称                               |
| `visual.base_color` | [float×4] | ✅   | RGBA，值域 `[0.0, 1.0]`，对应 Principled BSDF Base Color |
| `visual.metallic`   | float     | ✅   | 值域 `[0.0, 1.0]`，对应 Principled BSDF Metallic        |
| `visual.roughness`  | float     | ✅   | 值域 `[0.0, 1.0]`，对应 Principled BSDF Roughness       |


**内置材质 ID 约定（生成层预置，可直接引用无需在 materials 数组中重复定义）：**


| `material_id`         | 说明       |
| --------------------- | -------- |
| `mat_carbon_steel`    | 碳钢（管道默认） |
| `mat_stainless_steel` | 不锈钢      |
| `mat_valve_body`      | 阀门本体（红色） |


---

## 4. `assets` 块（大型设备）

每个 asset 对应一个独立的工艺设备（如储罐、容器）。

### 4.1 通用字段

```json
{
  "id":           "tank_01",
  "type":         "Tank",
  "display_name": "原料储罐 T-101",
  "voxel_origin": [2, 2, 0],
  "voxel_extent": [3, 3, 6],
  "material_id":  "mat_stainless_steel",
  "geometry":     { ... },
  "ports":        [ ... ]
}
```


| 字段             | 类型        | 必需  | 说明                                                            |
| -------------- | --------- | --- | ------------------------------------------------------------- |
| `id`           | string    | ✅   | 全局唯一资产标识                                                      |
| `type`         | string    | ✅   | 见[枚举值速查表](#7-枚举值速查表)                                          |
| `display_name` | string    | ❌   | Blender 对象名称                                                  |
| `voxel_origin` | [int×3]   | 条件  | 包围盒最小角体素坐标；与 `voxel_extent` 或 `wc_center` 二选一                 |
| `voxel_extent` | [int×3]   | 条件  | 包围盒尺寸（格数）；与 `voxel_origin` 成对，或改用 `wc_center`                 |
| `wc_center`    | [float×3] | ❌   | 设备几何中心世界坐标；省略时由 `voxel_origin`+`voxel_extent` 推导（见 Tank 定位约定） |
| `material_id`  | string    | ✅   | 引用 `materials` 中的 `id`                                        |
| `geometry`     | object    | ✅   | 该 `type` 专属几何参数，见下                                            |
| `ports`        | array     | ✅   | 设备对外接口，见 [4.3 节](#43-port-对象)                                 |


### 4.2 `geometry` 字段（按 type 分类）

#### `type: "Tank"`（储罐）

```json
"geometry": {
  "shell_radius":  0.5,
  "shell_height":  0.8,
  "head_type":     "ellipsoidal",
  "head_ratio":    0.25,
  "orientation":   "vertical"
}
```


| 字段             | 类型     | 必需  | 说明                                             |
| -------------- | ------ | --- | ---------------------------------------------- |
| `shell_radius` | float  | ✅   | 筒体半径（米）                                        |
| `shell_height` | float  | ✅   | 筒体高度（米），不含封头                                   |
| `head_type`    | string | ✅   | `"ellipsoidal"` | `"hemispherical"` | `"flat"` |
| `head_ratio`   | float  | ❌   | 椭球封头高度与半径之比，默认 `0.25`（2:1 标准封头）                |
| `orientation`  | string | ✅   | `"vertical"` | `"horizontal"`                  |


**Tank 定位（生成层约定）：** 设备位置可由 `voxel_origin` + `voxel_extent` 推导中心，或显式给出 `wc_center`。`wc_center` 表示储罐**几何中心**（筒体+封头组装体中心）。立式罐罐底世界坐标 = `wc_center.z - (shell_height/2 + head_height)`（`head_height`：半球 = shell_radius，椭球 = shell_radius×head_ratio）。端口若省略 `wc`，由 `direction` 与几何自动推导；底部 -Z 端口根在罐底表面。编排管线时须保证罐底与喷嘴不插入下方弯头/直管：喷嘴末端应与 segments 首段管件 `wc_start` 一致，故 `wc_center.z` = 首段 `wc_start.z` + nozzle_length + shell_height/2 + head_height。

### 4.3 `port` 对象

设备接口点，是管线段与设备的连接锚点。

```json
{
  "port_id":          "tank_01_nozzle_bottom",
  "role":             "outlet",
  "vc":               [3, 3, 0],
  "wc":               [0.7, 0.7, 0.0],
  "direction":        "-Z",
  "nominal_diameter": 0.1,
  "flange_spec": {
    "standard":       "GB/T 9119",
    "pressure_class": "PN16",
    "face_type":      "RF",
    "thickness_m":    0.022
  }
}
```


| 字段                 | 类型        | 必需  | 说明                                            |
| ------------------ | --------- | --- | --------------------------------------------- |
| `port_id`          | string    | ✅   | 全局唯一，被 `segments[].from_port` / `to_port` 引用  |
| `role`             | string    | ❌   | `"inlet"` | `"outlet"` | `"vent"` | `"drain"` |
| `vc`               | [int×3]   | ✅   | 接口所在体素坐标                                      |
| `wc`               | [float×3] | ✅   | 接口世界坐标（bpy 直接使用）                              |
| `direction`        | string    | ✅   | 接管朝外方向，见[枚举值速查表](#7-枚举值速查表)                   |
| `nominal_diameter` | float     | ✅   | 公称直径（米），如 `0.1` 表示 DN100                      |
| `flange_spec`      | object    | ❌   | 接管法兰规格，省略时继承所属管线段的 `spec`                     |


---

## 5. `tee_joints` 块（三通节点）

三通是管线拓扑分叉点，**不归属于任何单一 segment**，在顶层独立定义。

```json
"tee_joints": [
  {
    "tee_id":     "tee_01",
    "vc_center":  [5, 3, 3],
    "wc_center":  [1.1, 0.7, 0.7],
    "ports": [
      {
        "port_id":         "tee_01_run_a",
        "axis":            "-X",
        "connects_to_comp": "seg01_c03"
      },
      {
        "port_id":         "tee_01_run_b",
        "axis":            "+X",
        "connects_to_comp": "seg02_c01"
      },
      {
        "port_id":         "tee_01_branch",
        "axis":            "+Y",
        "connects_to_comp": "seg03_c01"
      }
    ],
    "spec": {
      "main_diameter":   0.1,
      "branch_diameter": 0.1,
      "material_id":     "mat_carbon_steel"
    }
  }
]
```


| 字段                         | 类型        | 必需  | 说明                     |
| -------------------------- | --------- | --- | ---------------------- |
| `tee_id`                   | string    | ✅   | 全局唯一标识                 |
| `vc_center`                | [int×3]   | ✅   | 三通中心体素坐标               |
| `wc_center`                | [float×3] | ✅   | 三通中心世界坐标               |
| `ports`                    | array     | ✅   | 恰好 3 个端口对象             |
| `ports[].port_id`          | string    | ✅   | 全局唯一                   |
| `ports[].axis`             | string    | ✅   | 该端口朝外方向                |
| `ports[].connects_to_comp` | string    | ✅   | 引用相邻管件的 `comp_id`      |
| `spec.main_diameter`       | float     | ✅   | 主管公称直径（米）              |
| `spec.branch_diameter`     | float     | ✅   | 支管公称直径（米），等径三通时与主管相同   |
| `spec.material_id`         | string    | ✅   | 引用 `materials` 中的 `id` |


> **拓扑约定：** 两个 `axis` 方向互为反方向的端口为**主管（run）**，第三个为**支管（branch）**。生成层通过此约定自动判断布尔操作方向。
> **几何拼接约定：** 连接 tee 的 Pipe 应与 tee 对应端口位置对齐（由端口 `axis` 与 tee 本体长度共同决定），不应将 Pipe 端点放在 `tee.wc_center`，否则会与三通实体重叠。

---

## 6. `segments` 块（管线段）

管线段是从一个端口到另一个端口的完整路径，内部包含**有序的管件序列**。

### 6.1 段头部字段

```json
{
  "id":           "seg_01",
  "display_name": "T-101出口到V-201入口",
  "from_port":    "tank_01_nozzle_bottom",
  "to_port":      "valve_01_port_a",
  "spec": {
    "nominal_diameter": 0.1,
    "pipe_schedule":    "SCH40",
    "material_id":      "mat_carbon_steel",
    "with_flanges":     true,
    "flange_face_type": "RF"
  },
  "components": [ ... ]
}
```


| 字段                      | 类型     | 必需  | 说明                                                   |
| ----------------------- | ------ | --- | ---------------------------------------------------- |
| `id`                    | string | ✅   | 全局唯一                                                 |
| `display_name`          | string | ❌   | 用于 Blender Collection 命名                             |
| `from_port`             | string | ✅   | 起始端口 `port_id`，引用 asset 或 tee_joint 的端口；`null` 表示自由端 |
| `to_port`               | string | ✅   | 终止端口 `port_id`；`null` 表示自由端                          |
| `spec.nominal_diameter` | float  | ✅   | 本段管线公称直径（米），管件默认继承此值；遇 Reducer 后下游自动沿用其 `diameter_out_m` |
| `spec.pipe_schedule`    | string | ❌   | 管道壁厚标准，如 `"SCH40"`，用于查 DN 表                          |
| `spec.material_id`      | string | ✅   | 本段默认材质                                               |
| `spec.with_flanges`     | bool   | ✅   | 是否为本段管线启用自动法兰生成；**当前路由层自动生成的 JSON 为了避免弯头/三通内部多余法兰，一律将其置为 `false`，推荐使用端口级 `port.flange_spec` 精细控制** |
| `spec.flange_face_type` | string | ❌   | `"RF"`（突面）| `"FF"`（全平面），默认 `"RF"`                    |
| `components`            | array  | ✅   | 有序管件序列，从 `from_port` 到 `to_port` 方向排列                |


### 6.2 `components` 数组——管件对象

所有管件共有以下基础字段：


| 字段        | 类型     | 必需  | 说明                                          |
| --------- | ------ | --- | ------------------------------------------- |
| `comp_id` | string | ✅   | 全局唯一，被 `tee_joints` 的 `connects_to_comp` 引用 |
| `type`    | string | ✅   | 见[枚举值速查表](#7-枚举值速查表)                        |


---

#### `type: "Pipe"`（直管）

```json
{
  "comp_id":  "seg01_c01",
  "type":     "Pipe",
  "vc_start": [3, 3, 0],
  "vc_end":   [3, 3, 3],
  "wc_start": [0.7, 0.7, 0.1],
  "wc_end":   [0.7, 0.7, 0.7],
  "axis":     "+Z",
  "length_m": 0.6
}
```


| 字段                    | 类型        | 必需  | 说明                                  |
| --------------------- | --------- | --- | ----------------------------------- |
| `vc_start` / `vc_end` | [int×3]   | ✅   | 起止体素坐标                              |
| `wc_start` / `wc_end` | [float×3] | ✅   | 起止世界坐标（bpy 直接使用）                    |
| `axis`                | string    | ✅   | 管道延伸方向（从 start 指向 end）              |
| `length_m`            | float     | ✅   | 管道长度（米），应与 `wc_start`/`wc_end` 距离一致 |


---

#### `type: "Elbow"`（弯头）

```json
{
  "comp_id":       "seg01_c02",
  "type":          "Elbow",
  "vc_center":     [3, 3, 3],
  "wc_center":     [0.7, 0.7, 0.7],
  "axis_in":       "+Z",
  "axis_out":      "+X",
  "angle_deg":     90,
  "bend_radius_m": 0.15
}
```


| 字段              | 类型        | 必需  | 说明                               |
| --------------- | --------- | --- | -------------------------------- |
| `vc_center`     | [int×3]   | ✅   | 弯头所在体素坐标                         |
| `wc_center`     | [float×3] | ✅   | 弯头转角处世界坐标                        |
| `axis_in`       | string    | ✅   | 流体进入方向                           |
| `axis_out`      | string    | ✅   | 流体离开方向                           |
| `angle_deg`     | int       | ✅   | 弯曲角度，枚举值：`45` | `90`             |
| `bend_radius_m` | float     | ❌   | 弯曲半径（米），默认 `1.5 × 管道外径`（工业长半径标准） |


> **约束：** `axis_in` 与 `axis_out` 不得相同，不得互为反方向（反方向为 180° 直管，不是弯头）。
> **几何拼接约定：** 与 Elbow 相邻的 Pipe 端点应位于弯头切点（而非 `wc_center`），避免出现“拐角处两段直管多伸出一段”的重叠。

---

#### `type: "Valve"`（阀门）

```json
{
  "comp_id":          "seg01_c03",
  "type":             "Valve",
  "subtype":          "Gate",
  "vc_start":         [6, 3, 3],
  "vc_end":           [8, 3, 3],
  "wc_start":         [1.3, 0.7, 0.7],
  "wc_end":           [1.7, 0.7, 0.7],
  "axis":             "+X",
  "nominal_diameter": 0.1
}
```


| 字段                    | 类型        | 必需  | 说明                                       |
| --------------------- | --------- | --- | ---------------------------------------- |
| `subtype`             | string    | ✅   | `"Gate"` | `"Ball"`，见[枚举值速查表](#7-枚举值速查表) |
| `vc_start` / `vc_end` | [int×3]   | ✅   | 阀门两端体素坐标，通常跨 2 个体素                       |
| `wc_start` / `wc_end` | [float×3] | ✅   | 阀门两端世界坐标（即管道连接端面位置）                      |
| `axis`                | string    | ✅   | 阀门通流方向                                   |
| `nominal_diameter`    | float     | ❌   | 若与 `spec` 不同可在此覆盖                        |


---

#### `type: "Reducer"`（变径管）

```json
{
  "comp_id":         "seg01_c04",
  "type":            "Reducer",
  "vc_start":        [8, 3, 3],
  "vc_end":          [9, 3, 3],
  "wc_start":        [1.7, 0.7, 0.7],
  "wc_end":          [1.9, 0.7, 0.7],
  "axis":            "+X",
  "diameter_in_m":   0.1,
  "diameter_out_m":  0.05
}
```


| 字段               | 类型    | 必需  | 说明         |
| ---------------- | ----- | --- | ---------- |
| `diameter_in_m`  | float | ✅   | 入口端公称直径（米） |
| `diameter_out_m` | float | ✅   | 出口端公称直径（米） |

> **生成层约定：** 同一 segment 内，紧接在 Reducer 之后的 Pipe、Valve 等管件会自动使用该 Reducer 的 `diameter_out_m` 作为 `nominal_diameter`，无需在 JSON 中为下游管件重复指定；若需覆盖可在该 component 上显式写 `nominal_diameter`。

---

#### `type: "Cap"`（管帽/盲端）

```json
{
  "comp_id":  "seg01_c05",
  "type":     "Cap",
  "vc":       [10, 3, 3],
  "wc":       [2.1, 0.7, 0.7],
  "axis":     "+X"
}
```


| 字段     | 类型        | 必需  | 说明                |
| ------ | --------- | --- | ----------------- |
| `vc`   | [int×3]   | ✅   | 管帽所在体素坐标          |
| `wc`   | [float×3] | ✅   | 管帽端面世界坐标          |
| `axis` | string    | ✅   | 指向管帽封堵方向（即管道终止方向） |


---

## 7. 枚举值速查表

### `axis` 方向枚举


| 值      | 含义      | Blender 向量   |
| ------ | ------- | ------------ |
| `"+X"` | 向右      | `(1, 0, 0)`  |
| `"-X"` | 向左      | `(-1, 0, 0)` |
| `"+Y"` | 向前（屏幕内） | `(0, 1, 0)`  |
| `"-Y"` | 向后      | `(0, -1, 0)` |
| `"+Z"` | 向上      | `(0, 0, 1)`  |
| `"-Z"` | 向下      | `(0, 0, -1)` |


### `type`（资产类型）枚举


| 值           | 所属块                   | 说明  |
| ----------- | --------------------- | --- |
| `"Tank"`    | `assets`              | 储罐  |
| `"Pipe"`    | `segments.components` | 直管  |
| `"Elbow"`   | `segments.components` | 弯头  |
| `"Valve"`   | `segments.components` | 阀门  |
| `"Reducer"` | `segments.components` | 变径管 |
| `"Cap"`     | `segments.components` | 管帽  |


### `Valve.subtype` 枚举


| 值        | 说明  |
| -------- | --- |
| `"Gate"` | 闸阀  |
| `"Ball"` | 球阀  |


### `Tank.geometry.head_type` 枚举


| 值                 | 说明             |
| ----------------- | -------------- |
| `"ellipsoidal"`   | 椭球封头（2:1，工业标准） |
| `"hemispherical"` | 半球封头           |
| `"flat"`          | 平封头（无封头）       |


### `Tank.geometry.orientation` 枚举


| 值              | 说明            |
| -------------- | ------------- |
| `"vertical"`   | 立式（筒体轴线平行 +Z） |
| `"horizontal"` | 卧式（筒体轴线平行 +X） |


---

## 8. 完整示例

一个最小可运行场景：**立式储罐 → 弯头 → 闸阀 → 排液管**。

```json
{
  "meta": {
    "protocol_version": "1.0.0",
    "generator": "router_layer_v1",
    "timestamp": "2026-03-05T10:00:00Z",
    "coordinate_system": {
      "type": "right_handed",
      "up_axis": "Z",
      "unit": "meter"
    },
    "voxel_grid": {
      "voxel_size": 0.2,
      "origin_wc": [0.0, 0.0, 0.0],
      "dimensions": [20, 20, 20]
    },
    "scene_bounds": {
      "min_wc": [0.0, 0.0, 0.0],
      "max_wc": [4.0, 4.0, 4.0]
    }
  },

  "materials": [
    {
      "id": "mat_cs",
      "display_name": "碳钢",
      "visual": {
        "base_color": [0.4, 0.4, 0.45, 1.0],
        "metallic": 0.9,
        "roughness": 0.4
      }
    },
    {
      "id": "mat_ss",
      "display_name": "不锈钢",
      "visual": {
        "base_color": [0.75, 0.75, 0.8, 1.0],
        "metallic": 1.0,
        "roughness": 0.2
      }
    }
  ],

  "assets": [
    {
      "id": "tank_01",
      "type": "Tank",
      "display_name": "原料储罐 T-101",
      "voxel_origin": [2, 2, 2],
      "voxel_extent": [4, 4, 8],
      "material_id": "mat_ss",
      "geometry": {
        "shell_radius": 0.35,
        "shell_height": 0.8,
        "head_type": "ellipsoidal",
        "head_ratio": 0.25,
        "orientation": "vertical"
      },
      "ports": [
        {
          "port_id": "tank_01_outlet",
          "role": "outlet",
          "vc": [4, 4, 2],
          "wc": [0.9, 0.9, 0.4],
          "direction": "-Z",
          "nominal_diameter": 0.1
        }
      ]
    }
  ],

  "tee_joints": [],

  "segments": [
    {
      "id": "seg_01",
      "display_name": "T-101出口排液管线",
      "from_port": "tank_01_outlet",
      "to_port": null,
      "spec": {
        "nominal_diameter": 0.1,
        "pipe_schedule": "SCH40",
        "material_id": "mat_cs",
        "with_flanges": true,
        "flange_face_type": "RF"
      },
      "components": [
        {
          "comp_id": "s01_c01",
          "type": "Pipe",
          "vc_start": [4, 4, 2],
          "vc_end":   [4, 4, 0],
          "wc_start": [0.9, 0.9, 0.4],
          "wc_end":   [0.9, 0.9, 0.0],
          "axis": "-Z",
          "length_m": 0.4
        },
        {
          "comp_id": "s01_c02",
          "type": "Elbow",
          "vc_center": [4, 4, 0],
          "wc_center": [0.9, 0.9, 0.0],
          "axis_in":  "-Z",
          "axis_out": "+X",
          "angle_deg": 90,
          "bend_radius_m": 0.15
        },
        {
          "comp_id": "s01_c03",
          "type": "Valve",
          "subtype": "Gate",
          "vc_start": [5, 4, 0],
          "vc_end":   [7, 4, 0],
          "wc_start": [1.1, 0.9, 0.0],
          "wc_end":   [1.5, 0.9, 0.0],
          "axis": "+X",
          "nominal_diameter": 0.1
        },
        {
          "comp_id": "s01_c04",
          "type": "Pipe",
          "vc_start": [7, 4, 0],
          "vc_end":   [10, 4, 0],
          "wc_start": [1.5, 0.9, 0.0],
          "wc_end":   [2.1, 0.9, 0.0],
          "axis": "+X",
          "length_m": 0.6
        },
        {
          "comp_id": "s01_c05",
          "type": "Cap",
          "vc": [10, 4, 0],
          "wc": [2.1, 0.9, 0.0],
          "axis": "+X"
        }
      ]
    }
  ]
}
```

---

## 9. 设计约定

### 9.1 ID 命名规范


| ID 类型     | 推荐格式                            | 示例               |
| --------- | ------------------------------- | ---------------- |
| asset     | `{类型缩写}_{两位序号}`                 | `tank_01`        |
| port（设备）  | `{asset_id}_{接管位置}`             | `tank_01_outlet` |
| tee       | `tee_{两位序号}`                    | `tee_01`         |
| port（三通）  | `{tee_id}_{run_a|run_b|branch}` | `tee_01_branch`  |
| segment   | `seg_{两位序号}`                    | `seg_01`         |
| component | `s{段序号}_c{管件序号}`                | `s01_c03`        |


### 9.2 坐标双轨制约定

每个管件**同时提供体素坐标（`vc`）和世界坐标（`wc`）**：

- `vc`（体素坐标，整数）：供校验层复检、调试定位使用
- `wc`（世界坐标，浮点米制）：供 bpy 直接使用，**生成层以 `wc` 为准**

两者应满足：`wc = origin_wc + (vc + 0.5) × voxel_size`，不满足时生成层发出 `WARNING` 但仍继续执行。

### 9.3 `components` 有序性约定

`segments[].components` 数组**必须按流向顺序排列**（从 `from_port` 到 `to_port`）。生成层依此顺序依次构造，确保布尔操作与端口注册的稳定性。

### 9.4 法兰的隐式生成规则

当 `spec.with_flanges == true` 时，生成层可以在管线端点自动添加法兰，以减少 JSON 冗余。但实际工程中，**弯头内部、三通内部通常不应出现独立法兰**，因此对于由路由层自动生成的场景，暂不使用该开关，统一置为 `false`，后续将通过：

- 设备/阀门端口上的 `port.flange_spec`
- 以及显式建模的法兰组件

来表达法兰位置与规格。

### 9.5 公称直径与实际几何尺寸

`nominal_diameter` 是**公称直径**（米），不是实际外径。生成层内部查 DN 规格表（`config.DN_TABLE`）得到实际外径与壁厚。同一 segment 内，紧接在 **Reducer** 之后的 Pipe、Valve 等会自动使用该 Reducer 的 `diameter_out_m` 作为当前公称直径，直至本段结束或遇到新的 Reducer。


| 公称直径    | DN 标准 | 实际外径（米）  | 壁厚 SCH40（米） |
| ------- | ----- | -------- | ----------- |
| `0.025` | DN25  | `0.0334` | `0.0038`    |
| `0.050` | DN50  | `0.0603` | `0.0046`    |
| `0.100` | DN100 | `0.1143` | `0.0060`    |
| `0.150` | DN150 | `0.1683` | `0.0071`    |
| `0.200` | DN200 | `0.2191` | `0.0081`    |


### 9.6 版本兼容性


| 字段变化   | 版本升级策略                         |
| ------ | ------------------------------ |
| 新增可选字段 | 次版本升级（`1.0.0` → `1.1.0`），向后兼容  |
| 新增必需字段 | 主版本升级（`1.x.x` → `2.0.0`），不向后兼容 |
| 枚举值新增  | 次版本升级                          |
| 坐标系变更  | 主版本升级                          |


生成层在收到 JSON 后，首先检查 `meta.protocol_version` 的主版本号是否匹配，不匹配则**立即抛出异常**拒绝执行。