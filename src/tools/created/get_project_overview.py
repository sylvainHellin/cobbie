import ifcopenshell
from typing import Any, Dict, List, Optional, Union


def get_project_overview(
    model: ifcopenshell.file,
    include_element_counts: bool = True,
    include_storey_details: bool = True,
    element_types_to_count: Optional[List[str]] = None,
    storey_attributes: Optional[List[str]] = None,
    include_detailed_address: bool = False,
    include_raw_geolocation: bool = False,
    include_floor_heights: bool = False,
    include_global_ids: bool = False
) -> Dict[str, Any]:
    """
    Retrieves a comprehensive overview of project metadata including project name,
    building name, location, basic characteristics, and structural elements.
    
    This function provides a high-level summary of an IFC model, useful for
    context-setting and answering 'what is this project?' questions.
    
    Args:
        model: The loaded IFC model instance
        include_element_counts: Whether to include basic element type counts (default: True)
        include_storey_details: Whether to include detailed storey information (default: True)
        element_types_to_count: Specific IFC types to count. If None, uses default
            building elements like IfcWall, IfcSlab, IfcWindow, IfcDoor, etc.
        storey_attributes: List of IfcBuildingStorey attributes to extract. If None,
            defaults to ['Name', 'Elevation', 'LongName']. These will be stored in
            the result dictionary with the same casing as specified here.
        include_detailed_address: If True, parses IfcSite.SiteAddress to extract
            specific fields (Town, Region, Country, PostalCode, AddressLines, AddressLine1)
            rather than just returning a summary or None. (default: False)
        include_raw_geolocation: If True, includes raw RefLatitude and RefLongitude
            values from IfcSite in the location dictionary. (default: False)
        include_floor_heights: If True, calculates floor-to-floor heights between
            consecutive storeys. Implies include_storey_details=True. Adds a
            'floor_heights' key to the result containing a list of transitions with
            from_storey, to_storey, and height values. (default: False)
        include_global_ids: If True, adds GlobalId fields to project_info, building_info,
            and location/site dicts. (default: False)
    
    Returns:
        A structured dictionary containing:
            - project_info: Project name, description, GlobalId (if requested)
            - building_info: Building name, gross floor area, number of storeys, GlobalId (if requested)
            - location: Site name, GlobalId (if requested), address (or detailed address dict if requested),
              geographic coordinates (if available)
            - storeys: List of storey information dictionaries with specified attributes
            - building_height: Calculated height from lowest to highest storey
            - floor_heights: List of floor-to-floor height transitions (if requested)
            - element_counts: Dictionary of element type counts (if include_element_counts=True)
            - spaces: Number of spaces in the model
    
    Example usage:
        >>> import ifcopenshell
        >>> model = ifcopenshell.open('path/to/model.ifc')
        >>> overview = get_project_overview(model)
        >>> print(overview['project_info']['name'])
        >>> detailed = get_project_overview(model, include_detailed_address=True)
        >>> print(detailed['location']['address']['Town'])
        >>> with_ids = get_project_overview(model, include_global_ids=True)
        >>> print(with_ids['project_info']['global_id'])
        >>> with_heights = get_project_overview(model, include_floor_heights=True)
        >>> for transition in with_heights['floor_heights']:
        ...     print(f"{transition['from_storey']} to {transition['to_storey']}: {transition['height']}m")
    """
    # If floor heights are requested, we need storey details
    if include_floor_heights:
        include_storey_details = True
    
    result: Dict[str, Any] = {
        'project_info': {},
        'building_info': {},
        'location': {},
        'storeys': [],
        'building_height': None,
        'floor_heights': [],
        'element_counts': {},
        'spaces': 0
    }
    
    # ===== PROJECT INFO =====
    projects = model.by_type('IfcProject')
    if projects:
        project = projects[0]
        result['project_info']['name'] = getattr(project, 'Name', None) or 'Unknown'
        result['project_info']['description'] = getattr(project, 'Description', None)
        result['project_info']['long_name'] = getattr(project, 'LongName', None)
        if include_global_ids:
            result['project_info']['global_id'] = getattr(project, 'GlobalId', None)
    else:
        result['project_info']['name'] = 'No IfcProject found'
    
    # ===== BUILDING INFO =====
    buildings = model.by_type('IfcBuilding')
    if buildings:
        building = buildings[0]
        result['building_info']['name'] = getattr(building, 'Name', None) or 'Unknown'
        result['building_info']['description'] = getattr(building, 'Description', None)
        result['building_info']['long_name'] = getattr(building, 'LongName', None)
        result['building_info']['number_of_storeys'] = getattr(building, 'NumberOfStoreys', None)
        if include_global_ids:
            result['building_info']['global_id'] = getattr(building, 'GlobalId', None)
        
        # Extract quantities like GrossFloorArea
        gross_floor_area = None
        try:
            for rel in building.IsDefinedBy:
                if hasattr(rel, 'RelatingPropertyDefinition'):
                    pdef = rel.RelatingPropertyDefinition
                    if hasattr(pdef, 'is_a') and pdef.is_a('IfcElementQuantity'):
                        for qty in pdef.Quantities:
                            if hasattr(qty, 'Name') and qty.Name == 'GrossFloorArea':
                                if hasattr(qty, 'AreaValue'):
                                    gross_floor_area = qty.AreaValue
                                    break
        except (AttributeError, TypeError):
            pass
        result['building_info']['gross_floor_area'] = gross_floor_area
    else:
        result['building_info']['name'] = 'No IfcBuilding found'
    
    # ===== LOCATION INFO =====
    sites = model.by_type('IfcSite')
    if sites:
        site = sites[0]
        result['location']['site_name'] = getattr(site, 'Name', None)
        if include_global_ids:
            result['location']['site_global_id'] = getattr(site, 'GlobalId', None)
        
        # Address information
        address_info: Any = None
        try:
            if hasattr(site, 'SiteAddress') and site.SiteAddress:
                addr = site.SiteAddress
                
                if include_detailed_address:
                    # Extract detailed address fields as a dictionary
                    # Support both IFC2x3 (AddressLines as list) and IFC4 (AddressLine1, etc.)
                    address_info: Dict[str, Any] = {}
                    
                    # Try to get individual address line attributes (IFC4 style)
                    for i in range(1, 4):  # AddressLine1, AddressLine2, AddressLine3
                        line_val = getattr(addr, f'AddressLine{i}', None)
                        if line_val is not None:
                            if f'address_line{i}' not in address_info:
                                address_info[f'address_line{i}'] = []
                            address_info[f'address_line{i}'].append(line_val)
                    
                    # Also try AddressLines (IFC2x3 style - a LIST)
                    address_lines = getattr(addr, 'AddressLines', None)
                    if address_lines is not None:
                        if isinstance(address_lines, tuple):
                            address_info['address_lines'] = list(address_lines)
                        else:
                            address_info['address_lines'] = address_lines
                    
                    # Extract other address fields
                    for attr in ['PostalCode', 'Town', 'Region', 'Country']:
                        val = getattr(addr, attr, None)
                        if val is not None:
                            address_info[attr] = val
                else:
                    # Backward compatible: create a summary string or None
                    town = getattr(addr, 'Town', None)
                    region = getattr(addr, 'Region', None)
                    country = getattr(addr, 'Country', None)
                    parts = [p for p in [town, region, country] if p]
                    if parts:
                        address_info = ', '.join(parts)
        except (AttributeError, TypeError):
            pass
        result['location']['address'] = address_info
        
        # Geographic coordinates
        lat = getattr(site, 'RefLatitude', None)
        lon = getattr(site, 'RefLongitude', None)
        
        if include_raw_geolocation:
            result['location']['latitude'] = lat
            result['location']['longitude'] = lon
            # Add raw values unconditionally when requested
            # Convert tuples to lists for JSON serialization
            if lat is not None:
                result['location']['raw_latitude'] = list(lat) if isinstance(lat, tuple) else lat
            else:
                result['location']['raw_latitude'] = None
            
            if lon is not None:
                result['location']['raw_longitude'] = list(lon) if isinstance(lon, tuple) else lon
            else:
                result['location']['raw_longitude'] = None
        else:
            # Backward compatible: simple values
            result['location']['latitude'] = lat
            result['location']['longitude'] = lon
    else:
        result['location']['site_name'] = 'No IfcSite found'
    
    # ===== STOREY INFO =====
    if include_storey_details:
        # Set default storey attributes to match successful execution pattern
        if storey_attributes is None:
            storey_attributes = ['Name', 'Elevation', 'LongName']
        
        storeys = model.by_type('IfcBuildingStorey')
        storey_list = []
        elevations = []
        
        for storey in storeys:
            storey_info = {}
            for attr in storey_attributes:
                # Get attribute value, default to None if not present
                value = getattr(storey, attr, None)
                # Convert tuples to lists for JSON serialization
                if isinstance(value, tuple):
                    value = list(value)
                storey_info[attr] = value
                
                # Collect elevations for sorting and height calculation
                if attr == 'Elevation' and value is not None:
                    elevations.append(value)
            
            storey_list.append(storey_info)
        
        # Sort storeys by elevation (ascending)
        # Handle None values by treating them as -infinity (putting them at the start)
        storey_list.sort(key=lambda x: x.get('Elevation') if x.get('Elevation') is not None else float('-inf'))
        result['storeys'] = storey_list
        
        # Calculate building height
        if elevations:
            result['building_height'] = max(elevations) - min(elevations)
        
        # Calculate floor-to-floor heights if requested
        if include_floor_heights and len(storey_list) >= 2:
            floor_heights = []
            for i in range(len(storey_list) - 1):
                from_storey = storey_list[i]
                to_storey = storey_list[i + 1]
                
                from_elevation = from_storey.get('Elevation')
                to_elevation = to_storey.get('Elevation')
                
                # Only calculate if both elevations are valid numbers
                if from_elevation is not None and to_elevation is not None:
                    height = to_elevation - from_elevation
                    
                    transition = {
                        'from_storey': from_storey.get('Name', 'Unknown'),
                        'to_storey': to_storey.get('Name', 'Unknown'),
                        'height': round(height, 2)  # Round to 2 decimal places for readability
                    }
                    floor_heights.append(transition)
            
            result['floor_heights'] = floor_heights
    
    # Update building info with actual storey count
    storeys = model.by_type('IfcBuildingStorey')
    result['building_info']['number_of_storeys_detected'] = len(storeys)
    
    # ===== SPACES =====
    spaces = model.by_type('IfcSpace')
    result['spaces'] = len(spaces)
    
    # ===== ELEMENT COUNTS =====
    if include_element_counts:
        if element_types_to_count is None:
            element_types_to_count = [
                'IfcWall', 'IfcWallStandardCase', 'IfcSlab', 'IfcColumn', 'IfcBeam',
                'IfcStair', 'IfcRoof', 'IfcWindow', 'IfcDoor', 'IfcRailing', 'IfcCovering'
            ]
        
        counts: Dict[str, int] = {}
        for elem_type in element_types_to_count:
            count = len(model.by_type(elem_type))
            if count > 0:
                counts[elem_type] = count
        result['element_counts'] = counts
    
    return result