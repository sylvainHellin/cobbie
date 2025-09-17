import ifcopenshell
import ifcopenshell.util.element
from typing import List, Dict, Any

def get_external_wall_thickness(model_path: str) -> List[Dict[str, Any]]:
    """
    Identifies external walls in an IFC model and calculates their total thickness based on material layers.
    
    Args:
        model_path (str): Path to the IFC file
        
    Returns:
        List[Dict[str, Any]]: List of dictionaries containing wall information and thickness details
    """
    # Load the IFC model
    model = ifcopenshell.open(model_path)
    
    # Get all wall entities
    walls = model.by_type("IfcWall")
    
    # Keywords to identify external walls
    external_keywords = ["exterior", "external", "outside", "perimeter"]
    
    external_walls_info = []
    
    # Process each wall
    for wall in walls:
        wall_name = wall.Name if hasattr(wall, 'Name') and wall.Name else ""
        
        # Check if the wall is external based on name patterns
        is_external = any(keyword in wall_name.lower() for keyword in external_keywords)
        
        if is_external:
            # Get material information
            material_info = ifcopenshell.util.element.get_material(wall)
            
            wall_data = {
                "wall_name": wall_name,
                "wall_id": wall.GlobalId,
                "layers": [],
                "total_thickness": 0.0
            }
            
            # Process material layers if available
            if material_info and material_info.is_a() == "IfcMaterialLayerSetUsage":
                layer_set = material_info.ForLayerSet
                
                layers = []
                total_thickness = 0.0
                
                if hasattr(layer_set, 'MaterialLayers'):
                    for i, layer in enumerate(layer_set.MaterialLayers):
                        # Get layer thickness
                        thickness = layer.LayerThickness if hasattr(layer, 'LayerThickness') else 0.0
                        
                        # Get material name
                        material_name = layer.Material.Name if layer.Material and hasattr(layer.Material, 'Name') else "Unknown"
                        
                        layer_data = {
                            "material_name": material_name,
                            "layer_thickness": thickness,
                            "layer_position": i
                        }
                        
                        layers.append(layer_data)
                        total_thickness += thickness
                
                wall_data["layers"] = layers
                wall_data["total_thickness"] = total_thickness
            
            external_walls_info.append(wall_data)
    
    return external_walls_info