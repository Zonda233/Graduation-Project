"""
测试脚本：路由层 → 生成层 JSON → 保存 + Schema 校验

按 chemical-piping-lib/TESTING.md 的流程：
1. 用 router-input 跑路由层，生成 generation-layer JSON 并保存。
2. 用 protocol_v1.json 做 jsonschema 校验（无需 Blender）。
3. Blender 实机验证：本脚本只输出可复制到 Blender 中执行的代码，不实际调用 Blender。

运行方式（在项目根目录 Graduation-Project 下）：

    python router-layer/tests/test_router_to_generation.py
    python router-layer/tests/test_router_to_generation.py --input router-layer/router-input-protocol/examples/complex_cooling_water.json --output router-layer/output/router_output_complex_cooling_water.json
    python router-layer/tests/test_router_to_generation.py --input router-layer/router-input-protocol/examples/instrument_process_signal.json --output router-layer/output/router_output_instrument_process_signal.json

或先 cd router-layer，设置 PYTHONPATH 后：

    set PYTHONPATH=..
    python tests/test_router_to_generation.py
"""

import json
import argparse
import os
import sys

# 项目根目录（Graduation-Project）
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
ROUTER_LAYER_DIR = os.path.dirname(SCRIPT_DIR)
PROJECT_ROOT = os.path.dirname(ROUTER_LAYER_DIR)

# 项目根加入 path，用于 chemical-piping-lib 与后续以包形式加载 router_layer
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)
CPL_ROOT = os.path.join(PROJECT_ROOT, "chemical-piping-lib")
if CPL_ROOT not in sys.path:
    sys.path.insert(0, CPL_ROOT)

# 将 router-layer 目录作为包 "router_layer" 加载，以便其内部相对导入可用
def _load_router_layer_package():
    import importlib.util
    pkg_init = os.path.join(ROUTER_LAYER_DIR, "__init__.py")
    spec = importlib.util.spec_from_file_location(
        "router_layer",
        pkg_init,
        submodule_search_locations=[ROUTER_LAYER_DIR],
    )
    pkg = importlib.util.module_from_spec(spec)
    sys.modules["router_layer"] = pkg
    spec.loader.exec_module(pkg)
    return pkg

_load_router_layer_package()

# 路径常量
DEFAULT_ROUTER_INPUT_EXAMPLE = os.path.join(
    ROUTER_LAYER_DIR,
    "router-input-protocol",
    "examples",
    "sample_cooling_water.json",
)
OUTPUT_DIR = os.path.join(ROUTER_LAYER_DIR, "output")
DEFAULT_OUTPUT_JSON = os.path.join(OUTPUT_DIR, "router_output_cooling_water.json")
SCHEMA_PATH = os.path.join(CPL_ROOT, "chemical_piping_lib", "schema", "protocol_v1.json")


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Router-layer to generation JSON test.")
    parser.add_argument(
        "--input",
        default=DEFAULT_ROUTER_INPUT_EXAMPLE,
        help="Absolute/relative path to router-input JSON.",
    )
    parser.add_argument(
        "--output",
        default=DEFAULT_OUTPUT_JSON,
        help="Absolute/relative path for generated output JSON.",
    )
    return parser.parse_args()


def main():
    args = _parse_args()
    router_input_path = args.input
    output_json_path = args.output
    print("=" * 60)
    print("  路由层 → 生成层 JSON 测试（顺序 A* + Schema 校验）")
    print("=" * 60)
    print(f"  项目根目录: {PROJECT_ROOT}")
    print(f"  路由输入  : {router_input_path}")
    print(f"  输出文件  : {output_json_path}")
    print(f"  Schema    : {SCHEMA_PATH}")
    print("=" * 60)

    # 1. 加载 router-input
    if not os.path.isfile(router_input_path):
        print(f"\n错误: 未找到输入文件 {router_input_path}")
        sys.exit(1)
    with open(router_input_path, "r", encoding="utf-8") as f:
        router_input = json.load(f)
    print("\n[1/4] 已加载 router-input JSON")

    # 2. 运行路由层（使用 SchemaCompliantJsonEmitter 以通过生成层 schema）
    from router_layer.config import RouterConfig
    from router_layer.json_emitter import SchemaCompliantJsonEmitter
    from router_layer.service import DefaultRouterService

    service = DefaultRouterService(json_emitter=SchemaCompliantJsonEmitter())
    generation_json = service.route(router_input)
    print("[2/4] 路由层已生成 generation-layer JSON")

    # 3. 保存
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    with open(output_json_path, "w", encoding="utf-8") as f:
        json.dump(generation_json, f, ensure_ascii=False, indent=2)
    print(f"[3/4] 已保存到 {output_json_path}")

    # 4. Schema 校验（TESTING.md §1）
    if not os.path.isfile(SCHEMA_PATH):
        print(f"\n警告: 未找到 Schema 文件 {SCHEMA_PATH}，跳过校验")
    else:
        try:
            import jsonschema
            with open(SCHEMA_PATH, "r", encoding="utf-8") as f:
                schema = json.load(f)
            jsonschema.validate(instance=generation_json, schema=schema)
            print("[4/4] Schema 校验通过 (protocol_v1.json)")
        except ImportError:
            print("[4/4] 未安装 jsonschema，跳过校验。建议: pip install jsonschema")
        except jsonschema.ValidationError as e:
            print(f"[4/4] Schema 校验失败: {e}")
            print(f"      路径: {list(e.absolute_path)}")
            sys.exit(1)

    print("\n" + "=" * 60)
    print("  测试完成。Blender 实机验证请使用下方代码。")
    print("=" * 60)

    # Blender 中执行的代码（用户自行复制到 Blender Scripting 中运行）
    output_json_abs = os.path.abspath(output_json_path)
    blender_code = f'''
# ---------- 复制到 Blender 4.5 Scripting 中执行 ----------
import os
import sys

# 修改为你的项目根目录（Graduation-Project 的绝对路径）
PROJECT_ROOT = r"{PROJECT_ROOT.replace(chr(92), chr(92)+chr(92))}"

CPL_ROOT = os.path.join(PROJECT_ROOT, "chemical-piping-lib")
JSON_FILE = r"{output_json_abs.replace(chr(92), chr(92)+chr(92))}"

if CPL_ROOT not in sys.path:
    sys.path.insert(0, CPL_ROOT)

from chemical_piping_lib.api import build_from_file

report = build_from_file(JSON_FILE)
print("BUILD RESULT:", "SUCCESS" if report.success else "FAILED")
print("Assets built:", report.assets_built, "| Assets failed:", report.assets_failed)
print("Warnings:", len(report.warnings), "| Errors:", len(report.errors))
for w in report.warnings:
    print("  [W]", w)
for e in report.errors:
    print("  [E]", e)
# ---------- 以上复制到 Blender 中执行 ----------
'''
    print(blender_code)
    print("\n说明: 将 PROJECT_ROOT 改为本机路径后，整段复制到 Blender 脚本编辑器运行即可。")


if __name__ == "__main__":
    main()
