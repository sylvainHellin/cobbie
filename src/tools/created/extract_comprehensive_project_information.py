import ifcopenshell
import ifcopenshell.util.element
from typing import Dict, Any, Optional, List, Union

def extract_comprehensive_project_information(
    ifc_file: ifcopenshell.file,
    include_file_metadata: bool = True,
    include_project_info: bool = True,
    include_site_info: bool = True,
    include_building_info: bool = True,
    include_properties: bool = True
) -> Dict[str, Any]:
    """
    Extracts comprehensive project information from an IFC model including file metadata,
    project details, site/location information, and building information.
    
    Args:
        ifc_file: Loaded IFC model (ifcopenshell.file)
        include_file_metadata: Boolean to include file header metadata (default: True)
        include_project_info: Boolean to include IfcProject details (default: True)
        include_site_info: Boolean to include IfcSite location data (default: True)
        include_building_info: Boolean to include IfcBuilding details (default: True)
        include_properties: Boolean to include property sets for project/site/building (default: True)
    
    Returns:
        Dict containing structured project information with keys:
        - 'file_metadata': File header information (if included)
        - 'project': Project details from IfcProject elements
        - 'site': Site and location information from IfcSite elements
        - 'building': Building information from IfcBuilding elements
        - 'summary': High-level project overview
    
    Example:
        >>> import ifcopenshell
        >>> model = ifcopenshell.open('model.ifc')
        >>> info = extract_comprehensive_project_information(model)
        >>> print(info['summary']['project_name'])
    """
    
    result: Dict[str, Any] = {
        'file_metadata': {},
        'project': {},
        'site': {},
        'building': {},
        'summary': {}
    }
    
    try:
        # Extract file metadata
        if include_file_metadata:
            try:
                # File description
                file_desc = ifc_file.get_file_description()
                if file_desc:
                    result['file_metadata']['file_description'] = {
                        'description': file_desc.description,
                        'implementation_level': file_desc.implementation_level
                    }
                
                # File name
                file_name = ifc_file.get_file_name()
                if file_name:
                    result['file_metadata']['file_name'] = {
                        'name': file_name.name,
                        'time_stamp': file_name.time_stamp,
                        'author': file_name.author,
                        'organization': file_name.organization,
                        'preprocessor_version': file_name.preprocessor_version,
                        'originating_system': file_name.originating_system,
                        'authorization': file_name.authorization
                    }
                
                # Schema
                file_schema = ifc_file.get_file_schema()
                if file_schema:
                    result['file_metadata']['schema'] = {
                        'identifiers': file_schema.schema_identifiers
                    }
                    
            except Exception as e:
                result['file_metadata']['error'] = f"Failed to extract file metadata: {str(e)}"
        
        # Extract project information
        if include_project_info:
            try:
                projects = ifc_file.by_type('IfcProject')
                if projects:
                    project = projects[0]
                    project_info = {
                        'name': project.Name,
                        'description': project.Description,
                        'global_id': project.GlobalId,
                        'properties': {}
                    }
                    
                    # Extract project properties
                    if include_properties and hasattr(project, 'IsDefinedBy'):
                        try:
                            psets = ifcopenshell.util.element.get_psets(project)
                            project_info['properties'] = psets
                        except:
                            # Fallback to manual property extraction
                            if hasattr(project, 'IsDefinedBy'):
                                for rel in project.IsDefinedBy:
                                    if hasattr(rel, 'RelatingPropertyDefinition'):
                                        prop_def = rel.RelatingPropertyDefinition
                                        if hasattr(prop_def, 'HasProperties'):
                                            for prop in prop_def.HasProperties:
                                                if hasattr(prop, 'Name') and hasattr(prop, 'NominalValue'):
                                                    project_info['properties'][prop.Name] = prop.NominalValue.wrappedValue if prop.NominalValue else None
                    
                    result['project'] = project_info
                    
            except Exception as e:
                result['project']['error'] = f"Failed to extract project info: {str(e)}"
        
        # Extract site information
        if include_site_info:
            try:
                sites = ifc_file.by_type('IfcSite')
                if sites:
                    site = sites[0]
                    site_info = {
                        'name': site.Name,
                        'description': site.Description,
                        'global_id': site.GlobalId,
                        'location': {},
                        'address': {},
                        'properties': {}
                    }
                    
                    # Geographic coordinates
                    if hasattr(site, 'RefLatitude') and site.RefLatitude:
                        site_info['location']['latitude'] = site.RefLatitude
                    if hasattr(site, 'RefLongitude') and site.RefLongitude:
                        site_info['location']['longitude'] = site.RefLongitude
                    if hasattr(site, 'RefElevation') and site.RefElevation:
                        site_info['location']['elevation'] = site.RefElevation
                    
                    # Address information
                    if hasattr(site, 'Address') and site.Address:
                        addr = site.Address
                        address_info = {}
                        if hasattr(addr, 'AddressLines') and addr.AddressLines:
                            address_info['address_lines'] = list(addr.AddressLines)
                        if hasattr(addr, 'PostalCode') and addr.PostalCode:
                            address_info['postal_code'] = addr.PostalCode
                        if hasattr(addr, 'Town') and addr.Town:
                            address_info['town'] = addr.Town
                        if hasattr(addr, 'Country') and addr.Country:
                            address_info['country'] = addr.Country
                        site_info['address'] = address_info
                    
                    # Extract site properties
                    if include_properties:
                        try:
                            psets = ifcopenshell.util.element.get_psets(site)
                            site_info['properties'] = psets
                        except:
                            pass
                    
                    result['site'] = site_info
                    
            except Exception as e:
                result['site']['error'] = f"Failed to extract site info: {str(e)}"
        
        # Extract building information
        if include_building_info:
            try:
                buildings = ifc_file.by_type('IfcBuilding')
                if buildings:
                    building = buildings[0]
                    building_info = {
                        'name': building.Name,
                        'description': building.Description,
                        'global_id': building.GlobalId,
                        'address': {},
                        'properties': {}
                    }
                    
                    # Building address
                    if hasattr(building, 'BuildingAddress') and building.BuildingAddress:
                        addr = building.BuildingAddress
                        address_info = {}
                        if hasattr(addr, 'AddressLines') and addr.AddressLines:
                            address_info['address_lines'] = list(addr.AddressLines)
                        if hasattr(addr, 'PostalCode') and addr.PostalCode:
                            address_info['postal_code'] = addr.PostalCode
                        if hasattr(addr, 'Town') and addr.Town:
                            address_info['town'] = addr.Town
                        if hasattr(addr, 'Country') and addr.Country:
                            address_info['country'] = addr.Country
                        building_info['address'] = address_info
                    
                    # Extract building properties
                    if include_properties:
                        try:
                            psets = ifcopenshell.util.element.get_psets(building)
                            building_info['properties'] = psets
                        except:
                            pass
                    
                    result['building'] = building_info
                    
            except Exception as e:
                result['building']['error'] = f"Failed to extract building info: {str(e)}"
        
        # Create summary
        summary = {}
        if result['project'].get('name'):
            summary['project_name'] = result['project']['name']
        if result['project'].get('description'):
            summary['project_description'] = result['project']['description']
        if result['building'].get('name'):
            summary['building_name'] = result['building']['name']
        if result['site'].get('name'):
            summary['site_name'] = result['site']['name']
        if result['site'].get('location'):
            summary['location'] = result['site']['location']
        if result['file_metadata'].get('file_name', {}).get('originating_system'):
            summary['authoring_system'] = result['file_metadata']['file_name']['originating_system']
        
        result['summary'] = summary
        
    except Exception as e:
        result['error'] = f"General error extracting project information: {str(e)}"
    
    return result