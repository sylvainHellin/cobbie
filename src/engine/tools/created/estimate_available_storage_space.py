import ifcopenshell
import ifcopenshell.util.element
import math
from typing import Dict, Union, List

def estimate_available_storage_space(model_path: str) -> Dict[str, Union[float, str, List[Dict]]]:
    """
    Estimate available storage space in a BIM model.
    
    This function identifies storage-related elements (primarily cabinets) in an IFC model
    and estimates their storage capacity based on dimensional properties. The estimation
    accounts for the fact that storage space availability depends on many factors beyond
    just room area, including the presence of storage furniture.
    
    Assumptions:
    - Storage elements are primarily represented as IfcFurnishingElement entities
    - Storage capacity is estimated based on cabinet dimensions from PSet_Revit_Type_Dimensions
    - Cabinet depth is estimated when not explicitly provided
    - Storage efficiency factor accounts for unusable space and accessibility
    
    Args:
        model_path (str): Path to the IFC model file
        
    Returns:
        Dict containing:
        - estimated_storage_volume: Total estimated storage volume in cubic meters
        - confidence_level: Confidence level of the estimation ("low", "medium", "high")
        - storage_elements: List of identified storage elements with details
        - methodology: Description of the estimation approach
        - limitations: Important limitations of the estimation
    """
    try:
        # Load the IFC model
        model = ifcopenshell.open(model_path)
        
        # Find storage-related furnishing elements (cabinets, shelves, etc.)
        furnishing_elements = model.by_type("IfcFurnishingElement")
        
        # Filter for storage-related elements based on name patterns
        storage_elements = []
        for element in furnishing_elements:
            name = element.Name or ""
            if any(keyword in name.upper() for keyword in ['CABINET', 'SHELF', 'STORAGE']):
                storage_elements.append(element)
        
        # Calculate estimated storage volume
        total_volume = 0.0
        detailed_elements = []
        
        for element in storage_elements:
            name = element.Name or "Unnamed"
            psets = ifcopenshell.util.element.get_psets(element)
            
            # Extract dimensions from property sets
            length = None
 # Initialize as None
            width = None
            height = None
            
            # Look for dimensions in various possible property sets
            dimension_pset = None
            for pset_name in ['PSet_Revit_Type_Dimensions', 'PSet_Revit_Dimensions', 'Dimensions']:
                if pset_name in psets:
                    dimension_pset = psets[pset_name]
                    break
            
            if dimension_pset:
                # Extract dimensions (values might be in mm, need to convert to meters)
                for prop_name, prop_value in dimension_pset.items():
                    if isinstance(prop_value, (int, float)):
                        # Convert from mm to meters if the value is large (likely in mm)
                        value_in_meters = prop_value / 1000.0 if abs(prop_value) > 100 else prop_value
                        
                        if 'LENGTH' in prop_name.upper() or prop_name.upper() == 'L':
                            length = value_in_meters
                        elif 'WIDTH' in prop_name.upper() or prop_name.upper() == 'W':
                            width = value_in_meters
                        elif 'HEIGHT' in prop_name.upper() or prop_name.upper() == 'H':
                            height = value_in_meters
                        elif 'DEPTH' in prop_name.upper():
                            # Treat depth as width for our calculations
                            width = value_in_meters
            
            # Estimate missing dimensions if we have some
            if length and not width:
                # Assume standard cabinet depth of 600mm for base cabinets, 300mm for upper cabinets
                if 'BASE' in name.upper():
                    width = 0.6
                else:
                    width = 0.3
            
            if width and not length:
                # Assume standard cabinet depth
                if 'BASE' in name.upper():
                    length = 0.6
                else:
                    length = 0.3
            
            # Calculate volume if we have sufficient dimensions
            volume = 0.0
            if length and width and height:
                # Apply a storage efficiency factor (accounting for unusable space, shelves, etc.)
                efficiency_factor = 0.7
                volume = length * width * height * efficiency_factor
                total_volume += volume
            
            detailed_elements.append({
                "element_name": name,
                "type": element.is_a(),
                "length_m": length,
                "width_m": width,
                "height_m": height,
                "estimated_volume_m3": volume
            })
        
        # Determine confidence level based on number of elements found
        if len(storage_elements) == 0:
            confidence = "low"
        elif len(storage_elements) < 10:
            confidence = "medium"
        else:
            confidence = "high"
        
        return {
            "estimated_storage_volume": round(total_volume, 2),
            "confidence_level": confidence,
            "storage_elements": detailed_elements,
            "methodology": "Storage space estimated by identifying storage furniture (cabinets, shelves) and calculating volume based on dimensional properties. An efficiency factor accounts for unusable space.",
            "limitations": "Estimation assumes standard cabinet depths when not explicitly provided. Does not account for storage furniture not modeled as IfcFurnishingElement or without dimensional properties. Actual storage capacity depends on organization and usage patterns."
        }
        
    except Exception as e:
        return {
            "estimated_storage_volume": 0.0,
            "confidence_level": "low",
            "storage_elements": [],
            "methodology": "Storage space estimation based on identifying storage furniture and calculating volume from dimensional properties.",
            "limitations": f"Function execution failed: {str(e)}. The model may not contain identifiable storage elements or required property sets.",
            "error": str(e)
        }