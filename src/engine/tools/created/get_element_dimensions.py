
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
    # Default property set names if not provided
    if property_set_names is None:
        property_set_names = [
            'Pset_ElementCommon', 'Pset_DoorCommon', 'Pset_WindowCommon', 
            'Pset_SpaceCommon', 'Pset_ColumnCommon', 'Pset_WallCommon', 
            'Pset_BeamCommon', 'Pset_SlabCommon', 'Pset_RoofCommon', 
            'Pset_StairCommon', 'Pset_StairFlightCommon', 'Pset_StairLandingCommon'
        ]
    
    # Load IFC file
    try:
        ifc_file = ifcopenshell.open(ifc_file_path)
    except Exception as e:
        # Return an error message if the file cannot be opened
        return {"error": f"Error loading IFC file: {str(e)}"}
    
    # Get all elements of the specified type
    try:
        elements = ifc_file.by_type(element_type)
    except Exception as e:
        # Return an error message if elements of the type cannot be retrieved
        return {"error": f"Error getting elements of type {element_type}: {str(e)}"}
    
    results = []
    
    for element in elements:
        element_name = getattr(element, 'Name', 'Unnamed')
        element_guid = getattr(element, 'GlobalId', 'Unknown')
        
        extracted_dimensions = {}
        sources = {}
        confidences = {}
        
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
                    continue # Skip this element if it doesn't match filter criteria
            except Exception as e:
                # If filtering fails for an element, skip it and log a warning (optional)
                # print(f"Warning: Could not apply filter criteria to element {element_guid}: {e}")
                continue

        # 1. Try to get dimension values from properties
        for dim_name in dimension_names:
            dim_value = None
            found_in_properties = False
            
            # Check in specified property sets first
            for pset_name in property_set_names:
                try:
                    pset = ifcopenshell.util.element.get_pset(element, pset_name)
                    if pset and dim_name in pset and pset[dim_name] is not None:
                        dim_value = pset[dim_name]
                        extracted_dimensions[dim_name] = dim_value
                        sources[dim_name] = 'property'
                        confidences[dim_name] = 1.0
                        found_in_properties = True
                        break
                except Exception as e:
                    pass # Ignore errors for specific property sets or dimensions
            
            if found_in_properties: continue

            # If not found in specified psets, try all available psets
            try:
                all_psets = ifcopenshell.util.element.get_psets(element)
                for pset_name, pset_dict in all_psets.items():
                    if dim_name in pset_dict and pset_dict[dim_name] is not None:
                        dim_value = pset_dict[dim_name]
                        extracted_dimensions[dim_name] = dim_value
                        sources[dim_name] = 'property'
                        confidences[dim_name] = 1.0
                        found_in_properties = True
                        break
            except Exception as e:
                pass # Ignore errors when accessing all psets
            
            if found_in_properties: continue

        # 2. If dimensions not fully found, try to extract from geometry
        # Check if any requested dimension is still missing or None
        missing_dims = [dim for dim in dimension_names if dim not in extracted_dimensions or extracted_dimensions[dim] is None]
        if missing_dims:
            try:
                # Accessing geometry directly via element.Representation
                representation = element.Representation
                if representation:
                    for rep_item in representation.Representations:
                        # We are interested in the 'Body' representation for geometry
                        if rep_item.RepresentationIdentifier == 'Body':
                            for item in rep_item.Items:
                                # Check if the item has a ProfileDef, common for extrusions and sweeps
                                if hasattr(item, 'ProfileDef') and item.ProfileDef:
                                    profile_def = item.ProfileDef
                                    profile_type = profile_def.is_a()

                                    # Specific handling for common steel profiles (I-shape)
                                    if profile_type == 'IfcIShapeProfileDef':
                                        if 'OverallWidth' in missing_dims and hasattr(profile_def, 'OverallWidth') and profile_def.OverallWidth is not None:
                                            extracted_dimensions['OverallWidth'] = profile_def.OverallWidth
                                            sources['OverallWidth'] = 'geometry'
                                            confidences['OverallWidth'] = 0.9
                                            missing_dims.remove('OverallWidth')
                                        if 'OverallDepth' in missing_dims and hasattr(profile_def, 'OverallDepth') and profile_def.OverallDepth is not None:
                                            extracted_dimensions['OverallDepth'] = profile_def.OverallDepth
                                            sources['OverallDepth'] = 'geometry'
                                            confidences['OverallDepth'] = 0.9
                                            missing_dims.remove('OverallDepth')
                                        if 'WebThickness' in missing_dims and hasattr(profile_def, 'WebThickness') and profile_def.WebThickness is not None:
                                            extracted_dimensions['WebThickness'] = profile_def.WebThickness
                                            sources['WebThickness'] = 'geometry'
                                            confidences['WebThickness'] = 0.9
                                            missing_dims.remove('WebThickness')
                                        if 'FlangeThickness' in missing_dims and hasattr(profile_def, 'FlangeThickness') and profile_def.FlangeThickness is not None:
                                            extracted_dimensions['FlangeThickness'] = profile_def.FlangeThickness
                                            sources['FlangeThickness'] = 'geometry'
                                            confidences['FlangeThickness'] = 0.9
                                            missing_dims.remove('FlangeThickness')
                                    
                                    # Handling for rectangular profiles
                                    elif profile_type == 'IfcRectangleProfileDef':
                                        if 'Width' in missing_dims and hasattr(profile_def, 'XDim') and profile_def.XDim is not None:
                                            extracted_dimensions['Width'] = profile_def.XDim
                                            sources['Width'] = 'geometry'
                                            confidences['Width'] = 0.9
                                            missing_dims.remove('Width')
                                        if 'Height' in missing_dims and hasattr(profile_def, 'YDim') and profile_def.YDim is not None:
                                            extracted_dimensions['Height'] = profile_def.YDim
                                            sources['Height'] = 'geometry'
                                            confidences['Height'] = 0.9
                                            missing_dims.remove('Height')
                                    # Handling for circular profiles
                                    elif profile_type == 'IfcCircleProfileDef':
                                        if 'Diameter' in missing_dims and hasattr(profile_def, 'Diameter') and profile_def.Diameter is not None:
                                            extracted_dimensions['Diameter'] = profile_def.Diameter
                                            sources['Diameter'] = 'geometry'
                                            confidences['Diameter'] = 0.9
                                            missing_dims.remove('Diameter')
                                    # Add more profile types as needed (e.g., IfcArbitraryClosedProfileDef, IfcTShapeProfileDef, etc.)

            except Exception as e:
                # print(f"Debug: Error accessing geometry for element {element_guid}: {e}")
                pass # Continue processing even if geometry access fails

        # 3. If dimensions still not fully found and name_pattern is provided, try parsing from name
        missing_dims_after_geom = [dim for dim in dimension_names if dim not in extracted_dimensions or extracted_dimensions[dim] is None]
        if name_pattern and missing_dims_after_geom:
            try:
                match = re.search(name_pattern, element_name or '')
                if match:
                    groups = match.groups()
                    # Map regex groups to dimension names. Assumes order of groups matches order in dimension_names.
                    for i, dim_name in enumerate(dimension_names):
                        if i < len(groups) and groups[i] is not None and (dim_name not in extracted_dimensions or extracted_dimensions[dim_name] is None):
                            value_str = groups[i]
                            try:
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
                                pass # If conversion fails, keep it as None or log an error
            except Exception as e:
                # print(f"Debug: Error parsing name for element {element_guid}: {e}")
                pass

        # Prepare the final output for this element
        final_element_data = {
            'element_name': element_name or 'Unnamed',
            'element_guid': element_guid,
            'dimensions': {}, 
            'source': 'none', 
            'confidence': 0.0
        }
        
        overall_confidence = 0.0
        final_source = 'none'
        
        # Populate the final dimensions dictionary and determine overall source/confidence
        for dim_name in dimension_names:
            value = extracted_dimensions.get(dim_name)
            final_element_data['dimensions'][dim_name] = value
            
            if value is not None:
                current_dim_source = sources.get(dim_name, 'none')
                current_dim_confidence = confidences.get(dim_name, 0.0)
                
                # Update overall confidence and source based on highest confidence found
                if current_dim_confidence > overall_confidence:
                    overall_confidence = current_dim_confidence
                    final_source = current_dim_source
        
        final_element_data['source'] = final_source
        final_element_data['confidence'] = overall_confidence
        
        results.append(final_element_data)
    
    return results
