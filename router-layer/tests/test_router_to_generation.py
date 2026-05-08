"""
test_router_to_generation.py
============================
路由层 → 生成层 JSON → 保存 + Schema 校验

流程：
1. 加载 router-input JSON。
2. 通过 router-layer/bridge 调用路由层，生成 generation-layer JSON 并保存。
3. 用 protocol_v1.json 做 jsonschema 校验（无需 Blender）。
4. 输出可直接粘贴到 Blender 4.5 Scripting 中执行的代码。

运行方式（在项目根目录 Graduation-Project 下）：

    python router-layer/tests/test_router_to_generation.py
    python router-layer/tests/test_router_to_generation.py \\
        --input  router-layer/router-input-protocol/examples/complex_cooling_water.json \\
        --output router-layer/output/router_output_complex_cooling_water.json
    python router-layer/tests/test_router_to_generation.py \\
        --input  router-layer/router-input-protocol/examples/instrument_process_signal.json \\
        --output router-layer/output/router_output_instrument_process_signal.json
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# 路径常量
# ---------------------------------------------------------------------------
SCRIPT_DIR       = Path(__file__).resolve().parent
ROUTER_LAYER_DIR = SCRIPT_DIR.parent
PROJECT_ROOT     = ROUTER_LAYER_DIR.parent
CPL_ROOT         = PROJECT_ROOT / "chemical-piping-lib"

DEFAULT_ROUTER_INPUT = (
    ROUTER_LAYER_DIR
    / "router-input-protocol"
    / "examples"
    / "sample_cooling_water.json"
)
OUTPUT_DIR          = ROUTER_LAYER_DIR / "output"
DEFAULT_OUTPUT_JSON = OUTPUT_DIR / "router_output_cooling_water.json"
SCHEMA_PATH         = CPL_ROOT / "chemical_piping_lib" / "schema" / "protocol_v1.json"


# ---------------------------------------------------------------------------
# 动态加载 router-layer/bridge
# ---------------------------------------------------------------------------

def _load_bridge():
    """
    动态加载 router-layer/bridge/generation_bridge.py 并返回该模块。

    使用 importlib 以避免要求 router-layer 必须安装到 sys.path。
    """
    bridge_path = ROUTER_LAYER_DIR / "bridge" / "generation_bridge.py"
    mod_name = "router_layer.bridge.generation_bridge"

    if mod_name in sys.modules:
        return sys.modules[mod_name]

    spec = importlib.util.spec_from_file_location(mod_name, str(bridge_path))
    if spec is None or spec.loader is None:
        raise RuntimeError(f"无法加载 bridge 模块: {bridge_path}")

    mod = importlib.util.module_from_spec(spec)
    sys.modules[mod_name] = mod
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="路由层 → 生成层 JSON 测试（顺序 A* + Schema 校验）"
    )
    parser.add_argument(
        "--input",
        default=str(DEFAULT_ROUTER_INPUT),
        help="router-input JSON 文件路径（绝对或相对）。",
    )
    parser.add_argument(
        "--output",
        default=str(DEFAULT_OUTPUT_JSON),
        help="生成的 generation-layer JSON 输出路径。",
    )
    parser.add_argument(
        "--no-schema-validate",
        action="store_true",
        help="跳过 JSON Schema 校验。",
    )
    return parser.parse_args()


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------

def main() -> None:
    args        = _parse_args()
    input_path  = Path(args.input).resolve()
    output_path = Path(args.output).resolve()

    print("=" * 60)
    print("  路由层 → 生成层 JSON 测试（顺序 A* + Schema 校验）")
    print("=" * 60)
    print(f"  项目根目录: {PROJECT_ROOT}")
    print(f"  路由输入  : {input_path}")
    print(f"  输出文件  : {output_path}")
    print(f"  Schema    : {SCHEMA_PATH}")
    print("=" * 60)

    # 1. 加载 router-input
    if not input_path.is_file():
        print(f"\n错误: 未找到输入文件 {input_path}")
        sys.exit(1)

    with input_path.open(encoding="utf-8") as fh:
        router_input = json.load(fh)
    print("\n[1/4] 已加载 router-input JSON")

    # 2. 通过 bridge 运行路由层
    bridge = _load_bridge()
    generation_json = bridge.route_to_generation_json(PROJECT_ROOT, router_input)
    print("[2/4] 路由层已生成 generation-layer JSON")

    # 3. 保存
    bridge.dump_json(output_path, generation_json)
    print(f"[3/4] 已保存到 {output_path}")

    # 4. Schema 校验
    if args.no_schema_validate:
        print("[4/4] 已跳过 Schema 校验（--no-schema-validate）")
    elif not SCHEMA_PATH.is_file():
        print(f"\n警告: 未找到 Schema 文件 {SCHEMA_PATH}，跳过校验")
    else:
        try:
            import jsonschema
            with SCHEMA_PATH.open(encoding="utf-8") as fh:
                schema = json.load(fh)
            jsonschema.validate(instance=generation_json, schema=schema)
            print("[4/4] Schema 校验通过 (protocol_v1.json)")
        except ImportError:
            print("[4/4] 未安装 jsonschema，跳过校验。建议: pip install jsonschema")
        except jsonschema.ValidationError as exc:
            print(f"[4/4] Schema 校验失败: {exc.message}")
            print(f"      路径: {list(exc.absolute_path)}")
            sys.exit(1)

    # 5. 输出 Blender 脚本
    blender_script = bridge.build_blender_script(
        generation_json_path=output_path,
        cpl_root=CPL_ROOT,
    )

    print("\n" + "=" * 60)
    print("  测试完成。Blender 实机验证请将以下代码粘贴到")
    print("  Blender 4.5 Scripting 编辑器中执行：")
    print("=" * 60)
    print(blender_script)


if __name__ == "__main__":
    main()
