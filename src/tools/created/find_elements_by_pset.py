import ifcopenshell
from typing import List, Dict, Optional, Any, Union


def find_elements_by_pset(
    model: ifcopenshell.file,
    pset_name: str,
    entity_type_filter: Optional[str] = None,
    return_all_psets: bool = False
) -> Union[List[Dict[str, Any]], Dict[str, int]]:
    """
    Finds all IFC elements that have a specific Property Set (Pset) defined,
    or returns a count of all property sets in the model.
    
    This function traverses IfcRelDefinesByProperties relationships to identify
    elements associated with named property sets. It's useful for queries like
    'which elements have fire rating data' or 'find all elements with Pset_WallCommon'.
    
    Args:
        model: The IFC model to search
        pset_name: Name of the property set to search for (e.g., 'Pset_FireRatingProperties').
                   Required when return_all_psets=False. Ignored when return_all_psets=True.
        entity_type_filter: Optional filter to only return elements of a specific type
                           (e.g., 'IfcDoor'). If None, all element types are returned.
                           Applied in both modes (discovery and search).
        return_all_psets: If True, returns a dictionary mapping each property set name to
                         the count of elements having that property set. If False (default),
                         returns the list of elements for the specified pset_name.
    
    Returns:
        If return_all_psets=False (default): List of dictionaries containing element information:
        - 'element': The ifcopenshell entity instance
        - 'name': Element name
        - 'type': Element type (is_a())
        - 'pset': The property set object
        - 'properties': Dict of property name-value pairs in the pset
        
        If return_all_psets=True: Dictionary mapping property set names to element counts:
        - Keys: Property set names (str)
        - Values: Count of elements with that property set (int)
    
    Example:
        >>> model = ifcopenshell.open('model.ifc')
        >>> # Find elements with specific pset
        >>> results = find_elements_by_pset(model, 'Pset_FireRatingProperties', 'IfcDoor')
        >>> for item in results:
        ...     print(f"{item['name']}: {item['properties']}")
        
        >>> # Get all psets with element counts
        >>> all_psets = find_elements_by_pset(model, 'AnyPset', return_all_psets=True)
        >>> for pset_name, count in all_psets.items():
        ...     print(f"{pset_name}: {count}")
        
        >>> # Get all psets but only for walls
        >>> wall_psets = find_elements_by_pset(model, 'AnyPset', entity_type_filter='IfcWall', return_all_psets=True)
    """
    # Input validation
    if model is None:
        raise ValueError("Model cannot be None")
    
    if not return_all_psets:
        if not pset_name or not isinstance(pset_name, str):
            raise ValueError("pset_name must be a non-empty string when return_all_psets=False")
    
    if entity_type_filter is not None and not isinstance(entity_type_filter, str):
        raise ValueError("entity_type_filter must be a string or None")
    
    # Get all IfcRelDefinesByProperties relationships
    try:
        rel_defines_by_props = model.by_type('IfcRelDefinesByProperties')
    except RuntimeError as e:
        raise RuntimeError(f"Failed to retrieve IfcRelDefinesByProperties: {e}")
    
    # If return_all_psets is True, return a dictionary of pset names to counts
    if return_all_psets:
        pset_counts: Dict[str, int] = {}
        skipped_count = 0
        
        for rel in rel_defines_by_props:
            try:
                # Check if this relationship has a RelatingPropertyDefinition
                if not hasattr(rel, 'RelatingPropertyDefinition'):
                    skipped_count += 1
                    continue
                
                pset = rel.RelatingPropertyDefinition
                
                # Check if it's an IfcPropertySet
                if pset.is_a() != 'IfcPropertySet':
                    continue
                
                if not hasattr(pset, 'Name'):
                    continue
                
                pset_name_val = pset.Name
                
                # Get the related objects (elements)
                if not hasattr(rel, 'RelatedObjects'):
                    skipped_count += 1
                    continue
                
                related_objects = rel.RelatedObjects
                
                # Process each related object and count if it matches the filter
                for obj in related_objects:
                    try:
                        obj_type = obj.is_a()
                        
                        # Apply entity type filter if specified
                        if entity_type_filter is not None and obj_type != entity_type_filter:
                            continue
                        
                        # Increment count for this pset
                        if pset_name_val not in pset_counts:
                            pset_counts[pset_name_val] = 0
                        pset_counts[pset_name_val] += 1
                        
                    except (AttributeError, RuntimeError):
                        skipped_count += 1
                        continue
                        
            except (AttributeError, RuntimeError):
                skipped_count += 1
                continue
        
        # Report skipped items if any
        if skipped_count > 0:
            print(f"Warning: Skipped {skipped_count} relationships or elements due to missing attributes or errors")
        
        return pset_counts
    
    # Original behavior: return list of elements for specific pset_name
    results: List[Dict[str, Any]] = []
    skipped_count = 0
    
    # Iterate through relationships to find matching property sets
    for rel in rel_defines_by_props:
        try:
            # Check if this relationship has a RelatingPropertyDefinition
            if not hasattr(rel, 'RelatingPropertyDefinition'):
                skipped_count += 1
                continue
            
            pset = rel.RelatingPropertyDefinition
            
            # Check if it's an IfcPropertySet with matching name
            if pset.is_a() != 'IfcPropertySet':
                continue
            
            if not hasattr(pset, 'Name'):
                continue
            
            if pset.Name != pset_name:
                continue
            
            # Get the related objects (elements)
            if not hasattr(rel, 'RelatedObjects'):
                skipped_count += 1
                continue
            
            related_objects = rel.RelatedObjects
            
            # Process each related object
            for obj in related_objects:
                try:
                    obj_type = obj.is_a()
                    
                    # Apply entity type filter if specified
                    if entity_type_filter is not None and obj_type != entity_type_filter:
                        continue
                    
                    # Extract element name with safe attribute access
                    obj_name = getattr(obj, 'Name', 'Unnamed')
                    if obj_name is None:
                        obj_name = 'Unnamed'
                    
                    # Extract properties from the pset
                    properties: Dict[str, Any] = {}
                    if hasattr(pset, 'HasProperties'):
                        for prop in pset.HasProperties:
                            try:
                                prop_name = getattr(prop, 'Name', 'Unknown')
                                if prop_name is None:
                                    prop_name = 'Unknown'
                                
                                # Extract property value
                                prop_value = None
                                if hasattr(prop, 'NominalValue') and prop.NominalValue is not None:
                                    try:
                                        prop_value = prop.NominalValue.wrappedValue
                                    except AttributeError:
                                        prop_value = str(prop.NominalValue)
                                
                                properties[prop_name] = prop_value
                            except AttributeError:
                                # Skip individual properties that fail to parse
                                continue
                    
                    # Build result dictionary
                    result = {
                        'element': obj,
                        'name': obj_name,
                        'type': obj_type,
                        'pset': pset,
                        'properties': properties
                    }
                    
                    results.append(result)
                    
                except (AttributeError, RuntimeError):
                    skipped_count += 1
                    continue
                    
        except (AttributeError, RuntimeError):
            skipped_count += 1
            continue
    
    # Report skipped items if any
    if skipped_count > 0:
        print(f"Warning: Skipped {skipped_count} relationships or elements due to missing attributes or errors")
    
    return results