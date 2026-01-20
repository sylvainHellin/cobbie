"""Python file parser for extracting docstrings from source code."""

import ast
import hashlib
import re
from pathlib import Path

from src.docs_indexer.models import DocChunk


def _generate_chunk_id(module: str, name: str, chunk_type: str) -> str:
    """Generate a unique ID for a chunk."""
    content = f"{module}:{name}:{chunk_type}"
    return hashlib.sha256(content.encode()).hexdigest()[:16]


def _get_function_signature(node: ast.FunctionDef | ast.AsyncFunctionDef) -> str:
    """Extract function signature from AST node."""
    args = []

    # Regular args
    for arg in node.args.args:
        arg_str = arg.arg
        if arg.annotation:
            arg_str += f": {ast.unparse(arg.annotation)}"
        args.append(arg_str)

    # Defaults (applied from the end)
    defaults = node.args.defaults
    num_defaults = len(defaults)
    if num_defaults > 0:
        for i, default in enumerate(defaults):
            arg_idx = len(node.args.args) - num_defaults + i
            if arg_idx >= 0:
                default_str = ast.unparse(default)
                # Truncate long defaults
                if len(default_str) > 30:
                    default_str = default_str[:27] + "..."
                args[arg_idx] += f" = {default_str}"

    # *args
    if node.args.vararg:
        vararg = f"*{node.args.vararg.arg}"
        if node.args.vararg.annotation:
            vararg += f": {ast.unparse(node.args.vararg.annotation)}"
        args.append(vararg)

    # **kwargs
    if node.args.kwarg:
        kwarg = f"**{node.args.kwarg.arg}"
        if node.args.kwarg.annotation:
            kwarg += f": {ast.unparse(node.args.kwarg.annotation)}"
        args.append(kwarg)

    # Return type
    returns = ""
    if node.returns:
        returns = f" -> {ast.unparse(node.returns)}"

    return f"def {node.name}({', '.join(args)}){returns}"


def _clean_docstring(docstring: str) -> str:
    """Clean and format a docstring for better readability."""
    # Convert RST code blocks to markdown
    docstring = re.sub(
        r"\.\. code::\s*(\w*)\n\n?((?:[ ]{4,}.*(?:\n|$))+)",
        lambda m: _convert_code_block(m.group(1) or "python", m.group(2)),
        docstring,
    )

    # Convert :param x: desc to - x: desc
    docstring = re.sub(r":param (\w+):", r"- \1:", docstring)

    # Convert :type x: to (type: ...)
    docstring = re.sub(r":type (\w+):\s*(.+)", r"  (type: \2)", docstring)

    # Convert :return: to Returns:
    docstring = re.sub(r":returns?:", "Returns:", docstring)

    # Convert :rtype: to (return type: ...)
    docstring = re.sub(r":rtype:\s*(.+)", r"(return type: \1)", docstring)

    return docstring.strip()


def _convert_code_block(lang: str, code: str) -> str:
    """Convert RST code block to markdown."""
    lines = code.split("\n")
    dedented = []
    for line in lines:
        # Find minimum indentation and remove it
        if line.strip():
            # Remove 4+ leading spaces
            match = re.match(r"^[ ]{4,}", line)
            if match:
                line = line[4:]
        dedented.append(line)
    return f"```{lang}\n" + "\n".join(dedented).strip() + "\n```"


def _path_to_module(file_path: Path, base_path: Path) -> str:
    """Convert file path to Python module path."""
    relative = file_path.relative_to(base_path)
    parts = list(relative.parts)
    # Remove .py extension
    if parts[-1].endswith(".py"):
        parts[-1] = parts[-1][:-3]
    # Remove __init__
    if parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(parts)


def extract_docstrings_from_file(
    file_path: Path, base_path: Path
) -> list[DocChunk]:
    """Extract docstrings from a Python file.

    Creates chunks for:
    - Module docstring
    - Class docstrings
    - Function/method docstrings (with meaningful content)
    """
    try:
        content = file_path.read_text(encoding="utf-8")
        tree = ast.parse(content)
    except (SyntaxError, UnicodeDecodeError) as e:
        print(f"  Warning: Could not parse {file_path}: {e}")
        return []

    chunks = []
    module = _path_to_module(file_path, base_path)
    source_file = str(file_path.relative_to(base_path))

    # Module docstring
    module_doc = ast.get_docstring(tree)
    if module_doc and len(module_doc) > 50:  # Skip trivial docstrings
        chunks.append(
            DocChunk(
                id=_generate_chunk_id(module, module, "module"),
                content=_clean_docstring(module_doc),
                chunk_type="module",
                name=module,
                source_file=source_file,
                module=module,
                signature=None,
                line_start=1,
                parent=None,
            )
        )

    # Process top-level functions
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            func_doc = ast.get_docstring(node)
            # Skip private functions and trivial docstrings
            if func_doc and len(func_doc) > 30 and not node.name.startswith("_"):
                chunks.append(
                    DocChunk(
                        id=_generate_chunk_id(module, node.name, "function"),
                        content=_clean_docstring(func_doc),
                        chunk_type="function",
                        name=node.name,
                        source_file=source_file,
                        module=module,
                        signature=_get_function_signature(node),
                        line_start=node.lineno,
                        parent=None,
                    )
                )

        elif isinstance(node, ast.ClassDef):
            class_doc = ast.get_docstring(node)
            if class_doc and len(class_doc) > 30:
                chunks.append(
                    DocChunk(
                        id=_generate_chunk_id(module, node.name, "class"),
                        content=_clean_docstring(class_doc),
                        chunk_type="class",
                        name=node.name,
                        source_file=source_file,
                        module=module,
                        signature=f"class {node.name}",
                        line_start=node.lineno,
                        parent=None,
                    )
                )

            # Methods inside class
            for item in node.body:
                if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    method_doc = ast.get_docstring(item)
                    # Skip private methods and trivial docstrings
                    if (
                        method_doc
                        and len(method_doc) > 30
                        and not item.name.startswith("_")
                    ):
                        chunks.append(
                            DocChunk(
                                id=_generate_chunk_id(
                                    module, f"{node.name}.{item.name}", "method"
                                ),
                                content=_clean_docstring(method_doc),
                                chunk_type="method",
                                name=f"{node.name}.{item.name}",
                                source_file=source_file,
                                module=module,
                                signature=_get_function_signature(item),
                                line_start=item.lineno,
                                parent=node.name,
                            )
                        )

    return chunks


def extract_all_python_docstrings(ifcopenshell_path: Path) -> list[DocChunk]:
    """Extract docstrings from all relevant ifcopenshell Python files."""
    all_chunks = []

    # Core modules
    core_files = [
        ifcopenshell_path / "__init__.py",
        ifcopenshell_path / "file.py",
        ifcopenshell_path / "entity_instance.py",
        ifcopenshell_path / "validate.py",
        ifcopenshell_path / "guid.py",
        ifcopenshell_path / "template.py",
    ]

    for file_path in core_files:
        if file_path.exists():
            chunks = extract_docstrings_from_file(file_path, ifcopenshell_path.parent)
            all_chunks.extend(chunks)
            print(f"  Parsed {file_path.name}: {len(chunks)} chunks")

    # API submodules
    api_path = ifcopenshell_path / "api"
    if api_path.exists():
        for subdir in api_path.iterdir():
            if subdir.is_dir() and not subdir.name.startswith("_"):
                for py_file in subdir.glob("*.py"):
                    if not py_file.name.startswith("_"):
                        chunks = extract_docstrings_from_file(
                            py_file, ifcopenshell_path.parent
                        )
                        all_chunks.extend(chunks)
                # Also get __init__.py for module docstring
                init_file = subdir / "__init__.py"
                if init_file.exists():
                    chunks = extract_docstrings_from_file(
                        init_file, ifcopenshell_path.parent
                    )
                    all_chunks.extend(chunks)
        print(f"  Parsed api/*: {len([c for c in all_chunks if 'api' in (c.module or '')])} chunks")

    # Util submodule
    util_path = ifcopenshell_path / "util"
    if util_path.exists():
        for py_file in util_path.glob("*.py"):
            if not py_file.name.startswith("_"):
                chunks = extract_docstrings_from_file(
                    py_file, ifcopenshell_path.parent
                )
                all_chunks.extend(chunks)
        print(f"  Parsed util/*: {len([c for c in all_chunks if 'util' in (c.module or '')])} chunks")

    # Geom module
    geom_path = ifcopenshell_path / "geom"
    if geom_path.exists():
        for py_file in geom_path.glob("*.py"):
            chunks = extract_docstrings_from_file(py_file, ifcopenshell_path.parent)
            all_chunks.extend(chunks)
        print(f"  Parsed geom/*: {len([c for c in all_chunks if 'geom' in (c.module or '')])} chunks")

    return all_chunks


if __name__ == "__main__":
    # Test the parser
    ifcopenshell_path = Path(
        "src/docs_indexer/external/ifcopenshell-docs/src/ifcopenshell-python/ifcopenshell"
    )
    chunks = extract_all_python_docstrings(ifcopenshell_path)
    print(f"\nTotal Python docstring chunks: {len(chunks)}")

    # Show some samples
    for chunk in chunks[:5]:
        print(f"\n--- {chunk.chunk_type}: {chunk.name} ---")
        if chunk.signature:
            print(f"Signature: {chunk.signature}")
        print(chunk.content[:200] + "..." if len(chunk.content) > 200 else chunk.content)
