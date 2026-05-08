"""VLM-layer public API.

Stable imports for external callers (main.py, tests, etc.):

    from vlm_layer import run_end_to_end, PipelineIO, PipelineResult
"""

from .pipeline import PipelineIO, PipelineResult, run_end_to_end

__all__ = ["run_end_to_end", "PipelineIO", "PipelineResult"]
