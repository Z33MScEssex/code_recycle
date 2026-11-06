"""Meaning search, tested with a tiny fake model so no download is needed.

The fake model gives each word a fixed direction, so texts sharing words point the same way, and
it treats "fetch" and "download" as the same word, which keyword search can't do.
"""
import zlib

import numpy as np
import pytest

from code_recycle import embed, index, search, settings

SYNONYMS = {"download": "fetch", "downloading": "fetch"}


def _vec(text):
    v = np.zeros(64, dtype=np.float32)
    for w in text.lower().replace("_", " ").split():
        w = SYNONYMS.get(w, w)
        v[zlib.crc32(w.encode()) % 64] += 1.0  # same word, same slot, every run
    return v


class FakeModel:
    def embed(self, texts, **kw):
        for t in texts:
            yield _vec(t)

    def query_embed(self, texts, **kw):
        for t in texts:
            yield _vec(t)


@pytest.fixture(autouse=True)
def fake_model(monkeypatch):
    monkeypatch.setattr(embed, "load_model", lambda name: FakeModel())
    search._vector_cache.clear()


def test_fuse_rewards_items_both_lists_agree_on():
    assert embed.fuse(["a", "b", "c"], ["c", "a", "d"])[:2] == ["a", "c"]


def test_nearest_orders_by_closeness():
    m = embed.embed_pieces(FakeModel(), ["fetch json", "parse dates", "fetch xml"])
    assert embed.nearest(m, [10, 20, 30], embed.embed_query(FakeModel(), "fetch json"), 2) == [10, 30]


def test_piece_text_for_code_and_research_entries():
    assert embed.piece_text("f", "def f(): pass") == "f\ndef f(): pass"
    assert embed.piece_text("Topic", "body ignored", taught="t", where="w", code="c") == "Topic\nt\nw\nc"
    assert len(embed.piece_text("n", "x" * 5000)) == embed.MAX_CHARS


@pytest.fixture
def built(make_tree, write_settings):
    make_tree({"net.py": "def fetch_json(url):\n    pass\n", "dates.py": "def parse_date(text):\n    pass\n",
               "notes.md": "## Notes\n\nfetch things\n"})
    p = write_settings('[index]\nfolders = ["."]\nindex_path = "idx.db"\n[embeddings]\nmodel = "fake"\n')
    s = settings.load(p)
    index.build(s, progress=lambda m: None)
    return s


def test_only_code_and_research_pieces_get_vectors(built):
    con = __import__("sqlite3").connect(built.index_path)
    kinds = {k for (k,) in con.execute("SELECT c.kind FROM chunks c JOIN vectors v ON v.id = c.rowid")}
    assert kinds == {"function"}  # the Markdown section stays keyword only


def test_meaning_finds_a_synonym_keyword_search_misses(built):
    assert search.search(built, "downloading").results[0].name == "fetch_json"
    built.embed_model = ""  # the same index, keyword only
    assert all(r.name != "fetch_json" for r in search.search(built, "downloading").results)


def test_changing_the_model_without_reindexing_is_refused(built):
    built.embed_model = "another-model"
    with pytest.raises(index.IndexBuildError, match="index' again"):
        search.search(built, "fetch")


def test_missing_fastembed_gives_the_install_command(monkeypatch):
    monkeypatch.undo()  # the real load_model
    import builtins
    real_import = builtins.__import__

    def no_fastembed(name, *a, **k):
        if name == "fastembed":
            raise ImportError
        return real_import(name, *a, **k)

    monkeypatch.setattr(builtins, "__import__", no_fastembed)
    with pytest.raises(embed.EmbeddingsUnavailable, match=r"code-recycle\[embed\]"):
        embed.load_model("BAAI/bge-small-en-v1.5")
