import ifcopenshell
from typing import List, Dict, Any, Optional


def get_building_summary(
    model: ifcopenshell.file,
    relevant_classes: Optional[List[str]] = None
) -> Dict[str, Any]:
    """
    Retrieves a high-level summary of key building metrics, including element counts 
    for relevant classes, the number of building storeys (with details), and the total 
    number of spaces.
    
    This function aggregates data from class audits and direct entity queries to provide 
    a comprehensive snapshot of the model's physical structure. It is useful for initial 
    model audits, quick reporting, and answering general questions about model size and 
    composition.
    
    Args:
        model: The opened IFC model.
        relevant_classes: A list of IFC classes to include in the element count summary. 
            Defaults to common structural and architectural elements.
    
    Returns:
        A dictionary containing:
            - 'element_counts' (Dict[str, int]): Counts for the relevant IFC classes.
            - 'num_storeys' (int): Total number of IfcBuildingStorey instances.
            - 'storeys' (List[Dict[str, Any]]): List of storey details (Name, Elevation, Description).
            - 'num_spaces' (int): Total number of IfcSpace instances.
    
    Example:
        >>> model = ifcopenshell.open('building.ifc')
        >>> summary = get_building_summary(model)
        >>> print(f"Storeys: {summary['num_storeys']}")
        >>> print(f"Spaces: {summary['num_spaces']}")
        >>> for storey in summary['storeys']:
        ...     print(f"  - {storey['Name']}: {storey['Elevation']}")
    """
    # Set default relevant classes if not provided
    if relevant_classes is None:
        relevant_classes = [
            'IfcWall', 'IfcSlab', 'IfcRoof', 'IfcFloor',
            'IfcColumn', 'IfcBeam', 'IfcFooting',
            'IfcDoor', 'IfcWindow',
            'IfcStair', 'IfcRailing', 'IfcCovering',
            'IfcBuildingElementProxy', 'IfcSpace',
            'IfcBuilding', 'IfcSite', 'IfcBuildingStorey'
        ]
    
    result: Dict[str, Any] = {
        'element_counts': {},
        'num_storeys': 0,
        'storeys': [],
        'num_spaces': 0
    }
    
    try:
        # Get element counts for relevant classes
        for ifc_class in relevant_classes:
            try:
                count = len(model.by_type(ifc_class))
                result['element_counts'][ifc_class] = count
            except Exception:
                result['element_counts'][ifc_class] = 0
        
        # Get storeys information
        try:
            storeys = model.by_type('IfcBuildingStorey')
            result['num_storeys'] = len(storeys)
            
            for storey in storeys:
                storey_info: Dict[str, Any] = {
                    'Name': None,
                    'Elevation': None,
                    'Description': None
                }
                try:
                    storey_info['Name'] = storey.Name
                except AttributeError:
                    pass
                try:
                    storey_info['Elevation'] = storey.Elevation
                except AttributeError:
                    pass
                try:
                    storey_info['Description'] = storey.Description
                except AttributeError:
                    pass
                result['storeys'].append(storey_info)
        except Exception:
            result['num_storeys'] = 0
            result['storeys'] = []
        
        # Get spaces count
        try:
            spaces = model.by_type('IfcSpace')
            result['num_spaces'] = len(spaces)
        except Exception:
            result['num_spaces'] = 0
            
    except Exception:
        # In case of major error, return partial results
        pass
    
    return result