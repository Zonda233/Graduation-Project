"""
main.py
=======
端到端入口：P&ID 图像 → VLM → router-input JSON → router-layer → generation JSON。

运行示例
--------
    # 正常运行
    python main.py
    python main.py --image VLM-layer/examples/TestPID.png
    python main.py --no-schema-validate

    # 配置管理（首次使用时运行）
    python main.py config init                        # 交互式生成 global_config.json
    python main.py config set openrouter.api_key sk-xxx
    python main.py config set openrouter.chat_model  deepseek-chat
    python main.py config show                        # 显示当前配置（隐藏 API Key）
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path

# ── 常量 ──────────────────────────────────────────────────────────────────────
REPO_ROOT = Path(__file__).resolve().parent
CONFIG_PATH = REPO_ROOT / "global_config.json"

DEFAULT_CONFIG: dict = {
    "openrouter": {
        "api_key": "",
        "base_url": "https://api.deepseek.com",
        "chat_model": "deepseek-chat",
        "http_referer": "",
        "app_title": "Graduation-Project-VLM",
        "reasoning": {
            "enabled": False,
            "comment": (
                "与 OpenRouter 文档一致，可在第二轮对话中透传 assistant 的"
                " reasoning_details；本冒烟脚本默认单轮且关闭 reasoning。"
            ),
        },
    }
}


# ── 配置管理子命令 ─────────────────────────────────────────────────────────────

def _nested_set(d: dict, dotted_key: str, value: object) -> None:
    """按 'a.b.c' 路径在嵌套 dict 中写入值，中间层不存在时自动创建。"""
    keys = dotted_key.split(".")
    for k in keys[:-1]:
        d = d.setdefault(k, {})
    d[keys[-1]] = value


def _nested_get(d: dict, dotted_key: str, default=None):
    """按 'a.b.c' 路径读取嵌套 dict 中的值。"""
    for k in dotted_key.split("."):
        if not isinstance(d, dict):
            return default
        d = d.get(k, default)  # type: ignore[assignment]
    return d


def _mask_config(cfg: dict) -> dict:
    """返回一份将 api_key 遮蔽的配置副本，用于安全展示。"""
    import copy
    masked = copy.deepcopy(cfg)
    key = _nested_get(masked, "openrouter.api_key", "")
    if key:
        visible = key[:6] if len(key) > 6 else key
        _nested_set(masked, "openrouter.api_key", visible + "****")
    return masked


def cmd_config_init(_args: argparse.Namespace) -> None:
    """交互式生成 global_config.json。"""
    if CONFIG_PATH.exists():
        answer = input(
            f"global_config.json 已存在于 {CONFIG_PATH}\n"
            "是否覆盖？[y/N] "
        ).strip().lower()
        if answer != "y":
            print("已取消。")
            return

    import copy
    cfg = copy.deepcopy(DEFAULT_CONFIG)

    print("\n=== 配置向导 ===")
    print("直接回车保留括号内的默认值。\n")

    fields = [
        ("openrouter.api_key",    "API Key",          ""),
        ("openrouter.base_url",   "Base URL",         cfg["openrouter"]["base_url"]),
        ("openrouter.chat_model", "Chat Model",       cfg["openrouter"]["chat_model"]),
        ("openrouter.http_referer","HTTP Referer",    ""),
        ("openrouter.app_title",  "App Title",        cfg["openrouter"]["app_title"]),
    ]

    for dotted, label, default in fields:
        prompt = f"  {label} [{default}]: " if default else f"  {label}: "
        val = input(prompt).strip()
        if val:
            _nested_set(cfg, dotted, val)

    CONFIG_PATH.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nglobal_config.json 已写入 {CONFIG_PATH}")
    print("请确认该文件已被 .gitignore 忽略，不要提交到版本控制！")


def cmd_config_set(args: argparse.Namespace) -> None:
    """设置配置中的单个字段：config set <key> <value>。"""
    key: str = args.key
    value: str = args.value

    cfg: dict = {}
    if CONFIG_PATH.exists():
        cfg = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))

    # 尝试将 value 解析为 JSON（支持 true/false/数字），失败则保留字符串
    try:
        parsed_value = json.loads(value)
    except json.JSONDecodeError:
        parsed_value = value

    _nested_set(cfg, key, parsed_value)
    CONFIG_PATH.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"已设置 {key} = {parsed_value!r}")


def cmd_config_show(_args: argparse.Namespace) -> None:
    """显示当前配置（API Key 部分遮蔽）。"""
    if not CONFIG_PATH.exists():
        print("global_config.json 不存在。运行 `python main.py config init` 创建。")
        return
    cfg = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    print(json.dumps(_mask_config(cfg), ensure_ascii=False, indent=2))


# ── 参数解析 ──────────────────────────────────────────────────────────────────

def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "端到端入口：P&ID 图像 → VLM router-input JSON"
            " → router-layer → generation JSON。"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "配置管理示例：\n"
            "  python main.py config init\n"
            "  python main.py config set openrouter.api_key sk-xxx\n"
            "  python main.py config show\n"
        ),
    )

    # ── 主流程参数 ──
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

    # ── config 子命令 ──
    subparsers = parser.add_subparsers(dest="subcommand", metavar="<subcommand>")

    config_parser = subparsers.add_parser("config", help="管理 global_config.json 配置文件。")
    config_sub = config_parser.add_subparsers(dest="config_action", metavar="<action>")

    config_sub.add_parser("init", help="交互式生成 global_config.json。")
    config_sub.add_parser("show", help="显示当前配置（API Key 部分遮蔽）。")

    set_parser = config_sub.add_parser("set", help="设置配置中的单个字段。")
    set_parser.add_argument("key",   help="点分路径，例如 openrouter.api_key")
    set_parser.add_argument("value", help="要写入的值（支持 JSON 字面量）")

    return parser


# ── 辅助函数 ──────────────────────────────────────────────────────────────────

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


def _check_config() -> None:
    """
    检查 global_config.json 是否存在。
    不存在时打印友好提示并退出，避免后续出现难以理解的 KeyError / FileNotFoundError。
    """
    if not CONFIG_PATH.exists():
        print("=" * 72)
        print("错误：找不到 global_config.json")
        print()
        print("该文件包含 API Key 等敏感信息，已被 .gitignore 排除，")
        print("不会随代码库分发。请按以下步骤创建：")
        print()
        print("  方式一（推荐）：交互式向导")
        print("    python main.py config init")
        print()
        print("  方式二：手动设置各字段")
        print("    python main.py config set openrouter.api_key  <你的 API Key>")
        print("    python main.py config set openrouter.base_url https://api.deepseek.com")
        print("    python main.py config set openrouter.chat_model deepseek-chat")
        print()
        print("  方式三：手动复制模板")
        print(f"    将以下内容保存为 {CONFIG_PATH.name}：")
        print()
        print(json.dumps(DEFAULT_CONFIG, ensure_ascii=False, indent=2))
        print("=" * 72)
        sys.exit(1)


# ── 主入口 ────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = _build_parser()
    args = parser.parse_args()

    # ── 处理 config 子命令（不需要 global_config.json 存在）──
    if args.subcommand == "config":
        action = getattr(args, "config_action", None)
        if action == "init":
            cmd_config_init(args)
        elif action == "set":
            cmd_config_set(args)
        elif action == "show":
            cmd_config_show(args)
        else:
            # 仅输入 `python main.py config` 时显示帮助
            parser.parse_args(["config", "--help"])
        return

    # ── 主流程：先检查配置文件 ──
    _check_config()

    _bootstrap_vlm_package(REPO_ROOT)

    from vlm_layer.pipeline import PipelineIO, run_end_to_end  # noqa: PLC0415

    io = PipelineIO(
        image_path               = (REPO_ROOT / args.image).resolve(),
        prompts_path             = (REPO_ROOT / "VLM-layer/config/prompts.json").resolve(),
        global_config_path       = CONFIG_PATH,
        router_schema_path       = (REPO_ROOT / "router-layer/router-input-protocol/schema/router_input_v1.json").resolve(),
        generation_schema_path   = (REPO_ROOT / "chemical-piping-lib/chemical_piping_lib/schema/protocol_v1.json").resolve(),
        router_input_output_path = (REPO_ROOT / args.router_input_out).resolve(),
        generation_output_path   = (REPO_ROOT / args.generation_out).resolve(),
        model_override           = args.model,
        max_retries              = args.max_retries,
    )

    if not io.image_path.is_file():
        raise FileNotFoundError(f"输入图像不存在: {io.image_path}")

    result = run_end_to_end(
        repo_root=REPO_ROOT,
        io=io,
        validate_schema=not args.no_schema_validate,
    )

    # ── 摘要输出 ──
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

    # ── 输出 Blender 可执行脚本 ──
    cpl_root = REPO_ROOT / "chemical-piping-lib"
    bridge   = _load_bridge(REPO_ROOT)
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
