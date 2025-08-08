
import ifcopenshell
import ifcopenshell.util.element
import ifcopenshell.util.shape
import ifcopenshell.geom
import re
from typing import List, Dict, Any, Optional

def is_valid_dimension_value(value: Any) -> bool:
    """
    Check if a value is a valid dimension value (numeric) rather than a string literal.
    
    Args:
        value: The value to check
        
    Returns:
        bool: True if the value is a valid numeric dimension, False otherwise
    """
    if value is None:
        return False
    
    # If it's already a number, it's valid
    if isinstance(value, (int, float)):
        return True
    
    # If it's a string, check if it's a numeric string
    if isinstance(value, str):
        # Check if it's a string representation of a number
        try:
            float(value)
            return True
        except ValueError:
            # It's a string but not a number
            return False
    
    return False

def get_element_dimensions(
    ifc_file_path: str,
    element_type: str,
    dimension_names: List[str] = None,
    property_set_names: Optional[List[str]] = None,
    filter_criteria: Optional[Dict[str, Any]] = None,
    name_pattern: Optional[str] = None
) -> List[Dict[str, Any]]:
    """
    Extracts dimensional properties from IFC elements of a specified type, with intelligent fallback mechanisms 
    for cases where formal properties are not available.

    This function is designed to work with IFC models exported from various BIM authoring software, including
    Revit (using PSet_Revit_Dimensions and other Revit-specific property sets), ArchiCAD, and others.

    Args:
        ifc_file_path: Path to the IFC file
        element_type: IFC element type (e.g., 'IfcDoor', 'IfcWindow', 'IfcSpace', 'IfcWall')
        dimension_names: List of dimension names to extract (default: ['Width', 'Height', 'Length']).
                         For steel elements, consider including 'OverallWidth', 'OverallDepth', 'WebThickness', 'FlangeThickness'.
        property_set_names: List of property set names to check for dimensions. Defaults to common property sets.
        filter_criteria: Dictionary of criteria to filter elements by their property values.
                         Example: {'IsExternal': False}
        name_pattern: Regex pattern to extract dimensions from element names when properties are unavailable.
                      Example: r"(\d+)x(\d+)mm"

    Returns:
        List of dictionaries, each containing:
        - element_name: The element's name
        - element_guid: The element's GlobalId
        - dimensions: Dictionary mapping dimension names to their values
        - source: Indicates whether the value came from 'property', 'geometry', or 'name_parsing'. 'none' if no value found.
        - confidence: A score indicating the reliability of the extracted value (1.0 for property, 0.9 for geometry, 0.7 for name_parsing, 0.0 if none found).
    """
    # Set default values
    if dimension_names is None:
        dimension_names = ['Width', 'Height', 'Length']
    
    if property_set_names is None:
        property_set_names = [
            'Pset_ElementCommon', 'Pset_DoorCommon', 'Pset_WindowCommon', 
            'Pset_SpaceCommon', 'Pset_ColumnCommon', 'Pset_WallCommon', 
            'Pset_BeamCommon', 'Pset_SlabCommon', 'Pset_RoofCommon', 
            'Pset_StairCommon', 'Pset_StairFlightCommon', 'Pset_StairLandingCommon',
            'PSet_Revit_Dimensions', 'PSet_Revit_Type_Dimensions',  # Adding more Revit-specific property sets
            'PSet_Revit_Type_Structural', 'PSet_Revit_Structural', 'PSet_Revit_Structural Analysis'
        ]
    
    # Mapping of common dimension names to their possible actual names in different software
    dimension_name_mapping = {
        'Width': ['Width', 'b', 'NominalWidth', 'OverallWidth'],
        'Height': ['Height', 'h', 'NominalHeight', 'OverallHeight', 'Length'],
        'Length': ['Length', 'l', 'NominalLength', 'OverallLength'],
        'OverallWidth': ['OverallWidth', 'Width', 'b', 'NominalWidth'],
        'OverallDepth': ['OverallDepth', 'Depth', 'h', 'NominalDepth'],
        'WebThickness': ['WebThickness', 'tw', 'Web Thickness'],
        'FlangeThickness': ['FlangeThickness', 'tf', 'Flange Thickness'],
        'Depth': ['Depth', 'd', 'h', 'OverallDepth']
    }
    
    # Load IFC file
    try:
        ifc_file = ifcopenshell.open(ifc_file_path)
    except Exception as e:
        raise Exception(f"Error loading IFC file: {str(e)}")
    
    # Get all elements of the specified type
    try:
        elements = ifc_file.by_type(element_type)
    except Exception as e:
        raise Exception(f"Error getting elements of type {element_type}: {str(e)}")
    
    results = []
    
    for element in elements:
        element_name = getattr(element, 'Name', 'Unnamed')
        element_guid = getattr(element, 'GlobalId', 'Unknown')
        
        # Apply filtering if filter_criteria is provided
        if filter_criteria:
            try:
                psets = ifcopenshell.util.element.get_psets(element)
                matches_criteria = True
                for filter_key, filter_value in filter_criteria.items():
                    found_match = False
                    for pset_dict in psets.values():
                        if filter_key in pset_dict and pset_dict[filter_key] == filter_value:
                            found_match = True
                            break
                    if not found_match:
                        matches_criteria = False
                        break
                if not matches_criteria:
                    continue  # Skip this element if it doesn't match filter criteria
            except Exception:
                continue  # If filtering fails, skip the element

        # Initialize data structures for this element
        extracted_dimensions = {dim: None for dim in dimension_names}
        sources = {dim: 'none' for dim in dimension_names}
        confidences = {dim: 0.0 for dim in dimension_names}
        
        # 1. Try to get dimension values from properties
        try:
            all_psets = ifcopenshell.util.element.get_psets(element)
            
            for dim_name in dimension_names:
                # Get possible actual names for this dimension
                possible_names = dimension_name_mapping.get(dim_name, [dim_name])
                
                # Check in specified property sets first
                for pset_name in property_set_names:
                    if pset_name in all_psets:
                        pset_dict = all_psets[pset_name]
                        # Check for any of the possible names
                        for possible_name in possible_names:
                            if possible_name in pset_dict:
                                dim_value = pset_dict[possible_name]
                                # Only accept valid dimension values (not string literals)
                                if is_valid_dimension_value(dim_value):
                                    extracted_dimensions[dim_name] = float(dim_value) if isinstance(dim_value, str) else dim_value
                                    sources[dim_name] = 'property'
                                    confidences[dim_name] = 1.0
                                    break
                        if extracted_dimensions[dim_name] is not None:
                            break
                
                # If not found in specified psets, try all available psets
                if extracted_dimensions[dim_name] is None:
                    for pset_name, pset_dict in all_psets.items():
                        # Check for any of the possible names
                        for possible_name in possible_names:
                            if possible_name in pset_dict:
                                dim_value = pset_dict[possible_name]
                                # Only accept valid dimension values (not string literals)
                                if is_valid_dimension_value(dim_value):
                                    extracted_dimensions[dim_name] = float(dim_value) if isinstance(dim_value, str) else dim_value
                                    sources[dim_name] = 'property'
                                    confidences[dim_name] = 1.0
                                    break
                        if extracted_dimensions[dim_name] is not None:
                            break
        except Exception:
            pass  # Continue if property extraction fails

        # 2. If dimensions still not fully found, try to extract from geometry
        missing_dims = [dim for dim in dimension_names if extracted_dimensions[dim] is None]
        if missing_dims:
            try:
                # Try to get geometry information
                settings = ifcopenshell.geom.settings()
                settings.set(settings.USE_WORLD_COORDS, True)
                
                shape = ifcopenshell.geom.create_shape(settings, element)
                if shape:
                    geometry = shape.geometry
                    # Calculate bounding box as a fallback for dimensions
                    verts = geometry.verts
                    if verts:
                        # Extract x, y, z coordinates
                        x_coords = [verts[i] for i in range(0, len(verts), 3)]
                        y_coords = [verts[i+1] for i in range(0, len(verts), 3)]
                        z_coords = [verts[i+2] for i in range(0, len(verts), 3)]
                        
                        # Calculate dimensions from bounding box
                        if x_coords and y_coords and z_coords:
                            width = max(x_coords) - min(x_coords)
                            depth = max(y_coords) - min(y_coords)
                            height = max(z_coords) - min(z_coords)
                            
                            # Map to requested dimensions based on what's missing
                            for dim_name in missing_dims:
                                if extracted_dimensions[dim_name] is None:
                                    # Simple mapping - could be improved with more sophisticated logic
                                    if dim_name in ['Width', 'OverallWidth'] and width > 0:
                                        extracted_dimensions[dim_name] = width
                                        sources[dim_name] = 'geometry'
                                        confidences[dim_name] = 0.9
                                    elif dim_name in ['Height', 'Length', 'OverallDepth', 'Depth'] and height > 0:
                                        extracted_dimensions[dim_name] = height
                                        sources[dim_name] = 'geometry'
                                        confidences[dim_name] = 0.9
                                    elif dim_name in ['Length', 'Depth'] and depth > 0:
                                        extracted_dimensions[dim_name] = depth
                                        sources[dim_name] = 'geometry'
                                        confidences[dim_name] = 0.9
            except Exception:
                pass  # Continue if geometry extraction fails

        # 3. If dimensions still not fully found and name_pattern is provided, try parsing from name
        missing_dims = [dim for dim in dimension_names if extracted_dimensions[dim] is None]
        if name_pattern and missing_dims and element_name:
            try:
                match = re.search(name_pattern, element_name)
                if match:
                    groups = match.groups()
                    # Map regex groups to dimension names
                    for i, dim_name in enumerate(missing_dims):
                        if i < len(groups) and groups[i] is not None:
                            try:
                                value_str = groups[i]
                                # Attempt to extract numeric part and handle units
                                numeric_part = re.search(r'(\d+\.?\d*)', value_str)
                                if numeric_part:
                                    dim_value = float(numeric_part.group(1))
                                    # Basic unit conversion: assume 'mm' means millimeters, convert to meters
                                    if 'mm' in value_str.lower() and 'm' not in value_str.lower():
                                        dim_value = dim_value / 1000
                                    
                                    extracted_dimensions[dim_name] = dim_value
                                    sources[dim_name] = 'name_parsing'
                                    confidences[dim_name] = 0.7
                            except ValueError:
                                pass  # If conversion fails, keep it as None
            except Exception:
                pass  # Continue if name parsing fails

        # Determine overall confidence and source
        max_confidence = max(confidences.values()) if confidences.values() else 0.0
        overall_source = 'none'
        if max_confidence > 0:
            # Find the source with the highest confidence
            for dim_name, confidence in confidences.items():
                if confidence == max_confidence:
                    overall_source = sources[dim_name]
                    break
        
        # Prepare the final output for this element
        final_element_data = {
            'element_name': element_name or 'Unnamed',
            'element_guid': element_guid,
            'dimensions': extracted_dimensions,
            'source': overall_source,
            'confidence': max_confidence
        }
        
        results.append(final_element_data)
    
    return results
