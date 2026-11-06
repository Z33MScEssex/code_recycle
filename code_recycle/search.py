"""Search the index, apply the reuse rules, and scan every result for secrets before returning it.

Ranking: SQLite FTS5 bm25() with a weight per column (research plan Topic 6). The weights are a
starting guess (original applied work), to be tuned only on the tuning half of the test set.
Reuse rules (no_suggest_from, no_suggest_into) are original applied work (Topic 9).
"""
import re  # turning free text into a safe FTS5 query
from dataclasses import dataclass, field  # plain records for results
from pathlib import Path  # finding which indexed folder a path belongs to
from pathspec import GitIgnoreSpec  # the same pattern language as the skip rules

from . import embed, index, secret_check

# One weight per searchable column, in index.COLUMNS order: name, path, url, taught, place, code, body.
WEIGHTS = (5.0, 2.0, 3.0, 4.0, 1.0, 2.0, 1.0)
SNIPPET_LINES = 40  # lines of code shown per result; the full text is in the file at the given lines
POOL = 200  # candidates taken from each ranking before rules and de-duplication
STOPWORDS = {"a", "an", "and", "the", "to", "of", "in", "for", "on", "with", "how", "do", "i", "is", "it", "my", "what"}


@dataclass
class Result:
    path: str  # file path relative to its folder
    folder: str  # the indexed folder it came from
    start: int  # first line
    end: int  # last line
    kind: str  # function, class, research_entry, section, ...
    name: str  # function or class name, or heading
    url: str = ""  # research entries: where the source lives online
    where: str = ""  # research entries: where on that page
    taught: str = ""  # research entries: what it taught
    snippet: str = ""  # the code pattern (research entries) or the chunk's text
    withheld: list = field(default_factory=list)  # secret-check hits; the snippet is withheld if any


@dataclass
class Answer:
    results: list  # Result records, best first
    note: str = ""  # anything the user should know, such as a rule that hid matches


def to_query(text):
    """Free text to an FTS5 query: every word, quoted so punctuation can't break the syntax, joined by OR."""
    words = [w for w in re.findall(r"[A-Za-z0-9]+", index.split_name(text).lower()) if w not in STOPWORDS]
    return " OR ".join(f'"{w}"' for w in dict.fromkeys(words))  # dict keeps order and drops repeats


def search(settings, text, from_path=None, limit=5):
    """Best matches for `text`. `from_path` is where the search is made from, so reuse rules can apply."""
    q = to_query(text)
    if not q:
        return Answer([], "The search had no usable words.")
    con = index.connect(settings)
    try:
        keyword = con.execute(
            f"SELECT rowid FROM chunks WHERE chunks MATCH ? ORDER BY bm25(chunks, {', '.join(map(str, WEIGHTS))}) LIMIT ?",
            (q, POOL),
        ).fetchall()
        order = [r for (r,) in keyword]
        if settings.embed_model:
            order = embed.fuse(order, _meaning(con, settings, text))  # keyword and meaning, combined by RRF
        order = order[:POOL]
        found = {}
        for rid in order:
            found[rid] = con.execute(
                "SELECT label, path, url, taught, place, code, body, kind, folder, start, end FROM chunks WHERE rowid = ?",
                (rid,)).fetchone()
        rows = [found[r] for r in order]
    finally:
        con.close()

    blocked_from = GitIgnoreSpec.from_lines(settings.no_suggest_from)
    into_spec = GitIgnoreSpec.from_lines(settings.no_suggest_into)
    protected = _protected_area(settings, from_path, into_spec)

    out, hidden, seen = [], 0, set()
    for name, path, url, taught, place, code, body, kind, folder, start, end in rows:
        # Rules first, then de-duplication: a blocked copy must never hide an allowed one
        if blocked_from.match_file(path):
            continue  # never suggested from here, and not counted: the user asked for silence
        if protected is not None and not (folder == protected[0] and path.startswith(protected[1])):
            hidden += 1  # a match outside the protected area: say it exists, but don't show it
            continue
        if body in seen:
            continue  # an identical copy (a backup or a vendored file) adds nothing; show the best-ranked one
        seen.add(body)
        r = Result(path, folder, int(start), int(end), kind, name, url, place, taught, code or _first_lines(body))
        r.withheld = sorted({hit for t in (r.snippet, r.url, r.where, r.taught, r.name) for hit in secret_check.scan_text(t)})
        if r.withheld:
            r.snippet = r.url = r.where = r.taught = ""  # fail closed: show only where it is, not what it says
        out.append(r)
        if len(out) == limit:
            break
    note = ""
    if hidden:
        note = (f"{hidden} matches exist outside this folder, but the no_suggest_into rule says not to "
                f"suggest them here.")
    return Answer(out, note)


_vector_cache = {}  # index file -> (modified time, rowids, matrix, model), so vectors load once per server


def _meaning(con, settings, text):
    """Rowids ranked by closeness in meaning to the query."""
    import numpy as np
    try:
        stored = con.execute("SELECT value FROM meta WHERE key = 'embed_model'").fetchone()
    except __import__("sqlite3").OperationalError:
        stored = None  # an index from before embeddings existed
    if not stored or stored[0] != settings.embed_model:
        raise index.IndexBuildError(
            f"The index was built with embeddings model {stored[0] if stored else 'none'!r}, but settings say "
            f"{settings.embed_model!r}. Run 'code-recycle index' again.")
    key = str(settings.index_path)
    mtime = Path(key).stat().st_mtime
    cached = _vector_cache.get(key)
    if not cached or cached[0] != mtime:
        rows = con.execute("SELECT id, v FROM vectors").fetchall()
        ids = [r for r, _ in rows]
        matrix = np.frombuffer(b"".join(v for _, v in rows), dtype=np.float32).reshape(len(rows), -1) if rows else None
        cached = (mtime, ids, matrix, embed.load_model(settings.embed_model))
        _vector_cache[key] = cached
    _, ids, matrix, model = cached
    if matrix is None:
        return []
    return embed.nearest(matrix, ids, embed.embed_query(model, text), POOL)


def _protected_area(settings, from_path, into_spec):
    """If the search comes from inside a no_suggest_into folder: (indexed folder, that folder's path
    with a trailing slash). Otherwise None. Only results inside that same area may be shown."""
    if not from_path:
        return None
    p = Path(from_path).expanduser().resolve()
    for folder in settings.folders:
        try:
            rel = p.relative_to(folder).as_posix()
        except ValueError:
            continue  # not inside this indexed folder
        parts = [] if rel == "." else rel.split("/")
        for i in range(1, len(parts) + 1):  # the shortest enclosing folder the rule names
            area = "/".join(parts[:i]) + "/"
            if into_spec.match_file(area):
                return str(folder), area
    return None


def _first_lines(text):
    lines = text.splitlines()
    more = len(lines) - SNIPPET_LINES
    return "\n".join(lines[:SNIPPET_LINES]) + (f"\n... ({more} more lines)" if more > 0 else "")


def format_answer(answer):
    """Plain text an AI client or a person can read: where each result is, and what it says."""
    if not answer.results:
        return answer.note or "No matches in your own work. Searching the web is fine."
    parts = []
    for i, r in enumerate(answer.results, start=1):
        head = f"{i}. {r.name or r.path} ({r.kind}) {Path(r.folder) / r.path}:{r.start}-{r.end}"
        lines = [head]
        if r.url:
            lines.append(f"   Source: {r.url}")
        if r.where:
            lines.append(f"   Where on the page: {r.where}")
        if r.taught:
            lines.append(f"   What it taught: {r.taught}")
        if r.withheld:
            lines.append(f"   Content withheld: it may contain a secret ({', '.join(r.withheld)}). Open the file to check.")
        elif r.snippet:
            lines.append("   ```\n" + "\n".join("   " + l for l in r.snippet.splitlines()) + "\n   ```")
        parts.append("\n".join(lines))
    if answer.note:
        parts.append(answer.note)
    return "\n\n".join(parts)
