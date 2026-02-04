import ifcopenshell
import ifcopenshell.geom
import multiprocessing
from typing import List
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def check_space_validation_intersect(path_ifc_model: str) -> List[str]:
    """
    Check for spaces that incorrectly intersect with building components.
    
    This rule checks that space geometry and location are correct by detecting
    intersections with slabs, walls, or other components.
    
    Parameters:
    - Include: Wall, CurtainWall, Column, Slab, Roof
    - Tolerance: 0.03 m
    - Exclude: Components fully inside the space
    
    Args:
        path_ifc_model: Path to the IFC model file.
    
    Returns:
        List of IFC GUIDs of spaces that violate the rule (have incorrect
        intersections with building components).
    
    Example:
        >>> model_path = "/path/to/model.ifc"
        >>> violations = check_space_validation_intersect(model_path)
        >>> print(f"Found {len(violations)} violating spaces")
    """
    try:
        model = ifcopenshell.open(path_ifc_model)
    except Exception as e:
        logger.error(f"Failed to open IFC model: {e}")
        return []
    
    # Get spaces and building elements
    spaces = list(model.by_type('IfcSpace'))
    if not spaces:
        logger.info("No spaces found in model")
        return []
    
    builtin_elements = []
    for ifc_class in ['IfcWall', 'IfcCurtainWall', 'IfcColumn', 'IfcSlab', 'IfcRoof']:
        builtin_elements.extend(model.by_type(ifc_class))
    
    if not builtin_elements:
        logger.info("No building elements found in model")
        return []
    
    logger.info(f"Found {len(spaces)} spaces and {len(builtin_elements)} building elements")
    
    # Build geometry tree
    settings = ifcopenshell.geom.settings()
    tree = ifcopenshell.geom.tree()
    
    try:
        iterator = ifcopenshell.geom.iterator(settings, model, multiprocessing.cpu_count())
        if iterator.initialize():
            count = 0
            while True:
                element = iterator.get()
                tree.add_element(element)
                count += 1
                if not iterator.next():
                    break
            logger.info(f"Built geometry tree with {count} elements")
        else:
            logger.warning("Iterator failed to initialize, attempting element-by-element approach")
            # Fallback: build tree element by element
            skipped = 0
            for element in spaces + builtin_elements:
                try:
                    shape = ifcopenshell.geom.create_shape(settings, element)
                    tree.add_element(shape)
                except Exception:
                    skipped += 1
            if skipped > 0:
                logger.warning(f"Skipped {skipped} elements during tree creation")
    except Exception as e:
        logger.error(f"Failed to build geometry tree: {e}")
        return []
    
    # Detect intersections with tolerance 0.03
    try:
        clashes = tree.clash_intersection_many(
            spaces, 
            builtin_elements, 
            tolerance=0.03, 
            check_all=True
        )
        logger.info(f"Found {len(clashes)} intersection clashes")
    except Exception as e:
        logger.error(f"Failed to detect intersections: {e}")
        return []
    
    violating_space_guids = set()
    
    for clash in clashes:
        try:
            elem_a = clash.a
            elem_b = clash.b
            
            # Identify which element is the space using is_a()
            space_elem = None
            builtin_elem = None
            
            if hasattr(elem_a, 'is_a') and elem_a.is_a() == 'IfcSpace':
                space_elem = elem_a
                builtin_elem = elem_b
            elif hasattr(elem_b, 'is_a') and elem_b.is_a() == 'IfcSpace':
                space_elem = elem_b
                builtin_elem = elem_a
            else:
                continue
            
            # Try to extract GUID from space element
            space_guid = None
            
            # Method 1: Try direct GlobalId attribute
            if hasattr(space_elem, 'GlobalId'):
                space_guid = space_elem.GlobalId
            # Method 2: Try guid property
            elif hasattr(space_elem, 'guid'):
                space_guid = space_elem.guid
            # Method 3: Look up by matching with original spaces list
            else:
                for space in spaces:
                    if space.id() == getattr(space_elem, 'id', lambda: None)():
                        space_guid = space.GlobalId
                        break
            
            if not space_guid:
                continue
            
            # Check if builtin element is fully inside the space (exclude condition)
            # Look up the actual space entity from the model
            try:
                space_entity = model.by_guid(space_guid)
                if space_entity:
                    elements_inside = tree.select(space_entity, completely_within=True)
                    
                    # Check if builtin_elem is among elements_inside
                    builtin_in_inside = False
                    builtin_guid = None
                    
                    # Try to get builtin element's GUID
                    if hasattr(builtin_elem, 'GlobalId'):
                        builtin_guid = builtin_elem.GlobalId
                    elif hasattr(builtin_elem, 'guid'):
                        builtin_guid = builtin_elem.guid
                    
                    if builtin_guid:
                        for elem in elements_inside:
                            elem_guid = getattr(elem, 'GlobalId', None) or getattr(elem, 'guid', None)
                            if elem_guid == builtin_guid:
                                builtin_in_inside = True
                                break
                    
                    if builtin_in_inside:
                        # Component is fully inside space - exclude this violation
                        continue
            except Exception as e:
                logger.debug(f"Could not check containment for space {space_guid}: {e}")
            
            violating_space_guids.add(space_guid)
            
        except Exception as e:
            logger.debug(f"Error processing clash: {e}")
            continue
    
    result = list(violating_space_guids)
    logger.info(f"Returning {len(result)} violating space GUIDs")
    return result