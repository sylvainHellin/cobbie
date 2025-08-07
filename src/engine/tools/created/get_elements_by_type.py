
def get_elements_by_type(ifc_file_path: str, ifc_type: str) -> list:
    """
    Retrieves elements of a specified IFC type from an IFC model.
    
    Args:
        ifc_file_path (str): The path to the IFC file.
        ifc_type (str): The IFC entity type to retrieve (e.g., 'IfcWall', 'IfcBeam', 'IfcDoor').
        
    Returns:
        List[ifcopenshell.entity_instance]: A list of IfcOpenShell entity instances
                                            of the specified type. Each entity has
                                            accessible attributes like 'Name' and 'GlobalId'.
                                            Returns an empty list if the file cannot be opened
                                            or no elements of the specified type are found.
    """
    try:
        # Open the IFC file
        ifc_file = ifcopenshell.open(ifc_file_path)
        
        # Retrieve elements of the specified type
        elements = ifc_file.by_type(ifc_type)
        
        # Return the list of elements
        return elements
    except Exception as e:
        # Return empty list if file cannot be opened or any other error occurs
        return []
