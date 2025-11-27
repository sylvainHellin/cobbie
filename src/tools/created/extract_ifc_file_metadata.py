import ifcopenshell
from typing import Dict, Any, Union

def extract_ifc_file_metadata(ifc_file: ifcopenshell.file, include_detailed_info: bool = True, include_raw_objects: bool = False, format_output: bool = False) -> Union[Dict[str, Any], str]:
    """
    Extracts comprehensive metadata from IFC file header including creation information, 
    software details, and schema specifications.
    
    Args:
        ifc_file: Loaded IFC model (ifcopenshell.file)
        include_detailed_info: Boolean to include all available header attributes (default: True)
        include_raw_objects: Boolean to include raw header objects for advanced analysis (default: False)
        format_output: Boolean to return formatted string representation (default: False)
    
    Returns:
        If format_output is False: Dict containing structured metadata with keys:
        - 'file_description': Dict with 'description' and 'implementation_level'
        - 'file_name': Dict with 'name', 'timestamp', 'author', 'organization', 
                      'originating_system', 'preprocessor_version'
        - 'schema_info': Dict with 'schema' identifier
        - optionally 'raw_objects' for advanced use cases
        
        If format_output is True: Formatted string representation of metadata
    
    Example:
        >>> import ifcopenshell
        >>> model = ifcopenshell.open('model.ifc')
        >>> metadata = extract_ifc_file_metadata(model)
        >>> print(metadata['schema_info']['schema'])
        'IFC2X3'
        >>> formatted = extract_ifc_file_metadata(model, format_output=True)
        >>> print(formatted)
    """
    metadata: Dict[str, Any] = {}
    
    try:
        header = ifc_file.header
        
        # Extract file description information
        file_desc_data: Dict[str, Any] = {}
        try:
            file_desc_data['description'] = header.file_description.description
            file_desc_data['implementation_level'] = header.file_description.implementation_level
        except AttributeError as e:
            file_desc_data['error'] = f'Could not access file description: {str(e)}'
        metadata['file_description'] = file_desc_data
        
        # Extract file name information
        file_name_data: Dict[str, Any] = {}
        try:
            file_name_data['name'] = header.file_name.name
            file_name_data['timestamp'] = header.file_name.time_stamp
            file_name_data['author'] = header.file_name.author
            file_name_data['organization'] = header.file_name.organization
            
            if include_detailed_info:
                # Try to access additional attributes that may not always be present
                try:
                    file_name_data['originating_system'] = header.file_name.originating_system
                except AttributeError:
                    file_name_data['originating_system'] = None
                    
                try:
                    file_name_data['preprocessor_version'] = header.file_name.preprocessor_version
                except AttributeError:
                    file_name_data['preprocessor_version'] = None
                    
                try:
                    file_name_data['authorization'] = header.file_name.authorization
                except AttributeError:
                    file_name_data['authorization'] = None
        except AttributeError as e:
            file_name_data['error'] = f'Could not access file name: {str(e)}'
        metadata['file_name'] = file_name_data
        
        # Extract schema information
        schema_data: Dict[str, Any] = {}
        try:
            schema_data['schema'] = str(ifc_file.schema)
        except AttributeError as e:
            schema_data['error'] = f'Could not access schema: {str(e)}'
        metadata['schema_info'] = schema_data
        
        # Include raw objects if requested
        if include_raw_objects:
            metadata['raw_objects'] = {
                'header': header,
                'file_description': header.file_description,
                'file_name': header.file_name,
                'schema': ifc_file.schema
            }
            
    except Exception as e:
        metadata['error'] = f'Failed to extract metadata: {str(e)}'
    
    # Return formatted string if requested
    if format_output:
        return _format_metadata(metadata)
    
    return metadata

def _format_metadata(metadata: Dict[str, Any]) -> str:
    """
    Helper function to format metadata dictionary into a readable string.
    """
    lines = []
    lines.append("IFC File Metadata:")
    lines.append("=" * 50)
    
    # Format file description
    if 'file_description' in metadata:
        lines.append("\nFile Description:")
        for key, value in metadata['file_description'].items():
            if key == 'description' and isinstance(value, tuple):
                lines.append(f"  {key}:")
                for desc_item in value:
                    lines.append(f"    - {desc_item}")
            else:
                lines.append(f"  {key}: {value}")
    
    # Format file name
    if 'file_name' in metadata:
        lines.append("\nFile Name:")
        for key, value in metadata['file_name'].items():
            if key in ['author', 'organization'] and isinstance(value, tuple):
                lines.append(f"  {key}: {value if value else 'None'}")
            else:
                lines.append(f"  {key}: {value}")
    
    # Format schema info
    if 'schema_info' in metadata:
        lines.append("\nFile Schema:")
        for key, value in metadata['schema_info'].items():
            lines.append(f"  {key}: {value}")
    
    # Format any errors
    if 'error' in metadata:
        lines.append("\nError:")
        lines.append(f"  {metadata['error']}")
    
    return "\n".join(lines)