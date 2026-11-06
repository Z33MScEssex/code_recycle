import os

import pytest

from code_recycle import index, search, settings
from conftest import FAKE_AWS

TREE = {
    "shared/http.py": 'def fetch_json(url):\n    """Download a URL and parse the JSON reply."""\n    return json.loads(get(url))\n',
    "shared/plan.md": (
        "## Topic 1: Telegram alerts\n\n"
        "- **URL:** https://core.telegram.org/bots/api\n"
        "- **Where on the page:** sendMessage\n"
        "- **What it taught:** check ok is true in the reply, an HTTP 200 is not enough.\n"
        "- **Code pattern from source:**\n```python\nsend_message(chat_id, text)\n```\n"
    ),
    "protected/sizing.py": "def position_size(risk, stop):\n    return risk / stop\n",
    "protected/alerts.py": "def telegram_alert(text):\n    pass\n",
    "private/notes.md": "## Telegram\n\nMy own telegram notes.\n",
    "camel/Client.py": "class HttpClient:\n    def loadSettings(self):\n        pass\n",
}


@pytest.fixture
def built(make_tree, write_settings):
    def _build(extra=""):
        root = make_tree(TREE)
        s = settings.load(write_settings(f'[index]\nfolders = ["."]\nindex_path = "idx.db"\n{extra}'))
        index.build(s, progress=lambda m: None)
        return root, s
    return _build


def test_finds_a_function_by_what_it_does(built):
    _, s = built()
    top = search.search(s, "download json from a url").results[0]
    assert (top.path, top.name, top.start, top.end) == ("shared/http.py", "fetch_json", 1, 3)


def test_research_entry_comes_back_with_its_source(built):
    _, s = built()
    r = [x for x in search.search(s, "telegram send message").results if x.kind == "research_entry"][0]
    assert r.url == "https://core.telegram.org/bots/api"
    assert r.where == "sendMessage" and "HTTP 200" in r.taught
    assert "send_message(chat_id, text)" in r.snippet


def test_stemming_and_camel_case(built):
    _, s = built()
    assert search.search(s, "load setting").results[0].name == "HttpClient.loadSettings"


def test_no_suggest_from_hides_a_folder_silently(built):
    _, s = built('[rules]\nno_suggest_from = ["private/"]\n')
    ans = search.search(s, "telegram")
    assert all(not r.path.startswith("private/") for r in ans.results) and ans.note == ""


def test_no_suggest_into_keeps_other_projects_out_but_says_they_exist(built):
    root, s = built('[rules]\nno_suggest_into = ["protected/"]\n')
    ans = search.search(s, "telegram", from_path=root / "protected" / "new_module.py")
    assert [r.path for r in ans.results] == ["protected/alerts.py"]  # only the protected folder's own code
    assert "matches exist outside this folder" in ans.note


def test_searching_from_elsewhere_is_not_restricted(built):
    root, s = built('[rules]\nno_suggest_into = ["protected/"]\n')
    paths = {r.path for r in search.search(s, "telegram", from_path=root / "shared").results}
    assert "shared/plan.md" in paths and "protected/alerts.py" in paths


def test_a_secret_that_reaches_a_result_is_withheld(built, monkeypatch):
    _, s = built('[secrets]\nallow = ["shared/http.py"]\n')
    # Simulate a key that slipped past the file scan: put it straight into the index
    con = __import__("sqlite3").connect(s.index_path)
    con.execute("UPDATE chunks SET body = ? WHERE name = 'fetch_json'", (f"key = '{FAKE_AWS}'",))
    con.commit(); con.close()
    r = [x for x in search.search(s, "fetch json").results if x.path == "shared/http.py"][0]
    assert r.withheld == ["AWS access key"] and r.snippet == ""
    assert (r.path, r.start) == ("shared/http.py", 1)  # still says where it is


def test_punctuation_cannot_break_the_query(built):
    _, s = built()
    assert isinstance(search.search(s, 'url" OR (json AND "').results, list)


def test_empty_query_gets_a_message(built):
    _, s = built()
    assert search.search(s, "the of and").note == "The search had no usable words."


def test_missing_index_says_how_to_build_one(make_tree, write_settings):
    make_tree({"a.py": "x = 1\n"})
    s = settings.load(write_settings('[index]\nfolders = ["."]\nindex_path = "none.db"\n'))
    with pytest.raises(index.IndexBuildError, match="code-recycle index"):
        search.search(s, "x")


def test_rebuild_replaces_the_old_index(built, make_tree):
    root, s = built()
    (root / "shared" / "http.py").unlink()
    index.build(s, progress=lambda m: None)
    assert all(r.path != "shared/http.py" for r in search.search(s, "fetch json").results)


def test_identical_copies_are_shown_once(make_tree, write_settings):
    make_tree({"a/util.py": "def slugify(text):\n    return text.lower()\n",
               "backup/util.py": "def slugify(text):\n    return text.lower()\n"})
    s = settings.load(write_settings('[index]\nfolders = ["."]\nindex_path = "idx.db"\n'))
    index.build(s, progress=lambda m: None)
    assert len([r for r in search.search(s, "slugify").results if r.name == "slugify"]) == 1


def test_a_blocked_copy_never_hides_an_allowed_copy(make_tree, write_settings):
    same = "def slugify(text):\n    return text.lower()\n"
    root = make_tree({"other/util.py": same, "protected/util.py": same})
    s = settings.load(write_settings('[index]\nfolders = ["."]\nindex_path = "idx.db"\n[rules]\nno_suggest_into = ["protected/"]\n'))
    index.build(s, progress=lambda m: None)
    got = search.search(s, "slugify", from_path=root / "protected" / "new.py").results
    assert [r.path for r in got if r.name == "slugify"] == ["protected/util.py"]


def test_index_path_with_awkward_characters_opens(make_tree, write_settings):
    make_tree({"a.py": "def odd_name():\n    pass\n"})
    awkward = "my index #1%" + ("" if os.name == "nt" else "?")  # Windows forbids "?" in a file name
    s = settings.load(write_settings(f'[index]\nfolders = ["."]\nindex_path = "{awkward}/idx.db"\n'))
    index.build(s, progress=lambda m: None)
    assert search.search(s, "odd name").results[0].name == "odd_name"
