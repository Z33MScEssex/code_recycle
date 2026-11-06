"""Build the search index: one SQLite file with a full-text (FTS5) table of chunks.

Sources: SQLite FTS5 page, overview examples, UNINDEXED column option, porter tokenizer
(research plan Topic 6). Each build writes a new file and swaps it in, so a failed build never
leaves a half-written index behind.
"""
import os  # replacing the old index file in one step
import re  # splitting camelCase names
import sqlite3  # Python's built-in SQLite, which includes FTS5 on most builds
from pathlib import Path  # paths that work on every platform

from . import chunks, embed, files  # splitting files into pieces; meaning search; walking the folders

# Searchable columns first, then stored-only ones. Order matters: bm25 weights follow it (search.py).
COLUMNS = ["name", "path", "url", "taught", "place", "code", "body"]
STORED = ["kind", "folder", "start", "end", "label"]  # label: the real name, since "name" holds the split-up form
SCHEMA = (
    "CREATE VIRTUAL TABLE chunks USING fts5("
    + ", ".join(COLUMNS)
    + ", "
    + ", ".join(f"{c} UNINDEXED" for c in STORED)  # kept for results, never matched
    + ", tokenize = 'porter unicode61')"  # stemming on top of the default tokenizer
)


class IndexBuildError(RuntimeError):
    """The index can't be built or opened. The message says what to do."""


def check_fts5():
    """Fail early with a clear message if this Python's SQLite was built without FTS5."""
    try:
        con = sqlite3.connect(":memory:")
        con.execute("CREATE VIRTUAL TABLE t USING fts5(x)")
        con.close()
    except sqlite3.OperationalError:
        raise IndexBuildError(
            "This Python's SQLite has no FTS5 full-text search, which code_recycle needs. "
            "Use the python.org installer, Homebrew or your Linux distribution's Python, which include it."
        )


def split_name(name):
    # "loadSettings" and "HTTPServer" become "load Settings" and "HTTP Server", so either word matches
    return re.sub(r"(?<=[a-z0-9])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])", " ", name)


def build(settings, progress=print):
    """Walk, chunk and index every folder. Returns the walk result for the index report."""
    check_fts5()
    walked = files.walk(settings)
    target = Path(settings.index_path)
    target.parent.mkdir(parents=True, exist_ok=True)  # e.g. create .code_recycle/
    tmp = target.with_name(target.name + ".building")  # built aside, then swapped in
    if tmp.exists():
        tmp.unlink()  # left over from a build that was interrupted
    con = sqlite3.connect(tmp)
    try:
        con.execute(SCHEMA)
        con.execute("CREATE TABLE vectors (id INTEGER PRIMARY KEY, v BLOB)")  # meaning vectors, same rowid as chunks
        model = embed.load_model(settings.embed_model) if settings.embed_model else None
        to_embed = []  # (rowid, text) for the pieces that get a meaning vector
        rows = 0
        for folder, rel in walked.included:
            try:
                text = (folder / rel).read_text(encoding="utf-8")
            except UnicodeDecodeError:
                text = (folder / rel).read_text(encoding="utf-8", errors="replace")  # still searchable
            for c in chunks.chunk_file(rel, text):
                f = c.fields
                cur = con.execute(
                    f"INSERT INTO chunks ({', '.join(COLUMNS + STORED)}) VALUES ({', '.join('?' * (len(COLUMNS) + len(STORED)))})",
                    (split_name(c.name), rel, f.get("url", ""), f.get("taught", ""), f.get("where", ""),
                     f.get("code", ""), c.text, c.kind, str(folder), c.start, c.end, c.name),
                )
                rows += 1
                if model and c.kind in embed.EMBEDDED_KINDS:
                    to_embed.append((cur.lastrowid, embed.piece_text(c.name, c.text, f.get("taught", ""),
                                                                     f.get("where", ""), f.get("code", ""))))
        if to_embed:
            progress(f"Embedding {len(to_embed)} pieces with {settings.embed_model}...")
            vecs = embed.embed_pieces(model, [t for _, t in to_embed])
            con.executemany("INSERT INTO vectors (id, v) VALUES (?, ?)",
                            [(rid, v.tobytes()) for (rid, _), v in zip(to_embed, vecs)])
        con.execute("CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT)")
        con.execute("INSERT INTO meta VALUES ('embed_model', ?)", (settings.embed_model,))  # search must use the same model
        con.commit()
    finally:
        con.close()
    os.replace(tmp, target)  # one step, so readers see the old index or the new one, never half of one
    progress(f"Indexed {rows} pieces from {len(walked.included)} files into {target}")
    return walked


def connect(settings):
    """Open an existing index read-only."""
    path = Path(settings.index_path)
    if not path.exists():
        raise IndexBuildError(f"No index at {path}. Run 'code-recycle index' first.")
    # as_uri() percent-encodes spaces, "#" and "?", and writes Windows drive letters correctly
    return sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)  # read-only: searching never changes it
