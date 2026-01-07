import ifcopenshell
from typing import Any, Dict, List, Optional

def get_project_overview(
    model: ifcopenshell.file, 
    include_storeys: bool = True, 
    include_quantities: bool = True
) -> Dict[str, Any]:
    """
    Retrieves a high-level overview of the project, site, and building.

    This function aggregates metadata from IfcProject, IfcSite, IfcBuilding, 
    and IfcBuildingStorey entities into a single structured dictionary.

    Args:
        model (ifcopenshell.file): The opened IFC model.
        include_storeys (bool): If True (default), includes a list of storeys 
                                 with names and elevations.
        include_quantities (bool): If True (default), attempts to extract 
                                   quantities (e.g., GrossFloorArea) from 
                                   the building entity.

    Returns:
        Dict[str, Any]: A dictionary containing:
            - 'project': {Name, LongName}
            - 'site': {Name, Address: {Town, Region, Country}, Coordinates: {Lat, Long}}
            - 'building': {Name, LongName, Description}
            - 'storeys': {count, list: [{Name, Elevation}]}
            - 'quantities': {quantity_name: value, ...}

    Example usage:
        >>> import ifcopenshell
        >>> model = ifcopenshell.open('path/to/model.ifc')
        >>> overview = get_project_overview(model)
        >>> print(overview['project']['Name'])
    """
    result: Dict[str, Any] = {
        'project': {},
        'site': {},
        'building': {},
        'storeys': {'count': 0, 'list': []},
        'quantities': {}
    }

    # Helper to safely get attributes
    def get_attr(entity, attr_name):
        return getattr(entity, attr_name, None)

    # 1. Project Information
    try:
        projects = model.by_type('IfcProject')
        if projects:
            proj = projects[0]
            result['project']['Name'] = get_attr(proj, 'Name')
            result['project']['LongName'] = get_attr(proj, 'LongName')
    except Exception:
        pass

    # 2. Site Information
    try:
        sites = model.by_type('IfcSite')
        if sites:
            site = sites[0]
            result['site']['Name'] = get_attr(site, 'Name')
            
            # Address
            addr_data: Dict[str, Optional[str]] = {'Town': None, 'Region': None, 'Country': None}
            if hasattr(site, 'SiteAddress') and site.SiteAddress:
                addr = site.SiteAddress
                addr_data['Town'] = get_attr(addr, 'Town')
                addr_data['Region'] = get_attr(addr, 'Region')
                addr_data['Country'] = get_attr(addr, 'Country')
            result['site']['Address'] = addr_data

            # Coordinates
            coords: Dict[str, Optional[Any]] = {'Lat': None, 'Long': None}
            if hasattr(site, 'RefLatitude'):
                coords['Lat'] = site.RefLatitude
            if hasattr(site, 'RefLongitude'):
                coords['Long'] = site.RefLongitude
            result['site']['Coordinates'] = coords
    except Exception:
        pass

    # 3. Building Information
    building = None
    try:
        buildings = model.by_type('IfcBuilding')
        if buildings:
            building = buildings[0]
            result['building']['Name'] = get_attr(building, 'Name')
            result['building']['LongName'] = get_attr(building, 'LongName')
            result['building']['Description'] = get_attr(building, 'Description')
    except Exception:
        pass

    # 4. Storeys
    if include_storeys:
        try:
            storeys = model.by_type('IfcBuildingStorey')
            result['storeys']['count'] = len(storeys)
            storey_list: List[Dict[str, Any]] = []
            for s in storeys:
                storey_list.append({
                    'Name': get_attr(s, 'Name'),
                    'Elevation': get_attr(s, 'Elevation')
                })
            result['storeys']['list'] = storey_list
        except Exception:
            pass

    # 5. Quantities
    if include_quantities and building:
        try:
            if hasattr(building, 'IsDefinedBy'):
                for rel in building.IsDefinedBy:
                    if hasattr(rel, 'RelatingPropertyDefinition'):
                        prop_def = rel.RelatingPropertyDefinition
                        if prop_def.is_a('IfcElementQuantity'):
                            for q in prop_def.Quantities:
                                qname = get_attr(q, 'Name')
                                qval = None
                                # Extract value based on quantity type
                                if hasattr(q, 'AreaValue'): qval = q.AreaValue
                                elif hasattr(q, 'VolumeValue'): qval = q.VolumeValue
                                elif hasattr(q, 'LengthValue'): qval = q.LengthValue
                                elif hasattr(q, 'CountValue'): qval = q.CountValue
                                elif hasattr(q, 'WeightValue'): qval = q.WeightValue
                                
                                if qname:
                                    result['quantities'][qname] = qval
        except Exception:
            pass

    return result