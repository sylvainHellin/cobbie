import ifcopenshell
import ifcopenshell.util.element
from typing import Dict, Any

def get_element_dimensions_by_guid(model_path: str, guid: str) -> Dict[str, Any]:
    """
    Retrieves all dimensional properties for an IFC element given its GlobalId.
    
    This function works with common IFC element types (IfcWall, IfcSlab, IfcDoor, IfcWindow, 
    IfcColumn, IfcBeam, IfcSpace, etc.) and extracts dimensions from standard property sets 
    like PSet_Revit_Dimensions, PSet_Revit_Type_Dimensions, and other common dimensional 
    property sets.
    
    Assumptions:
    - The model is exported from Revit or contains similar property set structures
    - Dimensional properties follow standard naming conventions
    
    Args:
        model_path (str): Path to the IFC model file
        guid (str): GlobalId of the element to retrieve dimensions for
        
    Returns:
        Dict[str, Any]: Dictionary containing:
            - element_name: Name of the element
            - element_type: IFC type of the element
            - dimensions: Dictionary of dimensional properties with standardized keys
            - property_sources: Information about which property sets the dimensions were extracted from
            
    Standardized dimension keys:
        - width: Element width
        - height: Element height
        - depth: Element depth/height (for 3D elements)
        - thickness: Element thickness
        - area: Surface area
        - volume: Volume
        - length: Element length (for 1D elements)
        - flange_width: Flange width (for steel sections)
        - web_thickness: Web thickness (for steel sections)
        - flange_thickness: Flange thickness (for steel sections)
    """
    # Load the IFC model
    model = ifcopenshell.open(model_path)
    
    # Retrieve the element by its GUID
    element = model.by_guid(guid)
    
    if not element:
        raise ValueError(f"No element found with GUID: {guid}")
    
    # Get element information
    element_name = getattr(element, 'Name', 'Unnamed')
    element_type = element.is_a()
    
    # Get all property sets for the element
    psets = ifcopenshell.util.element.get_psets(element)
    
    # Initialize results
    dimensions = {}
    property_sources = []
    
    # Define property set mappings for dimensional properties
    # These are specific mappings for Revit property sets
    dimensional_pset_mappings = {
        'PSet_Revit_Dimensions': {
            'Length': 'length',
            'Area': 'area',
            'Volume': 'volume',
            'Thickness': 'thickness',
            'Perimeter': 'perimeter'
        },
        'PSet_Revit_Type_Dimensions': {
            'bf': 'flange_width',
            'd': 'depth',
            'h': 'height',
            'b': 'width',
            'tf': 'flange_thickness',
            'tw': 'web_thickness',
            'k': 'k',
            'kr': 'kr'
        },
        'PSet_Revit_Type_Construction': {
            'Width': 'thickness'
        }
    }
    
    # Process each property set
    for pset_name, property_mappings in dimensional_pset_mappings.items():
        if pset_name in psets:
            source_info = {
                'property_set': pset_name,
                'properties_mapped': []
            }
            
            pset_properties = psets[pset_name]
            
            # Process each property in the property set
            for prop_name, prop_value in pset_properties.items():
                # Skip non-numeric properties and metadata
                if not isinstance(prop_value, (int, float)) or isinstance(prop_value, bool):
                    continue
                
                # Map property to standardized key if it exists in our mapping
                if prop_name in property_mappings:
                    standardized_key = property_mappings[prop_name]
                    dimensions[standardized_key] = prop_value
                    source_info['properties_mapped'].append({
                        'original_name': prop_name,
                        'standardized_key': standardized_key,
                        'value': prop_value
                    })
            
            # Add source info if we found dimensional properties
            if source_info['properties_mapped']:
                property_sources.append(source_info)
    
    # Handle element-specific dimensional properties from other property sets
    # Process constraint-related properties for walls
    if 'IfcWall' in element_type and 'PSet_Revit_Constraints' in psets:
        constraints = psets['PSet_Revit_Constraints']
        source_info = {
            'property_set': 'PSet_Revit_Constraints',
            'properties_mapped': []
        }
        
        # Map constraint properties that are dimensional
        constraint_mappings = {
            'Base Extension Distance': 'depth',
            'Top Extension Distance': 'depth',  # Additional depth information
            'Unconnected Height': 'height',
            'Base Offset': 'height'  # Part of height calculation
        }
        
        for prop_name, standardized_key in constraint_mappings.items():
            if prop_name in constraints and isinstance(constraints[prop_name], (int, float)) and not isinstance(constraints[prop_name], bool):
                # For walls, we might want to use the first available height-related value
                if standardized_key not in dimensions:
                    dimensions[standardized_key] = constraints[prop_name]
                    source_info['properties_mapped'].append({
                        'original_name': prop_name,
                        'standardized_key': standardized_key,
                        'value': constraints[prop_name]
                    })
        
        if source_info['properties_mapped']:
            property_sources.append(source_info)
    
    # Process common property sets that might contain dimensional data
    common_psets = ['Pset_BeamCommon', 'Pset_ColumnCommon', 'Pset_WallCommon', 'Pset_SlabCommon']
    for pset_name in common_psets:
        if pset_name in psets:
            source_info = {
                'property_set': pset_name,
                'properties_mapped': []
            }
            
            pset_properties = psets[pset_name]
            
            # Define mappings for common property sets
            common_mappings = {
                'Span': 'length',
                'Slope': 'slope'
            }
            
            for prop_name, prop_value in pset_properties.items():
                if not isinstance(prop_value, (int, float)) or isinstance(prop_value, bool):
                    continue
                
                if prop_name in common_mappings:
                    standardized_key = common_mappings[prop_name]
                    if standardized_key not in dimensions:  # Don't overwrite if already set
                        dimensions[standardized_key] = prop_value
                        source_info['properties_mapped'].append({
                            'original_name': prop_name,
                            'standardized_key': standardized_key,
                            'value': prop_value
                        })
            
            if source_info['properties_mapped']:
                property_sources.append(source_info)
    
    # Special handling for specific element types to ensure consistent dimension mapping
    if 'IfcSlab' in element_type:
        # For slabs, ensure thickness is properly mapped
        if 'Thickness' in psets.get('PSet_Revit_Dimensions', {}) and 'thickness' not in dimensions:
            dimensions['thickness'] = psets['PSet_Revit_Dimensions']['Thickness']
    
    elif 'IfcColumn' in element_type:
        # For columns, map b and h to width and height if available
        if 'PSet_Revit_Type_Dimensions' in psets:
            type_dims = psets['PSet_Revit_Type_Dimensions']
            if 'b' in type_dims and 'width' not in dimensions:
                dimensions['width'] = type_dims['b']
            if 'h' in type_dims and 'height' not in dimensions:
                dimensions['height'] = type_dims['h']
    
    elif 'IfcBeam' in element_type:
        # For beams, ensure all steel section dimensions are captured
        if 'PSet_Revit_Type_Dimensions' in psets:
            type_dims = psets['PSet_Revit_Type_Dimensions']
            beam_mappings = {
                'bf': 'flange_width',
                'd': 'depth',
                'tf': 'flange_thickness',
                'tw': 'web_thickness',
                'k': 'k',
                'kr': 'kr'
            }
            for prop_name, standardized_key in beam_mappings.items():
                if prop_name in type_dims and standardized_key not in dimensions:
                    dimensions[standardized_key] = type_dims[prop_name]
    
    # Return the complete information
    return {
        'element_name': element_name,
        'element_type': element_type,
        'dimensions': dimensions,
        'property_sources': property_sources
    }