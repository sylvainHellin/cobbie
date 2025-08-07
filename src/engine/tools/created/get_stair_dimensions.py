
import ifcopenshell
import ifcopenshell.util.element
from typing import List, Dict, Any, Optional

def get_stair_dimensions(
    ifc_file_path: str,
    stair_identifier: Optional[str] = None,
    dimension_names: Optional[List[str]] = None
) -> List[Dict[str, Any]]:
    """
    Retrieve dimensional properties of stair elements from an IFC model.
    
    Args:
        ifc_file_path (str): Path to the IFC file
        stair_identifier (Optional[str]): Name, GlobalId, or identifier of specific stair to query (if None, return all stairs)
        dimension_names (List[str], optional): Specific dimension names to extract
        
    Returns:
        List[Dict[str, Any]]: List of dictionaries containing stair information:
            - stair_name: Name of the stair element
            - stair_guid: GlobalId of the stair element
            - stair_type: IFC type (IfcStair or IfcStairFlight)
            - dimensions: Dictionary mapping dimension names to their values
            - property_sets: Dictionary of relevant property sets containing dimensional information
    """
    # Load the IFC model
    ifc_file = ifcopenshell.open(ifc_file_path)
    
    # Find all stair elements
    stairs = ifc_file.by_type("IfcStair")
    stair_flights = ifc_file.by_type("IfcStairFlight")
    all_stairs = stairs + stair_flights
    
    # Filter by identifier if provided
    if stair_identifier:
        filtered_stairs = []
        for stair in all_stairs:
            # Check if the identifier matches Name or GlobalId
            if (stair.Name and stair_identifier in stair.Name) or stair.GlobalId == stair_identifier:
                filtered_stairs.append(stair)
        all_stairs = filtered_stairs
    
    # Define the dimensional properties we're interested in
    dimension_mapping = {
        'NumberOfRiser': ['NumberOfRiser', 'Actual Number of Risers', 'Number of Risers'],
        'NumberOfTreads': ['NumberOfTreads', 'Actual Number of Treads', 'Number of Treads'],
        'RiserHeight': ['RiserHeight', 'Actual Riser Height', 'Riser Height'],
        'TreadLength': ['TreadLength', 'Actual Tread Depth', 'Tread Depth', 'Tread Length']
    }
    
    # If specific dimension names are requested, filter the mapping
    if dimension_names:
        filtered_mapping = {}
        for dim_name in dimension_names:
            if dim_name in dimension_mapping:
                filtered_mapping[dim_name] = dimension_mapping[dim_name]
        dimension_mapping = filtered_mapping
    
    results = []
    
    # Process each stair element
    for stair in all_stairs:
        # Get all property sets for this stair
        property_sets = ifcopenshell.util.element.get_psets(stair)
        
        # Identify relevant property sets for dimensions
        relevant_psets = {}
        dimensional_psets = ['Pset_StairCommon', 'Pset_StairFlightCommon', 'PSet_Revit_Dimensions']
        
        for pset_name, pset_data in property_sets.items():
            # Check if this is a dimensional property set
            if any(dim_pset.lower() in pset_name.lower() for dim_pset in dimensional_psets):
                relevant_psets[pset_name] = pset_data
        
        # Extract dimensional properties
        dimensions = {}
        
        # Look for each dimension in the relevant property sets
        for standard_name, possible_names in dimension_mapping.items():
            found = False
            # Search through all relevant property sets for this dimension
            for pset_name, pset_data in relevant_psets.items():
                for name in possible_names:
                    if name in pset_data:
                        dimensions[standard_name] = pset_data[name]
                        found = True
                        break
                if found:
                    break
            # If not found, set to None
            if not found:
                dimensions[standard_name] = None
        
        # Create result entry
        stair_info = {
            'stair_name': stair.Name if stair.Name else "Unnamed",
            'stair_guid': stair.GlobalId,
            'stair_type': stair.is_a(),
            'dimensions': dimensions,
            'property_sets': relevant_psets
        }
        
        results.append(stair_info)
    
    return results
