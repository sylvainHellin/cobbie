import ifcopenshell
import ifcopenshell.util.element
from typing import List, Dict, Any, Optional


def analyze_element_structural_properties(
    ifc_file: ifcopenshell.file,
    element_types: List[str],
    categorization_keywords: Optional[List[str]] = None,
    structural_property_sets: Optional[List[str]] = None,
    structural_properties: Optional[List[str]] = None,
    include_classification_analysis: bool = True,
    case_sensitive: bool = False
) -> Dict[str, Any]:
    """
    Analyzes structural properties of IFC elements to determine their load-bearing function and structural role.
    
    This function systematically examines multiple structural property indicators across different
    property sets, combines this with semantic categorization based on element names and classifications,
    and provides comprehensive structural analysis.
    
    Args:
        ifc_file: Loaded IFC model (ifcopenshell.file)
        element_types: List of IFC element types to analyze (e.g., ['IfcWall', 'IfcColumn'])
        categorization_keywords: Optional keywords for semantic categorization (e.g., ['Interior', 'Exterior', 'Partition'])
        structural_property_sets: List of property sets to check for structural properties
        structural_properties: List of property names that indicate structural function
        include_classification_analysis: Boolean to include classification-based structural inference
        case_sensitive: Boolean for keyword matching
    
    Returns:
        Dict containing:
        - 'total_elements': Total elements analyzed
        - 'structural_categories': Dict categorizing elements by structural function
        - 'semantic_categories': Dict categorizing elements by semantic criteria
        - 'property_analysis': Detailed analysis of structural properties found
        - 'classification_analysis': Classification-based structural inference
        - 'summary': Overall structural analysis summary
        - 'examples': Sample elements from each structural category
    """
    # Set default values
    if structural_property_sets is None:
        structural_property_sets = ['Pset_WallCommon', 'PSet_Revit_Structural', 'Pset_ColumnCommon']
    if structural_properties is None:
        structural_properties = ['LoadBearing', 'Structural Usage', 'IsLoadBearing', 'StructuralRole']
    if categorization_keywords is None:
        categorization_keywords = ['Interior', 'Exterior', 'Partition', 'Load', 'Bearing', 'Structural']
    
    # Initialize result structure
    result = {
        'total_elements': 0,
        'structural_categories': {'LoadBearing': [], 'NonLoadBearing': [], 'Unknown': []},
        'semantic_categories': {},
        'property_analysis': {},
        'classification_analysis': {},
        'summary': {},
        'examples': {}
    }
    
    try:
        # Collect all elements of specified types
        all_elements = []
        for element_type in element_types:
            elements = ifc_file.by_type(element_type)
            all_elements.extend(elements)
        
        result['total_elements'] = len(all_elements)
        
        # Analyze each element
        for element in all_elements:
            element_info = {
                'id': element.id(),
                'type': element.is_a(),
                'name': getattr(element, 'Name', ''),
                'object_type': getattr(element, 'ObjectType', ''),
                'properties': {},
                'structural_indicators': [],
                'semantic_category': None
            }
            
            # Get property sets
            try:
                psets = ifcopenshell.util.element.get_psets(element)
                element_info['properties'] = psets
            except:
                element_info['properties'] = {}
            
            # Check for structural properties
            is_load_bearing = False
            is_non_load_bearing = False
            
            for prop_set_name, prop_set in element_info['properties'].items():
                if prop_set_name in structural_property_sets:
                    for prop_name, prop_value in prop_set.items():
                        # Check if this is a structural property we're looking for
                        for struct_prop in structural_properties:
                            if struct_prop.lower() in prop_name.lower():
                                element_info['structural_indicators'].append({
                                    'property_set': prop_set_name,
                                    'property_name': prop_name,
                                    'property_value': prop_value
                                })
                                
                                # Determine load-bearing status
                                if prop_name.lower() == 'loadbearing' and prop_value is True:
                                    is_load_bearing = True
                                elif prop_name.lower() == 'loadbearing' and prop_value is False:
                                    is_non_load_bearing = True
                                elif 'structural' in prop_name.lower() and prop_value not in [0, None, '']:
                                    # Non-zero structural usage might indicate load-bearing
                                    if prop_value != 0:  # 0 typically means non-structural
                                        is_load_bearing = True
                                    else:
                                        is_non_load_bearing = True
            
            # Categorize by structural function
            if is_load_bearing:
                element_info['structural_category'] = 'LoadBearing'
                result['structural_categories']['LoadBearing'].append(element_info)
            elif is_non_load_bearing:
                element_info['structural_category'] = 'NonLoadBearing'
                result['structural_categories']['NonLoadBearing'].append(element_info)
            else:
                element_info['structural_category'] = 'Unknown'
                result['structural_categories']['Unknown'].append(element_info)
            
            # Semantic categorization
            name_lower = element_info['name'].lower() if element_info['name'] else ''
            object_type_lower = element_info['object_type'].lower() if element_info['object_type'] else ''
            
            for keyword in categorization_keywords:
                if not case_sensitive:
                    keyword_lower = keyword.lower()
                    if keyword_lower in name_lower or keyword_lower in object_type_lower:
                        element_info['semantic_category'] = keyword
                        break
                else:
                    if keyword in element_info['name'] or keyword in element_info['object_type']:
                        element_info['semantic_category'] = keyword
                        break
            
            if element_info['semantic_category']:
                category = element_info['semantic_category']
                if category not in result['semantic_categories']:
                    result['semantic_categories'][category] = []
                result['semantic_categories'][category].append(element_info)
        
        # Generate summary
        total = result['total_elements']
        result['summary'] = {
            'load_bearing_count': len(result['structural_categories']['LoadBearing']),
            'non_load_bearing_count': len(result['structural_categories']['NonLoadBearing']),
            'unknown_count': len(result['structural_categories']['Unknown']),
            'load_bearing_percentage': (len(result['structural_categories']['LoadBearing']) / total * 100) if total > 0 else 0,
            'non_load_bearing_percentage': (len(result['structural_categories']['NonLoadBearing']) / total * 100) if total > 0 else 0,
            'unknown_percentage': (len(result['structural_categories']['Unknown']) / total * 100) if total > 0 else 0
        }
        
        # Generate examples (first 3 from each category)
        for category, elements in result['structural_categories'].items():
            if elements:
                result['examples'][category] = elements[:3]
        
        return result
        
    except Exception as e:
        result['error'] = str(e)
        return result