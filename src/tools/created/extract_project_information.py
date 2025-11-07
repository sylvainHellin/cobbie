import ifcopenshell
import ifcopenshell.util.element
from typing import Dict, List, Optional, Any, Union

def extract_project_information(
    ifc_file: ifcopenshell.file,
    include_property_sets: bool = True,
    include_coordinates: bool = True,
    include_address: bool = True
) -> Dict[str, Any]:
    """
    Extracts comprehensive project information and location data from an IFC model by analyzing the project hierarchy (IfcProject, IfcSite, IfcBuilding elements).
    
    This function provides a unified interface for accessing project names, descriptions, geographic coordinates,
    building addresses, and relevant property sets. It handles the common pattern of navigating the IFC project
    structure and extracting metadata that answers questions about project identity, location, and basic building
    characteristics.
    
    Args:
        ifc_file (ifcopenshell.file): Loaded IFC model
        include_property_sets (bool, default=True): Whether to extract property sets from project elements
        include_coordinates (bool, default=True): Whether to extract geographic coordinates from site
        include_address (bool, default=True): Whether to extract building address information
    
    Returns:
        Dict containing project information with keys: 'project', 'site', 'building', and optionally 'property_sets'
    
    Example:
        >>> import ifcopenshell
        >>> model = ifcopenshell.open('building.ifc')
        >>> info = extract_project_information(model)
        >>> print(info['project']['name'])
    """
    result = {
        'project': {},
        'site': {},
        'building': {}
    }
    
    if include_property_sets:
        result['property_sets'] = {}
    
    try:
        # Extract project information
        projects = ifc_file.by_type('IfcProject')
        if projects:
            project = projects[0]
            result['project'] = {
                'id': project.id(),
                'name': getattr(project, 'Name', None),
                'description': getattr(project, 'Description', None),
                'long_name': getattr(project, 'LongName', None),
                'object_type': getattr(project, 'ObjectType', None)
            }
            
            if include_property_sets:
                try:
                    psets = ifcopenshell.util.element.get_psets(project)
                    if psets:
                        result['property_sets']['project'] = psets
                except Exception:
                    pass
        
        # Extract site information
        sites = ifc_file.by_type('IfcSite')
        if sites:
            site = sites[0]
            site_info = {
                'id': site.id(),
                'name': getattr(site, 'Name', None),
                'description': getattr(site, 'Description', None),
                'long_name': getattr(site, 'LongName', None),
                'object_type': getattr(site, 'ObjectType', None)
            }
            
            # Extract coordinates if requested
            if include_coordinates:
                try:
                    if hasattr(site, 'RefLatitude') and site.RefLatitude:
                        site_info['ref_latitude'] = site.RefLatitude
                    if hasattr(site, 'RefLongitude') and site.RefLongitude:
                        site_info['ref_longitude'] = site.RefLongitude
                    if hasattr(site, 'RefElevation') and site.RefElevation:
                        site_info['ref_elevation'] = site.RefElevation
                except Exception:
                    pass
            
            result['site'] = site_info
            
            if include_property_sets:
                try:
                    psets = ifcopenshell.util.element.get_psets(site)
                    if psets:
                        result['property_sets']['site'] = psets
                except Exception:
                    pass
        
        # Extract building information
        buildings = ifc_file.by_type('IfcBuilding')
        if buildings:
            building = buildings[0]
            building_info = {
                'id': building.id(),
                'name': getattr(building, 'Name', None),
                'description': getattr(building, 'Description', None),
                'long_name': getattr(building, 'LongName', None),
                'object_type': getattr(building, 'ObjectType', None)
            }
            
            # Extract address information if requested
            if include_address:
                try:
                    if hasattr(building, 'BuildingAddress') and building.BuildingAddress:
                        address = building.BuildingAddress
                        address_info = {}
                        
                        if hasattr(address, 'AddressLines') and address.AddressLines:
                            address_info['address_lines'] = list(address.AddressLines)
                        if hasattr(address, 'PostalCode') and address.PostalCode:
                            address_info['postal_code'] = address.PostalCode
                        if hasattr(address, 'Town') and address.Town:
                            address_info['town'] = address.Town
                        if hasattr(address, 'Country') and address.Country:
                            address_info['country'] = address.Country
                        if hasattr(address, 'Region') and address.Region:
                            address_info['region'] = address.Region
                        
                        if address_info:
                            building_info['address'] = address_info
                except Exception:
                    pass
            
            result['building'] = building_info
            
            if include_property_sets:
                try:
                    psets = ifcopenshell.util.element.get_psets(building)
                    if psets:
                        result['property_sets']['building'] = psets
                except Exception:
                    pass
    
    except Exception as e:
        # Add error information to result
        result['error'] = str(e)
    
    return result