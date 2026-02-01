import ifcopenshell
from typing import Union, List, Dict, Any, Optional


def get_model_header_info(
    model: Union[Any, str],
    return_sections: Optional[List[str]] = None,
    include_application_developer: bool = False,
    include_implementation_level: bool = False
) -> Dict[str, Any]:
    """
    Extracts comprehensive metadata from IFC file header including file description,
    file name details, schema identifiers, application information, and organization data.

    Args:
        model: Either a loaded IFC model instance or a file path to an IFC file
        return_sections: Optional list of sections to include ('file_description', 'file_name',
                        'file_schema', 'applications', 'organizations'). If None, returns all sections.
        include_application_developer: If True, includes developer information for each application.
                                        Default: False for backward compatibility.
        include_implementation_level: If True, includes implementation level in file description.
                                      Default: False for backward compatibility.

    Returns:
        Structured header information with keys matching the requested sections:
        - file_description: {'description': List[str], 'implementation_level': str (optional)}
        - file_name: {'name': str, 'time_stamp': str, 'author': tuple, 'organization': tuple,
                      'preprocessor_version': str, 'originating_system': str, 'authorization': str}
        - file_schema: {'schema_identifiers': List[str]}
        - applications: List[Dict] with 'identifier', 'name', 'version', 'developer' (optional)
        - organizations: List[Dict] with 'name', 'description'

    Example:
        >>> model = ifcopenshell.open('model.ifc')
        >>> header_info = get_model_header_info(model, ['file_schema', 'applications'])
        >>> print(header_info['file_schema']['schema_identifiers'])
        ['IFC4']

        >>> # Include developer information
        >>> header_info = get_model_header_info(model, include_application_developer=True)
        >>> for app in header_info['applications']:
        ...     print(f"{app['name']} by {app.get('developer', 'Unknown')}")
    """
    # Validate and load model if path is provided
    if isinstance(model, str):
        try:
            model = ifcopenshell.open(model)
        except Exception as e:
            raise RuntimeError(f"Failed to open IFC file: {e}")
    
    # Verify the loaded object has expected IFC model attributes
    if not hasattr(model, 'header') or not hasattr(model, 'by_type'):
        raise TypeError("model must be either an ifcopenshell model instance or a valid file path")
    
    # Define all valid sections
    all_sections = ['file_description', 'file_name', 'file_schema', 'applications', 'organizations']
    
    # Determine which sections to return
    if return_sections is None:
        sections_to_process = all_sections
    else:
        sections_to_process = [s for s in return_sections if s in all_sections]
        if not sections_to_process:
            return {}
    
    result: Dict[str, Any] = {}
    header = model.header
    
    # Extract file description
    if 'file_description' in sections_to_process:
        try:
            if hasattr(header, 'file_description') and header.file_description:
                desc_data = {'description': list(header.file_description.description)}
                if include_implementation_level:
                    desc_data['implementation_level'] = getattr(
                        header.file_description, 'implementation_level', ''
                    )
                result['file_description'] = desc_data
            else:
                result['file_description'] = {'description': []}
        except AttributeError:
            result['file_description'] = {'description': []}
    
    # Extract file name details
    if 'file_name' in sections_to_process:
        try:
            if hasattr(header, 'file_name') and header.file_name:
                fn = header.file_name
                result['file_name'] = {
                    'name': getattr(fn, 'name', ''),
                    'time_stamp': getattr(fn, 'time_stamp', ''),
                    'author': getattr(fn, 'author', ()),
                    'organization': getattr(fn, 'organization', ()),
                    'preprocessor_version': getattr(fn, 'preprocessor_version', ''),
                    'originating_system': getattr(fn, 'originating_system', ''),
                    'authorization': getattr(fn, 'authorization', '')
                }
            else:
                result['file_name'] = {
                    'name': '', 'time_stamp': '', 'author': (), 'organization': (),
                    'preprocessor_version': '', 'originating_system': '', 'authorization': ''
                }
        except AttributeError:
            result['file_name'] = {
                'name': '', 'time_stamp': '', 'author': (), 'organization': (),
                'preprocessor_version': '', 'originating_system': '', 'authorization': ''
            }
    
    # Extract file schema (modeling standard)
    if 'file_schema' in sections_to_process:
        try:
            if hasattr(header, 'file_schema') and header.file_schema:
                result['file_schema'] = {
                    'schema_identifiers': list(header.file_schema.schema_identifiers)
                }
            else:
                result['file_schema'] = {'schema_identifiers': []}
        except AttributeError:
            result['file_schema'] = {'schema_identifiers': []}
    
    # Extract application information
    if 'applications' in sections_to_process:
        applications = []
        skipped_apps = 0
        try:
            for entity in model.by_type('IfcApplication'):
                try:
                    app_dict = {
                        'identifier': getattr(entity, 'ApplicationIdentifier', ''),
                        'name': getattr(entity, 'ApplicationFullName', ''),
                        'version': getattr(entity, 'Version', '')
                    }
                    
                    if include_application_developer:
                        app_dev = getattr(entity, 'ApplicationDeveloper', None)
                        if app_dev is not None:
                            # Try to get Name attribute safely
                            dev_name = getattr(app_dev, 'Name', None)
                            if dev_name is None:
                                dev_name = str(app_dev)
                            app_dict['developer'] = dev_name
                    
                    applications.append(app_dict)
                except AttributeError:
                    skipped_apps += 1
                    continue
        except Exception as e:
            raise RuntimeError(f"Error accessing IfcApplication entities: {e}")
        
        result['applications'] = applications
        if skipped_apps > 0:
            print(f"Warning: Skipped {skipped_apps} application entities due to missing attributes")
    
    # Extract organization information
    if 'organizations' in sections_to_process:
        organizations = []
        skipped_orgs = 0
        try:
            for entity in model.by_type('IfcOrganization'):
                try:
                    org_dict = {
                        'name': getattr(entity, 'Name', ''),
                        'description': getattr(entity, 'Description', '')
                    }
                    organizations.append(org_dict)
                except AttributeError:
                    skipped_orgs += 1
                    continue
        except Exception as e:
            raise RuntimeError(f"Error accessing IfcOrganization entities: {e}")
        
        result['organizations'] = organizations
        if skipped_orgs > 0:
            print(f"Warning: Skipped {skipped_orgs} organization entities due to missing attributes")
    
    return result