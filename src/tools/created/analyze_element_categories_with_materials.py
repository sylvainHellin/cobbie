import ifcopenshell
import ifcopenshell.util.element
from typing import Dict, List, Any, Optional, Union

def analyze_element_categories_with_materials(
    ifc_file,
    element_type: str,
    categorization_field: str = 'ObjectType',
    include_property_sets: bool = True,
    include_type_object_analysis: bool = True,
    max_examples_per_category: int = 2,
    material_keywords: Optional[List[str]] = None,
    sort_by_count: bool = True,
    fallback_categorization_fields: List[str] = ['Name', 'PredefinedType', 'Description'],
    auto_select_best_field: bool = True,
    categorization_strategy: str = 'primary_only'
) -> Dict[str, Any]:
    """
    Analyzes IFC elements by categorizing them and extracting comprehensive material information for each category.
    This function combines element categorization with material analysis, handling both element-level and type-level material associations.
    Enhanced with intelligent categorization fallback mechanisms for robust handling of inconsistent IFC categorization data.
    
    Args:
        ifc_file: Loaded IFC model (ifcopenshell.file)
        element_type: IFC element type to analyze (e.g., 'IfcWall', 'IfcSlab')
        categorization_field: Field to categorize elements by (default: 'ObjectType', options: 'Name', 'PredefinedType', 'Description')
        include_property_sets: Boolean to include property set analysis (default: True)
        include_type_object_analysis: Boolean to analyze type object properties and materials (default: True)
        max_examples_per_category: Maximum example elements to show per category (default: 2)
        material_keywords: Optional keywords to filter material-related properties (default: ['material', 'finish', 'surface'])
        sort_by_count: Boolean to sort categories by element count (default: True)
        fallback_categorization_fields: List of alternative fields to try when primary field fails (default: ['Name', 'PredefinedType', 'Description'])
        auto_select_best_field: Boolean to automatically choose field with most unique non-null categories (default: True)
        categorization_strategy: Strategy for categorization (default: 'primary_only', options: 'primary_only', 'fallback_sequential', 'auto_best')
    
    Returns:
        Dict containing:
        - categories: Dict mapping category names to {count, examples, materials, properties}
        - total_elements: Total number of elements analyzed
        - elements_with_materials: Count of elements with direct material associations
        - material_summary: Summary of all materials found across categories
        - categorization_info: Information about which field was used and why (when using enhanced strategies)
    
    Example usage:
        import ifcopenshell
        model = ifcopenshell.open('building.ifc')
        
        # Traditional usage (backward compatible)
        result = analyze_element_categories_with_materials(
            model, 
            'IfcWall', 
            categorization_field='ObjectType'
        )
        
        # Enhanced usage with automatic field selection
        result = analyze_element_categories_with_materials(
            model,
            'IfcWall',
            categorization_strategy='auto_best'
        )
        
        # Enhanced usage with fallback
        result = analyze_element_categories_with_materials(
            model,
            'IfcWall',
            categorization_field='ObjectType',
            categorization_strategy='fallback_sequential'
        )
    """
    
    if material_keywords is None:
        material_keywords = ['material', 'finish', 'surface']
    
    try:
        # Get all elements of the specified type
        elements = ifc_file.by_type(element_type)
        total_elements = len(elements)
        
        if total_elements == 0:
            return {
                'categories': {},
                'total_elements': 0,
                'elements_with_materials': 0,
                'material_summary': {}
            }
        
        # Determine the best categorization field based on strategy
        selected_field = categorization_field
        categorization_info = {
            'strategy_used': categorization_strategy,
            'primary_field': categorization_field,
            'selected_field': categorization_field,
            'fallback_fields_tried': [],
            'field_analysis': {}
        }
        
        if categorization_strategy != 'primary_only':
            # Analyze all available fields
            all_fields_to_analyze = [categorization_field] + fallback_categorization_fields
            field_stats = {}
            
            for field in all_fields_to_analyze:
                null_count = 0
                unique_values = set()
                
                for element in elements:
                    try:
                        value = getattr(element, field, None)
                        if value is None or (isinstance(value, str) and value.strip() == ''):
                            null_count += 1
                        else:
                            unique_values.add(str(value))
                    except (AttributeError, TypeError):
                        null_count += 1
                
                null_percentage = (null_count / total_elements) * 100
                field_stats[field] = {
                    'null_count': null_count,
                    'null_percentage': null_percentage,
                    'unique_categories': len(unique_values),
                    'unique_values': list(unique_values)[:10]  # First 10 for inspection
                }
            
            categorization_info['field_analysis'] = field_stats
            
            if categorization_strategy == 'fallback_sequential':
                # Try primary field first, fallback if >50% null
                if field_stats[categorization_field]['null_percentage'] > 50:
                    for fallback_field in fallback_categorization_fields:
                        if fallback_field in field_stats:
                            categorization_info['fallback_fields_tried'].append(fallback_field)
                            if field_stats[fallback_field]['null_percentage'] <= 50:
                                selected_field = fallback_field
                                break
                    
                    # If all fallbacks still >50% null, use the one with least nulls
                    if selected_field == categorization_field:
                        best_field = min(field_stats.keys(), 
                                       key=lambda f: field_stats[f]['null_percentage'])
                        selected_field = best_field
                        categorization_info['fallback_fields_tried'].append(best_field)
                        
            elif categorization_strategy == 'auto_best':
                if auto_select_best_field:
                    # Select field with most unique non-null categories
                    best_field = max(field_stats.keys(), 
                                   key=lambda f: field_stats[f]['unique_categories'])
                    selected_field = best_field
                else:
                    # Select field with lowest null percentage
                    best_field = min(field_stats.keys(), 
                                   key=lambda f: field_stats[f]['null_percentage'])
                    selected_field = best_field
        
        categorization_info['selected_field'] = selected_field
        
        # Categorize elements using the selected field
        categories = {}
        elements_with_materials = 0
        all_materials_found = set()
        
        for element in elements:
            # Get categorization value from selected field
            category = getattr(element, selected_field, 'Unknown')
            if category is None or (isinstance(category, str) and category.strip() == ''):
                category = 'Unknown'
            else:
                category = str(category)
            
            if category not in categories:
                categories[category] = {
                    'count': 0,
                    'examples': [],
                    'materials': [],
                    'properties': {},
                    'type_materials': []
                }
            
            categories[category]['count'] += 1
            
            # Add examples (limit to max_examples_per_category)
            if len(categories[category]['examples']) < max_examples_per_category:
                example_info = {
                    'id': element.id,
                    'name': getattr(element, 'Name', 'Unknown'),
                    'global_id': getattr(element, 'GlobalId', 'Unknown')
                }
                categories[category]['examples'].append(example_info)
            
            # Extract materials from element
            try:
                element_materials = ifcopenshell.util.element.get_materials(element)
                if element_materials:
                    elements_with_materials += 1
                    for material in element_materials:
                        material_name = getattr(material, 'Name', 'Unknown')
                        if material_name not in categories[category]['materials']:
                            categories[category]['materials'].append(material_name)
                        all_materials_found.add(material_name)
            except Exception:
                # Continue if material extraction fails
                pass
            
            # Extract property sets if requested
            if include_property_sets and len(categories[category]['examples']) == 1:
                try:
                    psets = ifcopenshell.util.element.get_psets(element)
                    # Filter for material-related properties
                    filtered_psets = {}
                    for pset_name, properties in psets.items():
                        filtered_properties = {}
                        for prop_name, prop_value in properties.items():
                            prop_name_lower = prop_name.lower()
                            if any(keyword.lower() in prop_name_lower for keyword in material_keywords):
                                filtered_properties[prop_name] = prop_value
                        if filtered_properties:
                            filtered_psets[pset_name] = filtered_properties
                    
                    if filtered_psets:
                        categories[category]['properties'] = filtered_psets
                except Exception:
                    # Continue if property extraction fails
                    pass
            
            # Analyze type object if requested and this is the first element in category
            if include_type_object_analysis and len(categories[category]['examples']) == 1:
                try:
                    if hasattr(element, 'IsTypedBy') and element.IsTypedBy:
                        for rel in element.IsTypedBy:
                            if hasattr(rel, 'RelatingType'):
                                type_object = rel.RelatingType
                                type_materials = ifcopenshell.util.element.get_materials(type_object)
                                if type_materials:
                                    for material in type_materials:
                                        material_name = getattr(material, 'Name', 'Unknown')
                                        if material_name not in categories[category]['type_materials']:
                                            categories[category]['type_materials'].append(material_name)
                                        all_materials_found.add(material_name)
                except Exception:
                    # Continue if type object analysis fails
                    pass
        
        # Sort categories by count if requested
        if sort_by_count:
            categories = dict(sorted(categories.items(), key=lambda x: x[1]['count'], reverse=True))
        
        # Create material summary
        material_summary = {
            'total_unique_materials': len(all_materials_found),
            'materials': sorted(list(all_materials_found))
        }
        
        result = {
            'categories': categories,
            'total_elements': total_elements,
            'elements_with_materials': elements_with_materials,
            'material_summary': material_summary
        }
        
        # Add categorization info for enhanced strategies
        if categorization_strategy != 'primary_only':
            result['categorization_info'] = categorization_info
        
        return result
        
    except Exception as e:
        return {
            'categories': {},
            'total_elements': 0,
            'elements_with_materials': 0,
            'material_summary': {},
            'error': str(e)
        }