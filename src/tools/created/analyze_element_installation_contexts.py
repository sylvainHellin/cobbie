import ifcopenshell
import ifcopenshell.util.element
from typing import List, Dict, Any, Optional


def analyze_element_installation_contexts(
    ifc_file: ifcopenshell.file,
    element_type: str,
    relationship_types: List[str] = ['ContainedInStructure', 'Decomposes', 'HasAssociations'],
    include_level_info: bool = True,
    group_by_context: bool = True
) -> Dict[str, Any]:
    """
    Analyzes the installation contexts of IFC elements by exploring their relationships to other elements and structures.
    
    This function answers questions like 'where are these elements installed?' or 'what are these elements connected to?'
    by examining ContainedInStructure, Decomposes, and HasAssociations relationships. It's particularly useful for
    understanding how elements like railings, fixtures, or equipment are integrated into the building structure.
    
    Args:
        ifc_file: Loaded IFC model (ifcopenshell.file)
        element_type: IFC element type string to analyze (e.g., 'IfcRailing', 'IfcFlowTerminal')
        relationship_types: List of relationship types to explore (default: ['ContainedInStructure', 'Decomposes', 'HasAssociations'])
        include_level_info: Whether to include building level information (default: True)
        group_by_context: Whether to group elements by their installation contexts (default: True)
    
    Returns:
        Dict containing:
        - elements: List of elements with their relationship contexts
        - context_groups: Elements grouped by installation context (if group_by_context=True)
        - summary: Statistics about context distribution
        - level_distribution: Distribution by building levels (if include_level_info=True)
    
    Example:
        >>> import ifcopenshell
        >>> model = ifcopenshell.open('building.ifc')
        >>> result = analyze_element_installation_contexts(model, 'IfcRailing')
        >>> print(f"Found {result['summary']['total_elements']} railings")
    """
    try:
        # Get all elements of the specified type
        elements = ifc_file.by_type(element_type)
        
        if not elements:
            return {
                'elements': [],
                'context_groups': {},
                'summary': {'total_elements': 0, 'total_contexts': 0},
                'level_distribution': {}
            }
        
        # Analyze each element's relationships
        analyzed_elements = []
        context_groups = {}
        level_distribution = {}
        
        for element in elements:
            element_info = {
                'id': element.id(),
                'GlobalId': getattr(element, 'GlobalId', None),
                'Name': getattr(element, 'Name', None),
                'ObjectType': getattr(element, 'ObjectType', None),
                'PredefinedType': getattr(element, 'PredefinedType', None),
                'relationships': {}
            }
            
            # Get spatial container (level info)
            if include_level_info:
                try:
                    container = ifcopenshell.util.element.get_container(element)
                    if container:
                        element_info['level'] = container.Name
                        element_info['level_type'] = container.is_a()
                        
                        # Update level distribution
                        level_name = container.Name
                        if level_name not in level_distribution:
                            level_distribution[level_name] = {'count': 0, 'elements': []}
                        level_distribution[level_name]['count'] += 1
                        level_distribution[level_name]['elements'].append(element.Name)
                    else:
                        element_info['level'] = 'Unknown'
                        element_info['level_type'] = 'Unknown'
                except:
                    element_info['level'] = 'Unknown'
                    element_info['level_type'] = 'Unknown'
            
            # Analyze specified relationship types
            for rel_type in relationship_types:
                if hasattr(element, rel_type):
                    relationships = getattr(element, rel_type)
                    if relationships:
                        element_info['relationships'][rel_type] = []
                        
                        # Handle tuple of relationships
                        for rel in relationships:
                            try:
                                rel_info = {
                                    'id': rel.id(),
                                    'type': rel.is_a(),
                                    'name': getattr(rel, 'Name', None)
                                }
                                
                                # Get related object based on relationship type
                                if hasattr(rel, 'RelatingStructure'):
                                    related = rel.RelatingStructure
                                    rel_info['related_object'] = {
                                        'id': related.id(),
                                        'type': related.is_a(),
                                        'name': getattr(related, 'Name', None)
                                    }
                                    
                                    # Group by context if requested
                                    if group_by_context:
                                        context_key = f"{rel_type}_{related.is_a()}_{related.Name}"
                                        if context_key not in context_groups:
                                            context_groups[context_key] = []
                                        context_groups[context_key].append(element_info)
                                        
                                elif hasattr(rel, 'RelatingObject'):
                                    related = rel.RelatingObject
                                    rel_info['related_object'] = {
                                        'id': related.id(),
                                        'type': related.is_a(),
                                        'name': getattr(related, 'Name', None)
                                    }
                                    
                                    # Group by context if requested
                                    if group_by_context:
                                        context_key = f"{rel_type}_{related.is_a()}_{related.Name}"
                                        if context_key not in context_groups:
                                            context_groups[context_key] = []
                                        context_groups[context_key].append(element_info)
                                        
                                elif hasattr(rel, 'RelatedObjects'):
                                    related_objects = []
                                    for related in rel.RelatedObjects:
                                        related_objects.append({
                                            'id': related.id(),
                                            'type': related.is_a(),
                                            'name': getattr(related, 'Name', None)
                                        })
                                    rel_info['related_objects'] = related_objects
                                
                                element_info['relationships'][rel_type].append(rel_info)
                                    
                            except Exception as e:
                                # Skip problematic relationships but continue processing
                                continue
            
            analyzed_elements.append(element_info)
        
        # Create summary
        summary = {
            'total_elements': len(analyzed_elements),
            'total_contexts': len(context_groups) if group_by_context else 0,
            'relationship_types_found': list(set(
                rel_type 
                for elem in analyzed_elements 
                for rel_type in elem['relationships'].keys()
            )),
            'levels_found': list(level_distribution.keys()) if include_level_info else []
        }
        
        result = {
            'elements': analyzed_elements,
            'summary': summary
        }
        
        if group_by_context:
            result['context_groups'] = context_groups
        else:
            result['context_groups'] = {}
            
        if include_level_info:
            result['level_distribution'] = level_distribution
        else:
            result['level_distribution'] = {}
        
        return result
        
    except Exception as e:
        return {
            'elements': [],
            'context_groups': {},
            'summary': {'total_elements': 0, 'total_contexts': 0, 'error': str(e)},
            'level_distribution': {}
        }