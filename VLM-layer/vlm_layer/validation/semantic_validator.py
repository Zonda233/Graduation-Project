# -*- coding: utf-8 -*-
"""Semantic validator for router_input_v1 JSON.

Checks cross-reference integrity (Direction A) and simplified GB engineering
rules (Direction B).  Any violation -- warning or error -- blocks routing and
raises SemanticValidationError whose __str__ is a Chinese-language correction
message suitable for feeding directly into the VLM retry loop.

Direction A -- Semantic / cross-reference rules
    SEM-001  No duplicate node_id values in nodes[]
    SEM-002  No duplicate line_id values in lines[]
    SEM-003  from_node / to_node must reference an existing node_id
    SEM-004  Every entry in via_nodes[] must reference an existing node_id
    SEM-005  Junction nodes must appear in >= 2 lines  (warning)
    SEM-006  A line whose endpoint is a role=signal EquipmentPort must have
             its other endpoint be an InlineInstrument node  (warning)

Direction B -- Simplified GB engineering rules
    GB-001  design_pressure_kpa > 10000 (10 MPa) => valve_subtype required
            Ref: GB 50316 section 6.3
    GB-002  phase=steam + layout_type=buried => ERROR
            Ref: GB 50316 section 4 (thermal expansion, no buried steam pipes)
    GB-003  is_relief_line=true + allow_backflow=true => ERROR
            Ref: safety baseline (relief lines must not allow backflow)
    GB-004  fluid_class=A1 => requires_check_valve must be true
            Ref: GB 50316 section 7.2
"""

from __future__ import annotations

from typing import Any


# ---------------------------------------------------------------------------
# Exception
# ---------------------------------------------------------------------------


class SemanticValidationError(Exception):
    """Raised when router_input fails semantic validation.

    Attributes
    ----------
    violations:
        List of violation dicts, each with keys:
        - ``rule``     e.g. "SEM-001"
        - ``severity`` "error" or "warning"
        - ``message``  Chinese-language description
    """

    def __init__(self, violations: list[dict[str, str]]) -> None:
        self.violations = violations
        super().__init__(str(self))

    def __str__(self) -> str:
        header = "\u4ee5\u4e0b\u8bed\u4e49\u6821\u9a8c\u89c4\u5219\u88ab\u89e6\u53d1\uff0c\u8bf7\u4fee\u6b63\u540e\u91cd\u65b0\u751f\u6210 JSON\uff1a"
        lines = [header, ""]
        for i, v in enumerate(self.violations, start=1):
            if v["severity"] == "error":
                label = "\u3010\u9519\u8bef\u3011"
            else:
                label = "\u3010\u8b66\u544a\u3011"
            lines.append("%d. [%s] %s %s" % (i, v["rule"], label, v["message"]))
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _node_map(router_input: dict[str, Any]) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for node in router_input.get("nodes", []):
        nid = node.get("id", "")
        if nid and nid not in result:
            result[nid] = node
    return result


def _all_line_node_refs(line: dict[str, Any]) -> list[str]:
    refs: list[str] = []
    fn = line.get("from_node")
    tn = line.get("to_node")
    if fn:
        refs.append(fn)
    if tn:
        refs.append(tn)
    refs.extend(line.get("via_nodes") or [])
    return refs


# ---------------------------------------------------------------------------
# Direction A -- Semantic / cross-reference rules
# ---------------------------------------------------------------------------


def _check_sem001(nodes: list[dict], violations: list[dict]) -> None:
    """SEM-001: No duplicate node id values."""
    seen: set[str] = set()
    duplicates: set[str] = set()
    for node in nodes:
        nid = node.get("id", "")
        if not nid:
            continue
        if nid in seen:
            duplicates.add(nid)
        seen.add(nid)
    for nid in sorted(duplicates):
        msg = "node_id \u91cd\u590d\uff1a\u201c" + nid + "\u201d\u5728 nodes[] \u4e2d\u51fa\u73b0\u591a\u6b21\u3002"
        violations.append({"rule": "SEM-001", "severity": "error", "message": msg})


def _check_sem002(lines: list[dict], violations: list[dict]) -> None:
    """SEM-002: No duplicate line id values."""
    seen: set[str] = set()
    duplicates: set[str] = set()
    for line in lines:
        lid = line.get("id", "")
        if not lid:
            continue
        if lid in seen:
            duplicates.add(lid)
        seen.add(lid)
    for lid in sorted(duplicates):
        msg = "line_id \u91cd\u590d\uff1a\u201c" + lid + "\u201d\u5728 lines[] \u4e2d\u51fa\u73b0\u591a\u6b21\u3002"
        violations.append({"rule": "SEM-002", "severity": "error", "message": msg})


def _check_sem003(
    lines: list[dict], node_ids: set[str], violations: list[dict]
) -> None:
    """SEM-003: from_node / to_node must reference an existing node id."""
    for line in lines:
        lid = line.get("id", "<unknown>")
        for field in ("from_node", "to_node"):
            ref = line.get(field)
            if ref and ref not in node_ids:
                msg = (
                    "\u7ba1\u7ebf\u201c" + lid + "\u201d\u7684 " + field
                    + "=\u201c" + ref + "\u201d\u672a\u5728 nodes[] \u4e2d\u627e\u5230\u5bf9\u5e94\u7684 node_id\u3002"
                )
                violations.append({"rule": "SEM-003", "severity": "error", "message": msg})


def _check_sem004(
    lines: list[dict], node_ids: set[str], violations: list[dict]
) -> None:
    """SEM-004: Every via_nodes entry must reference an existing node id."""
    for line in lines:
        lid = line.get("id", "<unknown>")
        for ref in line.get("via_nodes") or []:
            if ref not in node_ids:
                msg = (
                    "\u7ba1\u7ebf\u201c" + lid + "\u201d\u7684 via_nodes \u4e2d\u5305\u542b\u672a\u77e5\u8282\u70b9\u201c"
                    + ref + "\u201d\uff0c\u8be5 node_id \u672a\u5728 nodes[] \u4e2d\u5b9a\u4e49\u3002"
                )
                violations.append({"rule": "SEM-004", "severity": "error", "message": msg})


def _check_sem005(
    nodes: list[dict],
    lines: list[dict],
    violations: list[dict],
) -> None:
    """SEM-005: Junction nodes must appear in >= 2 lines."""
    junction_ids = {
        n["id"]
        for n in nodes
        if n.get("type") == "Junction" and n.get("id")
    }
    if not junction_ids:
        return

    ref_count: dict[str, int] = {jid: 0 for jid in junction_ids}
    for line in lines:
        for ref in _all_line_node_refs(line):
            if ref in ref_count:
                ref_count[ref] += 1

    for jid, count in sorted(ref_count.items()):
        if count < 2:
            msg = (
                "Junction \u8282\u70b9\u201c" + jid + "\u201d\u4ec5\u51fa\u73b0\u5728 "
                + str(count) + " \u6761\u7ba1\u7ebf\u4e2d\uff0c"
                "\u4e09\u901a\u8282\u70b9\u5e94\u81f3\u5c11\u8fde\u63a5 2 \u6761\u7ba1\u7ebf\u3002"
            )
            violations.append({"rule": "SEM-005", "severity": "warning", "message": msg})


def _check_sem006(
    nodes: list[dict],
    lines: list[dict],
    violations: list[dict],
) -> None:
    """SEM-006: Signal EquipmentPort must connect to InlineInstrument."""
    node_type: dict[str, str] = {}
    node_role: dict[str, str] = {}
    for n in nodes:
        nid = n.get("id", "")
        if nid:
            node_type[nid] = n.get("type", "")
            node_role[nid] = (n.get("role") or "").strip().lower()

    for line in lines:
        lid = line.get("id", "<unknown>")
        fn = line.get("from_node", "")
        tn = line.get("to_node", "")

        for signal_end, other_end in [(fn, tn), (tn, fn)]:
            if not signal_end or not other_end:
                continue
            if (
                node_type.get(signal_end) == "EquipmentPort"
                and node_role.get(signal_end) == "signal"
            ):
                if node_type.get(other_end) != "InlineInstrument":
                    other_type = node_type.get(other_end, "\u672a\u77e5")
                    msg = (
                        "\u7ba1\u7ebf\u201c" + lid + "\u201d\u7684\u4fe1\u53f7\u7aef\u53e3\u201c"
                        + signal_end + "\u201d\uff08role=signal\uff09"
                        "\u53e6\u4e00\u7aef\u201c" + other_end + "\u201d\u7684\u7c7b\u578b\u4e3a\u201c"
                        + other_type + "\u201d\uff0c"
                        "\u4fe1\u53f7\u7ba1\u7ebf\u5e94\u8fde\u63a5\u5230 InlineInstrument \u8282\u70b9\u3002"
                    )
                    violations.append({"rule": "SEM-006", "severity": "warning", "message": msg})
                break  # report at most once per line


# ---------------------------------------------------------------------------
# Direction B -- Simplified GB engineering rules
# ---------------------------------------------------------------------------


def _check_gb001(lines: list[dict], violations: list[dict]) -> None:
    """GB-001: design_pressure_kpa > 10000 => valve_subtype required.
    Ref: GB 50316 section 6.3.
    """
    for line in lines:
        lid = line.get("id", "<unknown>")
        pressure = line.get("design_pressure_kpa")
        if pressure is None:
            continue
        try:
            pressure = float(pressure)
        except (TypeError, ValueError):
            continue
        if pressure > 10000 and not line.get("valve_subtype"):
            msg = (
                "\u7ba1\u7ebf\u201c" + lid + "\u201d\u8bbe\u8ba1\u538b\u529b\u4e3a "
                + str(pressure) + " kPa\uff08> 10 MPa\uff09\uff0c"
                "\u4f9d\u636e GB 50316 \u00a76.3\uff0c\u9ad8\u538b\u7ba1\u9053\u5fc5\u987b\u6307\u5b9a valve_subtype\u3002"
            )
            violations.append({"rule": "GB-001", "severity": "warning", "message": msg})


def _check_gb002(lines: list[dict], violations: list[dict]) -> None:
    """GB-002: phase=steam + layout_type=buried => ERROR.
    Ref: GB 50316 section 4.
    """
    for line in lines:
        lid = line.get("id", "<unknown>")
        phase = (line.get("phase") or "").strip().lower()
        layout = (line.get("layout_type") or "").strip().lower()
        if phase == "steam" and layout == "buried":
            msg = (
                "\u7ba1\u7ebf\u201c" + lid + "\u201d\u4ecb\u8d28\u76f8\u6001\u4e3a steam\uff08\u84b8\u6c7d\uff09\uff0c"
                "\u4f9d\u636e GB 50316 \u00a74\uff0c\u84b8\u6c7d\u7ba1\u9053\u4e0d\u5f97\u91c7\u7528 buried\uff08\u57cb\u5730\uff09\u654f\u8bbe\u65b9\u5f0f\u3002"
            )
            violations.append({"rule": "GB-002", "severity": "error", "message": msg})


def _check_gb003(lines: list[dict], violations: list[dict]) -> None:
    """GB-003: is_relief_line=true + allow_backflow=true => ERROR.
    Ref: safety baseline.
    """
    for line in lines:
        lid = line.get("id", "<unknown>")
        if line.get("is_relief_line") and line.get("allow_backflow"):
            msg = (
                "\u7ba1\u7ebf\u201c" + lid + "\u201d\u540c\u65f6\u8bbe\u7f6e\u4e86 is_relief_line=true \u548c allow_backflow=true\uff0c"
                "\u6cc4\u538b\u7ba1\u9053\u4e25\u7981\u5141\u8bb8\u56de\u6d41\uff0c\u8bf7\u79fb\u9664 allow_backflow \u6216\u5c06\u5176\u8bbe\u4e3a false\u3002"
            )
            violations.append({"rule": "GB-003", "severity": "error", "message": msg})


def _check_gb004(lines: list[dict], violations: list[dict]) -> None:
    """GB-004: fluid_class=A1 => requires_check_valve must be true.
    Ref: GB 50316 section 7.2.
    """
    for line in lines:
        lid = line.get("id", "<unknown>")
        fluid_class = (line.get("fluid_class") or "").strip().upper()
        if fluid_class == "A1" and not line.get("requires_check_valve"):
            msg = (
                "\u7ba1\u7ebf\u201c" + lid + "\u201d\u6d41\u4f53\u7c7b\u522b\u4e3a A1\uff08\u9ad8\u6bd2/\u9ad8\u5ea6\u6613\u71c3\uff09\uff0c"
                "\u4f9d\u636e GB 50316 \u00a77.2\uff0c\u5fc5\u987b\u8bbe\u7f6e requires_check_valve=true\u3002"
            )
            violations.append({"rule": "GB-004", "severity": "warning", "message": msg})


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def validate_semantics(router_input: dict[str, Any]) -> None:
    """Run all semantic validation rules against *router_input*.

    Any violation (warning or error) blocks routing and raises
    :class:`SemanticValidationError`.  The exception's string representation
    is a Chinese-language numbered list suitable for embedding directly in a
    VLM retry correction message.

    Parameters
    ----------
    router_input:
        A router_input_v1 dict that has already passed JSON Schema validation.

    Raises
    ------
    SemanticValidationError
        If any rule is violated.
    """
    nodes: list[dict] = router_input.get("nodes") or []
    lines: list[dict] = router_input.get("lines") or []

    violations: list[dict[str, str]] = []

    # --- Direction A: Semantic / cross-reference ---
    _check_sem001(nodes, violations)
    _check_sem002(lines, violations)

    node_ids: set[str] = {n.get("id", "") for n in nodes if n.get("id")}

    _check_sem003(lines, node_ids, violations)
    _check_sem004(lines, node_ids, violations)
    _check_sem005(nodes, lines, violations)
    _check_sem006(nodes, lines, violations)

    # --- Direction B: GB engineering rules ---
    _check_gb001(lines, violations)
    _check_gb002(lines, violations)
    _check_gb003(lines, violations)
    _check_gb004(lines, violations)

    if violations:
        raise SemanticValidationError(violations)
