import ifcopenshell
import ifcopenshell.util.element
from typing import List, Dict, Any, Optional

def count_elements_by_spatial_container(
    ifc_file: ifcopenshell.file,
    element_types: List[str],
    spatial_container_type: str = 'IfcBuildingStorey',
    include_unassigned: bool = True,
    sort_levels_by_elevation: bool = True,
    include_totals: bool = True
) -> Dict[str, Any]:
    """
    Counts IFC elements of specified types and groups them by their spatial container.
    
    This function analyzes spatial distribution of elements by examining 
    spatial containment relationships to determine which building 
    storey each element belongs to. It handles unassigned elements gracefully 
    and provides comprehensive counts with totals.
    
    Args:
        ifc_file: Loaded IFC model (ifcopenshell.file)
        element_types: List of IFC element type strings to count
        spatial_container_type: Type of spatial container to group by (default: 'IfcBuildingStorey')
        include_unassigned: Whether to include elements without spatial container assignment (default: True)
        sort_levels_by_elevation: Whether to sort building levels by elevation (default: True)
        include_totals: Whether to include total counts per level and overall (default: True)
    
    Returns:
        Dict with:
        - 'elements_by_container': Dict mapping container names to element type counts
        - 'container_info': List of container details (name, elevation, etc.)
        - 'summary': Overall statistics including total elements, assigned/unassigned counts
        - 'unassigned_elements': Counts of unassigned elements by type (if include_unassigned=True)
    
    Example:
        >>> import ifcopenshell
        >>> model = ifcopenshell.open('model.ifc')
        >>> mep_types = ['IfcFlowTerminal', 'IfcFlowSegment', 'IfcFlowFitting']
        >>> result = count_elements_by_spatial_container(model, mep_types)
        >>> print(result['elements_by_container']['Level 1'])
    """
    try:
        # Initialize result structures
        elements_by_container: Dict[str, Dict[str, int]] = {}
        container_info: List[Dict[str, Any]] = []
        unassigned_elements: Dict[str, int] = {}
        
        # Get all spatial containers of the specified type
        containers = ifc_file.by_type(spatial_container_type)
        
        # Build container info list
        for container in containers:
            info = {
                'name': container.Name or f'Unnamed_{container.id()}',
                'id': container.id(),
                'type': container.is_a(),
                'elevation': getattr(container, 'Elevation', None)
            }
            container_info.append(info)
        
        # Sort containers by elevation if requested
        if sort_levels_by_elevation and spatial_container_type == 'IfcBuildingStorey':
            container_info.sort(key=lambda x: x['elevation'] if x['elevation'] is not None else float('-inf'))
        
        # Initialize container dictionaries
        for container in container_info:
            elements_by_container[container['name']] = {}
        
        # Process each element type and count by container
        for element_type in element_types:
            try:
                elements = ifc_file.by_type(element_type)
                
                for element in elements:
                    # Use the proper API to get the spatial container
                    container = ifcopenshell.util.element.get_container(element)
                    
                    if container and container.is_a(spatial_container_type):
                        # Element has a valid spatial container
                        container_name = container.Name or f'Unnamed_{container.id()}'
                        
                        # Initialize container dict if needed
                        if container_name not in elements_by_container:
                            elements_by_container[container_name] = {}
                        
                        # Initialize element type count if needed
                        if element_type not in elements_by_container[container_name]:
                            elements_by_container[container_name][element_type] = 0
                        
                        # Increment count
                        elements_by_container[container_name][element_type] += 1
                        
                    elif include_unassigned:
                        # Element without spatial container assignment
                        if element_type not in unassigned_elements:
                            unassigned_elements[element_type] = 0
                        unassigned_elements[element_type] += 1
                        
            except Exception as e:
                # Skip invalid element types (e.g., IfcUnitaryEquipment in IFC2X3)
                continue
        
        # Calculate summary statistics
        total_assigned = sum(
            sum(counts.values()) for counts in elements_by_container.values()
        )
        total_unassigned = sum(unassigned_elements.values()) if include_unassigned else 0
        total_elements = total_assigned + total_unassigned
        
        summary = {
            'total_elements': total_elements,
            'total_assigned': total_assigned,
            'total_unassigned': total_unassigned,
            'num_containers': len(container_info),
            'element_types_analyzed': element_types
        }
        
        # Build result dictionary
        result: Dict[str, Any] = {
            'elements_by_container': elements_by_container,
            'container_info': container_info,
            'summary': summary
        }
        
        if include_unassigned:
            result['unassigned_elements'] = unassigned_elements
        
        return result
        
    except Exception as e:
        raise RuntimeError(f"Error counting elements by spatial container: {str(e)}")