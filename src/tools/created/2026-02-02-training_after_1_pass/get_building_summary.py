import ifcopenshell
from typing import List, Dict, Optional, Any, Union

def get_building_summary(
    model: ifcopenshell.file,
    include_element_counts: bool = True,
    include_storeys: bool = True,
    include_site: bool = True,
    element_types_to_count: Optional[List[str]] = None
) -> Dict[str, Any]:
    """
    Retrieves a comprehensive summary of an IFC project and building.
    
    This function consolidates multiple common queries into a single call,
    including project metadata, building details, location information,
    vertical structure, and element counts.

    Args:
        model: The IFC model instance
        include_element_counts: If True, includes counts of common building elements.
            Defaults to True.
        include_storeys: If True, includes storey details with names and elevations.
            Defaults to True.
        include_site: If True, includes site/location information. Defaults to True.
        element_types_to_count: Custom list of IFC types to count. If None,
            uses a sensible default list of common building elements.

    Returns:
        Dict containing:
            - 'project': Dict with project Name, LongName, and optionally full metadata
            - 'building': Dict with building Name, LongName, and optionally full metadata
            - 'site': Dict with site details including coordinates (lat/lon),
              elevation, and address (if present)
            - 'storeys': Dict with count, list of storeys with names/elevations,
              and calculated building height
            - 'element_counts': Dict of entity_type -> count mappings
            - 'authoring_info': Dict with schema info from file header

    Example:
        >>> model = ifcopenshell.open('path/to/model.ifc')
        >>> summary = get_building_summary(model)
        >>> print(f"Project: {summary['project']['Name']}")
        >>> print(f"Building height: {summary['storeys']['height_m']}m")
    """
    # Initialize result dictionary
    result: Dict[str, Any] = {
        'project': {},
        'building': {},
        'site': {},
        'storeys': {},
        'element_counts': {},
        'authoring_info': {}
    }
    
    # Default element types to count if not provided
    if element_types_to_count is None:
        element_types_to_count = [
            'IfcBuildingStorey', 'IfcSpace', 'IfcWall', 'IfcSlab',
            'IfcWindow', 'IfcDoor', 'IfcColumn', 'IfcBeam', 'IfcRoof'
        ]
    
    # ========== PROJECT INFORMATION ==========
    projects = model.by_type('IfcProject')
    if projects:
        project = projects[0]
        result['project'] = {
            'Name': getattr(project, 'Name', None),
            'LongName': getattr(project, 'LongName', None),
            'id': project.id()
        }
    else:
        result['project'] = {'error': 'No IfcProject found in model'}
    
    # ========== BUILDING INFORMATION ==========
    buildings = model.by_type('IfcBuilding')
    if buildings:
        building = buildings[0]
        result['building'] = {
            'Name': getattr(building, 'Name', None),
            'LongName': getattr(building, 'LongName', None),
            'id': building.id()
        }
    else:
        result['building'] = {'error': 'No IfcBuilding found in model'}
    
    # ========== SITE/LOCATION INFORMATION ==========
    if include_site:
        sites = model.by_type('IfcSite')
        if sites:
            site = sites[0]
            site_data: Dict[str, Any] = {
                'Name': getattr(site, 'Name', None),
                'LongName': getattr(site, 'LongName', None),
                'id': site.id()
            }
            
            # Get coordinates
            ref_lat = getattr(site, 'RefLatitude', None)
            if ref_lat:
                site_data['latitude'] = ref_lat
                # Format as readable string if tuple
                if isinstance(ref_lat, tuple) and len(ref_lat) >= 3:
                    site_data['latitude_formatted'] = f"{ref_lat[0]}° {ref_lat[1]}' {ref_lat[2]}\""
            
            ref_lon = getattr(site, 'RefLongitude', None)
            if ref_lon:
                site_data['longitude'] = ref_lon
                if isinstance(ref_lon, tuple) and len(ref_lon) >= 3:
                    site_data['longitude_formatted'] = f"{ref_lon[0]}° {ref_lon[1]}' {ref_lon[2]}\""
            
            ref_elev = getattr(site, 'RefElevation', None)
            if ref_elev is not None:
                site_data['elevation'] = ref_elev
            
            # Get address if available
            address_info: Dict[str, Any] = {}
            has_address = False
            if hasattr(site, 'HasAddress') and site.HasAddress:
                for rel in site.HasAddress:
                    addr = rel.Address
                    has_address = True
                    address_info['type'] = addr.is_a()
                    address_info['Town'] = getattr(addr, 'Town', None)
                    address_info['Region'] = getattr(addr, 'Region', None)
                    address_info['Country'] = getattr(addr, 'Country', None)
                    address_info['PostalCode'] = getattr(addr, 'PostalCode', None)
                    address_lines = getattr(addr, 'AddressLines', None)
                    if address_lines:
                        address_info['AddressLines'] = list(address_lines)
            
            site_data['has_address'] = has_address
            if has_address:
                site_data['address'] = address_info
            
            result['site'] = site_data
        else:
            result['site'] = {'error': 'No IfcSite found in model'}
    
    # ========== STOREY INFORMATION ==========
    if include_storeys:
        storeys = model.by_type('IfcBuildingStorey')
        storey_list = []
        elevations = []
        
        for storey in storeys:
            name = getattr(storey, 'Name', 'Unknown')
            elevation = getattr(storey, 'Elevation', None)
            
            storey_data = {
                'Name': name,
                'id': storey.id()
            }
            if elevation is not None:
                storey_data['Elevation'] = elevation
                elevations.append(elevation)
            
            storey_list.append(storey_data)
        
        # Calculate building height from elevations
        height_m = None
        if elevations:
            height_m = max(elevations) - min(elevations)
        
        result['storeys'] = {
            'count': len(storeys),
            'storeys': storey_list,
            'height_m': height_m
        }
    
    # ========== ELEMENT COUNTS ==========
    if include_element_counts:
        counts = {}
        for elem_type in element_types_to_count:
            try:
                count = len(model.by_type(elem_type))
                counts[elem_type] = count
            except Exception:
                counts[elem_type] = 0
        result['element_counts'] = counts
    
    # ========== AUTHORING INFO ==========
    result['authoring_info'] = {
        'schema': model.schema
    }
    
    return result