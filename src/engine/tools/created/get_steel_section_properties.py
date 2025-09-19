import ifcopenshell
import ifcopenshell.util.element
import re
from typing import List, Dict, Optional

def get_steel_section_properties(
    model_path: str,
    element_type: str = None,
    section_pattern: str = None,
    property_filters: dict = None
) -> List[dict]:
    """
    Retrieves standardized properties of steel sections from IFC models.
    
    This function works with IFC models exported from Revit and extracts steel section
    properties from Revit-specific property sets (PSet_Revit_*).
    
    Args:
        model_path (str): Path to the IFC model file
        element_type (str, optional): Specific structural element type to analyze 
            (IfcColumn, IfcBeam, IfcMember). If None, all structural elements are analyzed.
        section_pattern (str, optional): Pattern to filter steel sections by name 
            (e.g., "W150X22.5", "HSS*"). Uses simple string matching or regex.
        property_filters (dict, optional): Dictionary of property name-value pairs 
            to filter elements.
    
    Returns:
        List[dict]: List of dictionaries containing steel section properties:
            - element_name: Name of the structural element
            - element_guid: GlobalId of the element
            - element_type: IFC type of the element
            - section_name: Standard steel section designation
            - section_type: Type of steel section (W-shape, HSS, etc.)
            - nominal_depth: Nominal depth of section (mm)
            - flange_width: Width of flange (mm)
            - web_thickness: Thickness of web (mm)
            - flange_thickness: Thickness of flange (mm)
            - weight_per_meter: Weight per unit length (kg/m)
            - cross_sectional_area: Cross-sectional area (mm²)
            - moment_of_inertia_x: Moment of inertia about x-axis (mm⁴)
            - moment_of_inertia_y: Moment of inertia about y-axis (mm⁴)
            - section_modulus_x: Section modulus about x-axis (mm³)
            - section_modulus_y: Section modulus about y-axis (mm³)
            - property_source: Information about which property sets the data was extracted from
    
    Note:
        This function currently works with Revit-exported IFC models and extracts
        properties from Revit-specific property sets. Standard IFC property sets
        for steel sections are not yet widely implemented in BIM authoring tools.
    """
    
    def _extract_section_info(element, psets: dict) -> dict:
        """
        Extract section information from element property sets.
        
        Args:
            element: IFC element object
            psets (dict): Property sets dictionary from ifcopenshell.util.element.get_psets
            
        Returns:
            dict: Dictionary with section information or None if not a steel section
        """
        # Look for section reference in various property sets
        section_name = None
        section_type = None
        
        # Check common property sets for section reference
        for pset_name, pset_data in psets.items():
            if 'Reference' in pset_data:
                reference = pset_data['Reference']
                if reference and isinstance(reference, str):
                    section_name = reference
                    # Determine section type from reference
                    if ':' in reference:
                        # Handle Revit format like "M_W-Wide Flange:W460X60"
                        parts = reference.split(':')
                        if len(parts) > 1:
                            section_type = parts[1].split('X')[0] if 'X' in parts[1] else parts[1]
                    else:
                        section_type = reference.split('_')[0] if '_' in reference else "Unknown"
                    break
        
        # If no section reference found, check element name
        if not section_name and element.Name:
            section_name = element.Name
            # Try to determine section type from name
            if "W" in element.Name and "X" in element.Name:
                section_type = "W-Shape"
            elif "HSS" in element.Name:
                section_type = "HSS"
            elif "C" in element.Name and element.Name.index("C") == 0:
                section_type = "C-Shape"
            elif "L" in element.Name and element.Name.index("L") == 0:
                section_type = "L-Shape"
            else:
                # Try to extract section type from name
                if ":" in element.Name:
                    parts = element.Name.split(":")
                    for part in parts:
                        if "W" in part and "X" in part:
                            section_type = "W-Shape"
                            break
                        elif "HSS" in part:
                            section_type = "HSS"
                            break
                if not section_type:
                    section_type = "Unknown"
        
        # If still no section info, return None
        if not section_name:
            return None
        
        # Extract dimensional properties from Revit property sets
        nominal_depth = None
        flange_width = None
        web_thickness = None
        flange_thickness = None
        weight_per_meter = None
        cross_sectional_area = None
        moment_of_inertia_x = None
        moment_of_inertia_y = None
        section_modulus_x = None
        section_modulus_y = None
        property_source = []
        
        # Process PSet_Revit_Type_Dimensions
        if 'PSet_Revit_Type_Dimensions' in psets:
            dims = psets['PSet_Revit_Type_Dimensions']
            property_source.append('PSet_Revit_Type_Dimensions')
            
            # Convert from meters to millimeters for dimensional properties
            if 'd' in dims:  # depth
                nominal_depth = dims['d'] * 1000 if dims['d'] else None
            if 'bf' in dims:  # flange width
                flange_width = dims['bf'] * 1000 if dims['bf'] else None
            if 'tw' in dims:  # web thickness
                web_thickness = dims['tw'] * 1000 if dims['tw'] else None
            if 'tf' in dims:  # flange thickness
                flange_thickness = dims['tf'] * 1000 if dims['tf'] else None
        
        # Process PSet_Revit_Type_Structural
        if 'PSet_Revit_Type_Structural' in psets:
            struct = psets['PSet_Revit_Type_Structural']
            property_source.append('PSet_Revit_Type_Structural')
            
            if 'W' in struct:  # weight per unit length (kg/m)
                weight_per_meter = struct['W']
            if 'A' in struct:  # cross-sectional area (m² to mm²)
                cross_sectional_area = struct['A'] * 1000000 if struct['A'] else None
        
        # Process Pset_BeamCommon or similar
        for pset_name, pset_data in psets.items():
            if 'Pset_BeamCommon' in pset_name or 'BeamCommon' in pset_name:
                property_source.append(pset_name)
                if 'Reference' in pset_data and not section_name:
                    section_name = pset_data['Reference']
        
        # Calculate derived properties if we have basic dimensions
        if nominal_depth and flange_width and web_thickness and flange_thickness:
            # Convert to meters for calculations
            d = nominal_depth / 1000
            bf = flange_width / 1000
            tw = web_thickness / 1000
            tf = flange_thickness / 1000
            
            # Calculate moment of inertia (simplified for W-shapes)
            # Ix ≈ (bf * d³ - (bf-tw) * (d-2*tf)³) / 12
            # Iy ≈ (d * bf³ - (d-2*tf) * (bf-tw)³) / 12
            moment_of_inertia_x = ((bf * d**3 - (bf-tw) * (d-2*tf)**3) / 12) * 1000**4
            moment_of_inertia_y = ((d * bf**3 - (d-2*tf) * (bf-tw)**3) / 12) * 1000**4
            
            # Calculate section modulus
            section_modulus_x = moment_of_inertia_x / (d * 1000 / 2) if d > 0 else None
            section_modulus_y = moment_of_inertia_y / (bf * 1000 / 2) if bf > 0 else None
        
        # Create result dictionary
        result = {
            'element_name': element.Name if element.Name else "Unnamed",
            'element_guid': element.GlobalId,
            'element_type': element.is_a(),
            'section_name': section_name,
            'section_type': section_type,
            'nominal_depth': nominal_depth,
            'flange_width': flange_width,
            'web_thickness': web_thickness,
            'flange_thickness': flange_thickness,
            'weight_per_meter': weight_per_meter,
            'cross_sectional_area': cross_sectional_area,
            'moment_of_inertia_x': moment_of_inertia_x,
            'moment_of_inertia_y': moment_of_inertia_y,
            'section_modulus_x': section_modulus_x,
            'section_modulus_y': section_modulus_y,
            'property_source': "; ".join(property_source) if property_source else "None"
        }
        
        return result
    
    # Load the IFC model
    model = ifcopenshell.open(model_path)
    
    # Define structural element types to consider
    structural_element_types = ["IfcBeam", "IfcColumn", "IfcMember"]
    if element_type:
        if element_type in structural_element_types:
            structural_element_types = [element_type]
        else:
            # If specified element_type is not a structural type, return empty list
            return []
    
    # Collect all structural elements
    structural_elements = []
    for elem_type in structural_element_types:
        elements = model.by_type(elem_type)
        structural_elements.extend(elements)
    
    # Process elements and extract properties
    results = []
    
    for element in structural_elements:
        # Check if element matches section pattern filter
        if section_pattern:
            element_name = element.Name if element.Name else ""
            # Handle wildcard pattern matching
            if "*" in section_pattern:
                pattern = section_pattern.replace("*", ".*")
                if not re.search(pattern, element_name):
                    continue
            else:
                # Simple substring matching
                if section_pattern not in element_name:
                    continue
        
        # Get all property sets for the element
        psets = ifcopenshell.util.element.get_psets(element)
        
        # Extract section information
        section_info = _extract_section_info(element, psets)
        
        if section_info:  # Only add if we found section information
            results.append(section_info)
    
    # Apply property filters if provided
    if property_filters and isinstance(property_filters, dict):
        # Simple filtering implementation
        filtered_results = []
        for result in results:
            match = True
            for prop_name, prop_value in property_filters.items():
                if prop_name in result and result[prop_name] != prop_value:
                    match = False
                    break
            if match:
                filtered_results.append(result)
        results = filtered_results
    
    return results