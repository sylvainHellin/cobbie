
import ifcopenshell
import ifcopenshell.util.element
import re
from typing import List, Dict, Any, Optional

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
        
        # Get dimensions of steel columns, including geometric properties
        results = get_element_dimensions(
            "steel_columns.ifc",
            "IfcColumn",
            dimension_names=['OverallWidth', 'OverallDepth', 'WebThickness', 'FlangeThickness', 'Height'],
            property_set_names=['Pset_ColumnCommon', 'Pset_SteelColumnCommon'] # Example property sets
        )
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
            'PSet_Revit_Dimensions'  # Adding Revit-specific property set
        ]
    
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
                # Check in specified property sets first
                for pset_name in property_set_names:
                    if pset_name in all_psets and dim_name in all_psets[pset_name]:
                        dim_value = all_psets[pset_name][dim_name]
                        if dim_value is not None:
                            extracted_dimensions[dim_name] = dim_value
                            sources[dim_name] = 'property'
                            confidences[dim_name] = 1.0
                            break
                
                # If not found in specified psets, try all available psets
                if extracted_dimensions[dim_name] is None:
                    for pset_name, pset_dict in all_psets.items():
                        if dim_name in pset_dict and pset_dict[dim_name] is not None:
                            extracted_dimensions[dim_name] = pset_dict[dim_name]
                            sources[dim_name] = 'property'
                            confidences[dim_name] = 1.0
                            break
        except Exception:
            pass  # Continue if property extraction fails

        # 2. If dimensions still not fully found and name_pattern is provided, try parsing from name
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
