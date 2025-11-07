import ifcopenshell
from typing import Dict, Any

def extract_file_metadata(
    ifc_file: ifcopenshell.file,
    include_header_details: bool = False,
    include_owner_history: bool = True
) -> Dict[str, Any]:
    """
    Extracts comprehensive file metadata from an IFC model including IFC schema version,
    creating application information, and file creation details.
    
    Args:
        ifc_file: Loaded IFC model (ifcopenshell.file)
        include_header_details: Optional boolean to include raw header information (default: False)
        include_owner_history: Optional boolean to search IfcOwnerHistory for application info (default: True)
    
    Returns:
        Dict containing:
        - schema: IFC standard version (e.g., 'IFC2X3', 'IFC4')
        - application: Dict with application details (name, identifier, version, developer)
        - file_info: Additional file metadata (timestamp, author, organization if available)
        - header_details: Raw header information if requested
    
    Example:
        >>> import ifcopenshell
        >>> model = ifcopenshell.open('model.ifc')
        >>> metadata = extract_file_metadata(model)
        >>> print(metadata['schema'])
        'IFC2X3'
    """
    result = {
        'schema': None,
        'application': {},
        'file_info': {},
        'header_details': None
    }
    
    try:
        # Extract schema information
        result['schema'] = ifc_file.schema
        
        # Extract application information from IfcApplication entities
        applications = ifc_file.by_type('IfcApplication')
        if applications:
            app = applications[0]  # Take the first application
            result['application'] = {
                'name': getattr(app, 'ApplicationFullName', None),
                'identifier': getattr(app, 'ApplicationIdentifier', None),
                'version': getattr(app, 'Version', None),
                'developer': getattr(app, 'ApplicationDeveloper', None)
            }
        
        # Extract additional file information from header
        try:
            header = ifc_file.header
            
            # Try to access file name information
            if hasattr(header, 'file_name'):
                file_name = header.file_name
                if hasattr(file_name, 'name'):
                    result['file_info']['name'] = file_name.name
                if hasattr(file_name, 'author'):
                    result['file_info']['author'] = file_name.author
                if hasattr(file_name, 'organization'):
                    result['file_info']['organization'] = file_name.organization
                if hasattr(file_name, 'time_stamp'):
                    result['file_info']['timestamp'] = file_name.time_stamp
        except Exception:
            # If header access fails, continue without file info
            pass
        
        # Include owner history information if requested
        if include_owner_history:
            try:
                owner_histories = ifc_file.by_type('IfcOwnerHistory')
                for history in owner_histories:
                    if hasattr(history, 'OwningApplication') and history.OwningApplication:
                        app = history.OwningApplication
                        # Update application info if not already set or if this provides more info
                        if not result['application'].get('name') or app.ApplicationFullName:
                            result['application'] = {
                                'name': getattr(app, 'ApplicationFullName', None),
                                'identifier': getattr(app, 'ApplicationIdentifier', None),
                                'version': getattr(app, 'Version', None),
                                'developer': getattr(app, 'ApplicationDeveloper', None)
                            }
                        break
            except Exception:
                # If owner history access fails, continue without it
                pass
        
        # Include raw header details if requested
        if include_header_details:
            try:
                header_info = {}
                header = ifc_file.header
                for attr in dir(header):
                    if not attr.startswith('_'):
                        try:
                            value = getattr(header, attr)
                            if not callable(value):
                                header_info[attr] = str(value)
                        except:
                            header_info[attr] = '<unable to access>'
                result['header_details'] = header_info
            except Exception as e:
                result['header_details'] = {'error': str(e)}
        
    except Exception as e:
        result['error'] = str(e)
    
    return result