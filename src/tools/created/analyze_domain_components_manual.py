import ifcopenshell
import ifcopenshell.util.element
from typing import List, Dict, Any, Optional

def analyze_domain_components_manual(
    ifc_file: ifcopenshell.file,
    domain_element_types: List[str],
    categorization_fields: List[str] = ['ObjectType', 'Name'],
    include_examples: bool = True,
    max_examples_per_category: int = 3,
    include_summary: bool = True,
    explore_model_first: bool = True
) -> Dict[str, Any]:
    """
    Analyzes domain-specific components in an IFC model using manually specified element types.
    
    This function implements a comprehensive analysis pattern: first exploring model structure,
    then analyzing specified element types with detailed categorization and comprehensive summaries.
    It's particularly useful when domain discovery functions fail or when users need precise control
    over which element types to include in the analysis.
    
    Args:
        ifc_file: Loaded IFC model (ifcopenshell.file)
        domain_element_types: List of IFC element types to analyze (e.g., ['IfcElectricDistributionBoard', 'IfcLightFixture'])
        categorization_fields: List of fields to categorize by (default: ['ObjectType', 'Name'])
        include_examples: Boolean to include example elements per category (default: True)
        max_examples_per_category: Maximum examples to show (default: 3)
        include_summary: Boolean to include overall summary (default: True)
        explore_model_first: Boolean to first explore all element types in model (default: True)
    
    Returns:
        Dict containing:
        - 'model_exploration': All element types found in model (if explore_model_first=True)
        - 'domain_analysis': Detailed breakdown by element type with categorization
        - 'summary': Overall counts and statistics (if include_summary=True)
        - 'total_components': Total number of domain components found
    
    Example:
        >>> ifc_file = ifcopenshell.open('model.ifc')
        >>> electrical_types = ['IfcElectricDistributionBoard', 'IfcLightFixture', 'IfcOutlet']
        >>> result = analyze_domain_components_manual(ifc_file, electrical_types)
        >>> print(f"Total electrical components: {result['total_components']}")
    """
    
    result = {
        'model_exploration': {},
        'domain_analysis': {},
        'summary': {},
        'total_components': 0
    }
    
    try:
        # Step 1: Explore model structure if requested
        if explore_model_first:
            all_types = set()
            for element in ifc_file:
                if element.is_a('IfcObjectDefinition') and not element.is_a('IfcRelationship'):
                    all_types.add(element.is_a())
            
            for element_type in sorted(all_types):
                count = len(ifc_file.by_type(element_type))
                result['model_exploration'][element_type] = count
        
        # Step 2: Analyze domain-specific element types
        total_components = 0
        
        for element_type in domain_element_types:
            elements = ifc_file.by_type(element_type)
            if not elements:
                continue
                
            element_analysis = {
                'total_count': len(elements),
                'categories': {},
                'examples': [] if include_examples else None
            }
            
            # Categorize elements by specified fields
            categories = {}
            for element in elements:
                category_key = 'Uncategorized'
                
                # Try to categorize by each field in order
                for field in categorization_fields:
                    if hasattr(element, field):
                        field_value = getattr(element, field)
                        if field_value:
                            category_key = str(field_value)
                            break
                
                if category_key not in categories:
                    categories[category_key] = []
                
                element_info = {
                    'Name': getattr(element, 'Name', '') or 'Unnamed',
                    'ObjectType': getattr(element, 'ObjectType', '') or 'N/A',
                    'GlobalId': getattr(element, 'GlobalId', '')
                }
                categories[category_key].append(element_info)
            
            # Store category information
            for category, items in categories.items():
                element_analysis['categories'][category] = {
                    'count': len(items),
                    'examples': items[:max_examples_per_category] if include_examples else None
                }
                if include_examples and len(items) > max_examples_per_category:
                    element_analysis['categories'][category]['additional_count'] = len(items) - max_examples_per_category
            
            # Add overall examples if requested
            if include_examples:
                element_analysis['examples'] = [
                    {
                        'Name': getattr(element, 'Name', '') or 'Unnamed',
                        'ObjectType': getattr(element, 'ObjectType', '') or 'N/A',
                        'GlobalId': getattr(element, 'GlobalId', '')
                    }
                    for element in elements[:max_examples_per_category]
                ]
            
            result['domain_analysis'][element_type] = element_analysis
            total_components += len(elements)
        
        result['total_components'] = total_components
        
        # Step 3: Generate summary if requested
        if include_summary:
            summary = {
                'total_element_types_analyzed': len([t for t in domain_element_types if ifc_file.by_type(t)]),
                'total_components': total_components,
                'breakdown_by_type': {},
                'breakdown_by_category': {}
            }
            
            # Breakdown by element type
            for element_type, analysis in result['domain_analysis'].items():
                summary['breakdown_by_type'][element_type] = analysis['total_count']
            
            # Aggregate all categories across all element types
            all_categories = {}
            for element_type, analysis in result['domain_analysis'].items():
                for category, info in analysis['categories'].items():
                    if category not in all_categories:
                        all_categories[category] = 0
                    all_categories[category] += info['count']
            
            summary['breakdown_by_category'] = all_categories
            result['summary'] = summary
        
        return result
        
    except Exception as e:
        # Add error information to result
        result['error'] = str(e)
        return result