from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Iterable, List, Set

from .IMultiLineRouter import IMultiLineRouter
from .RouterInputModels import RouterInput
from .config import RouterConfig
from .domain_types import LineRouteMap, LineRouteResult, PlacedNode, Vc
from .grid import Grid3D
from .IPathFinder import IPathFinder


@dataclass
class SequentialMultiLineRouter(IMultiLineRouter):
    """Routes lines sequentially and blocks routed voxels for later lines."""

    def route_all_lines(
        self,
        grid: Grid3D,
        placed_nodes: Dict[str, PlacedNode],
        router_input: RouterInput,
        path_finder: IPathFinder,
        config: RouterConfig,
    ) -> LineRouteMap:
        results: LineRouteMap = {}
        forbidden: Set[Vc] = set()
        for line in router_input.lines:
            line_id = line.line_id
            start_placed = placed_nodes[line.from_node_id]
            goal_placed = placed_nodes[line.to_node_id]
            via_vc: List[Vc] = [placed_nodes[nid].vc for nid in line.via_node_ids]
            path = path_finder.find_path(
                grid=grid,
                start_vc=start_placed.vc,
                goal_vc=goal_placed.vc,
                via_vc=via_vc or None,
                forbidden=forbidden,
                line_ctx=line,
                start_direction=start_placed.direction,
                end_direction=goal_placed.direction,
            )
            if not path:
                results[line_id] = LineRouteResult(
                    line_id=line_id,
                    voxel_path=None,
                    success=False,
                    reason="no_path_found",
                )
                continue
            results[line_id] = LineRouteResult(
                line_id=line_id,
                voxel_path=path,
                success=True,
                reason=None,
            )
            forbidden.update(self._dilate_path(path, config.safety_margin_voxels))
        return results

    def _dilate_path(self, path: Iterable[Vc], margin: int) -> Set[Vc]:
        if margin <= 0:
            return set(path)
        expanded: Set[Vc] = set()
        for x, y, z in path:
            for dx in range(-margin, margin + 1):
                for dy in range(-margin, margin + 1):
                    for dz in range(-margin, margin + 1):
                        expanded.add((x + dx, y + dy, z + dz))
        return expanded
