import ifcopenshell
import math
from typing import List, Dict, Any, Optional, Literal


def calculate_aggregated_volume_from_geometry(
    model: ifcopenshell.file,
    elements: Optional[List[ifcopenshell.entity_instance]] = None,
    element_type: Optional[str] = None,
    aggregation: Literal['sum', 'avg', 'min', 'max'] = 'sum',
    include_details: bool = False
) -> Dict[str, Any]:
    """
    Calculates the aggregated volume of IFC elements based on their geometric 
    representations (IfcExtrudedAreaSolid) when explicit volume properties are 
    missing in Property Sets.

    This function handles the extraction of SweptArea and Depth from geometry 
    items and computes area for standard profiles (IfcRectangleProfileDef) and 
    arbitrary closed profiles (IfcArbitraryClosedProfileDef with IfcPolyline 
    using the Shoelace formula).

    Args:
        model: The IFC model instance.
        elements: A list of elements to calculate volume for. If None, 
                 `element_type` must be provided.
        element_type: The IFC entity type to retrieve (e.g., 'IfcSlab', 'IfcWall'). 
                      Used if `elements` is None.
        aggregation: The aggregation method to apply ('sum', 'avg', 'min', 'max'). 
                     Defaults to 'sum'.
        include_details: If True, returns details of individual element volumes. 
                         Defaults to False.

    Returns:
        A dictionary containing:
            - 'value' (float): The aggregated volume.
            - 'count' (int): The number of successfully processed elements.
            - 'element_details' (Optional[List[Dict[str, Any]]]): List of details 
              (id, name, volume) if requested, otherwise None.

    Example:
        >>> import ifcopenshell
        >>> model = ifcopenshell.open('model.ifc')
        >>> # Calculate total volume of all floor slabs
        >>> result = calculate_aggregated_volume_from_geometry(
        ...     model, 
        ...     element_type='IfcSlab'
        ... )
        >>> print(f"Total Volume: {result['value']}")
    """
    # Resolve elements list
    if elements is None:
        if element_type is None:
            raise ValueError("Either 'elements' or 'element_type' must be provided.")
        elements = model.by_type(element_type)
    
    if not elements:
        return {'value': 0.0, 'count': 0, 'element_details': [] if include_details else None}

    volumes = []
    element_details = []
    skipped = 0

    for elem in elements:
        vol = 0.0
        processed = False
        
        try:
            # Check for Representation
            if not hasattr(elem, 'Representation') or not elem.Representation:
                skipped += 1
                continue
            
            rep = elem.Representation
            # Iterate through representations (usually 'Body')
            for shape_rep in rep.Representations:
                if shape_rep.is_a('IfcShapeRepresentation'):
                    for item in shape_rep.Items:
                        if item.is_a('IfcExtrudedAreaSolid'):
                            depth = item.Depth
                            swept_area = item.SweptArea
                            area_mm2 = 0.0
                            
                            # Handle Rectangle Profile
                            if swept_area.is_a('IfcRectangleProfileDef'):
                                x_dim = getattr(swept_area, 'XDim', 0.0)
                                y_dim = getattr(swept_area, 'YDim', 0.0)
                                area_mm2 = x_dim * y_dim
                            
                            # Handle Arbitrary Closed Profile (e.g., Polylines)
                            elif swept_area.is_a('IfcArbitraryClosedProfileDef'):
                                outer_curve = swept_area.OuterCurve
                                if outer_curve and outer_curve.is_a('IfcPolyline'):
                                    points_list = []
                                    # Extract points from IfcPolyline
                                    if hasattr(outer_curve, 'Points'):
                                        for pt in outer_curve.Points:
                                            coords = getattr(pt, 'Coordinates', [0.0, 0.0])
                                            if len(coords) >= 2:
                                                points_list.append((coords[0], coords[1]))
                                    
                                    # Shoelace Formula for area
                                    if len(points_list) > 2:
                                        area_sum = 0.0
                                        n = len(points_list)
                                        for i in range(n):
                                            x_j, y_j = points_list[i]
                                            x_k, y_k = points_list[(i + 1) % n]
                                            area_sum += (x_j * y_k) - (x_k * y_j)
                                        area_mm2 = abs(area_sum) / 2.0
                            
                            # If area was calculated, compute volume
                            if area_mm2 > 0:
                                vol = area_mm2 * depth
                                volumes.append(vol)
                                processed = True
                                if include_details:
                                    element_details.append({
                                        'id': elem.id,
                                        'name': elem.Name,
                                        'volume': vol
                                    })
                                break # Found the solid geometry, break inner loop
                    if processed:
                        break # Break representation loop if processed
            
            if not processed:
                skipped += 1

        except (AttributeError, KeyError, RuntimeError):
            # Skip elements with geometry access issues or unexpected structures
            skipped += 1
            continue

    # Aggregation Logic
    result_value = 0.0
    if volumes:
        if aggregation == 'sum':
            result_value = sum(volumes)
        elif aggregation == 'avg':
            result_value = sum(volumes) / len(volumes)
        elif aggregation == 'min':
            result_value = min(volumes)
        elif aggregation == 'max':
            result_value = max(volumes)
    
    # Warning for skipped elements
    if skipped > 0:
        print(f"Warning: Skipped {skipped} elements due to missing or unsupported geometry.")

    return {
        'value': result_value,
        'count': len(volumes),
        'element_details': element_details if include_details else None
    }