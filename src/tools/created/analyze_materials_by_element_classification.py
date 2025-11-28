import ifcopenshell
import ifcopenshell.util.element
from typing import Dict, List, Tuple, Any, Optional, Union

def analyze_materials_by_element_classification(
    ifc_file: ifcopenshell.file,
    element_type: str,
    classification_property: Tuple[str, str],
    classification_mapping: Dict[str, str],
    material_property_sources: List[Tuple[str, str]],
    include_details: bool = False,
    max_examples: int = 3,
    case_sensitive: bool = False
) -> Dict[str, Any]:
    """
    Analyzes material distribution across IFC elements by extracting materials from property sets 
    and classifying elements based on specified criteria.
    
    This function handles the common BIM analysis pattern of determining what materials are 
    used in specific element categories (e.g., internal walls, exterior walls, slabs) and 
    their usage distribution. It supports multilingual property names and flexible classification logic.
    
    Args:
        ifc_file: Loaded IFC model (ifcopenshell.file)
        element_type: IFC element type to analyze (e.g., 'IfcWall', 'IfcSlab')
        classification_property: Tuple of (property_set_name, property_name) used to classify elements 
            (e.g., ('ArchiCADProperties', 'Ebene'))
        classification_mapping: Dict mapping property values to classifications 
            (e.g., {'Innenwände': 'Internal', 'Außenwände': 'External'})
        material_property_sources: List of tuples (property_set_name, property_name) for material extraction 
            (e.g., [('ArchiCADProperties', 'Baustoff / Mehrschichtiger Aufbau / Profil / Schraffur')])
        include_details: Boolean to include sample elements (default: False)
        max_examples: Maximum examples to include per classification (default: 3)
        case_sensitive: Boolean for case-sensitive matching (default: False)
    
    Returns:
        Dict containing:
        - total_elements: Total elements analyzed
        - classification_summary: Count of elements by classification
        - material_distribution: Materials used by classification with counts
        - examples: Sample elements with materials (if include_details=True)
    
    Example:
        >>> result = analyze_materials_by_element_classification(
        ...     ifc_file,
        ...     'IfcWall',
        ...     ('ArchiCADProperties', 'Ebene'),
        ...     {'Innenwände': 'Internal', 'Außenwände': 'External'},
        ...     [('ArchiCADProperties', 'Baustoff / Mehrschichtiger Aufbau / Profil / Schraffur')],
        ...     include_details=True
        ... )
        >>> print(f"Internal walls: {result['classification_summary']['Internal']}")
    """
    try:
        # Initialize result structure
        result = {
            'total_elements': 0,
            'classification_summary': {},
            'material_distribution': {},
            'examples': {}
        }
        
        # Get all elements of specified type
        elements = ifc_file.by_type(element_type)
        result['total_elements'] = len(elements)
        
        if not elements:
            return result
        
        # Process each element
        classified_elements = {}
        
        for element in elements:
            element_info = {
                'name': getattr(element, 'Name', 'Unknown'),
                'global_id': getattr(element, 'GlobalId', 'Unknown'),
                'classification': 'Unclassified',
                'materials': [],
                'property_sets': {}
            }
            
            try:
                # Get all property sets for the element
                psets = ifcopenshell.util.element.get_psets(element)
                
                # Extract classification
                class_pset_name, class_prop_name = classification_property
                if class_pset_name in psets and class_prop_name in psets[class_pset_name]:
                    class_value = str(psets[class_pset_name][class_prop_name])
                    
                    # Find matching classification
                    for mapping_key, classification in classification_mapping.items():
                        if case_sensitive:
                            if mapping_key in class_value:
                                element_info['classification'] = classification
                                break
                        else:
                            if mapping_key.lower() in class_value.lower():
                                element_info['classification'] = classification
                                break
                
                # Extract materials
                for mat_pset_name, mat_prop_name in material_property_sources:
                    if mat_pset_name in psets and mat_prop_name in psets[mat_pset_name]:
                        material_value = str(psets[mat_pset_name][mat_prop_name])
                        if material_value and material_value.strip():
                            element_info['materials'].append(material_value)
                
                # Store property sets for examples
                if include_details:
                    element_info['property_sets'] = psets
                
                # Group by classification
                classification = element_info['classification']
                if classification not in classified_elements:
                    classified_elements[classification] = []
                classified_elements[classification].append(element_info)
                
            except Exception as e:
                # Continue processing other elements if one fails
                continue
        
        # Build classification summary
        for classification, elements_list in classified_elements.items():
            result['classification_summary'][classification] = len(elements_list)
        
        # Build material distribution
        for classification, elements_list in classified_elements.items():
            if classification not in result['material_distribution']:
                result['material_distribution'][classification] = {}
            
            material_counts = {}
            for element in elements_list:
                for material in element['materials']:
                    if material not in material_counts:
                        material_counts[material] = 0
                    material_counts[material] += 1
            
            result['material_distribution'][classification] = material_counts
        
        # Add examples if requested
        if include_details:
            for classification, elements_list in classified_elements.items():
                result['examples'][classification] = elements_list[:max_examples]
        
        return result
        
    except Exception as e:
        # Return error information
        return {
            'error': str(e),
            'total_elements': 0,
            'classification_summary': {},
            'material_distribution': {},
            'examples': {}
        }