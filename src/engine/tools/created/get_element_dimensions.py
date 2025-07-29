import ifcopenshell
import ifcopenshell.util.element
import ifcopenshell.util.shape
import ifcopenshell.util.placement
import ifcopenshell.util.geolocation
import ifcopenshell.util.system
import ifcopenshell.geom
import math
import json
import re
from typing import *

def get_element_dimensions(
    ifc_file_path: str,
    element_type: str,
    dimension_names: List[str] = ['Width', 'Height', 'Length'],
    property_set_names: Optional[List[str]] = None,
    filter_criteria: Optional[Dict[str, Any]] = None,
    name_pattern: Optional[str] = None
) -> List[Dict[str, Any]]:
    """
    Extracts dimensional properties from IFC elements of a specified type, with intelligent fallback mechanisms 
    for cases where formal properties are not available.

    Args:
        ifc_file_path: Path to the IFC file
        element_type: IFC element type (e.g., 'IfcDoor', 'IfcWindow', 'IfcSpace', 'IfcWall')
        dimension_names: List of dimension names to extract (default: ['Width', 'Height', 'Length'])
        property_set_names: List of property set names to check for dimensions. Defaults to common property sets.
        filter_criteria: Dictionary of criteria to filter elements by their property values
        name_pattern: Regex pattern to extract dimensions from element names when properties are unavailable

    Returns:
        List of dictionaries, each containing:
        - element_name: The element's name
        - element_guid: The element's GlobalId
        - dimensions: Dictionary mapping dimension names to their values
        - source: Indicates whether the value came from 'property' or 'name_parsing'
        - confidence: A score indicating the reliability of the extracted value

    Example:
        # Get width of interior doors
        results = get_element_dimensions(
            "model.ifc", 
            "IfcDoor", 
            dimension_names=['Width'], 
            filter_criteria={'IsExternal': False}
        )

        # Get dimensions of spaces with name parsing fallback
        results = get_element_dimensions(
            "model.ifc", 
            "IfcSpace", 
            dimension_names=['Width', 'Length'], 
            name_pattern=r"(\d+)x(\d+)mm"
        )
    """
    # Default property set names
    if property_set_names is None:
        property_set_names = ['Pset_ElementCommon', 'Pset_DoorCommon', 'Pset_WindowCommon', 'Pset_SpaceCommon']
    
    # Load IFC file
    try:
        ifc_file = ifcopenshell.open(ifc_file_path)
    except Exception as e:
        raise Exception(f"Error loading IFC file: {str(e)}")
    
    # Get all elements of specified type
    try:
        elements = ifc_file.by_type(element_type)
    except Exception as e:
        raise Exception(f"Error getting elements of type {element_type}: {str(e)}")
    
    # Apply filtering if filter_criteria is provided
    if filter_criteria:
        filtered_elements = []
        for element in elements:
            # Get all property sets for this element
            try:
                psets = ifcopenshell.util.element.get_psets(element)
                matches_criteria = True
                
                # Check each filter criterion
                for filter_key, filter_value in filter_criteria.items():
                    found_match = False
                    # Check in all property sets
                    for pset_dict in psets.values():
                        if filter_key in pset_dict and pset_dict[filter_key] == filter_value:
                            found_match = True
                            break
                    
                    if not found_match:
                        matches_criteria = False
                        break
                
                if matches_criteria:
                    filtered_elements.append(element)
            except:
                # If there's an error checking properties, include the element
                filtered_elements.append(element)
        
        elements = filtered_elements
    
    # Process each element
    results = []
    for element in elements:
        # Get element name and GUID
        element_name = getattr(element, 'Name', 'Unnamed')
        element_guid = getattr(element, 'GlobalId', 'Unknown')
        
        # Initialize dimensions dictionary
        dimensions = {}
        source = 'property'  # Default source
        confidence = 1.0  # Default confidence
        
        # Try to get dimension values from properties
        for dim_name in dimension_names:
            dim_value = None
            # Check in specified property sets
            for pset_name in property_set_names:
                try:
                    pset = ifcopenshell.util.element.get_pset(element, pset_name)
                    if pset and dim_name in pset:
                        dim_value = pset[dim_name]
                        break
                except:
                    continue
            
            # If not found, try other common property sets
            if dim_value is None:
                try:
                    psets = ifcopenshell.util.element.get_psets(element)
                    for pset_name, pset_dict in psets.items():
                        # Skip unnamed property sets which may just contain the element name
                        if pset_name and dim_name in pset_dict:
                            dim_value = pset_dict[dim_name]
                            break
                except:
                    pass
            
            dimensions[dim_name] = dim_value
        
        # If no dimensions found from properties and name_pattern is provided, try parsing from name
        if name_pattern and all(v is None for v in dimensions.values()):
            # Try to extract dimensions from element name using regex
            try:
                match = re.search(name_pattern, element_name or '')
                if match:
                    # Extract values from regex groups
                    groups = match.groups()
                    for i, dim_name in enumerate(dimension_names[:len(groups)]):
                        # Try to convert to number
                        try:
                            # Handle unit conversion if needed (e.g., '1830mm' -> 1830)
                            value_str = groups[i]
                            if isinstance(value_str, str):
                                # Extract numeric part
                                numeric_part = re.search(r'(\d+\.?\d*)', value_str)
                                if numeric_part:
                                    dim_value = float(numeric_part.group(1))
                                    # Handle unit conversion if needed
                                    if 'mm' in value_str.lower() and 'm' not in value_str.lower():
                                        dim_value = dim_value / 1000  # Convert mm to meters
                                    dimensions[dim_name] = dim_value
                            else:
                                dimensions[dim_name] = float(value_str)
                            source = 'name_parsing'
                            confidence = 0.8  # Lower confidence for parsed values
                        except:
                            dimensions[dim_name] = None
                else:
                    source = 'property'
                    confidence = 0.0  # No values found
            except:
                source = 'property'
                confidence = 0.0  # Error in parsing
        elif all(v is None for v in dimensions.values()):
            # No dimensions found from properties and no name pattern provided or not applicable
            confidence = 0.0
        
        # Add result for this element
        results.append({
            'element_name': element_name or 'Unnamed',
            'element_guid': element_guid,
            'dimensions': dimensions,
            'source': source,
            'confidence': confidence
        })
    
    return results