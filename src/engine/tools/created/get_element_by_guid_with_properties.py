import ifcopenshell
import ifcopenshell.util.element
import ifcopenshell.util.shape
import ifcopenshell.geom
import math
from typing import Dict, Any, List, Tuple


def get_element_by_guid_with_properties(model_path: str, guid: str) -> Dict[str, Any]:
    """
    Retrieves an IFC element by its GlobalId and returns comprehensive information.
    
    This function is designed to handle IFC models exported from Revit with German
    property names and property sets. It properly extracts German property names
    like 'Fläche' for area and functional classifications. For wall elements,
    it also calculates paintable surface areas by analyzing actual geometry rather
    than relying solely on property set values that may include cumulative calculations.
    
    Args:
        model_path (str): Path to the IFC model file
        guid (str): GlobalId of the element to retrieve
        
    Returns:
        Dict containing element information with keys:
            - "element_info": Basic element details (name, guid, type)
            - "direct_attributes": Dictionary of direct attribute name-value pairs
            - "property_sets": Dictionary mapping property set names to their properties
            - "type_info": Information about the element type (if applicable)
            - "container_info": Spatial container information (if available)
            - "paintable_area": Calculated paintable surface area for wall elements (in square meters)
            
    Note:
        For Revit-exported IFC models with German properties:
        - Space names are typically found in 'ID-Daten' property set under 'Name'
        - Areas are typically found in 'Abmessungen' property set under 'Fläche'
        - Functional classifications may be in various property sets
        - For walls, property set areas may include both sides and cumulative calculations
          (hence the need for geometric paintable area calculation)
    """
    # Load the IFC model
    model = ifcopenshell.open(model_path)
    
    # Find the element by GlobalId
    element = model.by_guid(guid)
    
    if element is None:
        raise ValueError(f"No element found with GlobalId: {guid}")
    
    # 1. Basic element information
    element_info = {
        "name": element.Name if hasattr(element, "Name") else None,
        "long_name": element.LongName if hasattr(element, "LongName") else None,
        "guid": element.GlobalId,
        "type": element.is_a()
    }
    
    # 2. Direct attributes
    direct_attributes = {}
    # Get all attributes using the IfcOpenShell API
    for i in range(len(element)):
        try:
            attr = element.attribute_name(i)
            value = element[i]
            if attr not in ["Name", "GlobalId", "LongName"] and value is not None:
                # Handle different attribute value types
                if isinstance(value, (int, float, str, bool)):
                    direct_attributes[attr] = value
                elif hasattr(value, "wrappedValue"):
                    direct_attributes[attr] = value.wrappedValue
                elif hasattr(value, "is_a"):
                    # For complex types, store their type and name if available
                    direct_attributes[attr] = {
                        "type": value.is_a(),
                        "name": value.Name if hasattr(value, "Name") else None,
                        "guid": value.GlobalId if hasattr(value, "GlobalId") else None
                    }
                else:
                    direct_attributes[attr] = str(value)
        except Exception:
            # Skip attributes that cause issues
            continue
    
    # 3. Property sets - enhanced to handle German properties
    property_sets = {}
    related_properties = ifcopenshell.util.element.get_psets(element)
    if related_properties:
        # Process all property sets, preserving German names
        for pset_name, properties in related_properties.items():
            processed_properties = {}
            for prop_name, prop_value in properties.items():
                # Handle different property value types
                if isinstance(prop_value, (int, float, str, bool)):
                    processed_properties[prop_name] = prop_value
                elif hasattr(prop_value, 'wrappedValue'):
                    processed_properties[prop_name] = prop_value.wrappedValue
                elif isinstance(prop_value, dict):
                    # Handle complex property values
                    processed_properties[prop_name] = prop_value
                else:
                    processed_properties[prop_name] = str(prop_value)
            property_sets[pset_name] = processed_properties
    
    # 4. Type information
    type_info = {}
    
    # Try to get the element type using ifcopenshell.util.element.get_type first
    element_type = ifcopenshell.util.element.get_type(element)
    
    # If that doesn't work, try to find type through inverse relationships
    if not element_type:
        # Get all inverse relationships of the element
        inverses = model.get_inverse(element)
        for inverse in inverses:
            # Check if it's an IfcRelDefinesByType relationship
            if inverse.is_a("IfcRelDefinesByType"):
                element_type = inverse.RelatingType
                break
    
    if element_type:
        type_info = {
            "name": element_type.Name if hasattr(element_type, "Name") else None,
            "guid": element_type.GlobalId if hasattr(element_type, "GlobalId") else None,
            "type": element_type.is_a()
        }
        
        # Get type properties
        type_properties = ifcopenshell.util.element.get_psets(element_type)
        if type_properties:
            processed_type_properties = {}
            for pset_name, properties in type_properties.items():
                processed_properties = {}
                for prop_name, prop_value in properties.items():
                    if isinstance(prop_value, (int, float, str, bool)):
                        processed_properties[prop_name] = prop_value
                    elif hasattr(prop_value, 'wrappedValue'):
                        processed_properties[prop_name] = prop_value.wrappedValue
                    else:
                        processed_properties[prop_name] = str(prop_value)
                processed_type_properties[pset_name] = processed_properties
            type_info["properties"] = processed_type_properties
    
    # 5. Container/structure information
    container_info = {}
    container = ifcopenshell.util.element.get_container(element)
    if container:
        container_info = {
            "name": container.Name if hasattr(container, "Name") else None,
            "long_name": container.LongName if hasattr(container, "LongName") else None,
            "guid": container.GlobalId,
            "type": container.is_a()
        }
    
    # 6. Paintable area calculation for wall elements
    paintable_area = None
    
    if element.is_a("IfcWall"):
        try:
            paintable_area = _calculate_paintable_wall_area(model, element)
        except Exception as e:
            # If geometric calculation fails, log the error but continue
            print(f"Warning: Could not calculate paintable area for wall {guid}: {e}")
            paintable_area = None
    
    # Assemble the result
    result = {
        "element_info": element_info,
        "direct_attributes": direct_attributes,
        "property_sets": property_sets,
        "type_info": type_info,
        "container_info": container_info
    }
    
    # Add paintable area if calculated
    if paintable_area is not None:
        result["paintable_area"] = paintable_area
    
    return result


def _calculate_paintable_wall_area(model: ifcopenshell.file, wall_element) -> float:
    """
    Calculate the paintable surface area of a wall by analyzing its geometry.
    
    This function extracts the actual wall geometry and calculates paintable
    surface areas by:
    1. Analyzing individual wall faces
    2. Identifying paintable surfaces (excluding top/bottom faces)
    3. Calculating area of paintable surfaces only
    4. Returning the total paintable area in square meters
    
    Args:
        model: The IFC model
        wall_element: The wall element to analyze
        
    Returns:
        float: Paintable surface area in square meters
    """
    try:
        # Create geometry settings
        settings = ifcopenshell.geom.settings()
        settings.set(settings.USE_WORLD_COORDS, True)
        settings.set(settings.DISABLE_OPENING_SUBTRACTIONS, False)  # Include openings in calculation
        
        # Create shape geometry
        shape = ifcopenshell.geom.create_shape(settings, wall_element)
        
        # Get vertices and faces
        verts = shape.geometry.verts
        faces = shape.geometry.faces
        
        if len(verts) == 0 or len(faces) == 0:
            return 0.0
        
        # Group vertices into triples
        vertices = [(verts[i], verts[i+1], verts[i+2]) for i in range(0, len(verts), 3)]
        
        # Calculate area of each face
        total_paintable_area = 0.0
        
        for i in range(0, len(faces), 3):
            # Get face indices
            face_indices = [faces[i], faces[i+1], faces[i+2]]
            
            # Get the three vertices of the face
            if all(idx < len(vertices) for idx in face_indices):
                v1 = vertices[face_indices[0]]
                v2 = vertices[face_indices[1]]
                v3 = vertices[face_indices[2]]
                
                # Calculate face area using cross product
                area = _triangle_area(v1, v2, v3)
                
                # Check if this face is likely paintable (vertical surface)
                if _is_paintable_face(v1, v2, v3):
                    total_paintable_area += area
        
        return total_paintable_area
        
    except Exception as e:
        raise Exception(f"Failed to calculate paintable area: {e}")


def _triangle_area(v1: Tuple[float, float, float], 
                  v2: Tuple[float, float, float], 
                  v3: Tuple[float, float, float]) -> float:
    """
    Calculate the area of a triangle using cross product.
    
    Args:
        v1, v2, v3: Three vertices of the triangle
        
    Returns:
        float: Area of the triangle
    """
    # Calculate two edge vectors
    edge1 = (v2[0] - v1[0], v2[1] - v1[1], v2[2] - v1[2])
    edge2 = (v3[0] - v1[0], v3[1] - v1[1], v3[2] - v1[2])
    
    # Calculate cross product
    cross_x = edge1[1] * edge2[2] - edge1[2] * edge2[1]
    cross_y = edge1[2] * edge2[0] - edge1[0] * edge2[2]
    cross_z = edge1[0] * edge2[1] - edge1[1] * edge2[0]
    
    # Calculate magnitude of cross product
    cross_magnitude = math.sqrt(cross_x**2 + cross_y**2 + cross_z**2)
    
    # Area is half the magnitude of cross product
    return cross_magnitude / 2.0


def _is_paintable_face(v1: Tuple[float, float, float], 
                      v2: Tuple[float, float, float], 
                      v3: Tuple[float, float, float]) -> bool:
    """
    Determine if a face is paintable by checking its orientation.
    
    A face is considered paintable if it's primarily vertical (wall surface)
    rather than horizontal (floor/ceiling) or at an extreme angle.
    
    Args:
        v1, v2, v3: Three vertices of the face
        
    Returns:
        bool: True if the face is paintable, False otherwise
    """
    # Calculate face normal using cross product
    edge1 = (v2[0] - v1[0], v2[1] - v1[1], v2[2] - v1[2])
    edge2 = (v3[0] - v1[0], v3[1] - v1[1], v3[2] - v1[2])
    
    # Calculate normal vector
    normal_x = edge1[1] * edge2[2] - edge1[2] * edge2[1]
    normal_y = edge1[2] * edge2[0] - edge1[0] * edge2[2]
    normal_z = edge1[0] * edge2[1] - edge1[1] * edge2[0]
    
    # Normalize the normal vector
    magnitude = math.sqrt(normal_x**2 + normal_y**2 + normal_z**2)
    if magnitude == 0:
        return False
    
    normal_x /= magnitude
    normal_y /= magnitude
    normal_z /= magnitude
    
    # Check if the face is primarily vertical
    # A face is paintable if its normal has a significant vertical component
    # but is not purely horizontal (floor/ceiling)
    
    # Calculate the absolute Z component (vertical direction)
    abs_z = abs(normal_z)
    
    # Paintable if: 0.1 < |Z| < 0.9 (not too flat, not too steep)
    # This allows for both vertical and slightly angled wall surfaces
    return 0.1 < abs_z < 0.9