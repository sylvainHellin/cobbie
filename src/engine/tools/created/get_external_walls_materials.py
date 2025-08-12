
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

def get_external_walls_materials(model_path: str) -> List[Dict[str, Any]]:
    """
    Retrieves material information for external walls from IFC models.
    
    This function identifies external walls based on name patterns containing keywords
    like "exterior", "external", "outside", or "perimeter". For each identified external
    wall, it extracts complete material layer information using IfcOpenShell's 
    util.element.get_materials() function.
    
    Args:
        model_path (str): Path to the IFC model file
        
    Returns:
        List[Dict[str, Any]]: List of dictionaries containing:
            - wall_name: Name of the external wall
            - wall_id: GlobalId of the wall
            - materials: List of material names associated with the wall
            
    Example:
        >>> result = get_external_walls_materials("path/to/model.ifc")
        >>> print(result[0])
        {
            'wall_name': 'Basic Wall:Exterior - Brick on Block:143590',
            'wall_id': '2O2Fr$t4X7Zf8NOew3FLPP',
            'materials': ['Masonry - Brick', 'Misc. Air Layers - Air Space', ...]
        }
    """
    # Load the IFC model
    model = ifcopenshell.open(model_path)
    
    # Find all walls in the model
    walls = model.by_type("IfcWall")
    
    # Initialize list to store external wall materials
    external_walls_materials = []
    
    # Define keywords for identifying external walls
    external_keywords = ["exterior", "external", "outside", "perimeter"]
    
    # Iterate through all walls
    for wall in walls:
        # Get wall name, using GlobalId if Name is not available
        wall_name = wall.Name if wall.Name else wall.GlobalId
        
        # Check if the wall is external by checking name, description, and properties
        is_external = False
        
        # Check name
        if wall.Name and any(keyword in wall.Name.lower() for keyword in external_keywords):
            is_external = True
            
        # Check description
        if not is_external and hasattr(wall, 'Description') and wall.Description:
            if any(keyword in wall.Description.lower() for keyword in external_keywords):
                is_external = True
                
        # If still not identified as external, check for predefined type
        if not is_external and hasattr(wall, 'PredefinedType') and wall.PredefinedType:
            if any(keyword in wall.PredefinedType.lower() for keyword in external_keywords):
                is_external = True
                
        # If still not identified as external, check for object type
        if not is_external and hasattr(wall, 'ObjectType') and wall.ObjectType:
            if any(keyword in wall.ObjectType.lower() for keyword in external_keywords):
                is_external = True
        
        # If the wall is identified as external, get its materials
        if is_external:
            # Get materials for the wall using ifcopenshell.util.element.get_materials
            materials = ifcopenshell.util.element.get_materials(wall)
            
            # Extract material names
            material_names = []
            if materials:
                for material in materials:
                    if hasattr(material, 'Name') and material.Name:
                        material_names.append(material.Name)
                    else:
                        # Fallback to GlobalId or string representation if Name is not available
                        material_names.append(material.GlobalId if hasattr(material, 'GlobalId') else str(material))
            
            # Add wall information to the result list
            external_walls_materials.append({
                "wall_name": wall_name,
                "wall_id": wall.GlobalId,
                "materials": material_names
            })
    
    return external_walls_materials
