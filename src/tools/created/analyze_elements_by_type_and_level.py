import ifcopenshell
import ifcopenshell.util.element
from typing import List, Dict, Any, Optional

def analyze_elements_by_type_and_level(
    ifc_file: ifcopenshell.file,
    element_type: str,
    level_keywords: Optional[List[str]] = None,
    categorize_by: str = 'ObjectType',
    include_details: bool = False
) -> Dict[str, Any]:
    """
    Analyzes IFC elements of a specified type, categorizes them by their properties, 
    and determines their distribution by building level.
    
    Args:
        ifc_file: Loaded IFC model (ifcopenshell.file)
        element_type: IFC element type string (e.g., 'IfcSpaceHeater', 'IfcDoor', 'IfcWall')
        level_keywords: Optional list of keywords for identifying level-related properties 
                       (default: ['ebene', 'level', 'geschoss', 'stock', 'floor'])
        categorize_by: Field to categorize elements by (default: 'ObjectType', 
                      options: 'Name', 'ObjectType', 'PredefinedType')
        include_details: Whether to include detailed element information (default: False)
    
    Returns:
        Dict with structure:
        {
            'summary': {
                'total_elements': int,
                'element_types': Dict[str, int],
                'levels_found': List[str]
            },
            'distribution': {
                'level_name': {
                    'element_type': count,
                    'total_on_level': int
                }
            },
            'elements': List[Dict] (if include_details=True)
        }
        
    Example:
        >>> import ifcopenshell
        >>> model = ifcopenshell.open('building.ifc')
        >>> result = analyze_elements_by_type_and_level(
        ...     model, 'IfcDoor', categorize_by='ObjectType'
        ... )
        >>> print(f"Total doors: {result['summary']['total_elements']}")
        >>> for level, data in result['distribution'].items():
        ...     print(f"{level}: {data['total_on_level']} doors")
    """
    # Set default level keywords if not provided
    if level_keywords is None:
        level_keywords = ['ebene', 'level', 'geschoss', 'stock', 'floor']
    
    def normalize_level_name(level_name: str) -> str:
        """Normalize level names to avoid duplicates with different formatting."""
        if not level_name or level_name == 'Unknown':
            return level_name
        
        # Remove extra spaces around colons and normalize spacing
        normalized = level_name.replace(' : ', ':').replace(': ', ':').replace(' :', ':')
        # Remove leading/trailing whitespace
        normalized = normalized.strip()
        return normalized
    
    try:
        # Get all elements of the specified type
        elements = ifc_file.by_type(element_type)
        
        if not elements:
            return {
                'summary': {
                    'total_elements': 0,
                    'element_types': {},
                    'levels_found': []
                },
                'distribution': {},
                'elements': [] if include_details else None
            }
        
        # Initialize data structures
        element_type_counts = {}
        level_distribution = {}
        levels_found = set()
        detailed_elements = [] if include_details else None
        
        # Process each element
        for element in elements:
            # Get element category based on categorize_by field
            category = 'Unknown'
            if categorize_by == 'Name' and element.Name:
                category = element.Name
            elif categorize_by == 'ObjectType' and element.ObjectType:
                category = element.ObjectType
            elif categorize_by == 'PredefinedType' and hasattr(element, 'PredefinedType') and element.PredefinedType:
                category = element.PredefinedType
            
            # Count element types
            if category not in element_type_counts:
                element_type_counts[category] = 0
            element_type_counts[category] += 1
            
            # Find level information
            level = 'Unknown'
            
            # Method 1: Check property sets for level information
            psets = ifcopenshell.util.element.get_psets(element)
            for pset_name, pset_data in psets.items():
                # Check if property set name contains level keywords
                if any(keyword in pset_name.lower() for keyword in level_keywords):
                    for prop_name, prop_value in pset_data.items():
                        if any(keyword in prop_name.lower() for keyword in level_keywords):
                            level = normalize_level_name(str(prop_value))
                            break
                    if level != 'Unknown':
                        break
                
                # Also check property values for level information
                for prop_name, prop_value in pset_data.items():
                    if isinstance(prop_value, str) and any(keyword in prop_value.lower() for keyword in level_keywords):
                        level = normalize_level_name(prop_value)
                        break
                if level != 'Unknown':
                    break
            
            # Method 2: Check spatial container if level not found
            if level == 'Unknown':
                container = ifcopenshell.util.element.get_container(element)
                if container:
                    # Check container name for level information
                    if container.Name and any(keyword in container.Name.lower() for keyword in level_keywords):
                        level = normalize_level_name(container.Name)
                    else:
                        # Check container's property sets
                        container_psets = ifcopenshell.util.element.get_psets(container)
                        for pset_name, pset_data in container_psets.items():
                            if any(keyword in pset_name.lower() for keyword in level_keywords):
                                for prop_name, prop_value in pset_data.items():
                                    if any(keyword in prop_name.lower() for keyword in level_keywords):
                                        level = normalize_level_name(str(prop_value))
                                        break
                                if level != 'Unknown':
                                    break
            
            # Add to level distribution
            if level not in level_distribution:
                level_distribution[level] = {}
            if category not in level_distribution[level]:
                level_distribution[level][category] = 0
            level_distribution[level][category] += 1
            levels_found.add(level)
            
            # Add detailed information if requested
            if include_details:
                element_info = {
                    'GlobalId': element.GlobalId,
                    'Name': element.Name,
                    'ObjectType': element.ObjectType,
                    'Category': category,
                    'Level': level
                }
                
                # Add PredefinedType if available
                if hasattr(element, 'PredefinedType') and element.PredefinedType:
                    element_info['PredefinedType'] = element.PredefinedType
                
                detailed_elements.append(element_info)
        
        # Calculate totals for each level
        for level in level_distribution:
            level_distribution[level]['total_on_level'] = sum(level_distribution[level].values())
        
        # Prepare result
        result = {
            'summary': {
                'total_elements': len(elements),
                'element_types': element_type_counts,
                'levels_found': sorted(list(levels_found))
            },
            'distribution': level_distribution
        }
        
        if include_details:
            result['elements'] = detailed_elements
        
        return result
        
    except Exception as e:
        # Return error information
        return {
            'summary': {
                'total_elements': 0,
                'element_types': {},
                'levels_found': [],
                'error': str(e)
            },
            'distribution': {},
            'elements': [] if include_details else None
        }