#%%
# python packages
import sys
import os
sys.path.insert(0, os.path.dirname(os.getcwd()))

# state management
from state import get_model_path, get_state, set_state, get_available_models

# ifcopenshell
import ifcopenshell.util.element
import ifcopenshell.util.shape
import ifcopenshell.geom
import json
import numpy as np
from shapely.geometry import Polygon, MultiPolygon
from shapely.ops import unary_union
from shapely.validation import make_valid
from functools import wraps, lru_cache
from rtree import index
from concurrent.futures import ThreadPoolExecutor

def calculate_gross_floor_area():
    """
    Calculate the total gross floor area (GFA) for all architectural models in the current project.
    
    This function processes all available models (excluding MEP models) in the project and calculates
    their gross floor areas. For each model, it:
    1. Processes all walls and slabs (excluding roofs)
    2. Calculates areas by storey, distinguishing between interior and exterior elements
    3. Handles geometry processing with error management and caching
    4. Accounts for overlapping elements to avoid double-counting
    5. Uses parallel processing for multiple models
    
    The calculation includes:
    - Interior elements (walls and slabs)
    - Exterior elements (walls and slabs marked as external)
    - Area breakdown by storey
    - Handling of geometric intersections and overlaps
    
    Returns:
        str: A JSON string containing:
            - gross_floor_area: Total GFA across all models
            - Model-specific results including:
                - gross_floor_area: Total GFA for the model
                - areas_by_storey: Breakdown of areas per storey including:
                    - total: Total area for the storey
                    - interior: Area of interior elements
                    - exterior: Area of exterior elements
    
    Example output:
        {
            "model1": {
                "gross_floor_area": 1000.25,
                "areas_by_storey": {
                    "Level 1": {
                        "total": 500.12,
                        "interior": 400.10,
                        "exterior": 100.02
                    },
                    "Level 2": {
                        "total": 500.13,
                        "interior": 400.11,
                        "exterior": 100.02
                    }
                }
            },
            "gross_floor_area": 1000.25
        }
    """
    
    #################### helper functions ####################
    def calculate_gross_floor_area_model(model: str = None, include_external_elements: bool = True):
        """
        Calculate the total gross floor area of a building model, breaking down areas by storey and interior/exterior elements.
        """
        
        def handle_geometry_errors(func):
            """Decorator to handle common geometry processing errors"""
            @wraps(func)
            def wrapper(*args, **kwargs):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    print(f"Geometry processing error in {func.__name__}: {str(e)}")
                    return None
            return wrapper

        @lru_cache(maxsize=1000)
        def clean_coordinates(vertices_tuple):
            """Clean coordinate values to handle numerical precision issues"""
            vertices = np.array(vertices_tuple)
            return tuple(map(tuple, np.round(vertices, 6)))

        @handle_geometry_errors
        @lru_cache(maxsize=1000)
        def create_valid_polygon(vertices_tuple):
            """Create a valid polygon with various cleanup attempts"""
            vertices = np.array(vertices_tuple)
            poly = Polygon(vertices)
            if poly.is_valid and poly.area > 0:
                return poly
                
            methods = [
                lambda p: make_valid(p),
                lambda p: p.buffer(0),
                lambda p: p.buffer(1e-6).buffer(-1e-6),
                lambda p: p.simplify(1e-6)
            ]
            
            for method in methods:
                try:
                    cleaned = method(poly)
                    if cleaned.is_valid and cleaned.area > 0:
                        return cleaned
                except:
                    continue
                    
            return None

        @handle_geometry_errors
        def process_element_geometry(element, settings):
            """Process element geometry and return projected area"""
            shape = ifcopenshell.geom.create_shape(settings, element)
            vertices = np.array(ifcopenshell.util.shape.get_vertices(shape.geometry))
            faces = ifcopenshell.util.shape.get_faces(shape.geometry)
            projected_verts = clean_coordinates(tuple(map(tuple, vertices[:, :2])))
            
            polygons = []
            for face in faces:
                face_verts = tuple(projected_verts[i] for i in face)
                poly = create_valid_polygon(face_verts)
                if poly is not None:
                    polygons.append(poly)
            
            if not polygons:
                return 0.0, None
            
            try:
                union = unary_union(polygons)
                return union.area, union if union.is_valid else None
            except:
                try:
                    multi_poly = MultiPolygon(polygons)
                    return multi_poly.area, multi_poly if multi_poly.is_valid else None
                except:
                    return sum(p.area for p in polygons), None

        @lru_cache(maxsize=1000)
        def is_external_element(element_id):
            """Determine if an element is external based on various criteria"""
            element = ifc_model.by_id(element_id)
            element_rels = ifc_model.get_inverse(element)
            
            for rel in element_rels:
                if rel.is_a("IfcRelAssociatesMaterial"):
                    material = rel.RelatingMaterial
                    if material.is_a("IfcMaterialLayerSet"):
                        if any("exterior" in layer.Name.lower() 
                            for layer in material.MaterialLayers 
                            if layer.Name):
                            return True
                            
                elif rel.is_a("IfcRelDefinesByProperties"):
                    pset = rel.RelatingPropertyDefinition
                    if pset.is_a("IfcPropertySet"):
                        for prop in pset.HasProperties:
                            if prop.Name and "IsExternal" in prop.Name:
                                if hasattr(prop, "NominalValue") and prop.NominalValue.wrappedValue:
                                    return True
            
            return False

        def calculate_overlapping_area(elements, settings):
            """Calculate overlapping area between elements using spatial indexing"""
            element_polygons = {}
            idx_to_guid = {}  # Map index to GlobalId
            spatial_index = index.Index()
            
            # Build spatial index and store polygons
            for idx, element in enumerate(elements):
                area, polygon = process_element_geometry(element, settings)
                if polygon is not None:
                    guid = element.GlobalId
                    element_polygons[guid] = polygon
                    bounds = polygon.bounds
                    spatial_index.insert(idx, bounds)
                    idx_to_guid[idx] = guid
            
            overlaps = {}
            processed_pairs = set()
            
            # Use spatial index for efficient overlap detection
            for guid1, poly1 in element_polygons.items():
                bounds = poly1.bounds
                # Get potential intersections using the index
                for idx2 in spatial_index.intersection(bounds):
                    guid2 = idx_to_guid[idx2]
                    if guid1 >= guid2:  # Skip self and processed pairs
                        continue
                        
                    pair_key = (guid1, guid2)
                    if pair_key in processed_pairs:
                        continue
                    
                    poly2 = element_polygons[guid2]
                    try:
                        if poly1.intersects(poly2):  # Quick check before detailed intersection
                            intersection = poly1.intersection(poly2)
                            if intersection.is_valid and intersection.area > 0:
                                overlaps[pair_key] = round(intersection.area, 2)
                        processed_pairs.add(pair_key)
                    except Exception as e:
                        print(f"Failed to calculate overlap between {guid1} and {guid2}: {str(e)}")
                        continue
            
            return overlaps

        ifc_model = ifcopenshell.open(get_model_path(model=model))
        settings = ifcopenshell.geom.settings()
        settings.set(settings.USE_WORLD_COORDS, True)
        
        areas_by_storey = {}
        interior_elements_per_story = {}
        exterior_elements_per_story = {}

        # Get relevant elements
        all_elements = ifc_model.by_type('IfcWall') + ifc_model.by_type('IfcSlab')
        all_elements = [elem for elem in all_elements if not elem.is_a('IfcRoof') and 
                    not (hasattr(elem, 'PredefinedType') and elem.PredefinedType == 'ROOF')]

        # Process elements
        for element in all_elements:
            try:
                area, _ = process_element_geometry(element, settings)
                if area == 0:
                    continue

                is_external = is_external_element(element.id())
                container = ifcopenshell.util.element.get_container(element)
                storey_name = container.Name if container and container.is_a("IfcBuildingStorey") and container.Name else "Unknown"
                
                if storey_name not in areas_by_storey:
                    areas_by_storey[storey_name] = {"total": 0, "interior": 0, "exterior": 0}
                    interior_elements_per_story[storey_name] = []
                    exterior_elements_per_story[storey_name] = []
                
                if is_external:
                    areas_by_storey[storey_name]["exterior"] += area
                    exterior_elements_per_story[storey_name].append(element)
                else:
                    areas_by_storey[storey_name]["interior"] += area
                    interior_elements_per_story[storey_name].append(element)
                    
            except Exception as e:
                print(f"Failed to process element: {element.id()}: {str(e)}")
                continue

        # Calculate overlaps and adjust areas
        total_area = 0
        for storey in areas_by_storey:
            interior_overlaps = calculate_overlapping_area(interior_elements_per_story[storey], settings)
            areas_by_storey[storey]["interior"] -= sum(interior_overlaps.values())
            
            if include_external_elements:
                exterior_overlaps = calculate_overlapping_area(exterior_elements_per_story[storey], settings)
                areas_by_storey[storey]["exterior"] -= sum(exterior_overlaps.values())
                areas_by_storey[storey]["total"] = areas_by_storey[storey]["interior"] + areas_by_storey[storey]["exterior"]
            else:
                areas_by_storey[storey]["total"] = areas_by_storey[storey]["interior"]
            
            # Round values
            for key in areas_by_storey[storey]:
                areas_by_storey[storey][key] = round(areas_by_storey[storey][key], 2)
            
            total_area += areas_by_storey[storey]["total"]

        result = {
            "gross_floor_area": round(total_area, 2),
            "areas_by_storey": areas_by_storey
        }

        return json.dumps(result, indent=2)
    #################### Start of the function ####################
    # get available models for the current project
    state = get_state()
    project = state["project"]
    models = get_available_models(project=project)
    results = {}
    gfa = 0
    
    # Process models in parallel if there are multiple
    with ThreadPoolExecutor() as executor:
        future_to_model = {
            executor.submit(
                calculate_gross_floor_area_model, 
                model=model
            ): model for model in models if "mep" not in model
        }
        
        for future in future_to_model:
            model = future_to_model[future]
            try:
                if "mep" in model:
                    sub_gfa = {"gross_floor_area": 0}
                else:
                    sub_gfa = json.loads(future.result())
                gfa += sub_gfa["gross_floor_area"]
                results[model] = sub_gfa
            except Exception as e:
                print(f"Error processing model {model}: {str(e)}")
                results[model] = {"gross_floor_area": 0}
    
    results["gross_floor_area"] = gfa
    return json.dumps(results, indent=2)

if __name__ == "__main__":
    # Test the function
    old_state = get_state()
    project = "duplex"
    # project = "dental_clinic"

    set_state(project=project)
    gfa = calculate_gross_floor_area()
    print(gfa)

    # set the state back
    set_state(model=old_state["model"], project=old_state["project"])
# %%
