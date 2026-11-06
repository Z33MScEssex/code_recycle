"""Split indexed files into searchable pieces ("chunks").

- Python: one chunk per function, method and class, with exact line numbers.
  Source: Python docs, ast module (research plan Topic 3).
- Markdown research entries (URL, where on the page, what it taught, code pattern): one
  structured chunk each. The format is the author's own, so this parser is original applied work.
- Other Markdown: one chunk per heading section.
- Anything else, or Python that doesn't parse: fixed windows of lines.
"""
import ast  # Python's own parser, so no third-party install is needed
import re  # finding Markdown headings and research-entry fields
from dataclasses import dataclass, field  # a plain record for one chunk

WINDOW = 60  # lines per chunk for plain text
OVERLAP = 10  # lines shared between neighbouring windows, so a match on a boundary isn't lost
MAX_SECTION_LINES = 200  # a longer Markdown section is cut into windows


@dataclass
class Chunk:
    path: str  # file path relative to its indexed folder
    kind: str  # function, method, class, module, research_entry, section or text
    name: str  # function or class name, heading text, or "" for plain text
    start: int  # first line, counting from 1
    end: int  # last line, inclusive
    text: str  # the exact source text
    fields: dict = field(default_factory=dict)  # research entries only: url, where, taught, code


def chunk_file(path, text):
    """All chunks for one file. `path` is only used for its extension and for labelling."""
    if path.endswith((".py", ".pyi")):
        return python_chunks(path, text)
    if path.endswith(".md"):
        return markdown_chunks(path, text)
    return text_chunks(path, text)


# ---------- Python ----------

def python_chunks(path, text):
    try:
        tree = ast.parse(text)  # the whole module as a tree of nodes
    except (SyntaxError, ValueError):  # broken or non-UTF-8 source: fall back to plain windows
        return text_chunks(path, text)
    lines = text.splitlines()
    out = []
    doc = ast.get_docstring(tree)  # the module's own description, if it has one
    if doc:
        first = tree.body[0]  # a docstring is always the first statement
        out.append(Chunk(path, "module", path.rsplit("/", 1)[-1], first.lineno, first.end_lineno,
                         _lines(lines, first.lineno, first.end_lineno)))
    _visit(tree, path, lines, out, inside_class=None)
    return out or text_chunks(path, text)  # a file of plain statements still gets indexed


def _visit(node, path, lines, out, inside_class):
    for child in ast.iter_child_nodes(node):
        if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
            start = _start_with_decorators(child)
            name = f"{inside_class}.{child.name}" if inside_class else child.name
            kind = "method" if inside_class else "function"
            out.append(Chunk(path, kind, name, start, child.end_lineno, _lines(lines, start, child.end_lineno)))
            # Functions defined inside functions stay part of their parent's chunk
        elif isinstance(child, ast.ClassDef):
            start = _start_with_decorators(child)
            # The class chunk is its header, docstring and method names, not every line again,
            # so a search for the class doesn't just return its biggest method's text twice
            header_end = child.body[0].lineno - 1 if child.body else child.end_lineno
            doc = ast.get_docstring(child) or ""
            methods = [c.name for c in child.body if isinstance(c, (ast.FunctionDef, ast.AsyncFunctionDef))]
            summary = _lines(lines, start, max(start, header_end))
            if doc:
                summary += "\n" + doc
            if methods:
                summary += "\nmethods: " + ", ".join(methods)
            out.append(Chunk(path, "class", child.name, start, child.end_lineno, summary))
            _visit(child, path, lines, out, inside_class=child.name)


def _start_with_decorators(node):
    # lineno is the "def" or "class" line; decorators sit above it and belong to it
    return min([node.lineno] + [d.lineno for d in node.decorator_list])


def _lines(lines, start, end):
    return "\n".join(lines[start - 1:end])  # line numbers count from 1, list indexes from 0


# ---------- Markdown ----------

HEADING = re.compile(r"^(#{1,6})\s+(.*)")
# Bold or plain: "- **URL:** x", "- URL: x", "**What it taught (my reading):** x".
FIELD = re.compile(r"^\s*(?:[-*]\s+)?(?:\*\*)?(URLs?|Where on the page|What it taught|Code pattern from source)\b[^:*\n]*?:(?:\*\*)?\s?(.*)")
FIELD_KEYS = {"URL": "url", "URLs": "url", "Where on the page": "where",
              "What it taught": "taught", "Code pattern from source": "code"}


def markdown_chunks(path, text):
    lines = text.splitlines()
    sections = []  # (heading text, first line, last line)
    current_name, current_start, in_fence = "", 1, False
    for i, line in enumerate(lines, start=1):
        if line.lstrip().startswith("```"):
            in_fence = not in_fence  # a "#" inside a code block is not a heading
        m = None if in_fence else HEADING.match(line)
        if m:
            if i > current_start:
                sections.append((current_name, current_start, i - 1))
            current_name, current_start = m.group(2).strip(), i
    if lines:
        sections.append((current_name, current_start, len(lines)))

    out = []
    for name, start, end in sections:
        body = lines[start - 1:end]
        if not any(l.strip() for l in body):
            continue  # an empty section has nothing to find
        fields = research_fields(body)
        if fields.get("url"):
            out.append(Chunk(path, "research_entry", name, start, end, "\n".join(body), fields))
        elif end - start + 1 <= MAX_SECTION_LINES:
            out.append(Chunk(path, "section", name, start, end, "\n".join(body)))
        else:
            for c in _windows(path, body, start):
                c.kind, c.name = "section", name
                out.append(c)
    return out


def research_fields(body):
    """The four fields of a research entry, as plain text. Empty dict if the section has no URL field."""
    fields, key, in_fence = {}, None, False
    for line in body:
        if line.lstrip().startswith("```"):
            in_fence = not in_fence  # inside a code block, "#" lines are code, not headings
        m = None if in_fence else FIELD.match(line)
        if m:
            key = FIELD_KEYS[m.group(1)]
            fields[key] = m.group(2).strip()
        elif key and (in_fence or not HEADING.match(line)):
            fields[key] = fields[key] + "\n" + line if fields[key] else line  # a field runs on until the next label
    out = {k: v.strip() for k, v in fields.items()}
    if out.get("code"):
        out["code"] = strip_fences(out["code"])
    return out


def strip_fences(text):
    """Code blocks without their ``` marker lines, so the code reads as code. Blank lines inside are kept."""
    return "\n".join(l for l in text.splitlines() if not l.lstrip().startswith("```")).strip("\n")


# ---------- Plain text ----------

def text_chunks(path, text):
    return _windows(path, text.splitlines(), 1)


def _windows(path, lines, first_line):
    out, step = [], WINDOW - OVERLAP
    for i in range(0, max(len(lines), 1), step):
        part = lines[i:i + WINDOW]
        if any(l.strip() for l in part):
            out.append(Chunk(path, "text", "", first_line + i, first_line + i + len(part) - 1, "\n".join(part)))
        if i + WINDOW >= len(lines):
            break  # this window reached the end of the file
    return out
