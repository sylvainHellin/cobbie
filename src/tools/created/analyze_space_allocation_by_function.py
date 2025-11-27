import ifcopenshell
import ifcopenshell.util.element
from typing import List, Dict, Tuple, Optional, Any, Union

def analyze_space_allocation_by_function(
    ifc_file: ifcopenshell.file,
    function_property_sources: List[Tuple[str, str]] = [('ArchiCADProperties', 'Raumname'), ('AC_Pset_Allgemeiner_Raumstempel', 'Raumname'), ('Pset_SpaceCommon', 'Category')],
    area_property_sources: List[Tuple[str, str]] = [('BaseQuantities', 'NetFloorArea'), ('BaseQuantities', 'GrossFloorArea'), ('PSet_Revit_Dimensions', 'Area'), ('GSA Space Areas', 'GSA Space Areas'), ('ArchiCADQuantities', 'Area'), ('AC_Pset_Zone_Stamp_02_25', 'Measured Area')],
    exclude_generic_values: List[str] = ['Raumstempel', 'Leer', 'Allgemeines'],
    include_details: bool = True,
    sort_by: str = 'area',
    include_element_fields: bool = True,
    element_field_priority: List[str] = ['LongName', 'Name', 'ObjectType'],
    # Enhanced parameters with defaults for backward compatibility
    enable_attribute_access: bool = True,
    fallback_to_attributes: bool = True,
    additional_area_sources: Optional[List[Tuple[str, str]]] = None
) -> Dict[str, Any]:
    """
    Analyzes space allocation by functional classification in a BIM model.
    
    This function systematically discovers functional classifications from multiple sources including
    element fields and property sets, extracts area information, and provides comprehensive statistics
    about space allocation.
    
    Args:
        ifc_file: Loaded IFC model (ifcopenshell.file)
        function_property_sources: List of (property_set, property_name) tuples to search for functional classifications, in priority order
        area_property_sources: List of (property_set, property_name) tuples to search for area information, in priority order
        exclude_generic_values: List of generic values to exclude from functional classification
        include_details: Boolean to include individual space details in results
        sort_by: How to sort results ('area', 'count', 'function')
        include_element_fields: Boolean to control whether to check element fields for function data before property sets
        element_field_priority: List of element field names to check in priority order for functional classification
        enable_attribute_access: Boolean to enable direct IFC attribute access using ('__attribute__', 'AttributeName') syntax
        fallback_to_attributes: Boolean to enable fallback to basic attributes when property sets don't contain needed data
        additional_area_sources: Optional list of additional (property_set, property_name) tuples for area sources
    
    Returns:
        Dict containing:
        - 'total_spaces': Total number of spaces analyzed
        - 'total_area': Total building area
        - 'function_allocation': Dict of function names to allocation data (count, area, percentage, spaces)
        - 'space_details': List of individual space data (if include_details=True)
        - 'classification_sources': Dict showing which sources were used for each function
    
    Example:
        >>> import ifcopenshell
        >>> model = ifcopenshell.open('building.ifc')
        >>> result = analyze_space_allocation_by_function(model)
        >>> print(f"Total area: {result['total_area']:.2f} m\u00b2")
        >>> for func, data in result['function_allocation'].items():
        ...     print(f"{func}: {data['area']:.2f} m\u00b2 ({data['percentage']:.1f}%)")
    """
    try:
        # Initialize result structure
        result = {
            'total_spaces': 0,
            'total_area': 0.0,
            'function_allocation': {},
            'space_details': [],
            'classification_sources': {}
        }
        
        # Get all IfcSpace elements
        spaces = ifc_file.by_type('IfcSpace')
        result['total_spaces'] = len(spaces)
        
        if not spaces:
            return result
        
        # Enhanced area sources with NetFootprintArea and additional sources
        enhanced_area_sources = area_property_sources.copy()
        if ('BaseQuantities', 'NetFootprintArea') not in enhanced_area_sources:
            enhanced_area_sources.insert(0, ('BaseQuantities', 'NetFootprintArea'))
        
        # Add common quantity names
        common_quantities = [
            ('BaseQuantities', 'NetFloorArea'),
            ('BaseQuantities', 'GrossFloorArea'), 
            ('BaseQuantities', 'NetFootprintArea'),
            ('BaseQuantities', 'FloorArea'),
            ('Qto_SpaceBaseQuantities', 'NetFloorArea'),
            ('Qto_SpaceBaseQuantities', 'GrossFloorArea')
        ]
        
        for source in common_quantities:
            if source not in enhanced_area_sources:
                enhanced_area_sources.append(source)
        
        # Add additional area sources if provided
        if additional_area_sources:
            enhanced_area_sources.extend(additional_area_sources)
        
        # Process each space
        for space in spaces:
            space_data = {
                'id': space.id(),
                'name': getattr(space, 'Name', None),
                'long_name': getattr(space, 'LongName', None),
                'object_type': getattr(space, 'ObjectType', None),
                'function': None,
                'function_source': None,
                'area': None,
                'area_source': None
            }
            
            # Get property sets for this space
            try:
                psets = ifcopenshell.util.element.get_psets(space)
            except:
                psets = {}
            
            # Enhanced function finding with attribute access support
            function_found = False
            
            # Check element fields if enabled
            if include_element_fields:
                for field_name in element_field_priority:
                    field_value = getattr(space, field_name, None)
                    if field_value and str(field_value).strip() and str(field_value).strip() not in exclude_generic_values:
                        space_data['function'] = str(field_value).strip()
                        space_data['function_source'] = field_name
                        function_found = True
                        break
            
            # Check property sets with attribute access support
            if not function_found:
                for pset_name, prop_name in function_property_sources:
                    # Handle direct attribute access
                    if enable_attribute_access and pset_name == '__attribute__':
                        attr_value = getattr(space, prop_name, None)
                        if attr_value and str(attr_value).strip() and str(attr_value).strip() not in exclude_generic_values:
                            space_data['function'] = str(attr_value).strip()
                            space_data['function_source'] = f'attribute.{prop_name}'
                            function_found = True
                            break
                    # Handle regular property sets
                    elif pset_name in psets and prop_name in psets[pset_name]:
                        value = str(psets[pset_name][prop_name]).strip()
                        if value and value not in exclude_generic_values:
                            space_data['function'] = value
                            space_data['function_source'] = f'{pset_name}.{prop_name}'
                            function_found = True
                            break
            
            # Enhanced fallback logic
            if not function_found and fallback_to_attributes:
                # Try LongName first
                if space_data['long_name'] and str(space_data['long_name']).strip():
                    space_data['function'] = str(space_data['long_name']).strip()
                    space_data['function_source'] = 'LongName_fallback'
                    function_found = True
                # Then try Name
                elif space_data['name'] and str(space_data['name']).strip():
                    space_data['function'] = str(space_data['name']).strip()
                    space_data['function_source'] = 'Name_fallback'
                    function_found = True
                # Finally use ID
                else:
                    space_data['function'] = f'Space {space_data["id"]}'
                    space_data['function_source'] = 'ID_fallback'
            elif not function_found:
                space_data['function'] = f'Space {space_data["id"]}'
                space_data['function_source'] = 'ID_fallback'
            
            # Enhanced area finding with direct quantity access
            area_found = False
            
            # First try property sets with enhanced sources
            for pset_name, prop_name in enhanced_area_sources:
                if pset_name in psets and prop_name in psets[pset_name]:
                    try:
                        area_value = float(psets[pset_name][prop_name])
                        if area_value > 0:
                            space_data['area'] = area_value
                            space_data['area_source'] = f'{pset_name}.{prop_name}'
                            area_found = True
                            break
                    except (ValueError, TypeError):
                        continue
            
            # Fallback: try direct quantity access if property sets don't work
            if not area_found and fallback_to_attributes:
                try:
                    if space.IsDefinedBy:
                        for rel in space.IsDefinedBy:
                            if hasattr(rel, 'RelatingPropertyDefinition'):
                                prop_def = rel.RelatingPropertyDefinition
                                if hasattr(prop_def, 'Quantities'):
                                    for quantity in prop_def.Quantities:
                                        if quantity.Name in ['NetFootprintArea', 'NetFloorArea', 'GrossFloorArea', 'FloorArea']:
                                            if hasattr(quantity, 'AreaValue'):
                                                area_value = float(quantity.AreaValue)
                                                if area_value > 0:
                                                    space_data['area'] = area_value
                                                    space_data['area_source'] = f'quantity.{quantity.Name}'
                                                    area_found = True
                                                    break
                                if area_found:
                                    break
                except:
                    pass
            
            # Add to results if area was found
            if space_data['area'] is not None:
                result['total_area'] += space_data['area']
                
                # Add to function allocation
                func = space_data['function']
                if func not in result['function_allocation']:
                    result['function_allocation'][func] = {
                        'count': 0,
                        'area': 0.0,
                        'percentage': 0.0,
                        'spaces': [],
                        'sources': set()
                    }
                
                result['function_allocation'][func]['count'] += 1
                result['function_allocation'][func]['area'] += space_data['area']
                result['function_allocation'][func]['spaces'].append(space_data['id'])
                result['function_allocation'][func]['sources'].add(space_data['function_source'])
                
                # Track classification sources
                if func not in result['classification_sources']:
                    result['classification_sources'][func] = set()
                result['classification_sources'][func].add(space_data['function_source'])
                
                # Add space details if requested
                if include_details:
                    result['space_details'].append(space_data)
        
        # Calculate percentages
        if result['total_area'] > 0:
            for func_data in result['function_allocation'].values():
                func_data['percentage'] = (func_data['area'] / result['total_area']) * 100
                # Convert sets to lists for JSON serialization
                func_data['sources'] = list(func_data['sources'])
        
        # Convert classification sources sets to lists
        for func in result['classification_sources']:
            result['classification_sources'][func] = list(result['classification_sources'][func])
        
        # Sort function allocation
        if sort_by == 'area':
            sorted_funcs = sorted(result['function_allocation'].items(), key=lambda x: x[1]['area'], reverse=True)
        elif sort_by == 'count':
            sorted_funcs = sorted(result['function_allocation'].items(), key=lambda x: x[1]['count'], reverse=True)
        elif sort_by == 'function':
            sorted_funcs = sorted(result['function_allocation'].items(), key=lambda x: x[0].lower())
        else:
            sorted_funcs = result['function_allocation'].items()
        
        result['function_allocation'] = dict(sorted_funcs)
        
        return result
        
    except Exception as e:
        # Return error information
        return {
            'error': str(e),
            'total_spaces': 0,
            'total_area': 0.0,
            'function_allocation': {},
            'space_details': [],
            'classification_sources': {}
        }