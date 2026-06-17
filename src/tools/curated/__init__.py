"""Curated IFC helper library (tools axis).

The 15 helpers ranked by eval-set usage x success rate (see
`.agents/research/2026-06-16-tool-curation.md`), plus the literature tool.
Each helper takes the already-open ``model`` (an ``ifcopenshell.file``) as its
first argument; none holds module-level cache or global state.

In the tools arm these names are preloaded into the kernel namespace as ordinary
callables (CodeAct purity: the agent's only action is writing Python). They are
not registered as separate LangChain tools.
"""

from __future__ import annotations

# IFC util submodules used (some helpers reference them without importing).
import ifcopenshell.util.element  # noqa: F401
import ifcopenshell.util.unit  # noqa: F401

from src.tools.curated.calculate_total_quantity import calculate_total_quantity
from src.tools.curated.find_elements_by_ifc_class import find_elements_by_ifc_class
from src.tools.curated.find_elements_by_keywords import find_elements_by_keywords
from src.tools.curated.find_elements_by_pset import find_elements_by_pset
from src.tools.curated.get_building_summary import get_building_summary
from src.tools.curated.get_element_classification_breakdown import (
    get_element_classification_breakdown,
)
from src.tools.curated.get_element_container import get_element_container
from src.tools.curated.get_element_counts_by_type_object import (
    get_element_counts_by_type_object,
)
from src.tools.curated.get_element_properties import get_element_properties
from src.tools.curated.get_entity_metadata import get_entity_metadata
from src.tools.curated.get_storeys_names import get_storeys_names
from src.tools.curated.get_type_definitions_and_instances import (
    get_type_definitions_and_instances,
)
from src.tools.curated.list_object_types_for_ifc_entity import (
    list_object_types_for_ifc_entity,
)
from src.tools.curated.list_rooms import list_rooms
from src.tools.initial.query_ifcopenshell_documentation import query_ifcopenshell_docs

# Ordered: literature tool first, then the 14 ranked helpers (see curation note).
CURATED_TOOLS = [
    query_ifcopenshell_docs,
    find_elements_by_ifc_class,
    get_entity_metadata,
    get_element_properties,
    list_object_types_for_ifc_entity,
    get_element_classification_breakdown,
    get_building_summary,
    find_elements_by_pset,
    get_element_container,
    get_element_counts_by_type_object,
    find_elements_by_keywords,
    list_rooms,
    get_type_definitions_and_instances,
    get_storeys_names,
    calculate_total_quantity,
]

__all__ = [fn.__name__ for fn in CURATED_TOOLS] + ["CURATED_TOOLS"]
