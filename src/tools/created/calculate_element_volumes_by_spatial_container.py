import ifcopenshell
import ifcopenshell.util.element
import ifcopenshell.util.unit
import ifcopenshell.geom
import math
from typing import List, Dict, Any, Optional, Union

def calculate_element_volumes_by_spatial_container(
    ifc_file: ifcopenshell.file,
    element_type: str,
    subtype_filter: Optional[str] = None,
    spatial_container_type: str = 'IfcBuildingStorey',
    volume_property_names: List[str] = ['volume', 'volumen', 'volum'],
    include_geometry_fallback: bool = True,
    include_individual_elements: bool = True,
    sort_by_volume: bool = True,
    calculation_method_preference: str = 'auto',
    include_debug_info: bool = False,
    volume_unit_conversion: Optional[float] = None
) -> Dict[str, Any]:
    """
    Calculates volumes of IFC elements grouped by their spatial containers with enhanced control.
    
    This function analyzes IFC elements of a specified type, determines their spatial containers,
    and calculates volumes either from property sets or geometric representations. It supports both
    property-based and geometry-based volume calculations, making it robust for different BIM models.
    
    Args:
        ifc_file: Loaded IFC model (ifcopenshell.file)
        element_type: IFC element type to analyze (e.g., 'IfcSlab', 'IfcWall')
        subtype_filter: Optional filter for PredefinedType (e.g., 'FLOOR' for slabs)
        spatial_container_type: Type of spatial container to group by (default: 'IfcBuildingStorey')
        volume_property_names: List of property names to check for volume data
        include_geometry_fallback: Whether to calculate from geometry when properties missing
        include_individual_elements: Whether to include individual element details
        sort_by_volume: Whether to sort results by volume
        calculation_method_preference: Strategy for volume calculation ('property_first', 'geometry_first', 
                                      'property_only', 'geometry_only', 'auto')
        include_debug_info: Whether to include detailed breakdown of calculation methods
        volume_unit_conversion: Optional conversion factor for volume units (None = no conversion)
    
    Returns:
        Dict containing:
        - 'by_container': Dict mapping container names to volume data
        - 'total_volume': Total volume of all analyzed elements
        - 'total_elements': Total number of elements processed
        - 'calculation_method': 'properties', 'geometry', or 'mixed'
        - 'containers': List of container information
        - 'debug_info': Debug information if include_debug_info=True
    
    Example:
        >>> ifc_file = ifcopenshell.open('model.ifc')
        >>> result = calculate_element_volumes_by_spatial_container(
        ...     ifc_file, 'IfcSlab', subtype_filter='FLOOR',
        ...     calculation_method_preference='property_first',
        ...     include_debug_info=True
        ... )
        >>> print(f"Total volume: {result['total_volume']:.2f} m³")
    """
    
    # Validate calculation method preference
    valid_methods = ['property_first', 'geometry_first', 'property_only', 'geometry_only', 'auto']
    if calculation_method_preference not in valid_methods:
        raise ValueError(f"calculation_method_preference must be one of {valid_methods}")
    
    # Initialize result structure
    result = {
        'by_container': {},
        'total_volume': 0.0,
        'total_elements': 0,
        'calculation_method': 'none',
        'containers': []
    }
    
    # Add debug info structure if requested
    if include_debug_info:
        result['debug_info'] = {
            'elements_by_method': {'properties': [], 'geometry': [], 'none': [], 'error': []},
            'method_counts': {'properties': 0, 'geometry': 0, 'none': 0, 'error': 0},
            'unit_conversion_applied': False,
            'unit_conversion_factor': None,
            'length_unit_scale': None
        }
    
    # Get elements of specified type
    try:
        elements = ifc_file.by_type(element_type)
    except Exception as e:
        raise ValueError(f"Invalid element type '{element_type}': {e}")
    
    # Filter by subtype if specified
    if subtype_filter:
        elements = [elem for elem in elements 
                   if hasattr(elem, 'PredefinedType') and elem.PredefinedType == subtype_filter]
    
    result['total_elements'] = len(elements)
    
    if not elements:
        return result
    
    # Handle unit conversion - only apply if explicitly provided
    length_unit_scale = 1.0
    volume_unit_scale = 1.0
    
    if volume_unit_conversion is not None:
        # Custom conversion factor provided
        volume_unit_scale = volume_unit_conversion
        if include_debug_info:
            result['debug_info']['unit_conversion_applied'] = True
            result['debug_info']['unit_conversion_factor'] = volume_unit_scale
    else:
        # No conversion by default - property and geometry volumes are already in correct units
        try:
            length_unit_scale = ifcopenshell.util.unit.calculate_unit_scale(ifc_file)
            if include_debug_info:
                result['debug_info']['length_unit_scale'] = length_unit_scale
                result['debug_info']['unit_conversion_factor'] = 1.0  # No conversion applied
                result['debug_info']['unit_conversion_applied'] = False
        except Exception:
            length_unit_scale = 1.0
    
    # Initialize geometry settings if needed
    geometry_settings = None
    if include_geometry_fallback or calculation_method_preference in ['geometry_first', 'geometry_only']:
        geometry_settings = ifcopenshell.geom.settings()
        geometry_settings.set(geometry_settings.USE_WORLD_COORDS, True)
        geometry_settings.set(geometry_settings.DISABLE_OPENING_SUBTRACTIONS, False)
    
    # Process each element
    for element in elements:
        # Find spatial container
        container_name = "Unassigned"
        container = ifcopenshell.util.element.get_container(element)
        
        if container and container.is_a() == spatial_container_type:
            container_name = container.Name if container.Name else "Unnamed"
        
        # Initialize container entry if needed
        if container_name not in result['by_container']:
            result['by_container'][container_name] = {
                'elements': [],
                'total_volume': 0.0,
                'element_count': 0,
                'container_info': None
            }
        
        # Calculate volume based on preference
        volume = 0.0
        volume_source = 'none'
        
        # Try property-based calculation
        property_volume = 0.0
        try:
            psets = ifcopenshell.util.element.get_psets(element)
            for pset_name, pset_data in psets.items():
                if isinstance(pset_data, dict):
                    for prop_name, prop_value in pset_data.items():
                        if prop_name.lower() in [name.lower() for name in volume_property_names]:
                            if isinstance(prop_value, (int, float)):
                                property_volume = float(prop_value)
                                break
                    if property_volume > 0:
                        break
        except Exception:
            property_volume = 0.0
        
        # Try geometry-based calculation
        geometry_volume = 0.0
        if geometry_settings:
            try:
                shape = ifcopenshell.geom.create_shape(geometry_settings, element)
                geometry = shape.geometry
                
                # Calculate volume using signed tetrahedron method
                vertices = geometry.verts
                faces = geometry.faces
                
                # Group vertices into triples
                verts = [(vertices[i], vertices[i+1], vertices[i+2]) 
                        for i in range(0, len(vertices), 3)]
                
                # Group faces into triangles
                triangles = []
                for i in range(0, len(faces), 3):
                    if i+2 < len(faces):
                        triangles.append([faces[i], faces[i+1], faces[i+2]])
                
                # Calculate volume
                calc_volume = 0.0
                for triangle in triangles:
                    if len(triangle) == 3:
                        v0, v1, v2 = verts[triangle[0]], verts[triangle[1]], verts[triangle[2]]
                        signed_volume = (v0[0] * (v1[1] * v2[2] - v1[2] * v2[1]) -
                                       v0[1] * (v1[0] * v2[2] - v1[2] * v2[0]) +
                                       v0[2] * (v1[0] * v2[1] - v1[1] * v2[0])) / 6.0
                        calc_volume += signed_volume
                
                geometry_volume = abs(calc_volume)
                # Apply unit conversion only if explicitly requested
                if volume_unit_scale != 1.0:
                    geometry_volume = geometry_volume * volume_unit_scale
                    
            except Exception:
                geometry_volume = 0.0
        
        # Apply calculation method preference
        if calculation_method_preference == 'property_first':
            if property_volume > 0:
                volume = property_volume
                volume_source = 'properties'
            elif geometry_volume > 0:
                volume = geometry_volume
                volume_source = 'geometry'
        elif calculation_method_preference == 'geometry_first':
            if geometry_volume > 0:
                volume = geometry_volume
                volume_source = 'geometry'
            elif property_volume > 0:
                volume = property_volume
                volume_source = 'properties'
        elif calculation_method_preference == 'property_only':
            volume = property_volume
            volume_source = 'properties' if property_volume > 0 else 'none'
        elif calculation_method_preference == 'geometry_only':
            volume = geometry_volume
            volume_source = 'geometry' if geometry_volume > 0 else 'none'
        else:  # auto
            if property_volume > 0:
                volume = property_volume
                volume_source = 'properties'
            elif geometry_volume > 0:
                volume = geometry_volume
                volume_source = 'geometry'
        
        # Apply unit conversion to property volumes only if explicitly requested
        if volume_source == 'properties' and volume_unit_scale != 1.0:
            volume = volume * volume_unit_scale
        
        # Update calculation method tracking
        if volume_source == 'properties':
            if result['calculation_method'] == 'none':
                result['calculation_method'] = 'properties'
            elif result['calculation_method'] == 'geometry':
                result['calculation_method'] = 'mixed'
        elif volume_source == 'geometry':
            if result['calculation_method'] == 'none':
                result['calculation_method'] = 'geometry'
            elif result['calculation_method'] == 'properties':
                result['calculation_method'] = 'mixed'
        
        # Add element data to container
        element_data = {
            'id': element.id(),
            'name': element.Name if element.Name else f"Unnamed {element_type}",
            'volume': volume,
            'volume_source': volume_source
        }
        
        if include_individual_elements:
            result['by_container'][container_name]['elements'].append(element_data)
        
        # Update debug info if requested
        if include_debug_info:
            result['debug_info']['elements_by_method'][volume_source].append(element_data)
            result['debug_info']['method_counts'][volume_source] += 1
        
        result['by_container'][container_name]['total_volume'] += volume
        result['by_container'][container_name]['element_count'] += 1
        result['total_volume'] += volume
        
        # Store container info
        if container and result['by_container'][container_name]['container_info'] is None:
            result['by_container'][container_name]['container_info'] = {
                'id': container.id(),
                'name': container.Name,
                'type': container.is_a()
            }
    
    # Sort containers by volume if requested
    if sort_by_volume:
        sorted_containers = dict(sorted(
            result['by_container'].items(),
            key=lambda x: x[1]['total_volume'],
            reverse=True
        ))
        result['by_container'] = sorted_containers
    
    # Sort individual elements within each container
    if include_individual_elements and sort_by_volume:
        for container_data in result['by_container'].values():
            container_data['elements'].sort(key=lambda x: x['volume'], reverse=True)
    
    # Create containers list
    result['containers'] = [
        {
            'name': name,
            'total_volume': data['total_volume'],
            'element_count': data['element_count'],
            'info': data['container_info']
        }
        for name, data in result['by_container'].items()
    ]
    
    return result