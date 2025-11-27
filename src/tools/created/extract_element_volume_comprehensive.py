import ifcopenshell
import ifcopenshell.util.element
import ifcopenshell.geom
from typing import List, Dict, Any, Optional, Union
import math

def extract_element_volume_comprehensive(
    ifc_file: ifcopenshell.file,
    element_type: str,
    predefined_type_filter: Optional[str] = None,
    property_sets: Optional[List[str]] = None,
    use_geometric_fallback: bool = True,
    include_details: bool = False,
    aggregation: str = 'sum'
) -> Dict[str, Any]:
    """
    Extracts volume data from IFC elements using a comprehensive multi-strategy approach.
    
    This function handles the common challenge of volume extraction where data might be
    stored in various property sets or require geometric calculation. It implements a
    systematic workflow: 1) Discovers elements by type and optional filtering criteria,
    2) Attempts property-based volume extraction from multiple common property sets,
    3) Falls back to geometric volume calculation if property data is unavailable,
    4) Provides detailed reporting about data sources and extraction success/failure.
    
    Args:
        ifc_file: Loaded IFC model (ifcopenshell.file)
        element_type: IFC element type string (e.g., 'IfcSlab', 'IfcWall')
        predefined_type_filter: Optional predefined type to filter elements (e.g., 'FLOOR', 'BASESLAB')
        property_sets: Optional list of property sets to check for volume (defaults to common quantity sets)
        use_geometric_fallback: Boolean to enable geometric volume calculation (default: True)
        include_details: Boolean to include detailed element-by-element results (default: False)
        aggregation: Aggregation method ('sum', 'average', 'count', 'min', 'max') (default: 'sum')
    
    Returns:
        Dict containing:
        - total_volume: Total extracted volume (0 if none found)
        - volume_source: How volume was obtained ('property_based', 'geometric', 'none')
        - element_count: Number of elements processed
        - elements_with_volume: Number of elements with volume data
        - property_sets_checked: List of property sets that were examined
        - geometric_details: Information about geometric processing (if applicable)
        - element_details: Optional detailed results for each element
    
    Example:
        >>> ifc_file = ifcopenshell.open('model.ifc')
        >>> result = extract_element_volume_comprehensive(
        ...     ifc_file=ifc_file,
        ...     element_type='IfcSlab',
        ...     predefined_type_filter='FLOOR',
        ...     include_details=True
        ... )
        >>> print(f"Total volume: {result['total_volume']} m³")
    """
    
    # Default property sets to check for volume
    if property_sets is None:
        property_sets = [
            'BaseQuantities',
            'Qto_SlabBaseQuantities',
            'Qto_WallBaseQuantities',
            'Qto_BeamBaseQuantities',
            'Qto_ColumnBaseQuantities',
            'Qto_FootingBaseQuantities'
        ]
    
    # Common volume property names to check
    volume_properties = ['Volume', 'GrossVolume', 'NetVolume', 'NetFloorArea', 'GrossFloorArea']
    
    # Initialize result structure
    result = {
        'total_volume': 0.0,
        'volume_source': 'none',
        'element_count': 0,
        'elements_with_volume': 0,
        'property_sets_checked': property_sets.copy(),
        'geometric_details': {},
        'element_details': [] if include_details else None
    }
    
    # Get elements by type
    try:
        elements = ifc_file.by_type(element_type)
        result['element_count'] = len(elements)
        
        # Filter by predefined type if specified
        if predefined_type_filter:
            elements = [elem for elem in elements 
                       if hasattr(elem, 'PredefinedType') and elem.PredefinedType == predefined_type_filter]
            result['element_count'] = len(elements)
        
        if not elements:
            return result
            
    except Exception as e:
        result['error'] = f"Error retrieving elements: {str(e)}"
        return result
    
    # Try property-based volume extraction
    property_volumes = []
    elements_without_property_volume = []
    
    for element in elements:
        element_volume = None
        element_detail = {'id': element.id(), 'name': getattr(element, 'Name', 'N/A')}
        
        try:
            # Get all property sets (quantities only)
            psets = ifcopenshell.util.element.get_psets(element, qtos_only=True)
            
            # Check each property set for volume
            for pset_name in property_sets:
                if pset_name in psets:
                    pset_data = psets[pset_name]
                    for vol_prop in volume_properties:
                        if vol_prop in pset_data:
                            element_volume = float(pset_data[vol_prop])
                            element_detail['volume_source'] = f'property_based.{pset_name}.{vol_prop}'
                            element_detail['volume'] = element_volume
                            break
                    if element_volume is not None:
                        break
            
            if element_volume is not None:
                property_volumes.append(element_volume)
            else:
                elements_without_property_volume.append(element)
                element_detail['volume_source'] = 'none'
                element_detail['volume'] = 0.0
                
        except Exception as e:
            elements_without_property_volume.append(element)
            element_detail['error'] = str(e)
            element_detail['volume_source'] = 'error'
            element_detail['volume'] = 0.0
        
        if include_details:
            result['element_details'].append(element_detail)
    
    # If we found property-based volumes, use them
    if property_volumes:
        result['volume_source'] = 'property_based'
        result['elements_with_volume'] = len(property_volumes)
        
        # Aggregate volumes
        if aggregation == 'sum':
            result['total_volume'] = sum(property_volumes)
        elif aggregation == 'average':
            result['total_volume'] = sum(property_volumes) / len(property_volumes) if property_volumes else 0
        elif aggregation == 'count':
            result['total_volume'] = len(property_volumes)
        elif aggregation == 'min':
            result['total_volume'] = min(property_volumes) if property_volumes else 0
        elif aggregation == 'max':
            result['total_volume'] = max(property_volumes) if property_volumes else 0
        
        return result
    
    # If no property volumes and geometric fallback is enabled, try geometric calculation
    if use_geometric_fallback and elements_without_property_volume:
        result['volume_source'] = 'geometric'
        geometric_volumes = []
        
        try:
            settings = ifcopenshell.geom.settings()
            settings.set(settings.DISABLE_OPENING_SUBTRACTIONS, False)
            
            for element in elements_without_property_volume:
                try:
                    shape = ifcopenshell.geom.create_shape(settings, element)
                    geometry = shape.geometry
                    
                    # Check if geometry has direct volume
                    if hasattr(geometry, 'volume'):
                        volume = geometry.volume
                        geometric_volumes.append(volume)
                        
                        if include_details:
                            for detail in result['element_details']:
                                if detail['id'] == element.id():
                                    detail['volume_source'] = 'geometric.direct'
                                    detail['volume'] = volume
                                    break
                    else:
                        # No direct volume available - note this but don't calculate complex mesh volume
                        if include_details:
                            for detail in result['element_details']:
                                if detail['id'] == element.id():
                                    detail['volume_source'] = 'geometric.no_direct_volume'
                                    detail['geometry_info'] = {
                                        'vertices': len(geometry.verts) // 3,
                                        'faces': len(geometry.faces)
                                    }
                                    break
                        
                except Exception as e:
                    if include_details:
                        for detail in result['element_details']:
                            if detail['id'] == element.id():
                                detail['geometric_error'] = str(e)
                                break
            
            result['geometric_details'] = {
                'elements_processed': len(elements_without_property_volume),
                'volumes_found': len(geometric_volumes),
                'direct_volume_available': len(geometric_volumes) > 0
            }
            
            if geometric_volumes:
                result['elements_with_volume'] = len(geometric_volumes)
                
                # Aggregate geometric volumes
                if aggregation == 'sum':
                    result['total_volume'] = sum(geometric_volumes)
                elif aggregation == 'average':
                    result['total_volume'] = sum(geometric_volumes) / len(geometric_volumes) if geometric_volumes else 0
                elif aggregation == 'count':
                    result['total_volume'] = len(geometric_volumes)
                elif aggregation == 'min':
                    result['total_volume'] = min(geometric_volumes) if geometric_volumes else 0
                elif aggregation == 'max':
                    result['total_volume'] = max(geometric_volumes) if geometric_volumes else 0
            else:
                result['volume_source'] = 'none'
                
        except Exception as e:
            result['geometric_error'] = str(e)
            result['volume_source'] = 'none'
    
    return result