import ifcopenshell
import ifcopenshell.util.element
from typing import Dict, List, Optional, Any, Union

def calculate_total_element_volume(
    ifc_file,
    element_type: str,
    volume_quantity_names: List[str] = ['GrossVolume', 'NetVolume', 'Volume'],
    filter_criteria: Optional[Dict[str, Any]] = None,
    include_breakdown: bool = False,
    categorize_by: Optional[str] = None
) -> Dict[str, Any]:
    """
    Calculates the total volume of specified IFC elements by searching for volume quantities across all quantity sets.
    
    This function handles the common pattern where volume data may be stored in different quantity sets
    (like BaseQuantities, Qto_SlabBaseQuantities) and under different quantity names (GrossVolume, NetVolume, Volume).
    It provides a flexible approach to volume calculation that works across different IFC models and element types.
    
    Args:
        ifc_file: Loaded IFC model (ifcopenshell.file)
        element_type: IFC element type string (e.g., 'IfcSlab', 'IfcWall', 'IfcBeam')
        volume_quantity_names: List of possible volume quantity names to search for
        filter_criteria: Optional dict to filter elements by properties (e.g., {'ObjectType': 'Floor'})
        include_breakdown: Whether to return individual element volumes
        categorize_by: Optional field to categorize results by (e.g., 'ObjectType', 'PredefinedType')
    
    Returns:
        Dict containing:
        - total_volume: Combined total volume (float)
        - element_count: Number of elements processed (int)
        - elements_with_volume: Number of elements that had volume data (int)
        - breakdown: Optional dict with categorized volumes if categorize_by is specified
        - individual_volumes: Optional list of individual element volumes if include_breakdown is True
    
    Example:
        >>> import ifcopenshell
        >>> model = ifcopenshell.open('building.ifc')
        >>> result = calculate_total_element_volume(
        ...     model, 
        ...     'IfcSlab',
        ...     filter_criteria={'ObjectType': 'Floor'},
        ...     include_breakdown=True,
        ...     categorize_by='ObjectType'
        ... )
        >>> print(f"Total volume: {result['total_volume']:.2f} m³")
    """
    try:
        # Get all elements of the specified type
        elements = ifc_file.by_type(element_type)
        
        # Apply filter criteria if provided
        if filter_criteria:
            filtered_elements = []
            for element in elements:
                matches = True
                for attr_name, expected_value in filter_criteria.items():
                    if not hasattr(element, attr_name):
                        matches = False
                        break
                    actual_value = getattr(element, attr_name)
                    if actual_value != expected_value:
                        matches = False
                        break
                if matches:
                    filtered_elements.append(element)
            elements = filtered_elements
        
        total_volume = 0.0
        elements_with_volume = 0
        individual_volumes = []
        categorized_volumes = {}
        
        for element in elements:
            element_volume = 0.0
            
            # Get quantity sets using utility function
            quantity_sets = ifcopenshell.util.element.get_psets(element, qtos_only=True)
            
            # Search for volume in all quantity sets
            for qset_name, quantities in quantity_sets.items():
                for volume_name in volume_quantity_names:
                    if volume_name in quantities:
                        volume_value = quantities[volume_name]
                        if isinstance(volume_value, (int, float)) and volume_value > 0:
                            element_volume = float(volume_value)
                            break
                if element_volume > 0:
                    break
            
            # Add to totals
            if element_volume > 0:
                elements_with_volume += 1
                total_volume += element_volume
            
            # Store individual volume if requested
            if include_breakdown:
                element_info = {
                    'id': element.id,
                    'name': element.Name if hasattr(element, 'Name') else '',
                    'volume': element_volume
                }
                
                # Add categorization field if specified
                if categorize_by and hasattr(element, categorize_by):
                    element_info['category'] = getattr(element, categorize_by)
                
                individual_volumes.append(element_info)
            
            # Categorize by specified field
            if categorize_by and hasattr(element, categorize_by):
                category = getattr(element, categorize_by)
                if category not in categorized_volumes:
                    categorized_volumes[category] = {
                        'volume': 0.0,
                        'count': 0,
                        'with_volume': 0
                    }
                categorized_volumes[category]['count'] += 1
                categorized_volumes[category]['volume'] += element_volume
                if element_volume > 0:
                    categorized_volumes[category]['with_volume'] += 1
        
        # Prepare result
        result = {
            'total_volume': total_volume,
            'element_count': len(elements),
            'elements_with_volume': elements_with_volume
        }
        
        if include_breakdown:
            result['individual_volumes'] = individual_volumes
        
        if categorize_by:
            result['breakdown'] = categorized_volumes
        
        return result
        
    except Exception as e:
        # Return error information
        return {
            'total_volume': 0.0,
            'element_count': 0,
            'elements_with_volume': 0,
            'error': str(e)
        }