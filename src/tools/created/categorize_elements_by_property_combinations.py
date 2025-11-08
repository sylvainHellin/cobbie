import ifcopenshell
import ifcopenshell.util.element
from typing import Dict, List, Tuple, Any, Optional, Union

def categorize_elements_by_property_combinations(
    ifc_file: ifcopenshell.file,
    element_type: str,
    property_mappings: Dict[str, Tuple[str, str]],
    include_examples: bool = True,
    max_examples: int = 3
) -> Dict[str, Any]:
    """
    Categorizes IFC elements by combinations of property values from specified property sets.
    This function is designed for common BIM analysis tasks like categorizing walls by 
    LoadBearing+IsExternal, doors by FireRating+OperationType, or spaces by Function+AreaCategory.
    
    Args:
        ifc_file: Loaded IFC model (ifcopenshell.file)
        element_type: IFC element type string (e.g., 'IfcWall', 'IfcDoor')
        property_mappings: Dict mapping category names to property set/property name pairs
                          (e.g., {'structural': ('Pset_WallCommon', 'LoadBearing'), 
                                 'location': ('Pset_WallCommon', 'IsExternal')})
        include_examples: Boolean to include sample elements for each category (default: True)
        max_examples: Maximum number of examples to show per category (default: 3)
    
    Returns:
        Dict containing:
        - total_elements: Total number of elements processed
        - categories: Dict mapping combined property values to element counts and lists
        - summary_by_property: Dict showing distribution by individual properties
        - property_sets_found: List of property sets discovered
    
    Example:
        >>> model = ifcopenshell.open('model.ifc')
        >>> result = categorize_elements_by_property_combinations(
        ...     model, 'IfcWall',
        ...     {'structural': ('Pset_WallCommon', 'LoadBearing'),
        ...      'location': ('Pset_WallCommon', 'IsExternal')}
        ... )
        >>> print(f"Total walls: {result['total_elements']}")
        >>> for category, info in result['categories'].items():
        ...     print(f"{category}: {info['count']} walls")
    """
    try:
        # Get all elements of the specified type
        elements = ifc_file.by_type(element_type)
        total_elements = len(elements)
        
        if total_elements == 0:
            return {
                'total_elements': 0,
                'categories': {},
                'summary_by_property': {},
                'property_sets_found': []
            }
        
        # Initialize data structures
        categories: Dict[str, Dict[str, Any]] = {}
        property_sets_found = set()
        summary_by_property: Dict[str, Dict[str, int]] = {}
        
        # Initialize summary counters for each property
        for category_name, (pset_name, prop_name) in property_mappings.items():
            summary_by_property[category_name] = {}
        
        # Process each element
        for element in elements:
            try:
                # Get property sets for this element
                psets = ifcopenshell.util.element.get_psets(element)
                
                # Track property sets found
                for pset_name in psets.keys():
                    property_sets_found.add(pset_name)
                
                # Extract property values for each mapping
                property_values = {}
                for category_name, (pset_name, prop_name) in property_mappings.items():
                    value = 'Unknown'
                    
                    # Try to get the property value
                    if pset_name in psets and prop_name in psets[pset_name]:
                        value = psets[pset_name][prop_name]
                    
                    property_values[category_name] = value
                    
                    # Update summary by individual property
                    if value not in summary_by_property[category_name]:
                        summary_by_property[category_name][value] = 0
                    summary_by_property[category_name][value] += 1
                
                # Create combined category string
                category_parts = []
                for category_name in property_mappings.keys():
                    category_parts.append(f"{category_name}={property_values[category_name]}")
                combined_category = ", ".join(category_parts)
                
                # Add element to category
                if combined_category not in categories:
                    categories[combined_category] = {
                        'count': 0,
                        'elements': [] if include_examples else None
                    }
                
                categories[combined_category]['count'] += 1
                
                if include_examples and len(categories[combined_category]['elements']) < max_examples:
                    element_info = {
                        'GlobalId': element.GlobalId,
                        'Name': element.Name,
                        'ObjectType': element.ObjectType,
                        'PredefinedType': element.PredefinedType
                    }
                    categories[combined_category]['elements'].append(element_info)
                    
            except Exception as e:
                # Skip problematic elements but continue processing
                continue
        
        return {
            'total_elements': total_elements,
            'categories': categories,
            'summary_by_property': summary_by_property,
            'property_sets_found': sorted(list(property_sets_found))
        }
        
    except Exception as e:
        return {
            'total_elements': 0,
            'categories': {},
            'summary_by_property': {},
            'property_sets_found': [],
            'error': str(e)
        }