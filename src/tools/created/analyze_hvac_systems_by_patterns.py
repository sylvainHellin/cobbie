import ifcopenshell
import ifcopenshell.util.element
from typing import List, Dict, Any, Optional, Union

def analyze_hvac_systems_by_patterns(
    ifc_file: ifcopenshell.file,
    hvac_element_types: Optional[List[str]] = None,
    classification_rules: Optional[Dict[str, List[str]]] = None,
    include_type_definitions: bool = True,
    max_examples_per_type: int = 3,
    case_sensitive: bool = False,
    sample_size: int = 1000
) -> Dict[str, Any]:
    """
    Analyzes HVAC systems in IFC models using pattern-based classification when formal system organization is incomplete or schema compatibility issues exist.
    
    This function handles the common BIM challenge where ventilation/HVAC elements exist but aren't properly organized into systems,
    requiring classification based on naming patterns and ObjectType attributes. It provides comprehensive breakdowns of HVAC components
    by type with counts and examples.
    
    Args:
        ifc_file: The loaded IFC model (ifcopenshell.file)
        hvac_element_types: List of IFC element types to analyze (defaults to common HVAC types)
        classification_rules: Dict mapping classification names to keyword patterns
        include_type_definitions: Whether to analyze type definitions for additional context
        max_examples_per_type: Maximum examples to show per classification
        case_sensitive: Whether keyword matching is case sensitive
        sample_size: Maximum elements to analyze per type for performance
    
    Returns:
        Dict containing:
        - 'summary': Overall counts and statistics
        - 'elements_by_type': Breakdown by IFC element type with classifications
        - 'type_definitions': Analysis of type definitions if requested
        - 'classification_details': Detailed breakdown by classification with counts and examples
    
    Example:
        >>> import ifcopenshell
        >>> model = ifcopenshell.open('ventilation.ifc')
        >>> result = analyze_hvac_systems_by_patterns(model)
        >>> print(f"Total HVAC elements: {result['summary']['total_elements']}")
    """
    
    # Default HVAC element types if not provided
    if hvac_element_types is None:
        hvac_element_types = ['IfcFlowTerminal', 'IfcFlowController', 'IfcFlowSegment', 'IfcFlowFitting']
    
    # Default classification rules if not provided
    if classification_rules is None:
        classification_rules = {
            'Air Valve': ['ventiel', 'valve'],
            'Fire Damper': ['fire', 'brand'],
            'Control Damper': ['damper', 'klep'],
            'Air Diffuser': ['diffuser', 'spreider'],
            'Air Grille': ['grille', 'rooster'],
            'Air Terminal': ['terminal'],
            'Air Duct': ['duct', 'kanaal'],
            'Pipe': ['pipe', 'leiding'],
            'Tee Fitting': ['tee', 't-stuk'],
            'Elbow Fitting': ['elbow', 'bocht'],
            'Reducer Fitting': ['reducer', 'reductie'],
            'Transition Fitting': ['transition'],
            'Other Controller': [],
            'Other Fitting': [],
            'Other Air Terminal': [],
            'Other Segment': []
        }
    
    result = {
        'summary': {'total_elements': 0, 'elements_by_type': {}, 'total_classifications': 0},
        'elements_by_type': {},
        'type_definitions': {},
        'classification_details': {}
    }
    
    try:
        # Analyze each HVAC element type
        for element_type in hvac_element_types:
            try:
                elements = ifc_file.by_type(element_type)
                if not elements:
                    continue
                    
                # Limit sample size for performance
                elements_to_analyze = elements[:sample_size]
                
                type_analysis = {
                    'total_count': len(elements),
                    'analyzed_count': len(elements_to_analyze),
                    'classifications': {},
                    'unclassified': {'count': 0, 'examples': []}
                }
                
                # Classify elements based on naming patterns
                for element in elements_to_analyze:
                    name = getattr(element, 'Name', '') or ''
                    obj_type = getattr(element, 'ObjectType', '') or ''
                    
                    # Combine name and object type for classification
                    text_to_classify = f"{name} {obj_type}"
                    if not case_sensitive:
                        text_to_classify = text_to_classify.lower()
                    
                    classified = False
                    
                    # Try to classify using rules
                    for classification_name, keywords in classification_rules.items():
                        if not keywords:  # Handle "Other" categories
                            continue
                            
                        match_found = False
                        for keyword in keywords:
                            search_keyword = keyword if case_sensitive else keyword.lower()
                            if search_keyword in text_to_classify:
                                match_found = True
                                break
                        
                        if match_found:
                            if classification_name not in type_analysis['classifications']:
                                type_analysis['classifications'][classification_name] = {
                                    'count': 0,
                                    'examples': []
                                }
                            
                            type_analysis['classifications'][classification_name]['count'] += 1
                            
                            if len(type_analysis['classifications'][classification_name]['examples']) < max_examples_per_type:
                                type_analysis['classifications'][classification_name]['examples'].append({
                                    'Name': name,
                                    'ObjectType': obj_type,
                                    'GlobalId': getattr(element, 'GlobalId', '')
                                })
                            
                            classified = True
                            break
                    
                    # Handle unclassified elements
                    if not classified:
                        type_analysis['unclassified']['count'] += 1
                        if len(type_analysis['unclassified']['examples']) < max_examples_per_type:
                            type_analysis['unclassified']['examples'].append({
                                'Name': name,
                                'ObjectType': obj_type,
                                'GlobalId': getattr(element, 'GlobalId', '')
                            })
                
                result['elements_by_type'][element_type] = type_analysis
                result['summary']['elements_by_type'][element_type] = len(elements)
                result['summary']['total_elements'] += len(elements)
                
            except Exception as e:
                result['elements_by_type'][element_type] = {'error': str(e)}
        
        # Analyze type definitions if requested
        if include_type_definitions:
            type_definition_types = [
                'IfcAirTerminalType', 'IfcDamperType', 'IfcDuctFittingType', 
                'IfcDuctSegmentType', 'IfcAirTerminalBoxType'
            ]
            
            for type_def_type in type_definition_types:
                try:
                    type_defs = ifc_file.by_type(type_def_type)
                    if type_defs:
                        result['type_definitions'][type_def_type] = {
                            'count': len(type_defs),
                            'examples': []
                        }
                        
                        for type_def in type_defs[:max_examples_per_type]:
                            name = getattr(type_def, 'Name', '') or ''
                            result['type_definitions'][type_def_type]['examples'].append({
                                'Name': name,
                                'GlobalId': getattr(type_def, 'GlobalId', '')
                            })
                except Exception as e:
                    result['type_definitions'][type_def_type] = {'error': str(e)}
        
        # Aggregate classification details across all element types
        all_classifications = {}
        for element_type, type_data in result['elements_by_type'].items():
            if 'classifications' in type_data:
                for classification_name, class_data in type_data['classifications'].items():
                    if classification_name not in all_classifications:
                        all_classifications[classification_name] = {
                            'total_count': 0,
                            'by_element_type': {},
                            'examples': []
                        }
                    
                    all_classifications[classification_name]['total_count'] += class_data['count']
                    all_classifications[classification_name]['by_element_type'][element_type] = class_data['count']
                    
                    # Add examples (avoid duplicates)
                    for example in class_data['examples']:
                        if len(all_classifications[classification_name]['examples']) < max_examples_per_type:
                            example_copy = example.copy()
                            example_copy['ElementType'] = element_type
                            all_classifications[classification_name]['examples'].append(example_copy)
        
        result['classification_details'] = all_classifications
        result['summary']['total_classifications'] = len(all_classifications)
        
    except Exception as e:
        result['error'] = str(e)
    
    return result