import ifcopenshell
from typing import List, Dict, Any, Optional

def get_element_property_values(
    model_path: str,
    property_names: List[str],
    element_filter: Optional[Dict] = None,
    exact_match: bool = False,
    return_element_info: bool = True
) -> List[Dict[str, Any]]:
    """
    Retrieve specific property values from IFC elements' property sets.
    
    Args:
        model_path (str): The file path to the IFC model
        property_names (List[str]): List of property names or patterns to search for
        element_filter (Optional[Dict]): Optional filter criteria for elements 
            (e.g., {"type": "IfcSlab", "level": "Level 1"})
        exact_match (bool): Whether to perform exact matching or substring matching for property names
        return_element_info (bool): Whether to return element information along with property values
        
    Returns:
        List[Dict]: List of dictionaries containing element and property information
        
    Note:
        This function works with IFC models that follow standard property set conventions.
        For Revit-exported IFC models, property sets typically follow the PSet_Revit_* naming convention.
    """
    # Load the IFC model
    model = ifcopenshell.open(model_path)
    
    # Get unit information from the model and map to standard symbols
    unit_dict = {}
    units = model.by_type("IfcUnitAssignment")
    if units:
        for unit_assignment in units:
            if hasattr(unit_assignment, 'Units'):
                for unit in unit_assignment.Units:
                    if unit.is_a("IfcSIUnit"):
                        unit_type = unit.UnitType
                        unit_name = unit.Name if hasattr(unit, 'Name') else 'Unknown'
                        # Map IFC unit names to standard unit symbols
                        if unit_name == 'METRE':
                            unit_dict[unit_type] = 'm'
                        elif unit_name == 'SQUARE_METRE':
                            unit_dict[unit_type] = 'm²'
                        elif unit_name == 'CUBIC_METRE':
                            unit_dict[unit_type] = 'm³'
                        elif unit_name == 'SECOND':
                            unit_dict[unit_type] = 's'
                        elif unit_name == 'GRAM':
                            unit_dict[unit_type] = 'g'
                        else:
                            unit_dict[unit_type] = unit_name
                    elif unit.is_a("IfcConversionBasedUnit"):
                        unit_type = unit.UnitType
                        unit_name = unit.Name if hasattr(unit, 'Name') else 'Unknown'
                        # Handle common conversion based units
                        if unit_name == 'DEGREE':
                            unit_dict[unit_type] = '°'
                        else:
                            unit_dict[unit_type] = unit_name
    
    # Get all elements initially
    elements = model.by_type("IfcElement")
    
    # Apply element filtering if specified
    if element_filter:
        filtered_elements = []
        for element in elements:
            include_element = True
            
            # Filter by element type
            if "type" in element_filter:
                if element.is_a() != element_filter["type"]:
                    include_element = False
            
            # Filter by level
            if include_element and "level" in element_filter:
                contained_in_relations = [rel for rel in model.get_inverse(element) 
                                        if rel.is_a("IfcRelContainedInSpatialStructure")]
                level_match = False
                for rel in contained_in_relations:
                    if hasattr(rel.RelatingStructure, 'Name') and \
                       rel.RelatingStructure.Name == element_filter["level"]:
                        level_match = True
                        break
                if not level_match:
                    include_element = False
            
            if include_element:
                filtered_elements.append(element)
        
        elements = filtered_elements
    
    # Prepare results list
    results = []
    
    # Process each element
    for element in elements:
        # Get property sets directly from the element
        pset_relations = [rel for rel in model.get_inverse(element) 
                         if rel.is_a("IfcRelDefinesByProperties")]
        
        # Check each property set for matching properties
        for rel in pset_relations:
            prop_set = rel.RelatingPropertyDefinition
            if not prop_set.is_a("IfcPropertySet"):
                continue
                
            pset_name = prop_set.Name
            
            # Process each property in the property set
            for prop in prop_set.HasProperties:
                # Handle different property types
                if prop.is_a("IfcPropertySingleValue"):
                    prop_name = prop.Name
                    
                    # Check if this property matches any of our search terms
                    property_matches = False
                    matched_property_name = None
                    
                    for search_name in property_names:
                        if exact_match:
                            if prop_name == search_name:
                                property_matches = True
                                matched_property_name = search_name
                                break
                        else:
                            # Substring matching
                            if search_name.lower() in prop_name.lower():
                                property_matches = True
                                matched_property_name = search_name
                                break
                    
                    # If we found a matching property, get its value
                    if property_matches:
                        # Extract the actual value
                        prop_value = None
                        if prop.NominalValue:
                            # Get the wrapped value if it exists
                            if hasattr(prop.NominalValue, 'wrappedValue'):
                                prop_value = prop.NominalValue.wrappedValue
                            else:
                                prop_value = prop.NominalValue
                        
                        # Skip if value is None or if it's the same as the property name (indicating no real value)
                        if prop_value is None or (isinstance(prop_value, str) and prop_value == prop_name):
                            continue
                        
                        result_entry = {
                            "property_name": prop_name,
                            "property_value": prop_value,
                            "property_set_name": pset_name
                        }
                        
                        # Add unit information based on the model's unit definitions
                        property_unit = None
                        prop_name_lower = prop_name.lower()
                        if any(keyword in prop_name_lower for keyword in ['length', 'width', 'height', 'depth', 'thickness', 'span', 'cut', 'perimeter']):
                            property_unit = unit_dict.get('LENGTHUNIT')
                        elif 'area' in prop_name_lower:
                            property_unit = unit_dict.get('AREAUNIT')
                        elif 'volume' in prop_name_lower:
                            property_unit = unit_dict.get('VOLUMEUNIT')
                        elif any(keyword in prop_name_lower for keyword in ['weight', 'mass']):
                            property_unit = unit_dict.get('MASSUNIT')
                        elif 'angle' in prop_name_lower or prop_name_lower in ['slope']:
                            property_unit = unit_dict.get('PLANEANGLEUNIT')
                        
                        if property_unit:
                            result_entry["property_unit"] = property_unit
                        
                        # Add element information if requested
                        if return_element_info:
                            result_entry["element_name"] = element.Name if hasattr(element, 'Name') and element.Name else "Unnamed"
                            result_entry["element_type"] = element.is_a()
                        
                        results.append(result_entry)
    
    return results