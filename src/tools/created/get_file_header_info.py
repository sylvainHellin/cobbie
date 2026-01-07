import ifcopenshell
from typing import Dict, Any, List, Union, Tuple

def get_file_header_info(
    model: Any, 
    include_description_details: bool = False
) -> Dict[str, Any]:
    """
    Retrieves and structures metadata from the IFC file header and schema identifier.

    This function extracts standard metadata found in the IFC header, such as file 
    description, authorship, originating system, preprocessor version, and the schema 
    identifier. It abstracts the traversal of the `model.header` attributes and returns 
    a structured dictionary.

    Args:
        model: The opened IFC model instance.
        include_description_details: If False (default), returns the File Description 
            tuple as a list. If True, returns the raw tuple/list description.

    Returns:
        A dictionary containing keys like 'file_description', 'file_name', 'author', 
        'organization', 'originating_system', 'preprocessor_version', 'authorization', 
        and 'schema'. Values are structured data (lists, dicts, primitives), not formatted strings.

    Example:
        >>> model = ifcopenshell.open('model.ifc')
        >>> header_info = get_file_header_info(model)
        >>> print(header_info['schema'])
        'IFC4'
        >>> print(header_info['originating_system'])
        'GRAPHISOFT ARCHICAD-64 20.0.0'
    """
    result: Dict[str, Any] = {}
    
    try:
        # Get file description
        if hasattr(model.header, 'file_description') and model.header.file_description:
            file_desc = model.header.file_description
            if hasattr(file_desc, 'description'):
                if include_description_details:
                    result['file_description'] = file_desc.description
                else:
                    result['file_description'] = list(file_desc.description)
    except Exception as e:
        result['file_description'] = f"Error accessing file_description: {str(e)}"
    
    try:
        # Get file name details
        if hasattr(model.header, 'file_name') and model.header.file_name:
            file_name = model.header.file_name
            
            if hasattr(file_name, 'name'):
                result['file_name'] = file_name.name
            
            if hasattr(file_name, 'author'):
                result['author'] = list(file_name.author) if file_name.author else []
            
            if hasattr(file_name, 'organization'):
                result['organization'] = list(file_name.organization) if file_name.organization else []
            
            if hasattr(file_name, 'originating_system'):
                result['originating_system'] = file_name.originating_system
            
            if hasattr(file_name, 'preprocessor_version'):
                result['preprocessor_version'] = file_name.preprocessor_version
            
            if hasattr(file_name, 'authorization'):
                result['authorization'] = file_name.authorization
    except Exception as e:
        result['file_name_error'] = f"Error accessing file_name: {str(e)}"
    
    try:
        # Get schema identifier
        if hasattr(model, 'schema'):
            result['schema'] = model.schema
    except Exception as e:
        result['schema'] = f"Error accessing schema: {str(e)}"
    
    return result