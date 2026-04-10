# 形式化验证与测试 (Formal Verification & Testing)

除手动用 JSON 跑场景外，本库可通过以下方式做**形式化/自动化校验**，无需启动 Blender 即可验证大部分正确性。

---

## 1. 输入协议校验（JSON Schema）

**作用**：在数据进入生成层前，用 JSON Schema 检查结构是否符合 `doc/Final_JSON.md` 约定的 v1.x 协议（必填字段、类型、枚举、嵌套结构）。  
**位置**：`chemical_piping_lib/schema/protocol_v1.json`

- **校验内容**：`meta`（含 `protocol_version`、`voxel_grid`）、`materials`、`assets`（Tank + ports）、`tee_joints`、`segments`（含 `spec` 与 `components` 的 Pipe/Elbow/Valve 等）。
- **用法**：
  - 在路由层或上游生成 JSON 后，先 `jsonschema.validate(instance=data, schema=schema)` 再调用 `build_from_json`，可提前拦截格式错误。
  - 自动化测试中：所有 `examples/*.json` 会作为用例，通过 `test_schema_validation.py` 校验其符合 schema。

**不覆盖**：语义约束（如 `from_port` 指向的 `port_id` 是否真实存在、管件顺序是否与拓扑一致）由生成层在组装阶段通过 PortRegistry 等做校验并产生 warning/error。

---

## 2. 离线单元测试（config / coords）

**作用**：在不依赖 Blender 的环境下，用 pytest 验证配置与坐标逻辑的数学/查表正确性。  
**位置**：`tests/test_config.py`、`tests/test_coords.py`

- **test_config.py**
  - DN 查表：`get_dn_spec(0.1)` 等与 `DN_TABLE` 一致；超出 ±20% 时抛 `ValueError`。
  - 法兰查表：`get_flange_spec` 最近邻逻辑及与 `DN_TABLE` 的包含关系。
  - 材质预设、体素默认值等常量与协议约定一致。
- **test_coords.py**
  - 体素↔世界坐标：`vc_to_wc_center` 与文档公式一致；`wc_to_vc` 与 `vc_to_wc_center`  round-trip。
  - 轴向字符串：`axis_to_vec` 对 `+X`/`-Z` 等六向的向量与单位长。
  - `RUNTIME.apply_meta` 后，转换使用新的 `voxel_size` / `origin_wc`。

**运行方式**（需先安装依赖，无需 Blender）：

```bash
pip install -r requirements-dev.txt
# Windows PowerShell 下设置项目根为 PYTHONPATH 后执行：
$env:PYTHONPATH = (Get-Location).Path
pytest tests/ -v
```

测试通过时会通过 conftest 注入的 mock 使用“假”的 `bpy` 和 `mathutils`，仅 config/coords 等不依赖真实 Blender 的代码会被执行。

---

## 3. 形式化不变量（可人工/CI 检查）

以下性质在实现与测试中应保持成立，可作为“正确性契约”做回归与审查：

| 不变量 | 说明 |
|--------|------|
| **BuildReport** | `report.success == (report.assets_failed == 0)`；`report.assets_built + report.assets_failed` 等于本轮构建涉及的资产总数。 |
| **端口注册** | 每个成功 `build()` 的资产调用 `PortRegistry.register_many(get_ports())`；Phase 4 用 `from_port` / `to_port` 在 PortRegistry 中查找并给出 warning（不阻塞构建）。 |
| **坐标约定** | 文档公式：体素中心世界坐标 `wc = origin_wc + (vc + 0.5) × voxel_size`；生成层以 JSON 中的 `wc` 为准，`vc` 仅作校验/调试。 |
| **协议版本** | 生成层应校验 `meta.protocol_version` 主版本号；当前为 `1.x.x`。 |

可在后续为 BuildReport 增加断言（如 CI 中 `assert report.success == (report.assets_failed == 0)`），或在文档/代码注释中显式写出上述不变量。

---

## 4. 集成测试（需 Blender 环境）

真实几何与 PortRegistry 的端到端校验需在 Blender 内执行：

- 使用 `examples/run_in_blender.py`，指定 `JSON_FILE` 为某场景 JSON，在 Blender 4.5 中运行脚本（或 `blender --background --python examples/run_in_blender.py`）。
- 检查控制台输出的 `BuildReport`：`success`、`warnings`、`errors`；若有 `from_port`/`to_port` 未在 PortRegistry 中或位置偏差，会出现在 warnings 中。

---

## 5. 建议的 CI 流程

1. **无需 Blender**：`pytest tests/`（含 schema 校验 + config/coords 单元测试）。  
2. **可选**：在生成/路由层输出 JSON 后，先做 `jsonschema.validate` 再调 `build_from_json`，便于在上游就发现协议违反。  
3. **有 Blender**：定期用 1～2 个固定 JSON（如 `minimal_scene2.json`）跑 `run_in_blender.py`，确认 `report.success` 且无新增 error。

---

## 总结

| 方式 | 依赖 | 覆盖 |
|------|------|------|
| JSON Schema + 示例校验 | 无 Blender | 输入形状、必填项、枚举 |
| config/coords 单元测试 | 无 Blender（mock bpy/mathutils） | DN/法兰查表、体素坐标公式、轴向 |
| BuildReport / PortRegistry 不变量 | 文档 + 可选断言 | 成功与失败计数、端口一致性 |
| run_in_blender.py | Blender 4.5 | 端到端几何生成与连接校验 |

组合使用可在不“一个个试场景”的前提下，对协议符合性、数值正确性和组装契约做形式化或自动化验证。
