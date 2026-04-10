# 示例 JSON

| 文件 | 说明 |
|------|------|
| [minimal_router_input.json](minimal_router_input.json) | 最小图：单储罐出口 → 单条管线 → 末端封闭（Cap）。本例省略 `location_2d`，验证拓扑自动布局 + `placement_hint/bbox_hint/spatial_rules`。 |
| [sample_cooling_water.json](sample_cooling_water.json) | 储罐 → 三通分支点（via_nodes）→ 主管末端 + 支管末端。本例同样省略 `location_2d`，用于验证无坐标提示时的 NodePlacer 布局稳定性。 |
| [complex_cooling_water.json](complex_cooling_water.json) | 较复杂图：1 个设备出口 + 2 个三通 + 3 条管线（主管穿过两级三通 + 两级分支），用于验证弯头切点裁剪、三通端口裁剪与多段连接正确性。 |

使用方式：Router 或校验脚本将 JSON 路径作为输入，解析后构图、执行寻路或规则检查；输出为生成层协议时可对照 `chemical-piping-lib/examples/` 下示例。
