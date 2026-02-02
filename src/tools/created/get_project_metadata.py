import ifcopenshell
from typing import Dict, Any, List, Optional, Union

def get_project_metadata(
    model: ifcopenshell.file, 
    include_units: bool = True, 
    include_classifications: bool = True,
    include_file_header_details: bool = True
) -> Dict[str, Any]:
    """
    Extracts comprehensive metadata from an IFC model, including file header info,
    authoring software, schema, and optionally units and classifications.

    Args:
        model (ifcopenshell.file): The IFC model instance.
        include_units (bool): If True, extracts the list of project units. Defaults to True.
        include_classifications (bool): If True, extracts defined classification systems. Defaults to True.
        include_file_header_details (bool): If True, extracts detailed file header attributes including
            originating_system, preprocessor_version, author, and organization. Defaults to True.

    Returns:
        Dict[str, Any]: A dictionary containing:
            - 'schema': The IFC schema identifier (e.g., 'IFC2X3').
            - 'view_definitions': List of view definitions found in the file description.
            - 'authoring_software': Dict containing 'application_name', 'version', 'developer', and 'originating_system'.
            - 'file_info': Dict containing 'author', 'organization', 'timestamp', 'preprocessor_version',
              'originating_system', and 'file_description'.
            - 'units' (optional): List of dicts describing project units (type, name, prefix).
            - 'classifications' (optional): List of dicts describing classification references (name, source, edition).

    Example:
        >>> model = ifcopenshell.open('model.ifc')
        >>> metadata = get_project_metadata(model, include_units=True)
        >>> print(metadata['schema'])
        'IFC2X3'
        >>> print(metadata['file_info']['file_description'])
        'SynchroSoftwareLtd Ifc 4D Exporter.'
    """
    metadata: Dict[str, Any] = {}

    # 1. Extract Schema Information using model.schema (more reliable than header)
    try:
        if hasattr(model, 'schema'):
            metadata['schema'] = str(model.schema)
        else:
            metadata['schema'] = 'Unknown'
    except AttributeError:
        metadata['schema'] = 'Unknown'

    # 2. Extract View Definitions and File Description from Header
    view_definitions: List[str] = []
    file_description_str = 'Unknown'
    
    try:
        if hasattr(model.header, 'file_description') and model.header.file_description:
            fd = model.header.file_description
            if hasattr(fd, 'description') and fd.description:
                description = fd.description
                # Extract file description (first item in tuple)
                if isinstance(description, tuple) and len(description) > 0:
                    file_description_str = str(description[0])
                    # Check for view definitions
                    for desc in description:
                        if 'ViewDefinition' in str(desc):
                            view_definitions.append(str(desc))
                elif description:
                    file_description_str = str(description)
                    if 'ViewDefinition' in file_description_str:
                        view_definitions.append(file_description_str)
    except AttributeError:
        pass
    
    metadata['view_definitions'] = view_definitions

    # 3. Extract Detailed File Info from Header
    file_info: Dict[str, Any] = {
        'author': 'Unknown',
        'organization': 'Unknown',
        'timestamp': 'Unknown',
        'preprocessor_version': 'Unknown',
        'originating_system': 'Unknown',
        'file_description': file_description_str
    }
    
    if include_file_header_details:
        try:
            if hasattr(model.header, 'file_name') and model.header.file_name:
                fn = model.header.file_name
                
                # Handle author (may be tuple or string)
                if hasattr(fn, 'author') and fn.author:
                    if isinstance(fn.author, tuple) and len(fn.author) > 0:
                        file_info['author'] = fn.author[0]
                    else:
                        file_info['author'] = str(fn.author)
                
                # Handle organization (may be tuple or string)
                if hasattr(fn, 'organization') and fn.organization:
                    if isinstance(fn.organization, tuple) and len(fn.organization) > 0:
                        file_info['organization'] = fn.organization[0]
                    else:
                        file_info['organization'] = str(fn.organization)
                
                # Handle timestamp
                if hasattr(fn, 'time_stamp') and fn.time_stamp:
                    file_info['timestamp'] = fn.time_stamp
                
                # Handle preprocessor version
                if hasattr(fn, 'preprocessor_version') and fn.preprocessor_version:
                    file_info['preprocessor_version'] = fn.preprocessor_version
                
                # Handle originating system
                if hasattr(fn, 'originating_system') and fn.originating_system:
                    file_info['originating_system'] = fn.originating_system
        except AttributeError:
            pass
    
    metadata['file_info'] = file_info

    # 4. Extract Authoring Software from IfcProject OwnerHistory
    authoring_software: Dict[str, Any] = {
        'application_name': 'Unknown',
        'version': 'Unknown',
        'developer': 'Unknown',
        'originating_system': file_info.get('originating_system', 'Unknown')
    }
    
    try:
        projects = model.by_type('IfcProject')
        if projects:
            project = projects[0]
            if hasattr(project, 'OwnerHistory') and project.OwnerHistory:
                oh = project.OwnerHistory
                if hasattr(oh, 'OwningApplication') and oh.OwningApplication:
                    app = oh.OwningApplication
                    if hasattr(app, 'ApplicationFullName') and app.ApplicationFullName:
                        authoring_software['application_name'] = app.ApplicationFullName
                    if hasattr(app, 'Version') and app.Version:
                        authoring_software['version'] = app.Version
                    if hasattr(app, 'ApplicationDeveloper') and app.ApplicationDeveloper:
                        if hasattr(app.ApplicationDeveloper, 'Name') and app.ApplicationDeveloper.Name:
                            authoring_software['developer'] = app.ApplicationDeveloper.Name
    except (AttributeError, IndexError):
        pass
    
    metadata['authoring_software'] = authoring_software

    # 5. Extract Units (Optional)
    if include_units:
        units_list: List[Dict[str, Any]] = []
        try:
            projects = model.by_type('IfcProject')
            if projects and hasattr(projects[0], 'UnitsInContext') and projects[0].UnitsInContext:
                units = projects[0].UnitsInContext.Units
                for unit in units:
                    unit_data: Dict[str, Any] = {
                        'type': str(getattr(unit, 'UnitType', 'N/A')),
                        'name': 'N/A',
                        'prefix': 'N/A'
                    }
                    
                    if unit.is_a('IfcSIUnit'):
                        raw_name = getattr(unit, 'Name', None)
                        raw_prefix = getattr(unit, 'Prefix', None)
                        
                        unit_data['name'] = raw_name.name if hasattr(raw_name, 'name') else str(raw_name) if raw_name else 'N/A'
                        unit_data['prefix'] = raw_prefix.name if hasattr(raw_prefix, 'name') else str(raw_prefix) if raw_prefix else 'None'
                    elif unit.is_a('IfcConversionBasedUnit'):
                        unit_data['name'] = getattr(unit, 'Name', 'N/A')
                        unit_data['prefix'] = 'ConversionBased'
                    
                    units_list.append(unit_data)
        except (AttributeError, TypeError):
            pass
        metadata['units'] = units_list

    # 6. Extract Classifications (Optional)
    if include_classifications:
        classifications_list: List[Dict[str, Any]] = []
        try:
            classifications = model.by_type('IfcClassification')
            for cls in classifications:
                cls_data: Dict[str, Any] = {
                    'name': getattr(cls, 'Name', 'Unknown'),
                    'source': getattr(cls, 'Source', ''),
                    'edition': getattr(cls, 'Edition', '')
                }
                classifications_list.append(cls_data)
        except AttributeError:
            pass
        metadata['classifications'] = classifications_list

    return metadata