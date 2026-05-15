"""
generation_bridge.py
====================
router-layer → generation-layer (chemical-piping-lib) 的跨层桥接实现。

职责
----
1. 动态将 router-layer 目录注册为 ``router_layer`` Python 包（解决非安装包的
   相对导入问题）。
2. 将 router-input dict 通过 :class:`DefaultRouterService` 转换为
   generation-layer JSON dict。
3. 提供 JSON 文件写入工具函数。
4. 生成可直接粘贴到 Blender 4.5 Scripting 中执行的代码字符串。

设计约束
--------
- 本模块是 router-layer 与 chemical-piping-lib 之间的**唯一**耦合点。
- 本模块不应被 router-layer 内部的任何其他子包导入（单向依赖）。
- 所有对 ``router_layer.*`` 的导入均在函数体内延迟执行，以便在包尚未注册
  时也能安全 import 本模块。
"""

from __future__ import annotations

import importlib.util
import json
import os
import sys
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# 包加载
# ---------------------------------------------------------------------------

def load_router_layer_package(router_layer_dir: Path) -> None:
    """
    将 *router_layer_dir* 目录动态注册为 ``router_layer`` Python 包。

    如果 ``router_layer`` 已在 ``sys.modules`` 中，则跳过（幂等）。

    Parameters
    ----------
    router_layer_dir:
        router-layer 目录的绝对路径（包含 ``__init__.py``）。

    Raises
    ------
    FileNotFoundError
        如果目录或 ``__init__.py`` 不存在。
    RuntimeError
        如果 importlib 无法创建模块 spec。
    """
    if "router_layer" in sys.modules:
        return

    pkg_init = router_layer_dir / "__init__.py"
    if not pkg_init.is_file():
        raise FileNotFoundError(
            f"load_router_layer_package: __init__.py not found at {pkg_init}"
        )

    spec = importlib.util.spec_from_file_location(
        "router_layer",
        str(pkg_init),
        submodule_search_locations=[str(router_layer_dir)],
    )
    if spec is None or spec.loader is None:
        raise RuntimeError(
            f"load_router_layer_package: failed to create module spec for {pkg_init}"
        )

    pkg = importlib.util.module_from_spec(spec)
    sys.modules["router_layer"] = pkg
    spec.loader.exec_module(pkg)  # type: ignore[union-attr]


# ---------------------------------------------------------------------------
# 核心桥接函数
# ---------------------------------------------------------------------------

def route_to_generation_json(
    repo_root: Path,
    router_input: dict[str, Any],
) -> dict[str, Any]:
    """
    将 router-input dict 通过路由层转换为 generation-layer JSON dict。

    该函数负责：

    1. 将 ``repo_root`` 加入 ``sys.path``（使 ``router_layer`` 可作为顶层包导入）。
    2. 将 ``chemical-piping-lib`` 加入 ``sys.path``（SchemaCompliantJsonEmitter
       需要读取 ``protocol_v1.json`` schema）。
    3. 动态加载 router-layer 包。
    4. 实例化 :class:`DefaultRouterService` 并调用 ``route()``。

    Parameters
    ----------
    repo_root:
        项目根目录（包含 ``router-layer/`` 和 ``chemical-piping-lib/`` 的目录）。
    router_input:
        符合 ``router_input_v1.json`` schema 的 dict。

    Returns
    -------
    符合 ``protocol_v1.json`` schema 的 generation-layer dict。

    Raises
    ------
    FileNotFoundError
        如果 router-layer 目录不存在。
    """
    router_layer_dir = repo_root / "router-layer"
    if not router_layer_dir.is_dir():
        raise FileNotFoundError(
            f"route_to_generation_json: router-layer not found at {router_layer_dir}"
        )

    # 确保 repo_root 在 sys.path（router_layer 作为顶层包）
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))

    # 确保 chemical-piping-lib 在 sys.path（schema 文件读取）
    cpl_root = repo_root / "chemical-piping-lib"
    if cpl_root.is_dir() and str(cpl_root) not in sys.path:
        sys.path.insert(0, str(cpl_root))

    # 动态注册 router_layer 包
    load_router_layer_package(router_layer_dir)

    # 延迟导入，确保包已注册后再 import
    from router_layer.emission.schema_emitter import SchemaCompliantJsonEmitter  # noqa: PLC0415
    from router_layer.service.default_service import DefaultRouterService        # noqa: PLC0415

    service = DefaultRouterService(json_emitter=SchemaCompliantJsonEmitter())
    result = service.route(router_input)

    if not result.success:
        # Raise with the full diagnostic so callers (test harness, VLM loop)
        # can inspect or display it.
        raise RuntimeError(
            f"Routing failed for {len(result.failures)} line(s):\n\n"
            + (result.failure_report or "")
        )

    return result.output_json


# ---------------------------------------------------------------------------
# 文件工具
# ---------------------------------------------------------------------------

def dump_json(path: Path, payload: dict[str, Any]) -> None:
    """
    将 *payload* 序列化为 JSON 并写入 *path*。

    父目录不存在时自动创建。

    Parameters
    ----------
    path:
        目标文件路径。
    payload:
        可 JSON 序列化的 dict。
    """
    os.makedirs(path.parent, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=2)


# ---------------------------------------------------------------------------
# Blender 脚本生成
# ---------------------------------------------------------------------------

def build_blender_script(
    generation_json_path: Path,
    cpl_root: Path,
) -> str:
    """
    生成可直接粘贴到 Blender 4.5 Scripting 编辑器中执行的 Python 代码字符串。

    生成的脚本会：

    1. 将 ``chemical-piping-lib`` 加入 Blender 内置 Python 的 ``sys.path``。
    2. 调用 :func:`chemical_piping_lib.api.build_from_file` 加载 JSON 并构建场景。
    3. 打印 :class:`~chemical_piping_lib.scene.assembler.BuildReport`。

    Parameters
    ----------
    generation_json_path:
        generation-layer JSON 文件的**绝对**路径（将硬编码进脚本）。
    cpl_root:
        ``chemical-piping-lib`` 目录的**绝对**路径。

    Returns
    -------
    可执行的 Python 代码字符串（不含 shebang）。
    """
    # Windows 路径反斜杠需要转义
    json_path_str = str(generation_json_path.resolve()).replace("\\", "\\\\")
    cpl_root_str  = str(cpl_root.resolve()).replace("\\", "\\\\")

    return f'''\
# ============================================================
# 复制以下代码到 Blender 4.5 Scripting 编辑器中执行
# ============================================================
import sys

CPL_ROOT  = r"{cpl_root_str}"
JSON_FILE = r"{json_path_str}"

if CPL_ROOT not in sys.path:
    sys.path.insert(0, CPL_ROOT)

from chemical_piping_lib.api import build_from_file

report = build_from_file(JSON_FILE)
print("=" * 60)
print("BUILD RESULT:", "SUCCESS" if report.success else "FAILED")
print(f"  Assets built : {{report.assets_built}}")
print(f"  Assets failed: {{report.assets_failed}}")
print(f"  Warnings     : {{len(report.warnings)}}")
print(f"  Errors       : {{len(report.errors)}}")
print(f"  Build time   : {{report.build_time_s:.2f}} s")
print(f"  Collection   : {{report.scene_collection_name!r}}")
for w in report.warnings:
    print("  [W]", w)
for e in report.errors:
    print("  [E]", e)
print("=" * 60)
# ============================================================
# 以上代码复制到 Blender 4.5 Scripting 编辑器中执行
# ============================================================
'''
