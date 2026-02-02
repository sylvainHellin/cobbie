import ifcopenshell
import ifcopenshell.util.element
import ifcopenshell.util.placement
from typing import List, Dict, Any

def get_building_storey_heights(
    model: ifcopenshell.file,
    sort_by_elevation: bool = True,
    include_psets: bool = False,
    extract_height_properties: bool = False
) -> List[Dict[str, Any]]:
    """
    Retrieves building storeys (IfcBuildingStorey), sorts them by elevation, 
    and calculates floor-to-floor heights.

    Args:
        model: The IFC model instance.
        sort_by_elevation: If True (default), sorts storeys from lowest to highest elevation.
        include_psets: If True, includes property set data for each storey. 
                       Defaults to False.
        extract_height_properties: If True, extracts Height, NetHeight, and GrossHeight from 
                                   the BaseQuantities property set (QTO) and adds them as top-level keys.
                                   Defaults to False.

    Returns:
        A list of dictionaries where each dictionary represents a storey.
        Keys include: 'id', 'name', 'long_name', 'elevation' (float), 
        'height_to_next' (float or None), and optionally 'psets'.
        If extract_height_properties is True, also includes 'height', 'net_height', 'gross_height'.
        'height_to_next' represents the floor-to-floor height to the subsequent storey 
        in the sorted list.

    Example:
        >>> model = ifcopenshell.open('building.ifc')
        >>> storeys = get_building_storey_heights(model, extract_height_properties=True)
        >>> for storey in storeys:
        ...     print(f"{storey['name']}: Elev {storey['elevation']}m, Height {storey['height']}m")
    """
    # Validate input
    if model is None:
        return []
    
    # Get all IfcBuildingStorey elements
    storeys = model.by_type('IfcBuildingStorey')
    
    if not storeys:
        return []
    
    result = []
    skipped = 0
    
    for storey in storeys:
        try:
            # Get elevation using utility function for robustness
            elevation = ifcopenshell.util.placement.get_storey_elevation(storey)
            
            storey_data = {
                'id': storey.id(),
                'name': getattr(storey, 'Name', None),
                'long_name': getattr(storey, 'LongName', None),
                'elevation': float(elevation),
                'height_to_next': None
            }
            
            # Include property sets if requested
            if include_psets:
                try:
                    psets = ifcopenshell.util.element.get_psets(storey, psets_only=True)
                    storey_data['psets'] = psets
                except Exception:
                    storey_data['psets'] = {}
            
            # Extract specific height properties if requested
            if extract_height_properties:
                try:
                    # BaseQuantities is a Quantity Set (QTO), so we use qtos_only=True to get quantities
                    qtos = ifcopenshell.util.element.get_psets(storey, qtos_only=True)
                    base_quantities = qtos.get('BaseQuantities', {})
                    
                    storey_data['height'] = base_quantities.get('Height')
                    storey_data['net_height'] = base_quantities.get('NetHeight')
                    storey_data['gross_height'] = base_quantities.get('GrossHeight')
                    
                except Exception:
                    # Handle cases where qtos cannot be retrieved or keys are missing
                    storey_data['height'] = None
                    storey_data['net_height'] = None
                    storey_data['gross_height'] = None
            
            result.append(storey_data)
            
        except (AttributeError, RuntimeError) as e:
            skipped += 1
            continue
    
    if skipped > 0:
        print(f"Warning: Skipped {skipped} storey elements due to missing data")
    
    # Sort by elevation if requested
    if sort_by_elevation:
        result.sort(key=lambda x: x['elevation'])
    
    # Calculate height_to_next for each storey (except the last one)
    for i in range(len(result) - 1):
        result[i]['height_to_next'] = result[i + 1]['elevation'] - result[i]['elevation']
    
    return result