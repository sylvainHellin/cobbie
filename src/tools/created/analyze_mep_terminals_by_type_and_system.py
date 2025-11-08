import ifcopenshell
import ifcopenshell.util.element
import ifcopenshell.util.system
from typing import Dict, List, Any, Optional, Tuple


def analyze_mep_terminals_by_type_and_system(
    ifc_file: ifcopenshell.file,
    element_types: Optional[List[str]] = None,
    terminal_keywords: Optional[List[str]] = None,
    categorization_keywords: Optional[Dict[str, List[str]]] = None
) -> Dict[str, Any]:
    """
    Analyze MEP terminals in an IFC model by type and system distribution.
    
    This function identifies terminal elements (typically air terminals), categorizes them
    by their functional types (e.g., supply/return), analyzes their physical types,
    and determines their system connections.
    
    Args:
        ifc_file: An opened IFC file object
        element_types: List of IFC element types to search for terminals.
                    Defaults to ['IfcFlowTerminal'] for IFC2X3 compatibility.
        terminal_keywords: Keywords to identify terminal elements.
                        Defaults to ['air', 'terminal', 'diffuser', 'grille', 'vent'].
        categorization_keywords: Dictionary mapping category names to keywords for classification.
                               Defaults to supply/return categorization.
    
    Returns:
        Dictionary containing:
        - 'total_terminals': Total number of terminals found
        - 'physical_types': Dict of physical types with counts and percentages
        - 'functional_types': Dict of functional types (supply/return) with counts and percentages
        - 'system_distribution': Dict of system names with counts and percentages
        - 'terminals_by_system': Dict mapping system names to terminal details
        - 'unconnected_terminals': Count and percentage of terminals without system connections
        - 'sample_terminals': List of sample terminal details for each category
    
    Example:
        import ifcopenshell
        model = ifcopenshell.open('building.ifc')
        result = analyze_mep_terminals_by_type_and_system(model)
        print(f"Found {result['total_terminals']} terminals")
        print(f"Supply terminals: {result['functional_types']['Supply Air']['count']}")
    """
    # Set default parameters
    if element_types is None:
        element_types = ['IfcFlowTerminal']
    if terminal_keywords is None:
        terminal_keywords = ['air', 'terminal', 'diffuser', 'grille', 'vent']
    if categorization_keywords is None:
        categorization_keywords = {
            'Supply Air': ['supply'],
            'Return Air': ['return'],
            'Exhaust Air': ['exhaust'],
            'Other': []
        }
    
    try:
        # Initialize result structure
        result = {
            'total_terminals': 0,
            'physical_types': {},
            'functional_types': {},
            'system_distribution': {},
            'terminals_by_system': {},
            'unconnected_terminals': {'count': 0, 'percentage': 0.0},
            'sample_terminals': {}
        }
        
        # Find terminal elements
        all_terminals = []
        for element_type in element_types:
            try:
                elements = ifc_file.by_type(element_type)
                all_terminals.extend(elements)
            except Exception as e:
                print(f"Warning: Could not find elements of type {element_type}: {e}")
                continue
        
        # Filter for terminal elements using keywords
        terminal_elements = []
        for element in all_terminals:
            name = (element.Name or '').lower()
            obj_type = (element.ObjectType or '').lower()
            
            # Check if any terminal keyword matches
            is_terminal = any(
                keyword in name or keyword in obj_type 
                for keyword in terminal_keywords
            )
            
            if is_terminal:
                terminal_elements.append(element)
        
        result['total_terminals'] = len(terminal_elements)
        
        if result['total_terminals'] == 0:
            return result
        
        # Analyze physical types
        physical_type_counts = {}
        for element in terminal_elements:
            physical_type = element.ObjectType or 'Unknown Type'
            if physical_type not in physical_type_counts:
                physical_type_counts[physical_type] = 0
            physical_type_counts[physical_type] += 1
        
        # Calculate percentages for physical types
        for physical_type, count in physical_type_counts.items():
            percentage = (count / result['total_terminals']) * 100
            result['physical_types'][physical_type] = {
                'count': count,
                'percentage': round(percentage, 1)
            }
        
        # Categorize by functional type using keywords
        functional_type_counts = {}
        categorized_terminals = {category: [] for category in categorization_keywords.keys()}
        
        for element in terminal_elements:
            name = (element.Name or '').lower()
            obj_type = (element.ObjectType or '').lower()
            
            # Determine functional category
            assigned_category = None
            for category, keywords in categorization_keywords.items():
                if category == 'Other':
                    continue  # Skip 'Other' for initial assignment
                
                if any(keyword in name or keyword in obj_type for keyword in keywords):
                    assigned_category = category
                    break
            
            # If no category matched, assign to 'Other'
            if assigned_category is None:
                assigned_category = 'Other'
            
            categorized_terminals[assigned_category].append(element)
            
            if assigned_category not in functional_type_counts:
                functional_type_counts[assigned_category] = 0
            functional_type_counts[assigned_category] += 1
        
        # Calculate percentages for functional types
        for functional_type, count in functional_type_counts.items():
            percentage = (count / result['total_terminals']) * 100
            result['functional_types'][functional_type] = {
                'count': count,
                'percentage': round(percentage, 1)
            }
        
        # Analyze system connections
        system_counts = {}
        terminals_with_systems = []
        unconnected_count = 0
        
        for element in terminal_elements:
            try:
                systems = ifcopenshell.util.system.get_element_systems(element)
                
                if systems:
                    for system in systems:
                        system_name = system.Name or 'Unknown System'
                        if system_name not in system_counts:
                            system_counts[system_name] = 0
                            result['terminals_by_system'][system_name] = []
                        
                        system_counts[system_name] += 1
                        
                        # Store terminal details for this system
                        terminal_info = {
                            'id': element.id(),
                            'name': element.Name,
                            'object_type': element.ObjectType,
                            'functional_type': None
                        }
                        
                        # Determine functional type for this terminal
                        name = (element.Name or '').lower()
                        obj_type = (element.ObjectType or '').lower()
                        for category, keywords in categorization_keywords.items():
                            if category == 'Other':
                                continue
                            if any(keyword in name or keyword in obj_type for keyword in keywords):
                                terminal_info['functional_type'] = category
                                break
                        
                        if terminal_info['functional_type'] is None:
                            terminal_info['functional_type'] = 'Other'
                        
                        result['terminals_by_system'][system_name].append(terminal_info)
                        terminals_with_systems.append(element)
                else:
                    unconnected_count += 1
                    
            except Exception as e:
                print(f"Warning: Could not analyze systems for element {element.id()}: {e}")
                unconnected_count += 1
        
        # Calculate system distribution percentages
        for system_name, count in system_counts.items():
            percentage = (count / result['total_terminals']) * 100
            result['system_distribution'][system_name] = {
                'count': count,
                'percentage': round(percentage, 1)
            }
        
        # Calculate unconnected terminals percentage
        result['unconnected_terminals']['count'] = unconnected_count
        result['unconnected_terminals']['percentage'] = round(
            (unconnected_count / result['total_terminals']) * 100, 1
        )
        
        # Generate sample terminals for each category
        for category, elements in categorized_terminals.items():
            if elements:
                sample_elements = elements[:3]  # Take first 3 as samples
                result['sample_terminals'][category] = []
                
                for element in sample_elements:
                    try:
                        systems = ifcopenshell.util.system.get_element_systems(element)
                        system_names = [s.Name for s in systems] if systems else []
                        
                        result['sample_terminals'][category].append({
                            'id': element.id(),
                            'name': element.Name,
                            'object_type': element.ObjectType,
                            'systems': system_names
                        })
                    except Exception as e:
                        result['sample_terminals'][category].append({
                            'id': element.id(),
                            'name': element.Name,
                            'object_type': element.ObjectType,
                            'systems': ['Error retrieving systems']
                        })
        
        return result
        
    except Exception as e:
        # Return error information
        return {
            'error': f"Error analyzing MEP terminals: {str(e)}",
            'total_terminals': 0,
            'physical_types': {},
            'functional_types': {},
            'system_distribution': {},
            'terminals_by_system': {},
            'unconnected_terminals': {'count': 0, 'percentage': 0.0},
            'sample_terminals': {}
        }