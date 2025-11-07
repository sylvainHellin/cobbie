import ifcopenshell
import ifcopenshell.util.element
import ifcopenshell.util.selector
from typing import List, Dict, Any, Union, Optional

def analyze_building_envelope_properties_by_space(
    ifc_file: ifcopenshell.file,
    space_identifier: Union[str, int],
    envelope_element_types: List[str] = ['IfcWall', 'IfcDoor', 'IfcWindow'],
    envelope_filter_properties: Dict[str, Any] = {'IsExternal': True},
    target_properties: List[str] = ['ThermalTransmittance', 'FireRating'],
    group_by_property: bool = True
) -> Dict[str, Any]:
    """
    Analyzes building envelope properties (thermal, acoustic, fire, etc.) for elements associated with a specific space.
    
    This function handles the common pattern where spatial boundaries are not properly defined by:
    1) Finding the target space and its level
    2) Locating envelope elements on that level
    3) Filtering by envelope properties (IsExternal, etc.)
    4) Extracting specified technical properties
    5) Returning aggregated results
    
    Args:
        ifc_file: Loaded IFC model (ifcopenshell.file)
        space_identifier: Name, LongName, or ID of target space (e.g., 'Master Bedroom', '206', 209)
        envelope_element_types: List of IFC element types to analyze (default: ['IfcWall', 'IfcDoor', 'IfcWindow'])
        envelope_filter_properties: Dict of property filters (default: {'IsExternal': True})
        target_properties: List of property names to extract (e.g., ['ThermalTransmittance', 'FireRating'])
        group_by_property: Whether to group results by property values (default: True)
    
    Returns:
        Dict containing:
        - space_info: Information about the target space and its level
        - envelope_elements: List of envelope elements found with their properties
        - property_summary: Aggregated results grouped by property values
        - analysis_summary: Summary of findings and any data gaps
    
    Example:
        >>> model = ifcopenshell.open('building.ifc')
        >>> result = analyze_building_envelope_properties_by_space(
        ...     model, 'Master Bedroom', 
        ...     target_properties=['ThermalTransmittance']
        ... )
        >>> print(result['property_summary'])
    """
    
    try:
        # Initialize result structure
        result = {
            'space_info': {},
            'envelope_elements': [],
            'property_summary': {},
            'analysis_summary': {}
        }
        
        # Step 1: Find the target space
        target_space = None
        
        if isinstance(space_identifier, int):
            # Try to find by ID
            try:
                target_space = ifc_file.by_id(space_identifier)
                if not target_space.is_a('IfcSpace'):
                    target_space = None
            except:
                pass
        
        if target_space is None:
            # Try to find by name or LongName
            for space in ifc_file.by_type('IfcSpace'):
                if (space.Name == space_identifier or 
                    (space.LongName and space.LongName == space_identifier)):
                    target_space = space
                    break
        
        if target_space is None:
            result['analysis_summary']['error'] = f"Space '{space_identifier}' not found"
            return result
        
        # Store space information
        result['space_info'] = {
            'id': target_space.id(),
            'name': target_space.Name,
            'long_name': target_space.LongName,
            'object_type': target_space.ObjectType
        }
        
        # Step 2: Find the level/building storey containing the space
        space_container = None
        
        # Try get_container first
        try:
            space_container = ifcopenshell.util.element.get_container(target_space)
        except:
            pass
        
        # If that doesn't work, try Decomposes relationship
        if not space_container or not space_container.is_a('IfcBuildingStorey'):
            for rel in target_space.Decomposes:
                if rel.is_a('IfcRelAggregates'):
                    parent = rel.RelatingObject
                    if parent.is_a('IfcBuildingStorey'):
                        space_container = parent
                        break
        
        if not space_container or not space_container.is_a('IfcBuildingStorey'):
            result['analysis_summary']['error'] = f"Space '{space_identifier}' is not contained in a building storey"
            return result
        
        result['space_info']['level'] = {
            'id': space_container.id(),
            'name': space_container.Name,
            'object_type': space_container.ObjectType
        }
        
        # Step 3: Find all envelope elements on the same level
        level_elements = ifcopenshell.util.element.get_decomposition(space_container)
        
        # Filter by element types
        envelope_elements = []
        for element in level_elements:
            if element.is_a() in envelope_element_types:
                envelope_elements.append(element)
        
        # Step 4: Filter by envelope properties and extract target properties
        filtered_elements = []
        
        for element in envelope_elements:
            # Get all property sets for the element
            psets = ifcopenshell.util.element.get_psets(element)
            
            # Check if element matches filter properties
            matches_filter = True
            for filter_prop, filter_value in envelope_filter_properties.items():
                prop_found = False
                for pset_name, pset_data in psets.items():
                    if filter_prop in pset_data:
                        prop_found = True
                        if pset_data[filter_prop] != filter_value:
                            matches_filter = False
                            break
                if not prop_found:
                    matches_filter = False
                    break
                if not matches_filter:
                    break
            
            if matches_filter:
                # Extract target properties
                element_data = {
                    'id': element.id(),
                    'name': element.Name,
                    'type': element.is_a(),
                    'object_type': element.ObjectType,
                    'properties': {}
                }
                
                for target_prop in target_properties:
                    prop_value = None
                    for pset_name, pset_data in psets.items():
                        if target_prop in pset_data:
                            prop_value = pset_data[target_prop]
                            break
                    element_data['properties'][target_prop] = prop_value
                
                filtered_elements.append(element_data)
        
        result['envelope_elements'] = filtered_elements
        
        # Step 5: Group and summarize results
        if group_by_property and filtered_elements:
            property_groups = {}
            
            for element in filtered_elements:
                for prop_name, prop_value in element['properties'].items():
                    if prop_value is not None:
                        if prop_name not in property_groups:
                            property_groups[prop_name] = {}
                        if prop_value not in property_groups[prop_name]:
                            property_groups[prop_name][prop_value] = []
                        property_groups[prop_name][prop_value].append({
                            'id': element['id'],
                            'name': element['name'],
                            'type': element['type']
                        })
            
            result['property_summary'] = property_groups
        
        # Create analysis summary
        result['analysis_summary'] = {
            'total_envelope_elements_found': len(envelope_elements),
            'elements_matching_filters': len(filtered_elements),
            'properties_analyzed': target_properties,
            'data_gaps': []
        }
        
        # Check for data gaps
        for element in filtered_elements:
            missing_props = [prop for prop, value in element['properties'].items() if value is None]
            if missing_props:
                result['analysis_summary']['data_gaps'].append({
                    'element_id': element['id'],
                    'element_name': element['name'],
                    'missing_properties': missing_props
                })
        
        return result
        
    except Exception as e:
        return {
            'space_info': {},
            'envelope_elements': [],
            'property_summary': {},
            'analysis_summary': {'error': f'Analysis failed: {str(e)}'}
        }