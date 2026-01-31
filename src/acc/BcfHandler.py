"""
BCF Handler Module
Handles all BCF (BIM Collaboration Format) operations including:
- Topic extraction and parsing
- Compliance issue management
- IFC GUID matching
- BCF analysis and prioritization
"""

from pathlib import Path
from collections import defaultdict
import os
import re
import ast
import json
import uuid
import zipfile
import shutil
import string
import xml.dom.minidom as minidom
import pandas as pd
import ifcopenshell
from typing import List, Optional, Dict, Union, Any

from config import ACC_RES_PATH, ACC_MODELS_PATH


class Topic:
    """
    Represents a single BCF topic with metadata and IFC references.
    """
    
    def __init__(self, topic_id: str, directory: Optional[Path] = None, description: Optional[str] = None) -> None:
        self.directory: Optional[Path] = directory
        self.path: Optional[Path] = Path(directory) / topic_id if directory else None
        self.id: str = topic_id
        self.title: Optional[str] = None
        self.description: Optional[str] = description
        self.author: Optional[str] = None
        self.snapshot: Optional[Path] = None
        self.ifc_guids: List[str] = []
        self.ifc_guids_info: Dict[str, Dict[str, str]] = {}  # Detailed info per GUID
        
        if self.description is None and self.path:
            self._extract_topic_data()
    
    def _extract_topic_data(self) -> None:
        """Extract topic metadata from BCF markup and viewpoint files."""
        if not self.path:
            return
        
        try:
            # Parse markup.bcf for metadata
            markup = minidom.parse(str(self.path / 'markup.bcf'))
            title_nodes = markup.getElementsByTagName('Title')
            if title_nodes and title_nodes[0].childNodes:
                self.title = title_nodes[0].childNodes[0].nodeValue
                self.title = string.capwords(str(self.title), sep=None)
            
            desc_nodes_list = markup.getElementsByTagName('Description')
            if desc_nodes_list:
                desc_nodes = desc_nodes_list[0].childNodes
                self.description = desc_nodes[0].nodeValue if desc_nodes else ''
            
            author_nodes = markup.getElementsByTagName('CreationAuthor')
            if author_nodes and author_nodes[0].childNodes:
                self.author = author_nodes[0].childNodes[0].nodeValue
            
            # Parse viewpoint.bcfv for IFC GUIDs and additional info
            viewpoint_xml = minidom.parse(str(self.path / 'viewpoint.bcfv'))
            components = viewpoint_xml.getElementsByTagName('Component')
            
            # Extract GUIDs and detailed information
            for comp in components:
                guid = comp.getAttribute('IfcGuid')
                if guid:
                    # Add to simple list (backward compatibility)
                    self.ifc_guids.append(guid)
                    
                    # Extract additional information
                    originating_system = ""
                    authoring_tool_id = ""
                    
                    # Get OriginatingSystem
                    orig_sys_nodes = comp.getElementsByTagName('OriginatingSystem')
                    if orig_sys_nodes and orig_sys_nodes[0].childNodes:
                        originating_system = orig_sys_nodes[0].childNodes[0].nodeValue
                    
                    # Get AuthoringToolId
                    auth_tool_nodes = comp.getElementsByTagName('AuthoringToolId')
                    if auth_tool_nodes and auth_tool_nodes[0].childNodes:
                        authoring_tool_id = auth_tool_nodes[0].childNodes[0].nodeValue
                    
                    # Store detailed info
                    self.ifc_guids_info[guid] = { # type: ignore
                        "originating_system": originating_system,
                        "authoring_tool_id": authoring_tool_id
                    }
            
        except Exception as e:
            print(f"Error extracting topic data for {self.id}: {e}")
    
    def __repr__(self) -> str:
        return (f"Topic ID: {self.id}\n"
                f"Title: {self.title}\n"
                f"Description: {self.description}\n"
                f"Author: {self.author}\n"
                f"IFC GUIDs: {len(self.ifc_guids)}\n\n"
                )


class IfcInfoProvider:
    """
    Provides IFC model information and GUID matching capabilities.
    Uses lazy loading for efficient memory management.
    """
    
    def __init__(self, ifc_file_path: Union[str, Path]) -> None:
        self.ifc_file_path: Path = Path(ifc_file_path)
        self.ifc_model: Optional[Any] = None  # Lazy loading
    
    def _load_ifc_model(self) -> None:
        """Load IFC model only when needed."""
        if self.ifc_model is None:
            self.ifc_model = ifcopenshell.open(str(self.ifc_file_path))
    
    def match_objects(self, ifc_guids: List[str], attribute_target: str) -> str:
        """
        Match IFC elements by GUID and find the one matching the target attribute.
        
        Args:
            ifc_guids: List of IFC GUIDs to search
            attribute_target: Target element name or long name to match
        
        Returns:
            GUID of matched element, or empty string if no match
        """
        self._load_ifc_model()
        
        collection_elements: Dict[str, Any] = {}
        for guid in ifc_guids:
            try:
                element = self.ifc_model.by_guid(guid) # type: ignore
                if element:
                    collection_elements[guid] = element
            except Exception as e:
                print(f"Warning: Could not find element with GUID {guid}: {e}")
        
        # Match by name or long name
        matched_guid: str = ''
        if collection_elements:
            target_lower: str = str(attribute_target).lower()
            for guid, element in collection_elements.items():
                element_name: str = getattr(element, "Name", "").lower()
                element_name_long: str = getattr(element, "LongName", "").lower()
                
                if target_lower == element_name or target_lower == element_name_long:
                    matched_guid = guid
                    break
        
        return matched_guid


class BcfExtractor:
    """
    Extracts and manages BCF topics from a BCF ZIP file.
    Supports skipping extraction if already extracted.
    """
    
    def __init__(
        self, 
        zip_file_path: Union[str, Path],
        project_name: Optional[str] = None,
        force_extract: bool = False
    ) -> None:
        """
        Initialize BCF extractor.
        
        Args:
            zip_file_path: Path to BCF ZIP file
            project_name: Name of the project (if None, derived from zip filename)
            force_extract: If True, re-extract even if already extracted
        """
        self.path: Path = Path(zip_file_path)
        if not self.path:
            raise ValueError("BCF zip file path cannot be None")
        
        # Store project name (use provided name or derive from zip filename)
        self.project_name: str = project_name if project_name else self.to_model_name(self.path)
        
        # Setup extraction path
        self.extract_path: Path = self._create_extraction_path()
        
        # Extract or skip if already extracted
        if force_extract or not self.is_already_extracted_instance():
            self._extract_bcfzip()
        else:
            print(f"  Using existing extraction for {self.project_name}")
        
        # Load topics from extraction
        self.topics: List[Topic] = []
        self._create_topics()
        self._sort_topics_alphabetically()
    
    @staticmethod
    def to_model_name(filename: Union[str, Path]) -> str:
        """Normalize a file/model identifier to its base name without extension."""
        return Path(filename).stem

    @staticmethod
    def is_already_extracted(project_name: str, acc_res_root: Optional[Path] = None) -> bool:
        """
        Check if BCF content has been extracted for a given project.
        
        Args:
            project_name: Name of the project
            acc_res_root: Root path for acc_result (optional, will be resolved if None)
        
        Returns:
            True if already extracted with valid topics
        """
        if acc_res_root is None:
            acc_res_root = Path(ACC_RES_PATH)
        
        temp_dir: Path = acc_res_root / project_name / 'temp'
        if not temp_dir.is_dir():
            return False
        
        try:
            # Check if there are topic folders (excluding bcf.version)
            has_topics = any(
                item.is_dir() and item.name != 'bcf.version'
                for item in temp_dir.iterdir()
            )
            return has_topics
        except Exception:
            return False
    
    def is_already_extracted_instance(self) -> bool:
        """Check if this specific BCF file has been extracted."""
        if not self.extract_path.exists():
            return False
        
        try:
            # Check if there are topic folders
            has_topics = any(
                item.is_dir() and item.name != 'bcf.version'
                for item in self.extract_path.iterdir()
            )
            return has_topics
        except Exception:
            return False

    def _create_extraction_path(self) -> Path:
        """
        Create extraction path using the project name.
        Returns: data/processed/acc_result/<project_name>/temp
        """
        acc_res_root: Path = Path(ACC_RES_PATH)
        
        # Use self.project_name instead of deriving from zip path
        extract_path: Path = acc_res_root / self.project_name / 'temp'
        return extract_path
    
    def _extract_bcfzip(self) -> None:
        """Extract BCF ZIP file to temp directory."""
        if not self.path.exists():
            raise FileNotFoundError(f"BCF file not found: {self.path}")
        
        # Clean up existing extraction
        if self.extract_path.exists():
            shutil.rmtree(self.extract_path)
        
        self.extract_path.mkdir(parents=True, exist_ok=True)
        
        with zipfile.ZipFile(self.path, 'r') as zip_ref:
            zip_ref.extractall(self.extract_path)
    
    def _create_topics(self) -> None:
        """
        Create Topic objects from extracted BCF folders.
        Each topic is a subdirectory (excluding bcf.version).
        """
        if not self.extract_path.exists():
            return
        
        for item in self.extract_path.iterdir():
            if item.is_dir() and item.name != 'bcf.version':
                topic = Topic(topic_id=item.name, directory=self.extract_path)
                self.topics.append(topic)
    
    def _sort_topics_alphabetically(self) -> None:
        """Sort topics by title alphabetically."""
        self.topics.sort(key=lambda t: t.title if t.title else "")
    
    def export_snapshots(self, output_dir: Optional[Path] = None) -> None:
        """
        Export all topic snapshots to a specified directory.
        Defaults to data/processed/acc_result/<project_name>/snapshots
        """
        if output_dir is None:
            acc_res_root: Path = Path(ACC_RES_PATH)
            output_dir = acc_res_root / self.project_name / 'snapshots'
        
        if output_dir.exists():
            shutil.rmtree(output_dir)
        
        output_dir.mkdir(parents=True, exist_ok=True)
        
        for topic in self.topics:
            if topic.snapshot and topic.snapshot.exists():
                shutil.copy(topic.snapshot, output_dir / f"{topic.id}.png")


class BcfAnalyzer:
    """
    Analyzes BCF topics and provides prioritization and classification.
    Can be created directly from a BcfExtractor or standalone with topics.
    """
    
    def __init__(
        self, 
        bcf_extractor: Optional[BcfExtractor] = None,
        topics: Optional[List[Topic]] = None,
        bcfzip_path: Optional[Union[str, Path]] = None
    ) -> None:
        """
        Initialize BCF analyzer.
        
        Args:
            bcf_extractor: BcfExtractor instance (takes priority)
            topics: List of topics (used if bcf_extractor is None)
            bcfzip_path: Path to BCF file (used if bcf_extractor is None)
        """
        if bcf_extractor:
            self.path: Path = bcf_extractor.path
            self.topics: List[Topic] = bcf_extractor.topics
        elif topics is not None:
            self.path = Path(bcfzip_path) if bcfzip_path else Path()
            self.topics = topics
        else:
            raise ValueError("Either bcf_extractor or topics must be provided")
        
        self.ifcguid_mapping: Dict[str, List[Topic]] = defaultdict(list)
        self.description_mapping: Dict[str, List[Topic]] = defaultdict(list)
        self.prioritized_topics: List[Topic] = []
        
        self._classify_topics()
    
    def _extract_description_identifier(self, description: str) -> str:
        """Extract identifier from description (text before first period)."""
        return description.split(".")[0].strip() if description else "Unknown"
    
    def _classify_topics(self) -> None:
        """Classify topics by IFC GUID and description identifier."""
        for topic in self.topics:
            # Map by IFC GUID
            for guid in topic.ifc_guids:
                self.ifcguid_mapping[guid].append(topic)
            
            # Map by description identifier
            desc_id: str = self._extract_description_identifier(topic.description or "")
            if desc_id:
                self.description_mapping[desc_id].append(topic)
    
    def get_topics_by_ifcguid(self, guid: str) -> List[Topic]:
        """Retrieve topics associated with a specific IFC GUID."""
        return self.ifcguid_mapping.get(guid, [])
    
    def get_topics_by_description(self, description: str) -> List[Topic]:
        """Retrieve topics associated with a specific description identifier."""
        return self.description_mapping.get(
            self._extract_description_identifier(description), []
        )


class BcfProjectProcessor:
    """
    High-level processor for batch BCF project analysis.
    Manages path resolution and coordinates extraction/analysis.
    """
    
    def __init__(self) -> None:
        """Initialize processor with cached paths."""
        # Cache commonly used paths
        self.acc_res_root: Path = Path(ACC_RES_PATH)
        self.ifc_root: Path = Path(ACC_MODELS_PATH)
    
    def _to_model_name(self, filename: Union[str, Path]) -> str:
        """Convert filename to model name (stem without extension)."""
        return Path(filename).stem
    
    def _determine_target_names(self, model_names: Optional[List[str]]) -> List[str]:
        """Determine which project names to analyze."""
        if model_names:
            return [self._to_model_name(fn) for fn in model_names]
        
        if not self.acc_res_root.is_dir():
            print("No acc_result folder found.")
            return []
        
        return [
            d.name for d in self.acc_res_root.iterdir()
            if d.is_dir()
        ]
    
    def _find_bcfzip_for_project(self, name: str) -> Optional[Path]:
        """Find BCF ZIP file for this project (acc/res/{name}/bcfzip)."""
        bcf_folder: Path = Path(ACC_RES_PATH) / name / "bcfzip"
        if not bcf_folder.is_dir():
            print(f"- Skipping '{name}': no bcfzip folder at {bcf_folder}")
            return None
        for f in bcf_folder.iterdir():
            if f.is_file() and f.suffix.lower() == ".bcfzip":
                return f
        print(f"- Skipping '{name}': no .bcfzip found in {bcf_folder}")
        return None
    
    def _resolve_ifc_path(self, name: str) -> Optional[Path]:
        """Resolve IFC file path for a given project name."""
        ifc_path: Path = self.ifc_root / f"{name}.ifc"
        if ifc_path.is_file():
            return ifc_path
        
        alt: Path = self.ifc_root / name / f"{name}.ifc"
        if alt.is_file():
            return alt
        
        print(f"  Warning: IFC not found for '{name}' at {ifc_path}")
        return None
    
    def _print_summary(self, name: str, bcfzip_path: Path, bcf_analyzer: BcfAnalyzer) -> None:
        """Print summary of BCF analysis results."""
        num_topics: int = len(getattr(bcf_analyzer, 'prioritized_topics', []) or bcf_analyzer.topics)
        
        try:
            rel_bcf: str = str(bcfzip_path.relative_to(self.acc_res_root))
        except ValueError:
            rel_bcf = str(bcfzip_path)
        
        print(f"✓ {name}: {num_topics} topics | {rel_bcf}")
    
    def _export_issues(self, name: str, bcf_analyzer: BcfAnalyzer) -> None:
        """
        Save issues extracted from topics into acc/res/{name}/issues/topics.json
        Topics are sorted by topic_id for consistent output.
        """
        issues_dir: Path = Path(ACC_RES_PATH) / name / "issues"
        issues_dir.mkdir(parents=True, exist_ok=True)
        
        # Sort topics by topic_id for consistent output
        sorted_topics = sorted(
            bcf_analyzer.topics,
            key=lambda t: getattr(t, "id", "")
        )
        
        topics_out: List[Dict[str, Any]] = []
        for topic in sorted_topics:
            # Sort IFC GUIDs alphabetically for consistent order
            ifc_guids_sorted = sorted(getattr(topic, "ifc_guids", []))
            
            topics_out.append({
                "topic_id": getattr(topic, "id", ""),
                "title": getattr(topic, "title", ""),
                "description": getattr(topic, "description", ""),
                "ifc_guids": ifc_guids_sorted,
                # "ifc_guids_info": dict(getattr(topic, "ifc_guids_info", {})),
            })
        
        out_path: Path = issues_dir / "topics.json"
        try:
            with open(out_path, "w", encoding="utf-8") as f:
                json.dump(topics_out, f, ensure_ascii=False, indent=2, sort_keys=True)
            
            rel_path = str(out_path)
            
            print(f"  Issues saved to: {rel_path}")
        except Exception as e:
            print(f"  Warning: Failed to save issues for '{name}': {e}")
    
    def analyze_projects(
        self, 
        model_names: Optional[List[str]] = None,
        force_extract: bool = False
    ) -> List[str]:
        """
        Discover and analyze BCF results across projects.
        
        Args:
            model_names: Specific models to analyze (None = all)
            force_extract: Force re-extraction even if already extracted
        
        Returns:
            List of successfully analyzed project names
        """
        target_names: List[str] = self._determine_target_names(model_names)
        if not target_names:
            print("No projects to analyze.")
            return []
        
        successful_projects: List[str] = []
        
        for name in target_names:
            bcfzip_path: Optional[Path] = self._find_bcfzip_for_project(name)
            if not bcfzip_path:
                continue
            
            try:
                # Extract and analyze BCF with explicit project name
                bcf_extractor: BcfExtractor = BcfExtractor(
                    zip_file_path=bcfzip_path,
                    project_name=name,  # Pass the correct project name
                    force_extract=force_extract
                )
                bcf_analyzer: BcfAnalyzer = BcfAnalyzer(bcf_extractor=bcf_extractor)
                
                # Optionally load IFC provider (kept separate as requested)
                ifc_path: Optional[Path] = self._resolve_ifc_path(name)
                if ifc_path and ifc_path.is_file():
                    # Store for potential future use
                    _ifc_provider: IfcInfoProvider = IfcInfoProvider(ifc_file_path=ifc_path)
                
                # Export and summarize
                self._export_issues(name, bcf_analyzer)
                self._print_summary(name, bcfzip_path, bcf_analyzer)
                successful_projects.append(name)
                
            except Exception as e:
                print(f"× Failed to analyze '{name}': {e}")
        
        print(f"\n✓ Successfully analyzed {len(successful_projects)} BCF project(s)")
        return successful_projects


# -----------------------------
# Public API Functions
# -----------------------------

def extract_checking_issues(
    bcfzip_path: Union[str, Path],
    project_name: Optional[str] = None,
    force_extract: bool = False
) -> BcfAnalyzer:
    """
    Extract and analyze BCF issues from a single BCF file.
    
    Args:
        bcfzip_path: Path to BCF ZIP file
        project_name: Name of the project (if None, derived from filename)
        force_extract: Force re-extraction even if already extracted
    
    Returns:
        BcfAnalyzer instance with classified topics
    """
    bcf_extractor: BcfExtractor = BcfExtractor(
        zip_file_path=bcfzip_path,
        project_name=project_name,
        force_extract=force_extract
    )
    bcf_analyzer: BcfAnalyzer = BcfAnalyzer(bcf_extractor=bcf_extractor)
    return bcf_analyzer


def analyze_bcf_projects(
    model_names: Optional[List[str]] = None,
    force_extract: bool = False
) -> List[str]:
    """
    Discover and analyze BCF results across projects.
    
    Args:
        model_names: Specific models to analyze (None = all)
        force_extract: Force re-extraction even if already extracted
    
    Returns:
        List of successfully analyzed project names
    """
    processor = BcfProjectProcessor()
    return processor.analyze_projects(model_names, force_extract)


def batch_processing_bcf(
    model_filenames: Optional[List[str]] = None,
    force_extract: bool = False
) -> List[str]:
    """
    Batch process BCF files with smart extraction skipping.
    
    Args:
        model_filenames: List of model filenames to process (None = all)
        force_extract: Force re-extraction even if already extracted
    
    Returns:
        List of successfully processed project names
    """
    if model_filenames:
        # Normalize filenames to model names
        normalized = [BcfExtractor.to_model_name(m) for m in model_filenames]
        
        # Skip already extracted unless force_extract is True
        if not force_extract:
            acc_res_root: Path = Path(ACC_RES_PATH)
            
            pending = [
                n for n in normalized 
                if not BcfExtractor.is_already_extracted(n, acc_res_root)
            ]
            
            if not pending:
                print("All provided models already extracted. Skipping BCF analysis.")
                return []
            
            return analyze_bcf_projects(pending, force_extract=force_extract)
        
        return analyze_bcf_projects(normalized, force_extract=force_extract)
    
    # Analyze all discovered projects
    return analyze_bcf_projects(None, force_extract=force_extract)


def process_bcf_for_model(model_name: str, force_extract: bool = True) -> Path:
    """
    Process BCF results for a specific model and create topics.json.
    
    Looks for BCF in: acc/res/{model_name}/bcfzip/
    Creates topics.json in: acc/res/{model_name}/issues/
    
    Args:
        model_name: Name of the model directory
        force_extract: Force re-extraction even if already extracted
    
    Returns:
        Path to generated topics.json
    """
    model_res_dir = Path(ACC_RES_PATH) / model_name
    bcf_dir = model_res_dir / "bcfzip"
    issues_dir = model_res_dir / "issues"
    
    # Find BCF file
    bcf_files = list(bcf_dir.glob("*.bcfzip"))
    if not bcf_files:
        raise FileNotFoundError(f"No BCF file found in {bcf_dir}")
    bcf_path = bcf_files[0]
    
    print(f"  Extracting BCF: {bcf_path.name}")
    
    # Extract and analyze BCF
    extractor = BcfExtractor(
        zip_file_path=bcf_path,
        project_name=model_name,
        force_extract=force_extract
    )
    analyzer = BcfAnalyzer(bcf_extractor=extractor)
    
    # Export topics.json
    issues_dir.mkdir(parents=True, exist_ok=True)
    
    sorted_topics = sorted(analyzer.topics, key=lambda t: t.description or "")
    topics_out: List[Dict[str, Any]] = []
    for topic in sorted_topics:
        topics_out.append({
            "topic_id": topic.id,
            "title": topic.title or "",
            "description": topic.description or "",
            "ifc_guids": sorted(topic.ifc_guids),
        })
    
    out_path = issues_dir / "topics.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(topics_out, f, ensure_ascii=False, indent=2, sort_keys=True)
    
    print(f"  Created: {out_path} ({len(topics_out)} topics)")
    return out_path