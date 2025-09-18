import ifcopenshell
import ifcopenshell.util.element
from typing import List, Dict, Any, Optional

def get_structural_element_dimensions(
    model_path: str,
    element_type: str,
    name_pattern: Optional[str] = None,
    property_names: Optional[List[str]] = None
) -> List[Dict[str, Any]]:
    """
    Retrieves dimensional properties of structural elements from IFC models.
    
    This function extracts dimensional properties from Revit-exported IFC models,
    specifically targeting property sets like PSet_Revit_Type_Dimensions and 
    PSet_Revit_Type_Structural.
    
    Args:
        model_path (str): Path to the IFC model file
        element_type (str): The IFC structural element type (e.g., "IfcColumn", "IfcBeam", "IfcSlab")
        name_pattern (str, optional): Pattern to filter elements by name (case-insensitive substring match)
        property_names (List[str], optional): Specific dimensional properties to retrieve
        
    Returns:
        List[Dict[str, Any]]: List of dictionaries containing:
            - element_name: Name of the structural element
            - element_guid: GlobalId of the element
            - element_type: IFC type of the element
            - dimensions: Dictionary of dimensional properties with standardized keys
            - property_source: Information about which property sets the dimensions were extracted from
            
    Standardized dimension keys:
        - depth: Element depth/height
        - width: Element width
        - height: Element height (if different from depth)
        - thickness: Element thickness
        - flange_width: Flange width (for steel sections)
        - flange_thickness: Flange thickness (for steel sections)
        - web_thickness: Web thickness (for steel sections)
        - length: Element length
        - area: Cross-sectional area
        - volume: Element volume
    """
    
    # Load the IFC model
    model = ifcopenshell.open(model_path)
    
    # Get all elements of the specified type
    elements = model.by_type(element_type)
    
    # Filter by name pattern if provided
    if name_pattern:
        filtered_elements = []
        name_pattern_lower = name_pattern.lower()
        for element in elements:
            element_name = getattr(element, 'Name', '') or ''
            if name_pattern_lower in element_name.lower():
                filtered_elements.append(element)
        elements = filtered_elements
    
    results = []
    
    # Standardized dimension key mapping
    dimension_key_mapping = {
        # From PSet_Revit_Type_Dimensions
        'd': 'depth',
        'h': 'height',
        'b': 'width',
        'bf': 'flange_width',
        'tf': 'flange_thickness',
        'tw': 'web_thickness',
        # From PSet_Revit_Dimensions
        'Length': 'length',
        'Volume': 'volume',
        # From PSet_Revit_Type_Structural
        'A': 'area'
    }
    
    # Create reverse mapping for filtering by standardized names
    reverse_dimension_key_mapping = {v: k for k, v in dimension_key_mapping.items()}
    
    for element in elements:
        element_name = getattr(element, 'Name', '') or 'Unnamed'
        element_guid = element.GlobalId
        
        # Get property sets
        psets = ifcopenshell.util.element.get_psets(element)
        
        # Extract dimensional properties
        dimensions = {}
        property_sources = []
        
        # Check relevant property sets for dimensional data
        relevant_psets = ['PSet_Revit_Type_Dimensions', 'PSet_Revit_Type_Structural', 'PSet_Revit_Dimensions']
        
        for pset_name in relevant_psets:
            if pset_name in psets:
                pset_data = psets[pset_name]
                source_properties = []
                
                for prop_name, prop_value in pset_data.items():
                    # Skip metadata properties
                    if prop_name in ['id', 'Name', 'Description']:
                        continue
                    
                    # Map to standardized dimension keys
                    standardized_key = dimension_key_mapping.get(prop_name, prop_name)
                    
                    # If specific property names are requested, filter for those
                    if property_names:
                        # Check if either the original name or standardized key is in requested properties
                        if prop_name not in property_names and standardized_key not in property_names:
                            continue
                    
                    dimensions[standardized_key] = prop_value
                    source_properties.append(prop_name)
                
                if source_properties:
                    property_sources.append({
                        'pset': pset_name,
                        'properties': source_properties
                    })
        
        # Add to results
        results.append({
            'element_name': element_name,
            'element_guid': element_guid,
            'element_type': element_type,
            'dimensions': dimensions,
            'property_source': property_sources
        })
    
    return results