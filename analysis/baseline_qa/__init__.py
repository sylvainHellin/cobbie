"""
Baseline QA System for BIM Information Extraction.

A static summary approach for BIM-QA as a baseline comparison.
The system extracts a one-time model summary from each IFC file
and passes it as context to the LLM for every question.
"""

from analysis.baseline_qa.baseline_bim_qas import baseline_bim_qas
from analysis.baseline_qa.ifc_summary import (
    extract_model_summary,
    format_summary_for_llm,
    get_or_create_summary,
)

__all__ = [
    "baseline_bim_qas",
    "extract_model_summary",
    "format_summary_for_llm",
    "get_or_create_summary",
]
