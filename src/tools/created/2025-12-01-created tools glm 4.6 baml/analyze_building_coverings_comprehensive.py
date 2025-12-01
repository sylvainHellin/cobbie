import ifcopenshell
import ifcopenshell.util.element
import ifcopenshell.util.selector
from typing import List, Dict, Any, Optional, Union

def analyze_building_coverings_comprehensive(
    ifc_file: ifcopenshell.file,
    covering_element_types: List[str] = ['IfcBuildingElementProxy', 'IfcCovering', 'IfcFurnishingElement'],
    covering_keywords: List[str] = ['trim', 'muntin', 'finish', 'cover', 'clad', 'coating'],
    search_fields: List[str] = ['ObjectType', 'Name'],
    include_material_analysis: bool = True,
    material_keywords: List[str] = ['material', 'finish', 'surface'],
    max_examples_per_type: int = 3,
    case_sensitive: bool = False
) -> Dict[str, Any]:
    """
    Analyzes building coverings (finishes, trim, etc.) in IFC models by discovering elements 
    across multiple IFC types using semantic keyword matching and extracting their material associations.
    
    This function handles the common BIM pattern where coverings are modeled as various element types 
    (IfcBuildingElementProxy, IfcCovering, etc.) rather than a single standardized type. It provides 
    comprehensive analysis including element counts, categorization by covering type, and material information.
    
    Args:
        ifc_file: Loaded IFC model (ifcopenshell.file)
        covering_element_types: List of IFC element types to search (default: ['IfcBuildingElementProxy', 'IfcCovering', 'IfcFurnishingElement'])
        covering_keywords: List of keywords to identify covering elements (default: ['trim', 'muntin', 'finish', 'cover', 'clad', 'coating'])
        search_fields: Fields to search for keywords (default: ['ObjectType', 'Name'])
        include_material_analysis: Boolean to extract material associations (default: True)
        material_keywords: Keywords for material-related properties (default: ['material', 'finish', 'surface'])
        max_examples_per_type: Maximum examples to show per covering type (default: 3)
        case_sensitive: Boolean for case-sensitive keyword matching (default: False)
    
    Returns:
        Dict containing:
        - covering_types: Dict mapping covering type names to element counts and examples
        - materials: Dict of materials found with their associated covering types
        - summary: Total counts and overview of covering categories
        - element_details: Optional detailed information about individual elements
    
    Example:
        >>> import ifcopenshell
        >>> model = ifcopenshell.open('building.ifc')
        >>> result = analyze_building_coverings_comprehensive(model)
        >>> print(f"Found {result['summary']['total_coverings']} covering elements")
    """
    
    result = {
        'covering_types': {},
        'materials': {},
        'summary': {
            'total_coverings': 0,
            'total_types': 0,
            'categories': {}
        },
        'element_details': {}
    }
    
    try:
        # Process each element type
        for element_type in covering_element_types:
            try:
                elements = ifc_file.by_type(element_type)
                if not elements:
                    continue
                    
                # Find covering elements using keyword matching
                covering_elements = []
                
                for element in elements:
                    is_covering = False
                    element_info = {
                        'element': element,
                        'Name': getattr(element, 'Name', None),
                        'ObjectType': getattr(element, 'ObjectType', None),
                        'GlobalId': getattr(element, 'GlobalId', None)
                    }
                    
                    # Check search fields for covering keywords
                    for field in search_fields:
                        field_value = getattr(element, field, None)
                        if field_value:
                            search_text = field_value if case_sensitive else field_value.lower()
                            keywords = covering_keywords if case_sensitive else [k.lower() for k in covering_keywords]
                            
                            if any(keyword in search_text for keyword in keywords):
                                is_covering = True
                                break
                    
                    if is_covering:
                        covering_elements.append(element_info)
                
                # Group by ObjectType or Name
                if covering_elements:
                    for element_info in covering_elements:
                        element = element_info['element']
                        group_key = element_info['ObjectType'] or element_info['Name'] or 'Unknown'
                        
                        if group_key not in result['covering_types']:
                            result['covering_types'][group_key] = {
                                'count': 0,
                                'examples': [],
                                'element_type': element_type,
                                'materials': set()
                            }
                        
                        result['covering_types'][group_key]['count'] += 1
                        
                        # Add examples (limit to max_examples_per_type)
                        if len(result['covering_types'][group_key]['examples']) < max_examples_per_type:
                            example_info = {
                                'GlobalId': element_info['GlobalId'],
                                'Name': element_info['Name'],
                                'ObjectType': element_info['ObjectType']
                            }
                            result['covering_types'][group_key]['examples'].append(example_info)
                        
                        # Material analysis
                        if include_material_analysis:
                            try:
                                # Check for material associations
                                for rel in ifc_file.get_inverse(element):
                                    if rel.is_a('IfcRelAssociatesMaterial'):
                                        material = rel.RelatingMaterial
                                        if material:
                                            if hasattr(material, 'Name') and material.Name:
                                                result['covering_types'][group_key]['materials'].add(material.Name)
                                            elif hasattr(material, 'MaterialConstituents'):
                                                result['covering_types'][group_key]['materials'].add('Material constituents')
                                        break
                            except Exception:
                                continue
                        
                        # Store detailed element information
                        if element_info['GlobalId'] not in result['element_details']:
                            result['element_details'][element_info['GlobalId']] = {
                                'element_type': element_type,
                                'Name': element_info['Name'],
                                'ObjectType': element_info['ObjectType'],
                                'covering_type': group_key
                            }
                
            except Exception as e:
                # Continue with next element type if one fails
                continue
        
        # Process materials
        if include_material_analysis:
            for covering_type, info in result['covering_types'].items():
                for material in info['materials']:
                    if material not in result['materials']:
                        result['materials'][material] = {
                            'covering_types': [],
                            'element_count': 0
                        }
                    result['materials'][material]['covering_types'].append(covering_type)
                    result['materials'][material]['element_count'] += info['count']
        
        # Generate summary
        total_coverings = sum(info['count'] for info in result['covering_types'].values())
        result['summary']['total_coverings'] = total_coverings
        result['summary']['total_types'] = len(result['covering_types'])
        
        # Categorize coverings
        categories = {}
        for covering_type, info in result['covering_types'].items():
            category = 'Other'
            covering_lower = covering_type.lower()
            
            if 'trim' in covering_lower:
                category = 'Trim'
            elif 'muntin' in covering_lower:
                category = 'Muntin Patterns'
            elif 'finish' in covering_lower:
                category = 'Finishes'
            elif 'cover' in covering_lower:
                category = 'Coverings'
            elif 'clad' in covering_lower:
                category = 'Cladding'
            elif 'coating' in covering_lower:
                category = 'Coatings'
            
            if category not in categories:
                categories[category] = {'count': 0, 'types': []}
            categories[category]['count'] += info['count']
            categories[category]['types'].append(covering_type)
        
        result['summary']['categories'] = categories
        
        # Convert sets to lists for JSON serialization
        for covering_type in result['covering_types']:
            result['covering_types'][covering_type]['materials'] = list(result['covering_types'][covering_type]['materials'])
        
        return result
        
    except Exception as e:
        # Return partial results if error occurs
        result['error'] = str(e)
        return result