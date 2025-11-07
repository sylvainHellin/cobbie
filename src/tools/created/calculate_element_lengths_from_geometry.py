import ifcopenshell
import ifcopenshell.geom
import math
from typing import List, Dict, Any, Optional, Union

def calculate_element_lengths_from_geometry(
    ifc_file,
    element_type: str,
    filter_criteria: Dict[str, Any],
    prefer_quantities: bool = True,
    include_details: bool = True
) -> Dict[str, Any]:
    """
    Calculates total lengths of IFC elements using geometric analysis when quantity data is unavailable.
    
    This function implements a multi-strategy approach:
    1) Filters elements by specified criteria (element type, property sets/values)
    2) Attempts to extract length quantities from standard quantity sets first
    3) Falls back to geometric analysis by creating shape representations and calculating bounding box dimensions
    4) Uses the longest horizontal dimension (max of X or Y) as the element length
    5) Provides detailed breakdown with individual element lengths and totals
    
    This is particularly useful for IFC models where quantity takeoff data is incomplete or missing,
    which is common in many BIM projects.
    
    Args:
        ifc_file: Loaded IFC model (ifcopenshell.file)
        element_type: IFC element type string (e.g., 'IfcWall', 'IfcBeam')
        filter_criteria: Dict with property_set, property_name, property_value
            Example: {'property_set': 'Pset_WallCommon', 'property_name': 'IsExternal', 'property_value': True}
        prefer_quantities: Boolean to try quantity extraction first (default: True)
        include_details: Boolean to include individual element results (default: True)
    
    Returns:
        Dict with:
        - total_length: float - Total calculated length
        - elements_processed: int - Number of elements processed
        - elements_with_quantities: int - Elements with length quantities found
        - elements_with_geometry: int - Elements with geometric analysis
        - elements: List[Dict] - Detailed breakdown of each element (if include_details=True)
        - errors: List[str] - Any errors encountered
    
    Example:
        >>> import ifcopenshell
        >>> ifc_file = ifcopenshell.open('model.ifc')
        >>> result = calculate_element_lengths_from_geometry(
        ...     ifc_file,
        ...     'IfcWall',
        ...     {'property_set': 'Pset_WallCommon', 'property_name': 'IsExternal', 'property_value': True}
        ... )
        >>> print(f"Total length: {result['total_length']:.3f} m")
    """
    
    # Initialize result structure
    result = {
        'total_length': 0.0,
        'elements_processed': 0,
        'elements_with_quantities': 0,
        'elements_with_geometry': 0,
        'elements': [],
        'errors': []
    }
    
    try:
        # Get all elements of specified type
        elements = ifc_file.by_type(element_type)
        
        # Filter elements based on criteria
        filtered_elements = []
        for element in elements:
            matches_criteria = True
            
            if 'property_set' in filter_criteria and 'property_name' in filter_criteria:
                property_set_name = filter_criteria['property_set']
                property_name = filter_criteria['property_name']
                expected_value = filter_criteria.get('property_value')
                
                # Check if element has the required property
                found_property = False
                for rel in element.IsDefinedBy:
                    if hasattr(rel, 'RelatingPropertyDefinition'):
                        prop_def = rel.RelatingPropertyDefinition
                        if (hasattr(prop_def, 'Name') and 
                            prop_def.Name == property_set_name and
                            hasattr(prop_def, 'HasProperties')):
                            
                            for prop in prop_def.HasProperties:
                                if (hasattr(prop, 'Name') and 
                                    prop.Name == property_name and
                                    hasattr(prop, 'NominalValue')):
                                    
                                    actual_value = prop.NominalValue.wrappedValue
                                    found_property = True
                                    
                                    # Check if value matches expected value
                                    if expected_value is not None and actual_value != expected_value:
                                        matches_criteria = False
                                        break
                    
                    if not matches_criteria:
                        break
                
                if not found_property:
                    matches_criteria = False
            
            if matches_criteria:
                filtered_elements.append(element)
        
        result['elements_processed'] = len(filtered_elements)
        
        # Process each filtered element
        for element in filtered_elements:
            element_info = {
                'GlobalId': element.GlobalId,
                'Name': getattr(element, 'Name', None),
                'ObjectType': getattr(element, 'ObjectType', None),
                'length': 0.0,
                'calculation_method': 'none',
                'error': None
            }
            
            length_found = False
            
            # Strategy 1: Try to extract length from quantities
            if prefer_quantities:
                try:
                    for rel in element.IsDefinedBy:
                        if hasattr(rel, 'RelatingPropertyDefinition'):
                            prop_def = rel.RelatingPropertyDefinition
                            if hasattr(prop_def, 'Quantities') and prop_def.Quantities:
                                for qty in prop_def.Quantities:
                                    if hasattr(qty, 'Name'):
                                        qty_name = qty.Name.lower()
                                        if ('length' in qty_name or 'länge' in qty_name or 'laenge' in qty_name):
                                            if hasattr(qty, 'LengthValue'):
                                                element_info['length'] = float(qty.LengthValue.wrappedValue)
                                                element_info['calculation_method'] = 'quantity'
                                                length_found = True
                                                result['elements_with_quantities'] += 1
                                                break
                        if length_found:
                            break
                except Exception as e:
                    element_info['error'] = f"Quantity extraction error: {str(e)}"
                    result['errors'].append(f"Element {element.GlobalId}: {str(e)}")
            
            # Strategy 2: Fall back to geometric analysis
            if not length_found:
                try:
                    # Create geometry settings
                    settings = ifcopenshell.geom.settings()
                    settings.set(settings.DISABLE_OPENING_SUBTRACTIONS, True)
                    
                    # Create shape geometry
                    shape = ifcopenshell.geom.create_shape(settings, element)
                    
                    if shape and hasattr(shape.geometry, 'verts'):
                        verts = shape.geometry.verts
                        
                        if len(verts) >= 3:  # Need at least one vertex
                            # Calculate bounding box
                            min_x, min_y, min_z = float('inf'), float('inf'), float('inf')
                            max_x, max_y, max_z = float('-inf'), float('-inf'), float('-inf')
                            
                            for i in range(0, len(verts), 3):
                                if i + 2 < len(verts):
                                    x, y, z = verts[i], verts[i+1], verts[i+2]
                                    min_x, min_y, min_z = min(min_x, x), min(min_y, y), min(min_z, z)
                                    max_x, max_y, max_z = max(max_x, x), max(max_y, y), max(max_z, z)
                            
                            # Calculate dimensions
                            length_x = max_x - min_x
                            length_y = max_y - min_y
                            length_z = max_z - min_z
                            
                            # Use the longest horizontal dimension as length
                            element_length = max(length_x, length_y)
                            
                            # Sanity check: length should be reasonable
                            if element_length > 0 and element_length < 1000:  # Reasonable range in meters
                                element_info['length'] = element_length
                                element_info['calculation_method'] = 'geometry'
                                element_info['bounding_box'] = {
                                    'length_x': length_x,
                                    'length_y': length_y,
                                    'length_z': length_z
                                }
                                length_found = True
                                result['elements_with_geometry'] += 1
                            else:
                                element_info['error'] = f"Unreasonable length calculated: {element_length}"
                        else:
                            element_info['error'] = "Insufficient vertices for geometry analysis"
                    else:
                        element_info['error'] = "No geometry available"
                        
                except Exception as e:
                    element_info['error'] = f"Geometry analysis error: {str(e)}"
                    result['errors'].append(f"Element {element.GlobalId}: {str(e)}")
            
            # Add to total if length was found
            if length_found:
                result['total_length'] += element_info['length']
            
            # Add element details if requested
            if include_details:
                result['elements'].append(element_info)
                
    except Exception as e:
        result['errors'].append(f"General processing error: {str(e)}")
    
    return result