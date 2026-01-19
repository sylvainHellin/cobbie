"""RST file parser for extracting documentation sections."""

import hashlib
import re
from pathlib import Path

from src.docs_indexer.models import DocChunk


def _generate_chunk_id(source_file: str, name: str) -> str:
    """Generate a unique ID for a chunk."""
    content = f"{source_file}:{name}"
    return hashlib.sha256(content.encode()).hexdigest()[:16]


def _extract_sections(content: str) -> list[tuple[str, str, int]]:
    """Extract sections from RST content.

    Returns list of (title, content, line_number) tuples.
    Handles both major sections (====) and sub-sections (----).
    """
    lines = content.split("\n")
    sections: list[tuple[str, str, int]] = []

    i = 0
    while i < len(lines):
        line = lines[i]

        # Check if next line is an underline (section marker)
        if i + 1 < len(lines):
            next_line = lines[i + 1]
            # RST underlines are repeated chars like === or ---
            if next_line and len(next_line) >= 3 and len(set(next_line.strip())) == 1:
                underline_char = next_line.strip()[0]
                if underline_char in "=-~^":
                    title = line.strip()
                    title_line = i + 1  # Line number (1-indexed)

                    # Find content until next section
                    content_lines = []
                    j = i + 2  # Skip title and underline

                    while j < len(lines):
                        # Check if this is a new section
                        if j + 1 < len(lines):
                            potential_underline = lines[j + 1]
                            if (
                                potential_underline
                                and len(potential_underline) >= 3
                                and len(set(potential_underline.strip())) == 1
                                and potential_underline.strip()[0] in "=-~^"
                            ):
                                break
                        content_lines.append(lines[j])
                        j += 1

                    section_content = "\n".join(content_lines).strip()
                    if section_content:  # Only add non-empty sections
                        sections.append((title, section_content, title_line))

                    i = j
                    continue

        i += 1

    return sections


def _clean_rst_content(content: str) -> str:
    """Clean RST directives while preserving code blocks."""
    # Remove directive markers but keep content
    # .. seealso::, .. note::, .. warning:: etc.
    content = re.sub(r"^\.\. (seealso|note|warning|tip|important)::\s*$", "", content, flags=re.MULTILINE)

    # Remove container directives
    content = re.sub(r"^\.\. container::\s+\w+\s*$", "", content, flags=re.MULTILINE)

    # Convert code-block to readable format
    # Keep the code but mark it clearly
    def replace_code_block(match: re.Match[str]) -> str:
        lang = match.group(1) or "python"
        code = match.group(2)
        # Dedent the code (remove leading 4 spaces)
        code_lines = code.split("\n")
        dedented = []
        for line in code_lines:
            if line.startswith("    "):
                dedented.append(line[4:])
            elif line.strip() == "":
                dedented.append("")
            else:
                dedented.append(line)
        return f"```{lang}\n" + "\n".join(dedented).strip() + "\n```"

    # Match code blocks - handle optional empty line after directive
    content = re.sub(
        r"\.\. code-block::\s*(\w*)\n\n?((?:[ ]{4}.*(?:\n|$))+)",
        replace_code_block,
        content,
    )

    # Clean up excessive whitespace
    content = re.sub(r"\n{3,}", "\n\n", content)

    return content.strip()


def parse_rst_file(file_path: Path) -> list[DocChunk]:
    """Parse an RST file into documentation chunks.

    Each section becomes a chunk. Sub-sections are preferred
    as they tend to be more focused/self-contained.
    """
    content = file_path.read_text(encoding="utf-8")
    sections = _extract_sections(content)

    chunks = []
    source_file = str(file_path.relative_to(file_path.parent.parent.parent))

    for title, section_content, line_num in sections:
        # Skip very short sections (likely just references)
        if len(section_content) < 50:
            continue

        cleaned_content = _clean_rst_content(section_content)

        chunk = DocChunk(
            id=_generate_chunk_id(source_file, title),
            content=cleaned_content,
            chunk_type="tutorial_section",
            name=title,
            source_file=source_file,
            module=None,
            signature=None,
            line_start=line_num,
            parent=None,
        )
        chunks.append(chunk)

    return chunks


def parse_all_rst_tutorials(docs_dir: Path) -> list[DocChunk]:
    """Parse all RST tutorial files from the ifcopenshell-python docs."""
    tutorial_dir = docs_dir / "ifcopenshell-python"

    tutorial_files = [
        "code_examples.rst",
        "geometry_creation.rst",
        "geometry_processing.rst",
        "geometry_tree.rst",
        "hello_world.rst",
        "installation.rst",
        "schema_querying.rst",
        "selector_syntax.rst",
        "validation.rst",
    ]

    all_chunks = []
    for filename in tutorial_files:
        file_path = tutorial_dir / filename
        if file_path.exists():
            chunks = parse_rst_file(file_path)
            all_chunks.extend(chunks)
            print(f"  Parsed {filename}: {len(chunks)} chunks")

    return all_chunks


if __name__ == "__main__":
    # Test the parser
    docs_path = Path("external/ifcopenshell-docs/src/ifcopenshell-python/docs")
    chunks = parse_all_rst_tutorials(docs_path)
    print(f"\nTotal tutorial chunks: {len(chunks)}")
    for chunk in chunks[:3]:
        print(f"\n--- {chunk.name} ---")
        print(chunk.content[:200] + "...")
