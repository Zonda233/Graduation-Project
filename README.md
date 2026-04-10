# 神经符号混合架构的流程工业三维自动化生成系统

本毕业设计致力于解决流程工业三维设计中人工建模效率低下、端到端三维生成 AI 难以满足工业级几何精度与拓扑规范的问题。通过**“神经符号（Neuro-Symbolic）”混合架构**，将大模型定位为“意图翻译官”，把严谨的几何与物理约束交给图形学与规则引擎处理，实现从二维 P&ID 或自然语言到可编辑、合规范的三维参数化管道场景的自动化生成。

## 整体管线

```
P&ID 图 / 自然语言
        ↓
┌───────────────────┐
│  感知层 (VLM)     │  解析非结构化输入 → 设备节点、管线连接关系等结构化拓扑
└─────────┬─────────┘
          ↓
┌───────────────────┐
│  校验层 (规则引擎)  │  基于 GB 50316 等规范的硬编码自检；发现谬误 → Agent 多轮修正
└─────────┬─────────┘
          ↓  router-input-protocol JSON（图级）
┌───────────────────┐
│  空间路由层 (A*)   │  包围盒碰撞检测 + 曼哈顿 3D A* 寻路 → 无干涉、横平竖直的管线坐标
└─────────┬─────────┘
          ↓  生成层 JSON（chemical-piping-lib 协议）
┌───────────────────┐
│  生成层 (bpy)     │  参数化三维资产（法兰、阀门、管道、储罐等）→ Blender 场景
└───────────────────┘
```

当前仓库采用**从后往前构建**：生成层与进入路由层前的协议已就绪；路由层与感知/校验层待实现或接入。

## 仓库结构

| 目录 | 说明 |
|------|------|
| **[chemical-piping-lib/](chemical-piping-lib/)** | **生成层**：Blender 4.5 `bpy` 资产库，读入生成层 JSON，输出三维管道场景。已实现 Pipe、Elbow、Tee、Valve(Gate/Ball)、Flange、Tank、Reducer、Cap。 |
| **[router-layer/](router-layer/)** | **空间路由层**：读入图级 JSON，输出生成层 JSON。内含 [router-input-protocol](router-layer/router-input-protocol/)（进入 Router 前的协议、Schema 与示例）、路由实现与测试脚本。 |
| **_generated_docs/** | 说明性 MD（设计理由、GB 50316 与 P&ID 调研、路由层方案与接口等），已加入 `.gitignore`，不提交。 |

## 快速开始

- **只跑生成层**：在 `chemical-piping-lib` 中按 [README](chemical-piping-lib/README.md) 与 [TESTING.md](chemical-piping-lib/TESTING.md) 安装依赖、运行 schema 与单元测试；在 Blender 中或 `blender --background --python examples/run_in_blender.py` 加载示例 JSON（如 `examples/full_components_scene.json`）生成场景。
- **协议与示例**：`router-layer/router-input-protocol` 的 [doc/PreRouter_JSON.md](router-layer/router-input-protocol/doc/PreRouter_JSON.md) 与 [examples/](router-layer/router-input-protocol/examples/) 供路由层读入与联调；生成层协议见 `chemical-piping-lib` 的 `chemical_piping_lib/doc/Final_JSON.md`。运行路由测试：`python router-layer/tests/test_router_to_generation.py`。

## 参考文档

- 生成层协议与 API：`chemical-piping-lib/chemical_piping_lib/doc/Final_JSON.md`、`api.py`
- 进入 Router 前协议：`router-layer/router-input-protocol/doc/PreRouter_JSON.md`、`router-layer/router-input-protocol/schema/router_input_v1.json`；路由层说明：`router-layer/README.md`
- 设计理由与规范调研：见项目根下 `_generated_docs/`（若已生成，含 pre-router-protocol-design-rationale、gb50316-rule-engine-feasibility、pid-design-standards-research 等）

## 环境与依赖

- **生成层**：Blender 4.5+，无需额外 Python 包（使用 Blender 内置 Python）。
- **开发/测试**：`chemical-piping-lib` 下 `pip install -r requirements-dev.txt` 后可运行 pytest（schema、config、coords 等）。

---

毕设项目；各子模块版本与协议以各自 README 与 doc 为准。
