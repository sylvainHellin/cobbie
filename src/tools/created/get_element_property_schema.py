import ifcopenshell.util.element
from typing import Dict, List, Any, Optional


def get_element_property_schema(
    model: Any, 
    ifc_type: str, 
    sample_size: int = 3, 
    filter_keywords: Optional[List[str]] = None,
    property_name_keywords: Optional[List[str]] = None
) -> Dict[str, List[str]]:
    """Discovers all property sets and properties available for a given IFC element type.
    
    Samples multiple elements of the specified type and collects all unique property
    sets and properties defined on them. Use this to understand what properties exist
    in a model before querying specific values.

    Args:
        model: The loaded IFC model instance.
        ifc_type: The IFC class name to query (e.g., 'IfcWindow', 'IfcWall', 'IfcFooting').
        sample_size: Number of elements to sample for discovery (default: 3).
            Samples are taken to account for cases where different elements might have
            different property sets defined.
        filter_keywords: Optional list of strings to filter results. If provided,
            only property sets and properties where a keyword appears in the name
            (case-insensitive) will be returned. A property set is kept if its name
            matches OR if it contains at least one matching property.
        property_name_keywords: Optional list of strings to filter property names.
            If provided, only property sets containing at least one property whose
            name matches any keyword (case-insensitive) will be returned. Within
            matching sets, only properties with matching names are included. This
            filters only property names, not property set names.

    Returns:
        Dict[str, List[str]]: A dictionary where keys are property set names and
        values are alphabetically-sorted lists of unique property names available
        in those sets across the sampled elements. Returns empty dict if type not found
        or no matches found when filtering.

    Example:
        >>> # Get all properties for doors
        >>> schema = get_element_property_schema(model, 'IfcDoor')
        >>> # Returns: {'Pset_DoorCommon': ['IsExternal', 'Reference'], ...}
        
        >>> # Get only fire-related property sets or properties
        >>> fire_schema = get_element_property_schema(model, 'IfcDoor', filter_keywords=['fire', 'rating'])
        >>> # Returns: {'Pset_FireSafety': ['Duration', 'Integrity'], 
        >>> #          'Pset_DoorCommon': ['FireRating']}
        
        >>> # Get only properties with 'fire' in their name (not PSet names)
        >>> fire_props = get_element_property_schema(model, 'IfcDoor', property_name_keywords=['fire'])
        >>> # Returns: {'Pset_DoorCommon': ['FireRating']}
    """
    # Try to get all elements of the specified type
    try:
        elements = model.by_type(ifc_type)
    except RuntimeError:
        return {}
    
    # Return empty dict if no elements found
    if not elements:
        return {}
    
    # Determine how many elements to sample
    num_to_sample = min(sample_size, len(elements))
    
    # Dictionary to collect all unique property sets and their properties
    schema: Dict[str, List[str]] = {}
    
    skipped = 0
    
    # Sample elements and collect property schema
    for i in range(num_to_sample):
        element = elements[i]
        
        try:
            # Get all property sets for the element
            psets = ifcopenshell.util.element.get_psets(element)
            
            # Skip if no property sets found
            if not psets:
                continue
            
            # Collect property names from each property set
            for pset_name, properties in psets.items():
                # Initialize list for this property set if not exists
                if pset_name not in schema:
                    schema[pset_name] = []
                
                # Add all property names from this pset
                for prop_name in properties.keys():
                    if prop_name not in schema[pset_name]:
                        schema[pset_name].append(prop_name)
                        
        except (AttributeError, KeyError, RuntimeError):
            # Skip elements that can't be processed
            skipped += 1
            continue
    
    # Sort property names alphabetically for each property set
    for pset_name in schema:
        schema[pset_name].sort()
    
    # Apply filter_keywords first if provided
    if filter_keywords:
        # Pre-calculate lowercase keywords for case-insensitive matching
        keywords_lower = [k.lower() for k in filter_keywords]
        
        filtered_schema: Dict[str, List[str]] = {}
        
        for pset_name, prop_list in schema.items():
            # Check if property set name matches any keyword
            pset_matches = any(k in pset_name.lower() for k in keywords_lower)
            
            # Filter properties: keep only those that match keywords
            matching_props = [
                prop_name for prop_name in prop_list 
                if any(k in prop_name.lower() for k in keywords_lower)
            ]
            
            # Determine if this set should be included in results
            # Include if Pset Name matches OR if it contains matching properties
            if pset_matches:
                # If Pset name matches, include the full property list
                filtered_schema[pset_name] = prop_list
            elif matching_props:
                # Pset name didn't match, but specific properties did
                filtered_schema[pset_name] = matching_props
            # Else: skip this set entirely
        
        schema = filtered_schema
    
    # Apply property_name_keywords if provided
    if property_name_keywords:
        # Pre-calculate lowercase keywords for case-insensitive matching
        keywords_lower = [k.lower() for k in property_name_keywords]
        
        filtered_schema: Dict[str, List[str]] = {}
        
        for pset_name, prop_list in schema.items():
            # Only filter by property name, not pset name
            matching_props = [
                prop_name for prop_name in prop_list 
                if any(k in prop_name.lower() for k in keywords_lower)
            ]
            
            # Only include property sets that have matching properties
            if matching_props:
                filtered_schema[pset_name] = matching_props
        
        schema = filtered_schema

    # Report if any elements were skipped (but only if we got some results)
    if skipped > 0 and schema:
        print(f"Warning: Skipped {skipped}/{num_to_sample} elements due to errors")
    
    return schema