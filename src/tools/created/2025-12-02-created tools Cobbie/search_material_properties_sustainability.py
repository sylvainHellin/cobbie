import ifcopenshell
import ifcopenshell.util.element
from typing import List, Dict, Any, Optional, Union

def search_material_properties_sustainability(
    ifc_file: ifcopenshell.file,
    search_terms: List[str] = ['recycled', 'recycle', 'reclaimed', 'recovered', 'material', 'sustainability', 'green', 'environment', 'content'],
    element_types: Optional[List[str]] = None,
    include_direct_materials: bool = True,
    case_sensitive: bool = False,
    max_elements_per_type: int = 50,
    include_property_set_analysis: bool = True
) -> Dict[str, Any]:
    """
    Searches for material and sustainability-related properties across an IFC model using multiple strategies.
    
    This function handles the common BIM challenge of finding material information (including recycled content,
    sustainability data, environmental properties) that may be stored inconsistently across IfcMaterial elements,
    property sets, or element attributes. It provides a comprehensive search across direct material elements
    and property-based material information.
    
    Args:
        ifc_file: The loaded IFC model (ifcopenshell.file)
        search_terms: List of sustainability/material terms to search for
        element_types: Optional list of element types to search (default: searches all element types)
        include_direct_materials: Whether to include IfcMaterial elements in search
        case_sensitive: Whether search should be case sensitive
        max_elements_per_type: Maximum elements to analyze per type
        include_property_set_analysis: Whether to analyze all property sets for material relevance
    
    Returns:
        Dict containing:
        - 'direct_materials': List of IfcMaterial elements found
        - 'material_property_sets': List of property sets containing material-related terms
        - 'element_matches': Dictionary of element types with material property matches
        - 'sustainability_matches': Dictionary of elements with specific sustainability term matches
        - 'summary': Overall statistics and findings
    
    Example:
        import ifcopenshell
        model = ifcopenshell.open('model.ifc')
        results = search_material_properties_sustainability(model)
        print(f"Found {len(results['direct_materials'])} direct materials")
        print(f"Found {len(results['sustainability_matches'])} sustainability matches")
    """
    
    result = {
        'direct_materials': [],
        'material_property_sets': [],
        'element_matches': {},
        'sustainability_matches': {},
        'summary': {
            'total_elements_analyzed': 0,
            'total_property_sets_found': 0,
            'material_related_property_sets': 0,
            'elements_with_material_properties': 0,
            'elements_with_sustainability_properties': 0
        }
    }
    
    try:
        # 1. Search for direct IfcMaterial elements
        if include_direct_materials:
            direct_materials = ifc_file.by_type('IfcMaterial')
            for material in direct_materials:
                material_info = {
                    'id': material.id(),
                    'name': getattr(material, 'Name', None),
                    'description': getattr(material, 'Description', None),
                    'category': getattr(material, 'Category', None)
                }
                result['direct_materials'].append(material_info)
        
        # 2. Get all element types if not specified
        if element_types is None:
            # Discover element types in the model
            all_elements = ifc_file.by_type('IfcElement')
            element_type_counts = {}
            for element in all_elements:
                elem_type = element.is_a()
                element_type_counts[elem_type] = element_type_counts.get(elem_type, 0) + 1
            element_types = list(element_type_counts.keys())
        
        # 3. Search for material-related properties in elements
        all_property_sets = set()
        
        for element_type in element_types:
            try:
                elements = ifc_file.by_type(element_type)
                elements_analyzed = min(len(elements), max_elements_per_type)
                result['summary']['total_elements_analyzed'] += elements_analyzed
                
                element_matches = []
                sustainability_matches = []
                
                for element in elements[:elements_analyzed]:
                    try:
                        # Get property sets for this element
                        psets = ifcopenshell.util.element.get_psets(element)
                        
                        element_material_matches = []
                        element_sustainability_matches = []
                        
                        for pset_name, pset_properties in psets.items():
                            all_property_sets.add(pset_name)
                            
                            # Check if property set name contains material terms
                            pset_name_lower = pset_name.lower() if not case_sensitive else pset_name
                            if any(term in pset_name_lower for term in search_terms):
                                if pset_name not in result['material_property_sets']:
                                    result['material_property_sets'].append(pset_name)
                            
                            # Check individual properties
                            for prop_name, prop_value in pset_properties.items():
                                prop_name_str = str(prop_name)
                                prop_value_str = str(prop_value)
                                
                                prop_name_search = prop_name_str.lower() if not case_sensitive else prop_name_str
                                prop_value_search = prop_value_str.lower() if not case_sensitive else prop_value_str
                                
                                # Check for material-related terms
                                if any(term in prop_name_search or term in prop_value_search for term in search_terms):
                                    element_material_matches.append({
                                        'property_set': pset_name,
                                        'property_name': prop_name_str,
                                        'property_value': prop_value_str,
                                        'matched_terms': [term for term in search_terms if term in prop_name_search or term in prop_value_search]
                                    })
                                
                                # Check specifically for sustainability terms
                                sustainability_terms = ['recycled', 'recycle', 'reclaimed', 'recovered', 'sustainability', 'green', 'environment']
                                if any(term in prop_name_search or term in prop_value_search for term in sustainability_terms):
                                    element_sustainability_matches.append({
                                        'property_set': pset_name,
                                        'property_name': prop_name_str,
                                        'property_value': prop_value_str,
                                        'matched_terms': [term for term in sustainability_terms if term in prop_name_search or term in prop_value_search]
                                    })
                        
                        if element_material_matches:
                            element_matches.append({
                                'element_id': element.id(),
                                'element_type': element_type,
                                'matches': element_material_matches
                            })
                        
                        if element_sustainability_matches:
                            sustainability_matches.append({
                                'element_id': element.id(),
                                'element_type': element_type,
                                'matches': element_sustainability_matches
                            })
                    
                    except Exception as e:
                        # Continue with next element if there's an error
                        continue
                
                if element_matches:
                    result['element_matches'][element_type] = element_matches
                    result['summary']['elements_with_material_properties'] += len(element_matches)
                
                if sustainability_matches:
                    result['sustainability_matches'][element_type] = sustainability_matches
                    result['summary']['elements_with_sustainability_properties'] += len(sustainability_matches)
            
            except Exception as e:
                # Continue with next element type if there's an error
                continue
        
        # 4. Update summary statistics
        result['summary']['total_property_sets_found'] = len(all_property_sets)
        result['summary']['material_related_property_sets'] = len(result['material_property_sets'])
        
        # 5. Additional property set analysis if requested
        if include_property_set_analysis:
            # Analyze all property sets for material relevance
            material_related_sets = []
            for pset_name in all_property_sets:
                pset_name_lower = pset_name.lower() if not case_sensitive else pset_name
                if any(term in pset_name_lower for term in search_terms):
                    if pset_name not in material_related_sets:
                        material_related_sets.append(pset_name)
            
            result['material_property_sets'] = list(set(result['material_property_sets'] + material_related_sets))
    
    except Exception as e:
        result['error'] = str(e)
    
    return result