"""
Ground Truth Generator Module
Generates ground truth datasets from Solibri ACC topics for compliance checking evaluation.

Phase 4 of the ACC Ground Truth Pipeline:
- 4.1 Topics Parser: Load topics.json, extract rule codes, match to templates
- 4.2 Ground Truth Transformer: Apply GUID filtering, output ground_truth_{model_name}.json
"""

import json
import re
from pathlib import Path
from typing import Any
from dataclasses import dataclass, field

from config import ACC_RES_PATH


@dataclass
class ParsedTopic:
    """A topic parsed and matched to a rule template."""
    topic_id: str
    title: str
    description: str
    rule_code: str
    rule_title: str  # Unique identifier from rule_templates.json
    question: str
    rule: str  # Full rule text from template
    parameters: str  # Rule parameters from template
    ifc_guids: list[str]  # All GUIDs from the topic
    ifc_guids_enriched: list[dict[str, str]]
    required_guids: list[str] = field(default_factory=list)  # GUIDs required for compliance match
    guid_strategy: str = "single"
    guid_element: str | None = None  # For strategy "element": only GUIDs with this ifc_type


class TopicsParser:
    """
    Parses topics.json and matches topics to rule templates.

    Extracts rule code from description prefix and matches against
    rule_templates.json using description_pattern matching.
    """

    def __init__(self, templates_path: Path | None = None) -> None:
        """
        Initialize parser with rule templates.

        Args:
            templates_path: Path to rule_templates.json (defaults to acc/config/rule_templates.json)
        """
        if templates_path is None:
            templates_path = Path("acc/config/rule_templates.json")

        self.templates_path = templates_path
        self.templates: dict[str, dict[str, Any]] = {}
        self._load_templates()

    def _load_templates(self) -> None:
        """Load rule templates from JSON file."""
        if not self.templates_path.exists():
            raise FileNotFoundError(f"Rule templates not found: {self.templates_path}")

        with open(self.templates_path, encoding="utf-8") as f:
            self.templates = json.load(f)

    def _extract_rule_code(self, description: str) -> str:
        """
        Extract rule code from description (first line).

        Examples:
            "304.3.1 Circular Space\n..." -> "304.3.1 Circular Space"
            "504.2 Treads and Risers\n..." -> "504.2 Treads and Risers"
        """
        first_line = description.split("\n")[0].strip()
        return first_line

    def _match_template(self, description: str) -> tuple[str, dict[str, Any]] | None:
        """
        Match a topic description to a rule template.

        Uses description_pattern from templates to match against description.
        Patterns may contain wildcards (*) for flexible matching.

        Returns:
            Tuple of (template_key, template_dict) or None if no match
        """
        for key, template in self.templates.items():
            pattern = template.get("description_pattern", "")

            # Convert pattern to regex (escape special chars, convert * to .*)
            regex_pattern = re.escape(pattern).replace(r"\*", ".*")

            if re.search(regex_pattern, description, re.IGNORECASE | re.DOTALL):
                return key, template

        return None

    def parse_topics(self, topics_path: Path) -> list[ParsedTopic]:
        """
        Parse topics.json and match each topic to a rule template.

        Args:
            topics_path: Path to topics.json file

        Returns:
            List of ParsedTopic objects with matched templates
        """
        if not topics_path.exists():
            raise FileNotFoundError(f"Topics file not found: {topics_path}")

        with open(topics_path, encoding="utf-8") as f:
            topics_data = json.load(f)

        parsed_topics: list[ParsedTopic] = []
        unmatched_rules: set[str] = set()

        for topic in topics_data:
            description = topic.get("description", "")
            rule_code = self._extract_rule_code(description)

            match_result = self._match_template(description)

            if match_result is None:
                unmatched_rules.add(rule_code)
                continue

            template_key, template = match_result

            parsed_topic = ParsedTopic(
                topic_id=topic.get("topic_id", ""),
                title=topic.get("title", ""),
                description=description,
                rule_code=template.get("rule_code", rule_code.split()[0] if rule_code else ""),
                rule_title=template.get("rule_title", template_key),
                question=template.get("question", ""),
                rule=template.get("rule", ""),
                parameters=template.get("parameters", ""),
                ifc_guids=topic.get("ifc_guids", []),
                ifc_guids_enriched=topic.get("ifc_guids_enriched", []),
                guid_strategy=template.get("guid_strategy", "single"),
                guid_element=template.get("guid_element"),
            )

            parsed_topics.append(parsed_topic)

        if unmatched_rules:
            print(f"  Warning: {len(unmatched_rules)} unmatched rule(s): {sorted(unmatched_rules)}")

        return parsed_topics


class GuidFilter:
    """
    Applies GUID filtering strategies to determine required GUIDs for compliance matching.

    All GUIDs are preserved; this filter determines which ones are REQUIRED for a match.

    Strategies:
    - single, multiple: All GUIDs are required (treated the same; one topic = one issue)
    - primary_and_cause: First element only is required (primary), rest are cause/context
    - context_and_primary: All GUIDs after first type change are required
    - element: Only GUIDs whose ifc_type equals template guid_element (e.g. IfcSpace) are required
    """

    def get_required_guids(self, topic: ParsedTopic) -> list[str]:
        """
        Determine which GUIDs are required for compliance matching.

        All GUIDs are preserved in the topic; this returns the subset
        that must be found for a successful match.

        Args:
            topic: ParsedTopic with ifc_guids and guid_strategy

        Returns:
            List of required GUIDs based on strategy
        """
        strategy = topic.guid_strategy
        guids = topic.ifc_guids
        enriched = topic.ifc_guids_enriched

        # Build ordered list of types matching guids order
        guid_to_type: dict[str, str] = {}
        for item in enriched:
            guid_to_type[item.get("guid", "")] = item.get("ifc_type", "")

        types = [guid_to_type.get(g, "") for g in guids]

        if strategy in ("single", "multiple"):
            # Single and multiple treated the same: use all GUIDs (one topic = one issue)
            return guids.copy()
        elif strategy == "primary_and_cause":
            return self._required_first(guids)
        elif strategy == "context_and_primary":
            return self._required_after_type_change(guids, types)
        elif strategy == "element":
            return self._required_by_element_type(guids, guid_to_type, topic.guid_element)
        else:
            # Unknown strategy - default to all GUIDs (same as single/multiple)
            return guids.copy()

    def _required_first(self, guids: list[str]) -> list[str]:
        """Primary and cause: First element only is required."""
        return guids[:1] if guids else []

    def _required_after_type_change(self, guids: list[str], types: list[str]) -> list[str]:
        """
        Context and primary: All GUIDs after first type change are required.

        Example: ['IfcSpace', 'IfcSpace', 'IfcDoor'] -> ['IfcDoor'] (index 2 onwards)
        Example: ['IfcSpace', 'IfcDoor', 'IfcSpace'] -> ['IfcDoor', 'IfcSpace'] (index 1 onwards)
        """
        if not guids or not types:
            return []

        first_type = types[0]

        # Find first index where type differs from first
        for i, t in enumerate(types):
            if t != first_type:
                return guids[i:]

        # All same type - return all (edge case)
        return guids.copy()

    def _required_by_element_type(
        self,
        guids: list[str],
        guid_to_type: dict[str, str],
        element_type: str | None,
    ) -> list[str]:
        """
        Element: Only GUIDs whose ifc_type equals guid_element are required.

        Used e.g. for Space Validation where topic has space + walls/slabs;
        only IfcSpace is required for the compliance answer.
        """
        if not element_type:
            return guids.copy()
        return [g for g in guids if guid_to_type.get(g) == element_type]


class GroundTruthTransformer:
    """
    Transforms parsed topics into ground truth format.

    Groups topics by rule and applies GUID filtering to create
    a ground truth dataset for evaluation.

    Includes all rules from templates, even those with no matching topics (pass rules).
    """

    def __init__(self) -> None:
        self.guid_filter = GuidFilter()

    def transform(
        self,
        parsed_topics: list[ParsedTopic],
        templates: dict[str, dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        """
        Transform parsed topics to ground truth format.

        Args:
            parsed_topics: List of ParsedTopic objects
            templates: Optional dict of all rule templates. If provided, rules with
                no matching topics will be included with issues: [] (pass rules).

        Returns:
            Ground truth dictionary grouped by rule_title
        """
        # Group topics by rule_title
        by_rule: dict[str, list[ParsedTopic]] = {}
        for topic in parsed_topics:
            key = topic.rule_title
            if key not in by_rule:
                by_rule[key] = []
            by_rule[key].append(topic)

        # Build ground truth structure
        ground_truth: dict[str, Any] = {
            "metadata": {
                "total_topics": len(parsed_topics),
                "rules_count": len(by_rule),
                "pass_rules_count": 0,
            },
            "rules": {},
        }

        # Process rules with matching topics (issues found)
        for rule_title, topics in by_rule.items():
            # Apply GUID filtering to each topic
            issues: list[dict[str, Any]] = []
            for topic in topics:
                required_guids = self.guid_filter.get_required_guids(topic)
                topic.required_guids = required_guids

                issues.append({
                    "topic_id": topic.topic_id,
                    "title": topic.title,
                    "description": topic.description,
                    "all_guids": topic.ifc_guids,  # All GUIDs from Solibri
                    "required_guids": required_guids,  # GUIDs required for match
                    "guid_strategy": topic.guid_strategy,
                })

            # Get question from first topic (all should have same question)
            question = topics[0].question if topics else ""
            rule_code = topics[0].rule_code if topics else ""

            # Get additional fields from first topic (all topics in same rule have same template fields)
            first_topic = topics[0]

            ground_truth["rules"][rule_title] = {
                "rule_code": rule_code,
                "rule_title": rule_title,
                "question": question,
                "rule": first_topic.rule,
                "parameters": first_topic.parameters,
                "issues_count": len(issues),
                "issues": issues,
            }

        # Add pass rules (templates with no matching topics)
        if templates:
            pass_rules_count = 0
            for template_key, template in templates.items():
                rule_title = template.get("rule_title", template_key)
                if rule_title not in ground_truth["rules"]:
                    # This rule has no issues - it's a pass rule
                    ground_truth["rules"][rule_title] = {
                        "rule_code": template.get("rule_code", ""),
                        "rule_title": rule_title,
                        "question": template.get("question", ""),
                        "rule": template.get("rule", ""),
                        "parameters": template.get("parameters", ""),
                        "issues_count": 0,
                        "issues": [],
                    }
                    pass_rules_count += 1

            ground_truth["metadata"]["pass_rules_count"] = pass_rules_count
            ground_truth["metadata"]["rules_count"] = len(ground_truth["rules"])

        return ground_truth


class GroundTruthGenerator:
    """
    Main orchestrator for ground truth generation.

    Usage:
        generator = GroundTruthGenerator()
        generator.generate("duplex")  # Creates acc/res/duplex/ground_truth.json
    """

    def __init__(self, templates_path: Path | None = None) -> None:
        """
        Initialize generator.

        Args:
            templates_path: Path to rule_templates.json (optional)
        """
        self.parser = TopicsParser(templates_path)
        self.transformer = GroundTruthTransformer()

    def generate(self, model_name: str, output_dir: Path | None = None) -> Path:
        """
        Generate ground truth for a model.

        Args:
            model_name: Name of the model (e.g., "duplex", "dental_clinic")
            output_dir: Output directory (defaults to acc/res/{model_name}/)

        Returns:
            Path to generated ground_truth.json
        """
        # Resolve paths
        model_dir = Path(ACC_RES_PATH) / model_name
        topics_path = model_dir / "issues" / "topics.json"

        if output_dir is None:
            output_dir = model_dir

        output_path = output_dir / "ground_truth.json"

        print(f"Generating ground truth for '{model_name}'...")
        print(f"  Input: {topics_path}")

        # Parse topics
        parsed_topics = self.parser.parse_topics(topics_path)
        print(f"  Parsed: {len(parsed_topics)} topics matched to templates")

        # Transform to ground truth (pass templates to include pass rules)
        ground_truth = self.transformer.transform(parsed_topics, self.parser.templates)
        ground_truth["metadata"]["model_name"] = model_name

        # Write output
        output_dir.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(ground_truth, f, ensure_ascii=False, indent=2)

        print(f"  Output: {output_path}")
        print(f"  Rules: {ground_truth['metadata']['rules_count']} ({ground_truth['metadata'].get('pass_rules_count', 0)} pass rules)")

        return output_path

    def generate_all(self, model_names: list[str] | None = None) -> dict[str, Path]:
        """
        Generate ground truth for multiple models.

        Args:
            model_names: List of model names (defaults to discovering all in acc/res/)

        Returns:
            Dict mapping model_name to output path
        """
        if model_names is None:
            # Discover models
            acc_res = Path(ACC_RES_PATH)
            model_names = [
                d.name for d in acc_res.iterdir()
                if d.is_dir() and (d / "issues" / "topics.json").exists()
            ]

        results: dict[str, Path] = {}
        for model_name in model_names:
            try:
                output_path = self.generate(model_name)
                results[model_name] = output_path
            except Exception as e:
                print(f"  Error generating ground truth for '{model_name}': {e}")

        return results


def generate_ground_truth(model_name: str) -> Path:
    """
    Convenience function to generate ground truth for a single model.

    Args:
        model_name: Name of the model

    Returns:
        Path to generated ground_truth.json
    """
    generator = GroundTruthGenerator()
    return generator.generate(model_name)


def generate_all_ground_truth() -> dict[str, Path]:
    """
    Convenience function to generate ground truth for all models.

    Returns:
        Dict mapping model_name to output path
    """
    generator = GroundTruthGenerator()
    return generator.generate_all()


if __name__ == "__main__":
    # Generate for all discovered models
    results = generate_all_ground_truth()
    print(f"\nGenerated ground truth for {len(results)} model(s)")
