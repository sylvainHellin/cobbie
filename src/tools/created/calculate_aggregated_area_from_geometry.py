import ifcopenshell
from typing import List, Dict, Any, Optional

def calculate_aggregated_area_from_geometry(
    model: ifcopenshell.file,
    elements: Optional[List[ifcopenshell.entity_instance]] = None,
    element_type: Optional[str] = None,
    aggregation: str = 'none',
    unit_conversion: float = 1000000.0,
    include_details: bool = False
) -> Dict[str, Any]:
    """
    Calculates the area of IFC elements based on their geometric representations.
    
    Extracts the SweptArea from IfcExtrudedAreaSolid geometry items and computes area
    for both standard profiles (IfcRectangleProfileDef) and arbitrary closed profiles
    (IfcArbitraryClosedProfileDef with IfcPolyline using the Shoelace formula).

    Args:
        model: The IFC model instance
        elements: Optional list of elements to analyze. If None, element_type must be provided.
        element_type: IFC type to analyze if elements not provided (e.g., 'IfcSpace', 'IfcSlab')
        aggregation: Aggregation type - 'sum', 'avg', 'min', 'max', or 'none'. 
                    Default 'none' returns individual areas.
        unit_conversion: Divide result by this factor for unit conversion. 
                        Defaults to 1000000.0 (mm² to m²).
        include_details: If True, returns detailed breakdown with element names and IDs.

    Returns:
        Dict with aggregated value and optionally detailed element-by-element results.
        Structure:
        {
            'value': float | None,  # Aggregated value or None if no valid elements
            'unit': str,           # Unit description (e.g., 'm²')
            'count': int,          # Number of elements with valid geometry
            'details': List[Dict]  # Optional: individual element results
        }
        
    Example usage:
        >>> # Calculate total area of all spaces
        >>> result = calculate_aggregated_area_from_geometry(
        ...     model, element_type='IfcSpace', aggregation='sum'
        ... )
        >>> print(f"Total area: {result['value']:.2f} {result['unit']}")
        
        >>> # Get individual space areas
        >>> result = calculate_aggregated_area_from_geometry(
        ...     model, element_type='IfcSpace', include_details=True
        ... )
        >>> for detail in result['details']:
        ...     print(f"{detail['name']}: {detail['area']:.2f} m²")
    """
    # Input validation
    if elements is None:
        if element_type is None:
            raise ValueError("Either 'elements' or 'element_type' must be provided")
        elements = model.by_type(element_type)
    
    if not elements:
        return {
            'value': None,
            'unit': 'm²',
            'count': 0,
            'details': []
        }
    
    # Validate aggregation type
    valid_aggregations = ['sum', 'avg', 'min', 'max', 'none']
    if aggregation not in valid_aggregations:
        raise ValueError(f"Invalid aggregation type. Must be one of: {valid_aggregations}")
    
    def calculate_polygon_area(coords: List[tuple]) -> float:
        """Calculate area of a polygon using the Shoelace formula."""
        if len(coords) < 3:
            return 0.0
        area = 0.0
        n = len(coords)
        for i in range(n):
            j = (i + 1) % n
            area += coords[i][0] * coords[j][1]
            area -= coords[j][0] * coords[i][1]
        return abs(area) / 2.0
    
    def get_profile_from_representation(element: ifcopenshell.entity_instance) -> Optional[List[tuple]]:
        """Extract 2D profile coordinates from IfcExtrudedAreaSolid representation."""
        if not hasattr(element, 'Representation') or not element.Representation:
            return None
        
        rep = element.Representation
        if not hasattr(rep, 'Representations') or not rep.Representations:
            return None
        
        for shape_rep in rep.Representations:
            # Look for 'Body', 'FootPrint', or 'Annotation' representation identifiers
            if hasattr(shape_rep, 'RepresentationIdentifier'):
                identifier = shape_rep.RepresentationIdentifier
                if identifier not in ['Body', 'FootPrint', 'Annotation']:
                    continue
            
            if not hasattr(shape_rep, 'Items') or not shape_rep.Items:
                continue
            
            for item in shape_rep.Items:
                # Check for IfcExtrudedAreaSolid geometry
                if item.is_a('IfcExtrudedAreaSolid'):
                    profile = item.SweptArea
                    if profile.is_a('IfcRectangleProfileDef'):
                        # Return coordinates for rectangle (0,0) to (XDim, YDim)
                        x_dim = getattr(profile, 'XDim', None)
                        y_dim = getattr(profile, 'YDim', None)
                        if x_dim is not None and y_dim is not None:
                            return [(0.0, 0.0), (float(x_dim), 0.0), (float(x_dim), float(y_dim)), (0.0, float(y_dim))]
                    
                    elif profile.is_a('IfcRoundedRectangleProfileDef'):
                        x_dim = getattr(profile, 'XDim', None)
                        y_dim = getattr(profile, 'YDim', None)
                        if x_dim is not None and y_dim is not None:
                            return [(0.0, 0.0), (float(x_dim), 0.0), (float(x_dim), float(y_dim)), (0.0, float(y_dim))]
                    
                    elif profile.is_a('IfcArbitraryClosedProfileDef'):
                        if hasattr(profile, 'OuterCurve') and profile.OuterCurve:
                            curve = profile.OuterCurve
                            if curve.is_a('IfcPolyline') and hasattr(curve, 'Points'):
                                points = []
                                for point in curve.Points:
                                    if hasattr(point, 'Coordinates'):
                                        x = float(point.Coordinates[0])
                                        y = float(point.Coordinates[1])
                                        points.append((x, y))
                                if len(points) >= 3:
                                    return points
        
        return None
    
    # Collect areas from all elements
    areas: List[float] = []
    details: List[Dict[str, Any]] = []
    skipped = 0
    
    for element in elements:
        element_name = getattr(element, 'Name', 'Unnamed') or 'Unnamed'
        element_id = element.id()
        
        try:
            # Get profile coordinates using manual navigation
            coords = get_profile_from_representation(element)
            
            if coords:
                area_mm2 = calculate_polygon_area(coords)
                area_m2 = area_mm2 / unit_conversion
                areas.append(area_m2)
                
                if include_details:
                    details.append({
                        'id': element_id,
                        'name': element_name,
                        'area': round(area_m2, 2)
                    })
            else:
                skipped += 1
                if include_details:
                    details.append({
                        'id': element_id,
                        'name': element_name,
                        'area': None,
                        'error': 'No suitable geometry found'
                    })
        
        except (AttributeError, TypeError, IndexError) as e:
            skipped += 1
            if include_details:
                details.append({
                    'id': element_id,
                    'name': element_name,
                    'area': None,
                    'error': f'Exception: {str(e)}'
                })
    
    # Report skipped elements
    if skipped > 0:
        print(f"Warning: Skipped {skipped} elements (no valid geometry found)")
    
    # Calculate aggregated value
    value: Optional[float] = None
    count = len(areas)
    
    if count > 0:
        if aggregation == 'sum':
            value = sum(areas)
        elif aggregation == 'avg':
            value = sum(areas) / count
        elif aggregation == 'min':
            value = min(areas)
        elif aggregation == 'max':
            value = max(areas)
        elif aggregation == 'none':
            # Return sum for 'none' as a default aggregated value
            value = sum(areas)
    
    return {
        'value': round(value, 2) if value is not None else None,
        'unit': 'm²' if unit_conversion == 1000000.0 else 'unknown',
        'count': count,
        'details': details if include_details else []
    }