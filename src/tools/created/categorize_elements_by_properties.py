import ifcopenshell
import ifcopenshell.util.element
import ifcopenshell.util.classification
from typing import Dict, List, Optional, Any, Tuple
import re

def categorize_elements_by_properties(
    ifc_file,
    element_type: str,
    category_keywords: Optional[List[str]] = None,
    include_classification: bool = True
) -> Tuple[Dict[str, List[Dict[str, Any]]], Dict[str, Any]]:
    """
    Analyzes IFC elements of a specified type and categorizes them based on their properties.
    
    This function extracts properties from multiple sources (Name, ObjectType, PredefinedType, 
    Classification) and groups elements into categories using intelligent fallback logic.
    
    Args:
        ifc_file: The loaded IFC model (ifcopenshell.file)
        element_type: String specifying the IFC element type to analyze (e.g., 'IfcFlowTerminal')
        category_keywords: Optional list of keywords to filter for specific categories 
                          (e.g., ['sanitary', 'toilet', 'sink']). If None, all elements are included.
        include_classification: Boolean to include property set classification in categorization
    
    Returns:
        Tuple containing:
        - Dict mapping category names to lists of element information (id, name, properties)
        - Dict with summary statistics (total_elements, total_categories)
    
    Example:
        >>> import ifcopenshell
        >>> model = ifcopenshell.open('model.ifc')
        >>> categories, summary = categorize_elements_by_properties(
        ...     model, 'IfcFlowTerminal', ['sanitary', 'toilet', 'sink']
        ... )
        >>> print(f"Found {summary['total_elements']} elements in {summary['total_categories']} categories")
    """
    try:
        # Initialize result structures
        categories: Dict[str, List[Dict[str, Any]]] = {}
        total_elements = 0
        
        # Get all elements of the specified type
        try:
            elements = ifc_file.by_type(element_type)
        except Exception as e:
            raise ValueError(f"Invalid element type '{element_type}': {str(e)}")
        
        # Process each element
        for element in elements:
            total_elements += 1
            
            # Extract basic properties
            element_info = {
                'id': element.id(),
                'name': element.Name if element.Name else 'Unnamed',
                'object_type': element.ObjectType if element.ObjectType else 'Unknown',
                'predefined_type': getattr(element, 'PredefinedType', 'NOTDEFINED') or 'NOTDEFINED'
            }
            
            # Get classification from property sets if requested
            classification = 'None'
            if include_classification:
                try:
                    # Get property sets
                    psets = ifcopenshell.util.element.get_psets(element)
                    
                    # Look for classification in property sets
                    for pset_name, pset_data in psets.items():
                        if isinstance(pset_data, dict):
                            for prop_name, prop_value in pset_data.items():
                                if 'type' in prop_name.lower() or 'classification' in prop_name.lower():
                                    if prop_value is not None:
                                        classification = str(prop_value)
                                        break
                        if classification != 'None':
                            break
                except Exception:
                    # If property set access fails, continue with 'None'
                    pass
            
            element_info['classification'] = classification
            
            # Get classification references if available
            try:
                classification_refs = ifcopenshell.util.classification.get_references(element)
                if classification_refs:
                    element_info['classification_references'] = [
                        {
                            'system': ref.ReferencedSource.Name if hasattr(ref, 'ReferencedSource') and ref.ReferencedSource else 'Unknown',
                            'identification': ref.Identification if hasattr(ref, 'Identification') else '',
                            'name': ref.Name if hasattr(ref, 'Name') else ''
                        }
                        for ref in classification_refs
                    ]
            except Exception:
                element_info['classification_references'] = []
            
            # Determine category using intelligent fallback logic
            category = _determine_category(element_info, category_keywords)
            
            # Skip if category doesn't match keywords (when keywords are provided)
            if category_keywords and not _matches_keywords(category, category_keywords):
                total_elements -= 1  # Don't count this element
                continue
            
            # Add element to category
            if category not in categories:
                categories[category] = []
            
            categories[category].append(element_info)
        
        # Create summary statistics
        summary = {
            'total_elements': total_elements,
            'total_categories': len(categories),
            'element_type': element_type,
            'filtered_by_keywords': category_keywords is not None
        }
        
        return categories, summary
        
    except Exception as e:
        raise RuntimeError(f"Error categorizing elements: {str(e)}")

def _determine_category(element_info: Dict[str, Any], category_keywords: Optional[List[str]] = None) -> str:
    """
    Helper function to determine the category of an element using intelligent fallback logic.
    
    Priority order:
    1. Classification from property sets
    2. ObjectType
    3. PredefinedType (if not NOTDEFINED)
    4. Name (extract meaningful part)
    5. 'Uncategorized' as fallback
    """
    # Try classification first
    if element_info.get('classification') and element_info['classification'] != 'None':
        return element_info['classification']
    
    # Try ObjectType
    if element_info.get('object_type') and element_info['object_type'] != 'Unknown':
        return element_info['object_type']
    
    # Try PredefinedType
    if (element_info.get('predefined_type') and 
        element_info['predefined_type'] != 'NOTDEFINED' and 
        element_info['predefined_type'] != 'NOTDEFINED'):
        return element_info['predefined_type']
    
    # Try to extract meaningful part from Name
    name = element_info.get('name', '')
    if name and name != 'Unnamed':
        # Remove ID numbers and special characters, keep meaningful part
        # Split by common delimiters and take the first meaningful part
        parts = re.split(r'[:\-_]', name)
        for part in parts:
            part = part.strip()
            # Skip parts that are just numbers or very short
            if part and len(part) > 2 and not part.isdigit():
                return part
        # If no meaningful part found, return the first part
        if parts:
            return parts[0].strip()
    
    # Fallback
    return 'Uncategorized'

def _matches_keywords(category: str, keywords: List[str]) -> bool:
    """
    Helper function to check if a category matches any of the provided keywords.
    """
    category_lower = category.lower()
    for keyword in keywords:
        if keyword.lower() in category_lower:
            return True
    return False