"""
main.py
=======
端到端入口：P&ID 图像 → VLM → router-input JSON → router-layer → generation JSON。

运行示例
--------
    python main.py
    python main.py --image VLM-layer/examples/TestPID.png
    python main.py --no-schema-validate
"""

from __future__ import annotations

import argparse
import importlib.util
import sys
from pathlib import Path


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "端到端入口：P&ID 图像 → VLM router-input JSON"
            " → router-layer → generation JSON。"
        )
    )
    parser.add_argument(
        "--image",
        default="VLM-layer/examples/TestPID.png",
        help="输入 P&ID 图像路径。",
    )
    parser.add_argument(
        "--router-input-out",
        default="VLM-layer/output/router_input_from_vlm.json",
        help="VLM 生成的 router-input JSON 输出路径。",
    )
    parser.add_argument(
        "--generation-out",
        default="router-layer/output/router_output_from_vlm.json",
        help="router-layer 生成的 generation JSON 输出路径。",
    )
    parser.add_argument(
        "--model",
        default=None,
        help="可选：覆盖 global_config.json 中的 openrouter.chat_model。",
    )
    parser.add_argument(
        "--no-schema-validate",
        action="store_true",
        help="跳过 router-input 和 generation JSON 的 Schema 校验。",
    )
    parser.add_argument(
        "--max-retries",
        type=int,
        default=3,
        help="Schema 校验失败时最多重试 VLM 的次数（默认 3）。",
    )
    return parser.parse_args()


def _bootstrap_vlm_package(repo_root: Path) -> None:
    """将 VLM-layer 目录加入 sys.path，使 vlm_layer 包可被导入。"""
    vlm_pkg_root = repo_root / "VLM-layer"
    if str(vlm_pkg_root) not in sys.path:
        sys.path.insert(0, str(vlm_pkg_root))


def _load_bridge(repo_root: Path):
    """
    动态加载 router-layer/bridge/generation_bridge.py。

    用于在 main.py 中直接调用 build_blender_script，
    而无需将 router-layer 安装为包。
    """
    bridge_path = repo_root / "router-layer" / "bridge" / "generation_bridge.py"
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


def main() -> None:
    args      = _parse_args()
    repo_root = Path(__file__).resolve().parent
    _bootstrap_vlm_package(repo_root)

    from vlm_layer.pipeline import PipelineIO, run_end_to_end  # noqa: PLC0415

    io = PipelineIO(
        image_path               = (repo_root / args.image).resolve(),
        prompts_path             = (repo_root / "VLM-layer/config/prompts.json").resolve(),
        global_config_path       = (repo_root / "global_config.json").resolve(),
        router_schema_path       = (repo_root / "router-layer/router-input-protocol/schema/router_input_v1.json").resolve(),
        generation_schema_path   = (repo_root / "chemical-piping-lib/chemical_piping_lib/schema/protocol_v1.json").resolve(),
        router_input_output_path = (repo_root / args.router_input_out).resolve(),
        generation_output_path   = (repo_root / args.generation_out).resolve(),
        model_override           = args.model,
        max_retries              = args.max_retries,
    )

    if not io.image_path.is_file():
        raise FileNotFoundError(f"输入图像不存在: {io.image_path}")

    result = run_end_to_end(
        repo_root=repo_root,
        io=io,
        validate_schema=not args.no_schema_validate,
    )

    # ------------------------------------------------------------------
    # 摘要输出
    # ------------------------------------------------------------------
    nodes = len(result.router_input.get("nodes", []))
    lines = len(result.router_input.get("lines", []))

    print("=" * 72)
    print("Pipeline 完成")
    print(f"  图像             : {io.image_path}")
    print(f"  Router-input JSON: {io.router_input_output_path}")
    print(f"  Generation JSON  : {io.generation_output_path}")
    print(f"  节点数 / 管线数  : {nodes} / {lines}")
    print(f"  VLM 重试次数     : {result.retry_count}")
    print("=" * 72)

    # ------------------------------------------------------------------
    # 输出 Blender 可执行脚本
    # ------------------------------------------------------------------
    cpl_root = repo_root / "chemical-piping-lib"
    bridge   = _load_bridge(repo_root)
    blender_script = bridge.build_blender_script(
        generation_json_path=io.generation_output_path,
        cpl_root=cpl_root,
    )

    print("\n将以下代码粘贴到 Blender 4.5 Scripting 编辑器中执行：")
    print("=" * 72)
    print(blender_script)
    print("=" * 72)


if __name__ == "__main__":
    main()
