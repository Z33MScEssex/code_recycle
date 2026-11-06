from code_recycle import chunks

PY = '''"""Module about adding."""
import functools


@functools.cache
def add(a, b):
    """Add two numbers."""
    return a + b


class Calculator:
    """Keeps a running total."""

    def __init__(self):
        self.total = 0

    async def push(self, x):
        self.total += x
'''


def test_python_functions_methods_and_classes_get_exact_lines():
    got = {(c.kind, c.name): (c.start, c.end) for c in chunks.chunk_file("calc.py", PY)}
    assert got[("module", "calc.py")] == (1, 1)
    assert got[("function", "add")] == (5, 8)  # starts at the decorator, not the def line
    assert got[("class", "Calculator")] == (11, 18)
    assert got[("method", "Calculator.__init__")] == (14, 15)
    assert got[("method", "Calculator.push")] == (17, 18)


def test_function_chunk_text_is_the_exact_source():
    add = [c for c in chunks.chunk_file("calc.py", PY) if c.name == "add"][0]
    assert add.text == '@functools.cache\ndef add(a, b):\n    """Add two numbers."""\n    return a + b'


def test_class_chunk_is_a_summary_not_a_copy_of_every_method():
    cls = [c for c in chunks.chunk_file("calc.py", PY) if c.kind == "class"][0]
    assert "Keeps a running total." in cls.text and "methods: __init__, push" in cls.text
    assert "self.total += x" not in cls.text


def test_broken_python_falls_back_to_text_windows():
    got = chunks.chunk_file("bad.py", "def oops(:\n    pass\n")
    assert [c.kind for c in got] == ["text"] and got[0].start == 1


RESEARCH = '''# Plan

## Topic 1: Call a model

**Question:** how?

- **URL:** https://example.com/api
- **Where on the page:** "Chat request"
- **What it taught (my reading):** stream false gives one reply.
  It also gives timings.
- **Code pattern from source:**
```python
# not a heading
r = post(url)
```

## Topic 2: Blank one

- **URL:**
- **Where on the page:**

## Notes

Some prose.
'''


def test_research_entries_become_structured_chunks():
    got = chunks.chunk_file("docs/plan.md", RESEARCH)
    entry = [c for c in got if c.kind == "research_entry"]
    assert len(entry) == 1  # the blank Topic 2 has no URL, so it isn't an entry
    f = entry[0].fields
    assert entry[0].name == "Topic 1: Call a model"
    assert f["url"] == "https://example.com/api"
    assert f["where"] == '"Chat request"'
    assert f["taught"] == "stream false gives one reply.\n  It also gives timings."
    assert f["code"] == "# not a heading\nr = post(url)"  # fences removed, code kept


def test_other_markdown_splits_by_heading_and_ignores_hashes_in_code():
    got = chunks.chunk_file("docs/plan.md", RESEARCH)
    names = [c.name for c in got]
    assert "not a heading" not in " ".join(names)
    assert ("section", "Notes") in [(c.kind, c.name) for c in got]


def test_long_text_is_windowed_with_overlap():
    text = "\n".join(f"line {i}" for i in range(1, 131))
    got = chunks.chunk_file("notes.txt", text)
    assert [(c.start, c.end) for c in got] == [(1, 60), (51, 110), (101, 130)]


def test_plain_unbolded_field_labels_are_read_too():
    md = "## Topic 3: Hashing\n\n- URL: https://docs.python.org/3/library/hashlib.html\n- Where on the page: examples\n- What it taught: use sha256\n- Code pattern from source:\n```python\nh = sha256()\n```\n"
    e = chunks.chunk_file("plan.md", md)[0]
    assert e.kind == "research_entry" and e.fields["url"].endswith("hashlib.html") and "sha256()" in e.fields["code"]


def test_a_prose_line_mentioning_url_without_a_colon_label_is_not_an_entry():
    got = chunks.chunk_file("notes.md", "## Notes\n\nThe URL is in the config file.\n")
    assert [c.kind for c in got] == ["section"]


def test_blank_lines_inside_copied_code_are_kept():
    md = "## T\n\n- **URL:** https://x.org\n- **Code pattern from source:**\n```python\nimport a\n\nb = 1\n```\n"
    assert chunks.chunk_file("p.md", md)[0].fields["code"] == "import a\n\nb = 1"
