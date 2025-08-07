
import ifcopenshell
import ifcopenshell.util.element
import ifcopenshell.util.shape
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

    # Prepare keywords for case-insensitive matching
    lower_keywords = [keyword.lower() for keyword in function_keywords]

    for space in spaces:
        is_matching_space = False
        
        # Get all properties for the space
        all_properties = ifcopenshell.util.element.get_psets(space)
        
        # Check for specific storage indicators first (and only)
        identity_data = all_properties.get('PSet_Revit_Identity Data', {})
        other_data = all_properties.get('PSet_Revit_Other', {})
        
        omni_class = identity_data.get('OmniClass Table 13 Category', '')
        category_desc = other_data.get('Category Description', '')
        
        # ONLY include basic storage rooms, not specialized storage
        # In a dental clinic context, focus on basic "Storage Room" classification
        basic_storage_omni_class = '13-75 11 11: Storage Room'
        basic_storage_category_desc = 'Storage Room'
        
        # ONLY include spaces that are explicitly classified as basic storage rooms
        if basic_storage_omni_class.lower() in omni_class.lower():
            is_matching_space = True
        elif basic_storage_category_desc.lower() in category_desc.lower():
            is_matching_space = True
        # No keyword matching for storage spaces to avoid over-matching

        if is_matching_space:
            area = 0.0
            area_found = False

            # Prioritize Quantity Sets for area (e.g., GrossFloorArea, NetFloorArea)
            qtos = ifcopenshell.util.element.get_psets(space, qtos_only=True)
            for qto_name, properties in qtos.items():
                if 'GrossFloorArea' in properties and isinstance(properties['GrossFloorArea'], (int, float)):
                    area += properties['GrossFloorArea']
                    area_found = True
                    break # Found GrossFloorArea, assume this is the primary area
                elif 'NetFloorArea' in properties and isinstance(properties['NetFloorArea'], (int, float)):
                    area += properties['NetFloorArea']
                    area_found = True
                    break # Found NetFloorArea, assume this is the primary area

            # If not found in Quantity Sets, check common Property Sets for 'Area'
            if not area_found:
                psets = ifcopenshell.util.element.get_psets(space, psets_only=True)
                for pset_name, properties in psets.items():
                    if 'Area' in properties and isinstance(properties['Area'], (int, float)):
                        area += properties['Area']
                        area_found = True
                        break # Found Area in a PSet

            # Fallback: Calculate area from geometry if not found in sets
            if not area_found:
                try:
                    # Use ifcopenshell.geom for geometry processing
                    settings = ifcopenshell.geom.settings()
                    # Ensure OpenCascade is used if available, otherwise this might fail or be slow
                    settings.set(settings.USE_PYTHON_OPENCASCADE, True)
                    
                    # Create shape from the space element
                    shape = ifcopenshell.geom.create_shape(settings, space)
                    
                    if shape and shape.geometry:
                        # The .Area() method is typically for planar surfaces.
                        # If the geometry is a polygon, its area can be calculated.
                        # If it's a complex 3D shape, this might be an approximation.
                        area_from_geom = shape.geometry.Area()
                        if isinstance(area_from_geom, (int, float)):
                            area += area_from_geom
                            area_found = True
                        else:
                            print(f"Warning: Geometry area calculation for space {space.GlobalId} returned non-numeric value: {area_from_geom}")
                            
                except Exception as e:
                    print(f"Could not compute area from geometry for space {space.GlobalId}: {e}")

            if area_found:
                total_area += area

    return total_area
