
import ifcopenshell
import ifcopenshell.util.element
import ifcopenshell.util.shape
import ifcopenshell.geom
from typing import List, Dict, Any

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
    - Keywords are matched case-insensitively against the IfcSpace's Name and Description.
      Keyword matching within property set values is also attempted.
    - The IFC model is assumed to be exported with standard IfcSpace definitions
      and potentially common property sets like 'Pset_SpaceCommon'.
    - Geometry calculation requires IfcOpenShell to be built with OpenCascade support.

    :param ifc_file_path: Path to the IFC file.
    :param function_keywords: A list of keywords to filter spaces by.
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
        # Check if the space's name or description contains any of the keywords
        name_match = space.Name and any(keyword in space.Name.lower() for keyword in lower_keywords)
        description_match = space.Description and any(keyword in space.Description.lower() for keyword in lower_keywords)

        # Check for keywords within property set values
        property_match = False
        # Get all property sets and quantities for the space
        all_properties = ifcopenshell.util.element.get_psets(space)
        for pset_name, properties in all_properties.items():
            for prop_name, prop_value in properties.items():
                # Check if the property value is a string, int, or float and contains a keyword
                if isinstance(prop_value, (str, int, float)):
                    if any(keyword in str(prop_value).lower() for keyword in lower_keywords):
                        property_match = True
                        break
            if property_match:
                break

        if name_match or description_match or property_match:
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
