from __future__ import annotations

from typing import Dict, Tuple

# Numeric conversions and formatting
MM_TO_M: float = 1000.0
WC_PRECISION: int = 6
VOXEL_CENTER_OFFSET: float = 0.5

# Router defaults
DEFAULT_NOMINAL_DIAMETER_M: float = 0.1
DEFAULT_MATERIAL_ID: str = "mat_carbon_steel"
DEFAULT_SEED_NORM_XY: Tuple[float, float] = (0.5, 0.5)
MIN_FREE_ANCHOR_RADIUS: int = 8

# Tee naming conventions
TEE_ID_PREFIX: str = "tee_"
TEE_PORT_SUFFIX_RUN_A: str = "_run_a"
TEE_PORT_SUFFIX_RUN_B: str = "_run_b"
TEE_PORT_SUFFIX_BRANCH: str = "_branch"

TEE_DEFAULT_AXES: Dict[str, str] = {
    "run_a": "+X",
    "run_b": "-X",
    "branch": "+Y",
}
