import ifcopenshell
from typing import List, Dict, Any, Optional, Union

def get_element_dimensions_from_geometry(
    model: ifcopenshell.file,
    elements: Optional[List[ifcopenshell.entity_instance]] = None,
    element_type: Optional[str] = None,
    include_details: bool = False,
    aggregation: Optional[str] = None
) -> Dict[str, Any]:
    """
    Calculates dimensional attributes (width, length, height) of IFC elements by extracting 
    bounding box data from geometric representations. This function handles IfcPolygonalFaceSet 
    (mesh geometry) to calculate dimensions when explicit property values are missing.

    Args:
        model: The IFC model instance.
        elements: List of elements to analyze. If None, element_type must be provided.
        element_type: IFC entity type to analyze if elements not provided 
                      (e.g., 'IfcStairFlight', 'IfcBeam').
        include_details: If True, returns individual element results in addition to aggregated values.
        aggregation: Optional aggregation type ('sum', 'avg', 'min', 'max') for dimensions 
                     across all elements. Defaults to returning all values (as lists).

    Returns:
        Dictionary containing:
        - 'count': Number of elements successfully processed.
        - 'skipped': Number of elements skipped due to missing geometry or errors.
        - 'dimensions': Dict with dimension values. 
            If aggregation is specified, contains scalars (e.g., {'width': 1.5}). 
            If aggregation is None, contains lists of values (e.g., {'width': [1.5, 2.0]}).
        - 'elements': List of individual element results (if include_details=True).

    Example:
        >>> result = get_element_dimensions_from_geometry(model, element_type='IfcStairFlight', 
        ...                                               include_details=True, aggregation='avg')
        >>> print(f"Average Width: {result['dimensions']['width']:.2f} m")
        >>> for elem in result['elements']:
        ...     print(f"{elem['name']}: {elem['width']:.2f} m")
    """
    
    # Input Validation
    if elements is None:
        if element_type:
            elements = model.by_type(element_type)
        else:
            return {'count': 0, 'skipped': 0, 'dimensions': {}, 'elements': []}
    
    if not elements:
        return {'count': 0, 'skipped': 0, 'dimensions': {}, 'elements': []}
    
    element_results = []
    skipped = 0
    
    for elem in elements:
        try:
            # Check if element has a representation
            if not hasattr(elem, 'Representation') or not elem.Representation:
                skipped += 1
                continue
            
            # Collect all points from PolygonalFaceSets
            all_xs = []
            all_ys = []
            all_zs = []
            has_geometry = False
            
            rep = elem.Representation
            # Representation attribute is an IfcProductRepresentation, which has Representations list
            if hasattr(rep, 'Representations'):
                for rep_item in rep.Representations:
                    if hasattr(rep_item, 'Items'):
                        for item in rep_item.Items:
                            # We are specifically looking for mesh geometry (PolygonalFaceSet)
                            if item.is_a('IfcPolygonalFaceSet'):
                                coords = item.Coordinates
                                # IfcCartesianPointList3D contains a list of coordinate tuples
                                if hasattr(coords, 'CoordList'):
                                    points = coords.CoordList
                                    for point in points:
                                        all_xs.append(point[0])
                                        all_ys.append(point[1])
                                        all_zs.append(point[2])
                                    has_geometry = True
            
            if not has_geometry:
                skipped += 1
                continue
                
            # Calculate Bounding Box
            x_min, x_max = min(all_xs), max(all_xs)
            y_min, y_max = min(all_ys), max(all_ys)
            z_min, z_max = min(all_zs), max(all_zs)
            
            x_dim = x_max - x_min
            y_dim = y_max - y_min
            z_dim = z_max - z_min
            
            # Determine Width vs Length
            # Convention: Width is smaller horizontal dimension, Length is larger
            width = min(x_dim, y_dim)
            length = max(x_dim, y_dim)
            height = z_dim
            
            element_data = {
                'id': elem.id,
                'name': getattr(elem, 'Name', 'Unknown'),
                'global_id': getattr(elem, 'GlobalId', None),
                'width': width,
                'length': length,
                'height': height
            }
            element_results.append(element_data)
            
        except (AttributeError, IndexError, TypeError) as e:
            # Catch specific errors related to data access structure
            skipped += 1
            continue
            
    # Prepare Dimensions Result
    widths = [r['width'] for r in element_results]
    lengths = [r['length'] for r in element_results]
    heights = [r['height'] for r in element_results]
    
    dims_output: Dict[str, Any] = {}
    
    if aggregation:
        if not widths:
             dims_output = {'width': 0, 'length': 0, 'height': 0}
        elif aggregation == 'sum':
            dims_output = {'width': sum(widths), 'length': sum(lengths), 'height': sum(heights)}
        elif aggregation == 'avg':
            dims_output = {'width': sum(widths)/len(widths), 
                           'length': sum(lengths)/len(lengths), 
                           'height': sum(heights)/len(heights)}
        elif aggregation == 'min':
            dims_output = {'width': min(widths), 'length': min(lengths), 'height': min(heights)}
        elif aggregation == 'max':
            dims_output = {'width': max(widths), 'length': max(lengths), 'height': max(heights)}
        else:
            # Fallback to lists if aggregation string is unknown
            dims_output = {'width': widths, 'length': lengths, 'height': heights}
    else:
        # Default: Return all values as lists
        dims_output = {'width': widths, 'length': lengths, 'height': heights}
    
    return {
        'count': len(element_results),
        'skipped': skipped,
        'dimensions': dims_output,
        'elements': element_results if include_details else []
    }