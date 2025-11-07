import ifcopenshell
import ifcopenshell.util.element
from typing import Dict, List, Any, Optional, Union

def get_equipment_types_by_keywords(
    ifc_file: ifcopenshell.file,
    element_type: str,
    equipment_keywords: List[str],
    category_field: str = 'ObjectType',
    include_details: bool = False,
    case_sensitive: bool = False
) -> Dict[str, Any]:
    """
    Finds and categorizes specific equipment types within broader IFC element categories using semantic keyword filtering.
    
    This function is designed to answer questions like 'what types of switches/outlets/fixtures are installed?' 
    by searching for equipment using domain-specific keywords and returning categorized results with quantities.
    It combines keyword filtering, categorization, and counting into a single operation optimized for equipment analysis.
    
    Args:
        ifc_file: Loaded IFC model (ifcopenshell.file)
        element_type: IFC element type to search within (e.g., 'IfcFlowTerminal', 'IfcDistributionControlElement')
        equipment_keywords: List of keywords to identify equipment types (e.g., ['switch', 'outlet', 'fixture'])
        category_field: Field to categorize by (default: 'ObjectType')
        include_details: Whether to include element details (default: False)
        case_sensitive: Whether keyword matching is case sensitive (default: False)
    
    Returns:
        Dict with:
        - 'equipment_types': Dict mapping equipment type names to counts
        - 'total_count': Total number of equipment elements found
        - 'details': Optional list of element details if include_details=True
        - 'search_summary': Summary of search parameters and results
    
    Example:
        >>> import ifcopenshell
        >>> model = ifcopenshell.open('building.ifc')
        >>> result = get_equipment_types_by_keywords(
        ...     ifc_file=model,
        ...     element_type='IfcFlowTerminal',
        ...     equipment_keywords=['switch'],
        ...     category_field='ObjectType'
        ... )
        >>> print(result['equipment_types'])
        {'Single Pole': 94, 'Three Way': 5}
    
    Use cases:
    - Finding electrical switches/outlets and their quantities
    - Identifying types of lighting fixtures or HVAC equipment
    - Categorizing plumbing fixtures or fire protection devices
    - Any equipment classification task requiring semantic keyword matching
    """
    try:
        # Get all elements of the specified type
        elements = ifc_file.by_type(element_type)
        
        # Prepare keywords for matching
        if not case_sensitive:
            keywords_lower = [kw.lower() for kw in equipment_keywords]
        
        # Find elements containing keywords
        matching_elements = []
        element_details = []
        
        for element in elements:
            # Get searchable text from various fields
            searchable_text = []
            
            # Add basic attributes
            if hasattr(element, 'Name') and element.Name:
                searchable_text.append(str(element.Name))
            if hasattr(element, 'ObjectType') and element.ObjectType:
                searchable_text.append(str(element.ObjectType))
            if hasattr(element, 'PredefinedType') and element.PredefinedType:
                searchable_text.append(str(element.PredefinedType))
            if hasattr(element, 'Description') and element.Description:
                searchable_text.append(str(element.Description))
            
            # Add property set values
            try:
                psets = ifcopenshell.util.element.get_psets(element)
                for pset_name, pset_data in psets.items():
                    for prop_name, prop_value in pset_data.items():
                        if prop_value is not None:
                            searchable_text.append(str(prop_value))
            except Exception:
                pass  # Skip if can't get properties
            
            # Check if any keyword matches
            text_to_search = ' '.join(searchable_text)
            if not case_sensitive:
                text_to_search = text_to_search.lower()
            
            keyword_found = False
            if case_sensitive:
                keyword_found = any(kw in text_to_search for kw in equipment_keywords)
            else:
                keyword_found = any(kw in text_to_search for kw in keywords_lower)
            
            if keyword_found:
                matching_elements.append(element)
                
                if include_details:
                    element_info = {
                        'id': element.id(),
                        'type': element.is_a(),
                        'name': getattr(element, 'Name', None),
                        'object_type': getattr(element, 'ObjectType', None),
                        'predefined_type': getattr(element, 'PredefinedType', None)
                    }
                    
                    # Add category field value
                    if hasattr(element, category_field):
                        element_info[category_field] = getattr(element, category_field, None)
                    
                    element_details.append(element_info)
        
        # Categorize elements by the specified field
        equipment_types = {}
        uncategorized_count = 0
        
        for element in matching_elements:
            # Get category value
            category_value = None
            
            if hasattr(element, category_field):
                category_value = getattr(element, category_field, None)
            
            # If no category value, try to get from properties
            if not category_value:
                try:
                    psets = ifcopenshell.util.element.get_psets(element)
                    for pset_data in psets.values():
                        if category_field in pset_data:
                            category_value = pset_data[category_field]
                            break
                except Exception:
                    pass
            
            # Categorize
            if category_value:
                category_str = str(category_value)
                equipment_types[category_str] = equipment_types.get(category_str, 0) + 1
            else:
                uncategorized_count += 1
        
        # Add uncategorized if any
        if uncategorized_count > 0:
            equipment_types['Uncategorized'] = uncategorized_count
        
        # Prepare search summary
        search_summary = {
            'element_type': element_type,
            'keywords_searched': equipment_keywords,
            'category_field': category_field,
            'total_elements_scanned': len(elements),
            'matching_elements_found': len(matching_elements),
            'categories_found': len(equipment_types)
        }
        
        result = {
            'equipment_types': equipment_types,
            'total_count': len(matching_elements),
            'search_summary': search_summary
        }
        
        if include_details:
            result['details'] = element_details
        
        return result
        
    except Exception as e:
        return {
            'equipment_types': {},
            'total_count': 0,
            'search_summary': {
                'error': str(e),
                'element_type': element_type,
                'keywords_searched': equipment_keywords
            }
        }