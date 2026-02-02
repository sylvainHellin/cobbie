import os
from dotenv import load_dotenv, find_dotenv
from typing import Literal

load_dotenv(find_dotenv())

# Path
ROOT_PATH = os.environ["ROOT_PATH"]
SRC_PATH = os.path.join(ROOT_PATH, "src")
TEST_IFC_PATH = os.path.join(ROOT_PATH, "src/db/bim_models/duplex/arc.ifc")
DEVSET_PATH = os.path.join(ROOT_PATH, "src/db/dev_set.json")
DB_PATH = os.path.join(ROOT_PATH, "src/db/db.db")
DIRECTORY_IFC_MODELS_PATH = os.path.join(ROOT_PATH, "src/db/bim_models")
CREATED_TOOLS_PATH = os.path.join(ROOT_PATH, "src/tools/created")
INITIAL_TOOLS_PATH = os.path.join(ROOT_PATH, "src/tools/initial")
MANUAL_TOOLS_PATH = os.path.join(ROOT_PATH, "src/tools/manual")

# ACC paths
ACC_ROOT_PATH = os.path.join(ROOT_PATH, "acc")
ACC_RES_PATH = os.path.join(ROOT_PATH, "acc", "res")
ACC_TOOLS_PATH = os.path.join(ROOT_PATH, "acc", "tools")
ACC_CONFIG_PATH = os.path.join(ROOT_PATH, "acc", "config")
ACC_SETUP_PATH = os.path.join(ROOT_PATH, "acc", "setup")
ACC_MODELS_PATH = os.path.join(ROOT_PATH, "acc", "bim_models")

# URI
MLFLOW_URI = "http://127.0.0.1:5000"

# loads secrets
ANTHROPIC_API_KEY = os.environ["ANTHROPIC_API_KEY"]
OPENAI_API_KEY = os.environ["OPENAI_API_KEY"]
GEMINI_API_KEY = os.environ["GEMINI_API_KEY"]
DEEPSEEK_API_KEY = os.environ["DEEPSEEK_API_KEY"]
GROQ_API_KEY = os.environ["GROQ_API_KEY"]
MISTRAL_API_KEY = os.environ["MISTRAL_API_KEY"]
FIREWORKS_API_KEY = os.environ["FIREWORKS_API_KEY"]
CEREBRAS_API_KEY = os.environ["CEREBRAS_API_KEY"]
OPENROUTER_API_KEY = os.environ["OPENROUTER_API_KEY"]


# Boilerplate code for the toolmaker
FUNCTION_BOILERPLATE = """
import ifcopenshell
import ifcopenshell.util.element
import ifcopenshell.util.shape
import ifcopenshell.util.placement
import ifcopenshell.util.geolocation
import ifcopenshell.util.system
import ifcopenshell.geom
import math
import json
from typing import *
"""

TRIMESH_BOILERPLATE = "\nimport trimesh\nimport numpy as np\n"
SHAPELY_BOILERPLATE = "\nimport shapely\nimport shapely.geometry\nimport shapely.ops\n"

TRIMESH_DOCS = """\
## trimesh (pre-imported as `trimesh`, numpy as `np`)

Load a mesh from vertices/faces or from file:
  mesh = trimesh.Trimesh(vertices=verts, faces=faces)
  mesh = trimesh.load(path)

Key properties:
  mesh.bounds          – (2,3) min/max bounding box
  mesh.extents         – (3,) size along each axis
  mesh.area            – total surface area
  mesh.volume          – signed volume (watertight meshes)
  mesh.center_mass     – centre of mass
  mesh.is_watertight   – bool

Sections & cross-sections:
  section = mesh.section(plane_origin=[0,0,z], plane_normal=[0,0,1])
  if section:
      path2d = section.to_planar()[0]   # trimesh.path.Path2D
      polygon = path2d.polygons_full[0] # shapely Polygon

Boolean operations (requires manifold3d or blender backend):
  result = trimesh.boolean.union([mesh_a, mesh_b])
  result = trimesh.boolean.intersection([mesh_a, mesh_b])
  result = trimesh.boolean.difference([mesh_a, mesh_b])

Proximity / containment:
  trimesh.proximity.closest_point(mesh, points)       -> (closest, distances, triangle_id)
  mesh.contains(points)                                -> bool array
"""

SHAPELY_DOCS = """\
## shapely (pre-imported as `shapely`, submodules `shapely.geometry`, `shapely.ops`)

Create geometries:
  from shapely.geometry import Point, LineString, Polygon, MultiPolygon, box
  pt  = Point(x, y)
  ln  = LineString([(x1,y1), (x2,y2), ...])
  poly = Polygon([(x1,y1), ...])            # exterior ring
  poly = Polygon(shell, [hole1, hole2])      # with holes
  rect = box(minx, miny, maxx, maxy)

Key properties:
  geom.area, geom.length, geom.bounds, geom.centroid
  geom.is_valid, geom.is_empty

Spatial predicates:
  a.contains(b), a.within(b), a.intersects(b), a.overlaps(b), a.touches(b)

Set operations:
  a.intersection(b), a.union(b), a.difference(b), a.symmetric_difference(b)

Measurements:
  a.distance(b), a.hausdorff_distance(b)

Buffering:
  geom.buffer(distance)           # expand/shrink geometry

Useful helpers:
  shapely.ops.unary_union(geom_list)
  shapely.ops.nearest_points(a, b)
  Polygon.from_bounds(minx, miny, maxx, maxy)
"""


def get_boilerplate(no_trimesh: bool = False, no_shapely: bool = False) -> str:
    """Build the execution boilerplate string based on feature flags."""
    parts = [FUNCTION_BOILERPLATE]
    if not no_trimesh:
        parts.append(TRIMESH_BOILERPLATE)
    if not no_shapely:
        parts.append(SHAPELY_BOILERPLATE)
    return "".join(parts)


def get_library_docs(no_trimesh: bool = False, no_shapely: bool = False) -> str:
    """Build the library documentation string for the LLM prompt."""
    parts: list[str] = []
    if not no_trimesh:
        parts.append(TRIMESH_DOCS)
    if not no_shapely:
        parts.append(SHAPELY_DOCS)
    return "\n".join(parts)


# Configure logger
LOG_LEVEL: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"
