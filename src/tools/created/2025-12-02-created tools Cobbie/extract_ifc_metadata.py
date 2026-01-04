import ifcopenshell
from typing import Union, Dict, Any, List

def extract_ifc_metadata(
    ifc_input: Union[str, Any],
    include_schema_info: bool = True,
    include_file_description: bool = True,
    include_authorization: bool = True,
    return_raw_header: bool = False
) -> Dict[str, Any]:
    """
    Extracts comprehensive metadata from IFC file headers including software information,
    modeling standards, and file properties.
    
    Args:
        ifc_input: Either file path (str) or loaded IFC file
        include_schema_info: Whether to extract schema identifiers
        include_file_description: Whether to include file description details
        include_authorization: Whether to include authorization information
        return_raw_header: Whether to return raw header object for advanced use
    
    Returns:
        Dict[str, Any] containing:
        - file_description: List of description strings
        - file_name: Dict with name, timestamp, author, organization, preprocessor_version, 
                    originating_system, authorization
        - schema_identifiers: List of schema identifiers (if available)
        - raw_header: Raw header object (if return_raw_header=True)
    
    Example:
        >>> metadata = extract_ifc_metadata('model.ifc')
        >>> print(metadata['file_name']['originating_system'])
        'Autodesk Revit 24.2.10.64 (DEU) - IFC 24.3.20.8'
        
        >>> # Using loaded file
        >>> ifc_file = ifcopenshell.open('model.ifc')
        >>> metadata = extract_ifc_metadata(ifc_file, include_schema_info=True)
        >>> print(metadata['schema_identifiers'])
        ['IFC4']
    """
    result: Dict[str, Any] = {}
    
    try:
        # Handle input type (file path or loaded file)
        if isinstance(ifc_input, str):
            ifc_file = ifcopenshell.open(ifc_input)
        else:
            # Assume it's a loaded IFC file
            ifc_file = ifc_input
        
        # Get header information
        header = ifc_file.header
        
        # Extract file description
        if include_file_description:
            try:
                description_list = list(header.file_description.description)
                result['file_description'] = description_list
            except Exception as e:
                result['file_description'] = []
        
        # Extract file name information
        file_name_info = {
            'name': getattr(header.file_name, 'name', ''),
            'time_stamp': getattr(header.file_name, 'time_stamp', ''),
            'author': getattr(header.file_name, 'author', ('',)),
            'organization': getattr(header.file_name, 'organization', ('',)),
            'preprocessor_version': getattr(header.file_name, 'preprocessor_version', ''),
            'originating_system': getattr(header.file_name, 'originating_system', '')
        }
        
        # Include authorization if requested
        if include_authorization:
            file_name_info['authorization'] = getattr(header.file_name, 'authorization', '')
        
        result['file_name'] = file_name_info
        
        # Extract schema information
        if include_schema_info:
            try:
                # Try to get schema from model (most reliable method)
                schema_name = ifc_file.schema
                result['schema_identifiers'] = [schema_name] if schema_name else []
            except Exception as e:
                # Fallback: try to get from header file_schema if available
                try:
                    if hasattr(header, 'file_schema'):
                        schema_ids = list(header.file_schema.schema_identifiers)
                        result['schema_identifiers'] = schema_ids
                    else:
                        result['schema_identifiers'] = []
                except Exception:
                    result['schema_identifiers'] = []
        
        # Include raw header if requested
        if return_raw_header:
            result['raw_header'] = header
        
        return result
        
    except Exception as e:
        # Return error information in a structured way
        error_result = {
            'error': f"Failed to extract IFC metadata: {str(e)}",
            'file_description': [],
            'file_name': {},
            'schema_identifiers': []
        }
        if return_raw_header:
            error_result['raw_header'] = None
        return error_result