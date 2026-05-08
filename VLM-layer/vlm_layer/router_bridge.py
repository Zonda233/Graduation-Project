"""
router_bridge.py
================
VLM-layer → router-layer 的跨层桥接适配器。

该模块是 VLM-layer 调用 router-layer 的**唯一**入口。
实际桥接逻辑已迁移到 ``router-layer/bridge/generation_bridge.py``；
本模块仅负责：

1. 定位 repo_root 并加载 router-layer bridge 子包。
2. 将 VLM-layer 的调用转发给 router-layer bridge。
3. 重新导出 :func:`dump_json` 以保持 pipeline.py 的调用接口不变。

设计约束
--------
- VLM-layer 内部不直接 import router_layer.*，所有跨层调用经由本模块。
- router-layer bridge 经由 importlib 动态加载，避免在 VLM-layer 安装时
  要求 router-layer 也必须安装。
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# 定位 repo_root（本文件位于 VLM-layer/vlm_layer/，向上两级即为项目根）
# ---------------------------------------------------------------------------
_THIS_FILE  = Path(__file__).resolve()
_REPO_ROOT  = _THIS_FILE.parent.parent.parent   # Graduation-Project/


def _load_router_bridge_module():
    """
    动态加载 router-layer/bridge/generation_bridge.py 并返回该模块。

    使用 importlib 而非直接 import，以避免在 VLM-layer 的 Python 环境中
    要求 router-layer 目录必须在 sys.path 上。
    """
    bridge_path = _REPO_ROOT / "router-layer" / "bridge" / "generation_bridge.py"
    if not bridge_path.is_file():
        raise FileNotFoundError(
            f"router_bridge: generation_bridge.py not found at {bridge_path}\n"
            "请确认 router-layer/bridge/ 子包已创建。"
        )

    mod_name = "router_layer.bridge.generation_bridge"
    if mod_name in sys.modules:
        return sys.modules[mod_name]

    spec = importlib.util.spec_from_file_location(mod_name, str(bridge_path))
    if spec is None or spec.loader is None:
        raise RuntimeError(
            f"router_bridge: failed to create module spec for {bridge_path}"
        )
    mod = importlib.util.module_from_spec(spec)
    sys.modules[mod_name] = mod
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


# ---------------------------------------------------------------------------
# 公共 API（与旧接口保持兼容）
# ---------------------------------------------------------------------------

def route_to_generation_json(
    repo_root: Path,
    router_input: dict[str, Any],
) -> dict[str, Any]:
    """
    将 router-input dict 通过路由层转换为 generation-layer JSON dict。

    直接委托给 ``router-layer/bridge/generation_bridge.route_to_generation_json``。

    Parameters
    ----------
    repo_root:
        项目根目录（含 ``router-layer/`` 和 ``chemical-piping-lib/``）。
    router_input:
        符合 ``router_input_v1.json`` schema 的 dict。

    Returns
    -------
    符合 ``protocol_v1.json`` schema 的 generation-layer dict。
    """
    bridge = _load_router_bridge_module()
    return bridge.route_to_generation_json(repo_root, router_input)


def dump_json(path: Path, payload: dict[str, Any]) -> None:
    """
    将 *payload* 序列化为 JSON 并写入 *path*（父目录自动创建）。

    直接委托给 ``router-layer/bridge/generation_bridge.dump_json``。
    """
    bridge = _load_router_bridge_module()
    bridge.dump_json(path, payload)
