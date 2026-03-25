"""Generate ground_truth_v2.json using extraction_element from rule_templates.

Instead of the complex guid_strategy logic (single, primary_and_cause,
context_and_primary, element), V2 uses a single approach: filter each topic's
enriched GUIDs to only those whose ifc_type matches the rule's extraction_element.

Also compares V1 vs V2 and reports differences.

Usage:
    uv run scripts/generate_ground_truth_v2.py
    uv run scripts/generate_ground_truth_v2.py --models duplex digital_hub
"""

import argparse
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.config import ACC_RES_PATH, ACC_CONFIG_PATH  # noqa: E402

TEMPLATES_PATH = Path(ACC_CONFIG_PATH) / "rule_templates.json"


def load_templates() -> dict[str, dict]:
    with open(TEMPLATES_PATH, encoding="utf-8") as f:
        return json.load(f)


@dataclass
class ParsedTopic:
    """A topic parsed and matched to a rule template."""

    topic_id: str
    title: str
    description: str
    rule_code: str
    rule_title: str
    question: str
    rule: str
    parameters: str
    ifc_guids: list[str]
    ifc_guids_enriched: list[dict[str, str]]


def parse_extraction_elements(raw: str) -> set[str]:
    """Parse comma-separated extraction_element into a set of types."""
    return {t.strip() for t in raw.split(",") if t.strip()}


def match_template(
    description: str, templates: dict[str, dict]
) -> tuple[str, dict[str, Any]] | None:
    """Match a topic description to a rule template via description_pattern."""
    for key, template in templates.items():
        pattern = template.get("description_pattern", "")
        regex_pattern = re.escape(pattern).replace(r"\*", ".*")
        if re.search(regex_pattern, description, re.IGNORECASE | re.DOTALL):
            return key, template
    return None


def parse_topics(topics_path: Path, templates: dict[str, dict]) -> list[ParsedTopic]:
    """Parse topics.json and match each topic to a rule template."""
    with open(topics_path, encoding="utf-8") as f:
        topics_data = json.load(f)

    parsed: list[ParsedTopic] = []
    for topic in topics_data:
        description = topic.get("description", "")
        result = match_template(description, templates)
        if result is None:
            continue
        _key, tmpl = result
        parsed.append(
            ParsedTopic(
                topic_id=topic.get("topic_id", ""),
                title=topic.get("title", ""),
                description=description,
                rule_code=tmpl.get("rule_code", ""),
                rule_title=tmpl.get("rule_title", _key),
                question=tmpl.get("question", ""),
                rule=tmpl.get("rule", ""),
                parameters=tmpl.get("parameters", ""),
                ifc_guids=topic.get("ifc_guids", []),
                ifc_guids_enriched=topic.get("ifc_guids_enriched", []),
            )
        )
    return parsed


def generate_v2(model_name: str, templates: dict[str, dict]) -> dict:
    """Generate ground_truth_v2 for a single model."""
    model_dir = Path(ACC_RES_PATH) / model_name
    topics_path = model_dir / "issues" / "topics.json"

    if not topics_path.exists():
        raise FileNotFoundError(f"No topics.json for {model_name}: {topics_path}")

    parsed_topics = parse_topics(topics_path, templates)

    # Build extraction_element lookup from templates
    extraction_map: dict[str, set[str]] = {}
    for _key, tmpl in templates.items():
        rule_title = tmpl.get("rule_title", _key)
        raw = tmpl.get("extraction_element", "")
        extraction_map[rule_title] = parse_extraction_elements(raw)

    # Group topics by rule
    by_rule: dict[str, list] = {}
    for topic in parsed_topics:
        by_rule.setdefault(topic.rule_title, []).append(topic)

    ground_truth: dict = {
        "metadata": {
            "model_name": model_name,
            "version": "v2",
            "total_topics": len(parsed_topics),
            "rules_count": 0,
            "pass_rules_count": 0,
        },
        "rules": {},
    }

    # Process rules with topics
    for rule_title, topics in by_rule.items():
        allowed_types = extraction_map.get(rule_title, set())
        issues = []

        for topic in topics:
            guid_to_type = {
                item["guid"]: item.get("ifc_type", "")
                for item in topic.ifc_guids_enriched
            }

            if allowed_types:
                required = [
                    g
                    for g in topic.ifc_guids
                    if guid_to_type.get(g, "") in allowed_types
                ]
                if topic.ifc_guids and not required:
                    actual_types = sorted(
                        {guid_to_type.get(g, "Unknown") for g in topic.ifc_guids}
                    )
                    print(
                        f"  ERROR [{model_name}] {rule_title}: topic '{topic.title}' "
                        f"has {len(topic.ifc_guids)} GUIDs but none match "
                        f"extraction_element={sorted(allowed_types)}. "
                        f"Actual types: {actual_types}"
                    )
            else:
                # No extraction_element defined — use all GUIDs
                required = topic.ifc_guids.copy()

            issues.append(
                {
                    "topic_id": topic.topic_id,
                    "title": topic.title,
                    "description": topic.description,
                    "all_guids": topic.ifc_guids,
                    "all_guids_enriched": topic.ifc_guids_enriched,
                    "required_guids": required,
                    "extraction_element": sorted(allowed_types)
                    if allowed_types
                    else [],
                }
            )

        first = topics[0]
        ground_truth["rules"][rule_title] = {
            "rule_code": first.rule_code,
            "rule_title": rule_title,
            "question": first.question,
            "rule": first.rule,
            "parameters": first.parameters,
            "issues_count": len(issues),
            "issues": issues,
        }

    # Add pass rules
    pass_count = 0
    for _key, tmpl in templates.items():
        rule_title = tmpl.get("rule_title", _key)
        if rule_title not in ground_truth["rules"]:
            ground_truth["rules"][rule_title] = {
                "rule_code": tmpl.get("rule_code", ""),
                "rule_title": rule_title,
                "question": tmpl.get("question", ""),
                "rule": tmpl.get("rule", ""),
                "parameters": tmpl.get("parameters", ""),
                "issues_count": 0,
                "issues": [],
            }
            pass_count += 1

    ground_truth["metadata"]["rules_count"] = len(ground_truth["rules"])
    ground_truth["metadata"]["pass_rules_count"] = pass_count

    return ground_truth


def compare_v1_v2(model_name: str, v2: dict) -> list[dict]:
    """Compare V1 and V2 ground truth, return list of differences."""
    v1_path = Path(ACC_RES_PATH) / model_name / "ground_truth.json"
    if not v1_path.exists():
        return [{"rule": "ALL", "type": "v1_missing", "detail": str(v1_path)}]

    with open(v1_path, encoding="utf-8") as f:
        v1 = json.load(f)

    diffs = []

    all_rules = set(v1.get("rules", {}).keys()) | set(v2.get("rules", {}).keys())

    for rule_title in sorted(all_rules):
        v1_rule = v1.get("rules", {}).get(rule_title, {})
        v2_rule = v2.get("rules", {}).get(rule_title, {})

        # Collect required GUIDs
        v1_guids = set()
        for issue in v1_rule.get("issues", []):
            v1_guids.update(issue.get("required_guids", []))

        v2_guids = set()
        for issue in v2_rule.get("issues", []):
            v2_guids.update(issue.get("required_guids", []))

        if v1_guids != v2_guids:
            added = v2_guids - v1_guids
            removed = v1_guids - v2_guids
            diffs.append(
                {
                    "rule": rule_title,
                    "v1_count": len(v1_guids),
                    "v2_count": len(v2_guids),
                    "added": sorted(added),
                    "removed": sorted(removed),
                }
            )

    return diffs


def discover_models() -> list[str]:
    acc_res = Path(ACC_RES_PATH)
    return sorted(
        d.name
        for d in acc_res.iterdir()
        if d.is_dir() and (d / "issues" / "topics.json").exists()
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate ground_truth_v2")
    parser.add_argument("--models", nargs="*", help="Model names (default: all)")
    args = parser.parse_args()

    templates = load_templates()
    model_names = args.models or discover_models()

    print(f"Generating V2 ground truth for {len(model_names)} models\n")

    all_diffs: dict[str, list[dict]] = {}

    for model_name in model_names:
        print(f"=== {model_name} ===")
        v2 = generate_v2(model_name, templates)

        # Write V2
        out_path = Path(ACC_RES_PATH) / model_name / "ground_truth_v2.json"
        out_path.write_text(
            json.dumps(v2, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        print(f"  Wrote {out_path}")

        # Compare
        diffs = compare_v1_v2(model_name, v2)
        all_diffs[model_name] = diffs

        if diffs:
            print(f"  Differences: {len(diffs)} rules changed")
            for d in diffs:
                added = len(d.get("added", []))
                removed = len(d.get("removed", []))
                print(
                    f"    {d['rule']}: V1={d['v1_count']} -> V2={d['v2_count']} "
                    f"(+{added} -{removed})"
                )
        else:
            print("  No differences")
        print()

    # Write diff summary
    diff_path = Path(ACC_RES_PATH) / "ground_truth_v1_v2_diff.json"
    diff_path.write_text(
        json.dumps(all_diffs, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(f"Diff summary: {diff_path}")


if __name__ == "__main__":
    main()
