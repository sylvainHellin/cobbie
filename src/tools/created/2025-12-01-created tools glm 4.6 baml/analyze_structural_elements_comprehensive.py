import ifcopenshell
import ifcopenshell.util.element
from typing import Dict, List, Optional, Any, Union

def analyze_structural_elements_comprehensive(
    ifc_file: ifcopenshell.file,
    structural_type_mapping: Optional[Dict[str, List[str]]] = None,
    include_details: bool = True,
    sort_by_count: bool = True,
    max_examples_per_type: int = 3,
    custom_element_types: Optional[List[str]] = None
) -> Dict[str, Any]:
    """
    Analyzes structural elements in an IFC model by discovering element types, filtering for structural categories,
    and providing comprehensive counts and categorization.
    
    This function implements a multi-strategy approach:
    1) Discovers all building element types in the model
    2) Filters for structural categories using predefined type mappings
    3) Counts elements by type with detailed categorization
    4) Provides comprehensive summary with totals and optional examples
    
    Args:
        ifc_file: Loaded IFC model (ifcopenshell.file)
        structural_type_mapping: Optional dict mapping structural categories to IFC types.
            Default includes common structural types like beams, columns, slabs, walls, etc.
        include_details: Boolean to include element examples and subtype breakdown (default: True)
        sort_by_count: Boolean to sort results by count (default: True)
        max_examples_per_type: Maximum examples to show per type (default: 3)
        custom_element_types: Optional list of additional element types to include in analysis
    
    Returns:
        Dict containing:
        - 'total_count': Total number of structural elements found
        - 'structural_categories': Dict mapping category names to counts and details
        - 'element_types': Dict of all element types found with counts
        - 'discovered_types': List of all building element types discovered in model
        - 'analysis_summary': Summary of analysis approach and results
    
    Example:
        >>> import ifcopenshell
        >>> model = ifcopenshell.open('building.ifc')
        >>> results = analyze_structural_elements_comprehensive(model)
        >>> print(f"Total structural elements: {results['total_count']}")
    """
    
    try:
        # Default structural type mapping if not provided
        if structural_type_mapping is None:
            structural_type_mapping = {
                'Beams': ['IfcBeam'],
                'Columns': ['IfcColumn'],
                'Slabs': ['IfcSlab'],
                'Walls': ['IfcWall', 'IfcWallStandardCase'],
                'Members': ['IfcMember', 'IfcStructuralMember', 'IfcStructuralCurveMember'],
                'Plates': ['IfcPlate', 'IfcStructuralSurfaceMember'],
                'Foundations': ['IfcFooting', 'IfcFoundation', 'IfcPile'],
                'Stairs': ['IfcStair', 'IfcStairFlight'],
                'Roofs': ['IfcRoof'],
                'Ramps': ['IfcRamp'],
                'CurtainWalls': ['IfcCurtainWall']
            }
        
        # Step 1: Discover all building element types in the model
        all_building_elements = ifc_file.by_type('IfcBuildingElement')
        discovered_types = set()
        element_type_counts = {}
        
        for element in all_building_elements:
            element_type = element.is_a()
            discovered_types.add(element_type)
            element_type_counts[element_type] = element_type_counts.get(element_type, 0) + 1
        
        # Add custom element types if provided
        if custom_element_types:
            for custom_type in custom_element_types:
                try:
                    custom_elements = ifc_file.by_type(custom_type)
                    if custom_elements:
                        discovered_types.add(custom_type)
                        element_type_counts[custom_type] = len(custom_elements)
                except:
                    continue
        
        # Step 2: Filter for structural categories and count elements
        structural_categories = {}
        total_structural_count = 0
        
        for category, ifc_types in structural_type_mapping.items():
            category_count = 0
            category_details = {
                'total_count': 0,
                'type_breakdown': {},
                'examples': [] if include_details else None
            }
            
            for ifc_type in ifc_types:
                if ifc_type in discovered_types:
                    type_count = element_type_counts.get(ifc_type, 0)
                    category_count += type_count
                    category_details['type_breakdown'][ifc_type] = type_count
                    
                    # Get examples if requested
                    if include_details and type_count > 0:
                        try:
                            elements = ifc_file.by_type(ifc_type)
                            for element in elements[:max_examples_per_type]:
                                example_info = {
                                    'Name': getattr(element, 'Name', None),
                                    'ObjectType': getattr(element, 'ObjectType', None),
                                    'GlobalId': getattr(element, 'GlobalId', None)
                                }
                                category_details['examples'].append(example_info)
                        except:
                            continue
            
            category_details['total_count'] = category_count
            total_structural_count += category_count
            
            if category_count > 0:
                structural_categories[category] = category_details
        
        # Step 3: Sort results if requested
        if sort_by_count:
            structural_categories = dict(
                sorted(structural_categories.items(), 
                      key=lambda x: x[1]['total_count'], reverse=True)
            )
            element_type_counts = dict(
                sorted(element_type_counts.items(), 
                      key=lambda x: x[1], reverse=True)
            )
        
        # Step 4: Prepare comprehensive result
        result = {
            'total_count': total_structural_count,
            'structural_categories': structural_categories,
            'element_types': element_type_counts,
            'discovered_types': sorted(list(discovered_types)),
            'analysis_summary': {
                'total_building_element_types': len(discovered_types),
                'structural_categories_found': len(structural_categories),
                'analysis_method': 'comprehensive_discovery_and_filtering'
            }
        }
        
        return result
        
    except Exception as e:
        # Return error information
        return {
            'error': str(e),
            'total_count': 0,
            'structural_categories': {},
            'element_types': {},
            'discovered_types': [],
            'analysis_summary': {
                'status': 'failed',
                'error_message': str(e)
            }
        }