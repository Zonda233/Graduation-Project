# Router Input Protocol

进入**空间路由层（Router）**之前的 JSON 协议定义。上游为感知/校验层（P&ID 或自然语言解析 + GB 50316 等规则校验），下游为路由层输出的、供 `chemical-piping-lib` 消费的生成层 JSON。

## 定位

- **图级抽象**：描述工艺拓扑（设备节点、逻辑管线、工艺属性与约束），默认不包含精细 3D 几何；可通过 `placement_hint` / `bbox_hint` / `constraints.spatial_rules` 提供体素级放置与粗粒度占用语义（供 NodePlacer 做不重叠与回退搜索）。Router 据此构建网格并执行 A* 寻路后，输出生成层协议。
- **与生成层关系**：本协议中的 `nodes`/`lines` 经 Router 映射为生成层的 `assets`、`tee_joints`、`segments`；node_id（端口级）与生成层 `from_port`/`to_port` 建议一致。若存在 `EquipmentPort` 的 `equipment_ref` 且无对应 `type=Equipment` 节点，当前路由层会为该 equipment 输出**占位设备**（如小尺寸 Tank），以便生成层画出罐体；设备尺寸与位置由路由层根据端口位置推断，非本协议字段。

## 目录结构

| 路径 | 说明 |
|------|------|
| [doc/PreRouter_JSON.md](doc/PreRouter_JSON.md) | 人类可读的协议说明（图级语义、字段与枚举） |
| [schema/router_input_v1.json](schema/router_input_v1.json) | JSON Schema 草案，用于校验与 IDE 提示 |
| [examples/](examples/) | 示例 JSON，供 Router 单元测试与联调（含 `complex_cooling_water.json` 复杂拓扑样例） |

## 版本

- 当前协议版本：**0.1.0**（草案）
- Schema 与文档会随协议迭代更新；扩展字段可先放在各对象的 `extra` 中试点。

## 参考

- 设计理由与字段汇总见项目根下 `_generated_docs/pre-router-protocol-design-rationale.md`（若存在）。
- 生成层协议见并列仓库 `chemical-piping-lib` 的 `chemical_piping_lib/doc/Final_JSON.md` 与 `schema/protocol_v1.json`。
