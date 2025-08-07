
import ifcopenshell
import ifcopenshell.util.element
import ifcopenshell.geom
from typing import List

def get_spaces_by_function_and_area(ifc_file_path: str, function_keywords: List[str]) -> float:
    """
    Identifies IFC spaces by functional keywords and calculates their total area.

    This function parses IfcSpace elements, filters them based on provided keywords
    (checking names, descriptions, and property sets), and sums their associated
    area properties.

    Assumptions:
    - The area of an IfcSpace is primarily sought from its associated Quantity Sets
      (e.g., 'GrossFloorArea', 'NetFloorArea') or Property Sets (e.g., 'Area').
    - If area information is not found in sets, it will attempt to calculate it
      from the space's geometry using IfcOpenCascade.
    - For storage spaces, the function ONLY looks for specific indicators like:
      * OmniClass Table 13 Category values indicating storage rooms
      * Category Description values indicating storage rooms
    - Keyword matching is NOT used for storage identification to avoid over-matching.
    - The IFC model is assumed to be exported with standard IfcSpace definitions
      and potentially common property sets like 'Pset_SpaceCommon'.
    - Geometry calculation requires IfcOpenShell to be built with OpenCascade support.
    - In a dental clinic context, only basic "Storage Room" spaces are considered,
      excluding specialized storage like soiled or hazardous material storage.

    :param ifc_file_path: Path to the IFC file.
    :param function_keywords: A list of keywords to filter spaces by. For storage spaces,
                              keyword matching is not used to avoid over-matching.
    :return: The total area of the matching spaces, or 0.0 if no matching spaces are found or an error occurs.
    """
    try:
        ifc_file = ifcopenshell.open(ifc_file_path)
    except Exception as e:
        print(f"Error opening IFC file: {e}")
        return 0.0

    total_area = 0.0
    spaces = ifc_file.by_type("IfcSpace")

    for space in spaces:
        is_matching_space = False
        
        # Get all properties for the space
        all_properties = ifcopenshell.util.element.get_psets(space)
        
        # Get space name and description
        space_name = (space.Name or "").lower()
        space_description = (space.Description or "").lower()
        
        # Check for storage spaces first (special handling)
        is_storage_space = False
        identity_data = all_properties.get('PSet_Revit_Identity Data', {})
        other_data = all_properties.get('PSet_Revit_Other', {})
        
        omni_class = identity_data.get('OmniClass Table 13 Category', '')
        category_desc = other_data.get('Category Description', '')
        
        # Check for storage classification (case-insensitive)
        if '13-75 11 11: storage room' in str(omni_class).lower() and "soiled" not in str(omni_class).lower():
            is_storage_space = True
        elif 'storage room' in str(category_desc).lower() and "soiled" not in str(category_desc).lower():
            is_storage_space = True
            
        # Handle storage spaces (no keyword matching)
        if is_storage_space:
            # Only include if "storage" is in the function_keywords
            if "storage" in [kw.lower() for kw in function_keywords]:
                is_matching_space = True
        else:
            # Handle non-storage spaces with keyword matching
            # Check space name and description
            for keyword in function_keywords:
                keyword_lower = keyword.lower()
                if keyword_lower in space_name or keyword_lower in space_description:
                    is_matching_space = True
                    break
            
            # If not found in name/description, check property sets
            if not is_matching_space:
                for pset_name, properties in all_properties.items():
                    # Check identity data for classification
                    if 'Name' in properties and isinstance(properties['Name'], str):
                        space_type = properties['Name'].lower()
                        for keyword in function_keywords:
                            if keyword.lower() in space_type:
                                is_matching_space = True
                                break
                        if is_matching_space:
                            break
                    
                    # Check OmniClass category
                    if 'OmniClass Table 13 Category' in properties:
                        omni_category = str(properties['OmniClass Table 13 Category']).lower()
                        for keyword in function_keywords:
                            if keyword.lower() in omni_category:
                                is_matching_space = True
                                break
                        if is_matching_space:
                            break
                    
                    # Check Category Description
                    if 'Category Description' in properties:
                        category_description = str(properties['Category Description']).lower()
                        for keyword in function_keywords:
                            if keyword.lower() in category_description:
                                is_matching_space = True
                                break
                        if is_matching_space:
                            break

        if is_matching_space:
            area = 0.0
            area_found = False

            # Prioritize Quantity Sets for area (e.g., GrossFloorArea, NetFloorArea)
            qtos = ifcopenshell.util.element.get_psets(space, qtos_only=True)
            for qto_name, properties in qtos.items():
                for prop_name, prop_value in properties.items():
                    if 'area' in prop_name.lower() and isinstance(prop_value, (int, float)):
                        area += prop_value
                        area_found = True
                        break
                if area_found:
                    break

            # If not found in Quantity Sets, check common Property Sets for 'Area'
            if not area_found:
                psets = ifcopenshell.util.element.get_psets(space, psets_only=True)
                for pset_name, properties in psets.items():
                    for prop_name, prop_value in properties.items():
                        if 'area' in prop_name.lower() and isinstance(prop_value, (int, float)):
                            area += prop_value
                            area_found = True
                            break
                    if area_found:
                        break

            # Fallback: Calculate area from geometry if not found in sets
            if not area_found:
                try:
                    # Use ifcopenshell.geom for geometry processing
                    settings = ifcopenshell.geom.settings()
                    # Ensure OpenCascade is used if available
                    settings.set(settings.USE_PYTHON_OPENCASCADE, True)
                    
                    # Create shape from the space element
                    shape = ifcopenshell.geom.create_shape(settings, space)
                    
                    if shape and shape.geometry:
                        # Try to get area from the geometry
                        area_from_geom = shape.geometry.Area()
                        if isinstance(area_from_geom, (int, float)) and area_from_geom > 0:
                            area += area_from_geom
                            area_found = True
                            
                except Exception as e:
                    # Geometry calculation failed, which is acceptable
                    pass

            if area_found:
                total_area += area

    return total_area
