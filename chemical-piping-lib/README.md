# chemical-piping-lib

A **Blender 4.5** `bpy` asset library for procedural chemical plant 3D modeling.

Driven by a structured JSON input protocol, this library is the **generation layer** of a larger Neuro-Symbolic P&ID-to-3D pipeline:

```
P&ID Image → [VLM Perception] → [Rule Validation] → [A* Router] → [This Library] → Blender Scene
```

## Features
- Parametric assets: Pipe, Elbow, Tee, Valve (Gate/Ball), Flange, Tank, Reducer, Cap
- Voxel-grid coordinate system (0.2m resolution)
- JSON-driven scene assembly
- Blender 4.5 MANIFOLD boolean solver for reliable Tee geometry
- Pure `bmesh` construction — no `bpy.ops` dependency for geometry
- Headless (`blender --background`) compatible

## Project Structure
```
chemical_piping_lib/
├── config.py            # Global constants, DN table, material presets
├── utils/
│   ├── coords.py        # Voxel ↔ world coordinate transforms
│   ├── bmesh_utils.py   # bmesh geometry helpers
│   ├── ops_wrapper.py   # Safe bpy.ops wrappers (temp_override)
│   ├── material_utils.py# Material creation & cache
│   └── boolean_utils.py # Boolean operations (MANIFOLD solver)
├── assets/
│   ├── base.py          # Abstract base class PipingAsset
│   ├── pipe.py
│   ├── elbow.py
│   ├── tee.py
│   ├── flange.py
│   ├── valve.py
│   └── tank.py
├── scene/
│   ├── registry.py      # Global port registry
│   ├── assembler.py     # JSON parser & asset dispatcher
│   └── collection_manager.py
└── api.py               # Public entry point: build_from_json()
```

## Requirements
- Blender 4.5+
- No external Python packages required (uses Blender's bundled Python)

## Verification & testing

Without Blender: run **JSON Schema** checks and **offline unit tests** (config + coords):

```bash
pip install -r requirements-dev.txt
pytest tests/ -v
```

See [TESTING.md](TESTING.md) for the full verification strategy (schema, invariants, optional Blender integration).

## Quick Start
```python
import sys
sys.path.append('/path/to/chemical-piping-lib')

from chemical_piping_lib.api import build_from_json

with open('scene.json', 'r') as f:
    import json
    data = json.load(f)

report = build_from_json(data)
print(report)
```
