"""Own-entries test: can code_recycle find an existing verified source for a research topic?

Method (research plan Topic 7, original applied work):
- Every research entry whose URL is also used by another entry is a test case.
- The query is what you'd have before searching: the topic heading plus its "Question:" line.
- The entry itself is removed from the search, so it can't find itself.
- A hit is any other research entry that shares a URL with it.
- Reuse rules are not applied: this measures finding, not policy.
- Nothing was tuned on these cases, so all of them are reported.

Usage: python bench/own_entries.py SETTINGS_FILE [--detail FILE]
If the settings switch embeddings on, keyword and meaning results are combined by RRF, as in the
real search.
The per-case detail names private files, so write it outside the repo or to a gitignored path.
"""
import argparse
import re
import sqlite3
import tempfile
from collections import defaultdict
from pathlib import Path

from code_recycle import embed, index, search, settings as settings_mod

TOP = 5
URL = re.compile(r"https?://[^\s)\]>`\"'|,]+")


def norm_urls(text):
    # Same page however it was written: no #anchor, no trailing slash or punctuation
    return {u.rstrip(".;:").split("#")[0].rstrip("/") for u in URL.findall(text)}


def question(body):
    m = re.search(r"\*\*Question:\*\*\s*(.+)", body)
    return m.group(1).strip() if m else ""


def run(settings_path, detail_path=None, mode="both"):
    s = settings_mod.load(settings_path)
    with tempfile.TemporaryDirectory() as tmp:
        s.index_path = Path(tmp) / "eval.db"  # a private copy, so the real index is never touched
        index.build(s, progress=lambda m: None)
        con = sqlite3.connect(s.index_path)
        entries = con.execute("SELECT rowid, label, path, url, body FROM chunks WHERE kind = 'research_entry'").fetchall()
        urls = {rowid: norm_urls(url) for rowid, _, _, url, _ in entries}
        by_url = defaultdict(set)
        for rowid, us in urls.items():
            for u in us:
                by_url[u].add(rowid)
        cases = [e for e in entries if any(len(by_url[u]) > 1 for u in urls[e[0]])]

        weights = ", ".join(map(str, search.WEIGHTS))
        model = matrix = None
        if s.embed_model:
            import numpy as np
            vrows = con.execute("SELECT id, v FROM vectors").fetchall()
            vids = [r for r, _ in vrows]
            matrix = np.frombuffer(b"".join(v for _, v in vrows), dtype=np.float32).reshape(len(vrows), -1)
            model = embed.load_model(s.embed_model)
        rr, hits, lines = [], 0, []
        for rowid, label, path, url, body in cases:
            twins = {r for u in urls[rowid] for r in by_url[u]} - {rowid}
            q = search.to_query(f"{label} {question(body)}")
            order = [r for (r,) in con.execute(
                f"SELECT rowid FROM chunks WHERE chunks MATCH ? AND rowid != ? ORDER BY bm25(chunks, {weights}) LIMIT ?",
                (q, rowid, search.POOL))]
            if model is not None:
                meaning = [r for r in embed.nearest(matrix, vids, embed.embed_query(model, f"{label} {question(body)}"), search.POOL + 1)
                           if r != rowid][:search.POOL]
                order = meaning if mode == "meaning" else embed.fuse(order, meaning)[:search.POOL]
            ranked, seen = [], set()
            for r in order:
                (b,) = con.execute("SELECT body FROM chunks WHERE rowid = ?", (r,)).fetchone()
                if b not in seen:  # identical copies count once, as in the real search
                    seen.add(b)
                    ranked.append(r)
            pos = next((i for i, r in enumerate(ranked, start=1) if r in twins), None)
            rr.append(1 / pos if pos else 0.0)
            hits += bool(pos and pos <= TOP)
            lines.append(f"{'MISS' if not pos else pos:>4}  {path} | {label[:70]}")
        con.close()

    n = len(cases)
    projects = sorted({c[2].split("/", 1)[0] if "/" in c[2] else "(top level)" for c in cases})
    if detail_path:
        Path(detail_path).write_text(f"Rank of the first matching entry (MISS = not in the top {search.POOL})\n" + "\n".join(lines) + "\n")
    return {"cases": n, "projects": len(projects), "entries": len(entries), "mrr": sum(rr) / n if n else 0.0,
            "hit_at_5": hits / n if n else 0.0}


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("settings")
    p.add_argument("--detail")
    p.add_argument("--mode", choices=["both", "meaning"], default="both", help="only used when embeddings are on")
    a = p.parse_args()
    r = run(a.settings, a.detail, a.mode)
    print(f"Own-entries test (code_recycle {__import__('code_recycle').__version__})")
    print(f"Research entries indexed: {r['entries']}. Test cases (entries sharing a source with another): {r['cases']}, from {r['projects']} projects")
    print(f"MRR: {r['mrr']:.4f}")
    print(f"Hit rate at {TOP}: {r['hit_at_5']:.4f}")
