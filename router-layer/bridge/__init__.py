"""
bridge/
=======
router-layer 的跨层桥接子包。

该子包是 router-layer 与外部层级（generation-layer / chemical-piping-lib）
之间的唯一接口。所有跨层调用都应通过这里，而不是在各层内部直接 import 对方。

公共 API
--------
- :func:`route_to_generation_json` — 接收 router-input dict，返回 generation-layer dict
- :func:`load_router_layer_package` — 将 router-layer 目录动态注册为 ``router_layer`` 包
- :func:`dump_json` — 将 dict 写入 JSON 文件（带目录自动创建）
- :func:`build_blender_script` — 生成可直接粘贴到 Blender 4.5 Scripting 中执行的代码字符串
"""

from .generation_bridge import (
    build_blender_script,
    dump_json,
    load_router_layer_package,
    route_to_generation_json,
)

__all__ = [
    "load_router_layer_package",
    "route_to_generation_json",
    "dump_json",
    "build_blender_script",
]
