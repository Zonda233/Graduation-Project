# 进入 Router 前 JSON 协议规范（图级）

**版本：** `0.1.0`  
**适用模块：** 空间路由层（Router）输入  
**上游来源：** 感知层（VLM 解析 P&ID/自然语言）+ 校验层（如 GB 50316 规则）  
**下游输出：** 生成层协议（chemical-piping-lib 消费）

---

## 1. 总体结构

```json
{
  "meta":        { ... },
  "plant":       { ... },
  "nodes":       [ ... ],
  "lines":       [ ... ],
  "constraints": { ... },
  "source_trace": { ... }
}
```

| 顶层字段 | 类型 | 必需 | 说明 |
|----------|------|------|------|
| `meta` | object | ✅ | 协议版本、单位、坐标空间描述、生成器标识 |
| `plant` | object | ❌ | 工厂/区域/单元层级，轻量占位 |
| `nodes` | array | ✅ | 图顶点：设备端口、逻辑连接点、边界等 |
| `lines` | array | ✅ | 图边：逻辑工艺管线（from_node → to_node，可选 via_nodes） |
| `constraints` | object | ❌ | 路由约束与禁行/偏好区域 |
| `source_trace` | object | ❌ | P&ID 溯源与置信度，供 Agent 纠错闭环 |

**约定：** 所有对象通过 `id` 字符串引用；`id` 全局唯一。node_id（端口级）建议与生成层 `from_port`/`to_port` 可对应。

---

## 2. `meta` 块

| 字段 | 类型 | 必需 | 说明 |
|------|------|------|------|
| `schema_name` | string | ❌ | 固定 `"router_input_v1"` |
| `protocol_version` | string | ✅ | 语义版本，如 `"0.1.0"` |
| `created_at` | string | ❌ | ISO 8601 |
| `generator` | string | ❌ | 上游模块标识（如 VLM/校验层） |
| `units` | object | ❌ | `length`(mm/m)、`pressure`(kPa/MPa)、`temperature`(degC) |
| `coordinate_spaces` | object | ❌ | 描述 diagram_2d / plant_3d_hint 等，不给出具体 3D 坐标 |

---

## 3. `plant` 块（可选）

| 字段 | 类型 | 说明 |
|------|------|------|
| `plant_id` | string | 工厂 ID |
| `area_id` | string | 区域 |
| `unit_id` | string | 单元 |
| `system_id` | string | 系统（如 SYS-COOLING-WATER） |
| `extra` | object | 扩展 |

---

## 4. `nodes` 块

图的顶点，表示“管线可连接的位置”。设备端口建议为独立 node，便于与生成层 `assets[].ports`、`from_port`/`to_port` 一致。

| 字段 | 类型 | 必需 | 说明 |
|------|------|------|------|
| `id` | string | ✅ | 全局唯一，建议与生成层 port_id 对应 |
| `type` | string | ✅ | 见下表枚举 |
| `role` | string | ❌ | 语义角色，如 PumpSuction、TankNozzle、unit_battery_limit、maintenance_access |
| `label` | string | ❌ | 显示名 |
| `pid_tag` | string | ❌ | P&ID 设备位号（若为设备端口） |
| `equipment_ref` | string | ❌ | 所属设备 ID（若 type=EquipmentPort） |
| `ports` | array | ❌ | 仅 type=Equipment 时：内部端口列表 |
| `location_2d` | object | ❌ | P&ID 上近似位置，如 `{ "x", "y", "space": "diagram_2d" }` |
| `placement_hint` | object | ❌ | 放置提示（NodePlacer 使用）：如 `z_layers`、`anchor_policy`、`direction_preferred` |
| `bbox_hint` | object | ❌ | 体素占用提示：如 `extent_voxels:[ex,ey,ez]`、`clearance_voxels`（粗粒度 AABB） |
| `properties` | object | ❌ | 工艺属性（压力、温度、介质等）；`InlineInstrument` 可携带 `instrument_kind`/`nominal_diameter_mm`；`EquipmentPort` 可携带 `asset_type="custom_module"`、`port_local_wc`（局部端口坐标）、`port_kind` |
| `extra` | object | ❌ | 扩展 |

**node.type 枚举（建议）：** `Equipment` | `EquipmentPort` | `InlineInstrument` | `Junction` | `Boundary`

---

## 5. `lines` 块

逻辑工艺管线。一条 line 可能经 via_nodes 分支，路由后拆成多段 segment + tee_joints；变径、管帽由直径变化点与“无下游端点”表达。

| 字段 | 类型 | 必需 | 说明 |
|------|------|------|------|
| `id` | string | ✅ | 全局唯一 |
| `tag` | string | ❌ | 管道号风格，与 P&ID 标注对应（如物料-顺序-DN-等级） |
| `from_node` | string | ✅ | 起点 node id |
| `to_node` | string | ✅ | 终点 node id（末端封闭即对应生成层 Cap） |
| `via_nodes` | array | ❌ | 中间经过的节点 id 列表（如三通分支点） |
| `service` | string | ❌ | 介质/服务名（如 CoolingWater）；当值为 `instrument_signal` 时路由输出直段组件类型为 `SignalLine` |
| `fluid` | string | ❌ | 流体名 |
| `design_pressure_kpa` | number | ❌ | 设计压力 kPa |
| `design_temperature_degC` | number | ❌ | 设计温度 ℃ |
| `nominal_diameter_mm` | number | ❌ | 公称直径 mm；变径时可由多段或直径变化点表达 |
| `spec` | string | ❌ | 管道等级名，映射到生成层 material_id、pipe_schedule 等 |
| `fluid_class` | string | ❌ | GB 50316：`A1` \| `A2` \| `B` \| `C` \| `D`；可 `null`/`unknown` |
| `layout_type` | string | ❌ | 敷设方式：`above_ground` \| `trench` \| `buried` \| `pipe_rack` |
| `phase` | string | ❌ | 介质状态：`gas` \| `liquid` \| `steam` \| `two_phase` |
| `allow_backflow` | boolean | ❌ | 是否允许倒流；若 false 可要求止回阀 |
| `requires_check_valve` | boolean | ❌ | 是否需设止回阀 |
| `valve_subtype` | string | ❌ | 线上阀门类型（Demo）：`Gate` \| `Ball` |
| `with_flanges` | boolean | ❌ | 是否带法兰（预留字段；当前路由层生成的 JSON 一律输出为 `false`，以避免弯头/三通处多余法兰，后续将改为端口级 `flange_spec` 控制） |
| `is_relief_line` | boolean | ❌ | 是否泄压线（安全阀/爆破片出口） |
| `properties` | object | ❌ | 其他工艺属性 |
| `extra` | object | ❌ | 扩展 |

---

## 6. `constraints` 块（可选）

| 字段 | 类型 | 说明 |
|------|------|------|
| `routing_rules` | object | 全局规则：如 min_spacing_between_parallel_lines_m、min_clearance_to_floor_m、max_elbows_per_line、allow_overhead_crossing、min_passage_width_m |
| `spatial_rules` | object | NodePlacer 空间放置规则：如 `default_clearance_voxels`、`max_search_radius_voxels`、`default_z_layers` |
| `keepout_zones` | array | 禁行区：id、type、applies_to_lines、description、hint_2d、space_type（confined/ceiling_plenum/trench）、properties |
| `preferred_zones` | array | 偏好区：id、type、description、hint_2d |
| `extra` | object | 扩展 |

---

## 7. `source_trace` 块（可选）

| 字段 | 类型 | 说明 |
|------|------|------|
| `pid_document_id` | string | P&ID 文档 ID |
| `pages` | array | 页列表：page_id、image_ref、resolution |
| `nodes` | object | node_id → { page_id, bbox_px, symbol_id, confidence } |
| `lines` | object | line_id → { page_id, polyline_px, confidence } |
| `extra` | object | 扩展 |

---

## 8. 与生成层的映射关系（简要）

- **nodes（端口级）** → 生成层 `assets[].ports[].port_id`、`segments[].from_port`/`to_port`
- **lines[]** → Router 拆成多条 **segments** + **tee_joints**（via_nodes 对应三通）；变径点 → Reducer；无下游端点 → Cap
- **line.tag / spec / nominal_diameter_mm** → 生成层 segments[].spec、display_name
- **fluid_class / layout_type** → 供 GB 50316 规则引擎与 Router 代价/禁行区使用
- **InlineInstrument + instrument_signal** → 生成层 `assets[].type="Instrument"`（`ports[].port_id=node.id`）与信号段直段 `type="SignalLine"`，弯头仍为 `Elbow`

详见项目内设计理由文档与 `chemical-piping-lib` 的 `Final_JSON.md`。
