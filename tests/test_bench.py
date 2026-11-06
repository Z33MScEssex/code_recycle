import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "bench"))
import codesearchnet  # noqa: E402


def test_docstring_is_removed_and_code_kept():
    code = 'def f(x):\n    """Add one to x."""\n    return x + 1\n'
    out, how = codesearchnet.strip_docstring(code)
    assert how == "ast" and "Add one" not in out and "return x + 1" in out


def test_multiline_docstring_is_removed_whole():
    code = 'def f(x):\n    """Add one.\n\n    Longer text.\n    """\n    return x\n'
    out, _ = codesearchnet.strip_docstring(code)
    assert out == "def f(x):\n    return x"


def test_unparseable_code_is_counted_not_hidden():
    _, how = codesearchnet.strip_docstring("def f(:\n  pass")
    assert how == "unparsed"
