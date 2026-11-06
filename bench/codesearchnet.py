"""CodeSearchNet benchmark: find a Python function from its docstring among 999 others.

Method: research plan Topic 7, "a public benchmark as well as my own entries". Follows the
paper's test (Husain et al. 2019, Table 3): the docstring is the query, the right function must
rank among 999 distractors, scored by mean reciprocal rank (MRR).

Uses the same index columns, weights and query building as code_recycle's real search, so the
number describes the shipped tool, not a tuned copy of it.

Usage: python bench/codesearchnet.py [PARQUET] [--mode keyword|meaning|both] [--model NAME]
Default PARQUET: data/csn_python_test.parquet. The model is chosen on the validation split only
(results/prereg_embeddings.md); the test split is for the final number.
Get the data: see bench/README.md.
"""
import ast  # removing the docstring from each function
import random  # the fixed shuffle that builds the groups of 1,000
import sqlite3  # an in-memory FTS5 table per group
import argparse  # command-line options
from pathlib import Path

import pyarrow.parquet as pq  # reads the dataset file

from code_recycle import embed, index, search

SEED = 2026  # fixed before the first run, never changed
GROUP = 1000  # 1 right answer + 999 distractors, as in the paper
TOP = 5  # "hit rate at 5": is the right function in the first five?


def strip_docstring(code):
    """The function's code without its docstring, so the query isn't copied inside the answer.

    Returns (code, how) where how is "ast" or "unparsed" (the code doesn't parse; kept as is but counted).
    """
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return code, "unparsed"
    fn = tree.body[0] if tree.body else None
    if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)) or not fn.body:
        return code, "unparsed"
    first = fn.body[0]
    if not (isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant) and isinstance(first.value.value, str)):
        return code, "ast"  # no docstring to remove
    lines = code.splitlines()
    del lines[first.lineno - 1:first.end_lineno]  # drop exactly the docstring's lines
    return "\n".join(lines), "ast"


def run(path, mode="keyword", model_name=None, progress=lambda m: None):
    rows = pq.read_table(path, columns=["func_name", "func_code_string", "func_documentation_string"]).to_pylist()
    order = list(range(len(rows)))
    random.Random(SEED).shuffle(order)
    groups = [order[i:i + GROUP] for i in range(0, len(order) - GROUP + 1, GROUP)]  # leftover dropped

    stripped = [strip_docstring(r["func_code_string"]) for r in rows]
    names = [index.split_name(r["func_name"].rsplit(".", 1)[-1]) for r in rows]  # "YouTube.get_vid" -> "get_vid"
    model = vectors = None
    if mode != "keyword":
        model = embed.load_model(model_name)
        used = sorted({i for g in groups for i in g})
        progress(f"Embedding {len(used)} functions with {model_name}...")
        vecs = embed.embed_pieces(model, [embed.piece_text(names[i], stripped[i][0]) for i in used])
        vectors = dict(zip(used, vecs))

    modes = ["keyword", "meaning", "both"] if mode == "all" else [mode]
    rr = {m: [] for m in modes}
    hits = {m: 0 for m in modes}
    no_words = 0
    weights = ", ".join(map(str, search.WEIGHTS))
    for gi, g in enumerate(groups, start=1):
        con = sqlite3.connect(":memory:")
        con.execute(index.SCHEMA)
        for rowid, i in enumerate(g, start=1):
            con.execute(
                f"INSERT INTO chunks (rowid, {', '.join(index.COLUMNS + index.STORED)}) VALUES (?, {', '.join('?' * (len(index.COLUMNS) + len(index.STORED)))})",
                (rowid, names[i], "", "", "", "", "", stripped[i][0], "function", "", 0, 0, rows[i]["func_name"]),
            )
        if vectors is not None:
            import numpy as np
            matrix = np.stack([vectors[i] for i in g])  # row r-1 is rowid r
            ids = list(range(1, len(g) + 1))
        for rowid, i in enumerate(g, start=1):
            doc = rows[i]["func_documentation_string"]
            q = search.to_query(doc)
            keyword = [x for (x,) in con.execute(
                f"SELECT rowid FROM chunks WHERE chunks MATCH ? ORDER BY bm25(chunks, {weights})", (q,))] if q else []
            ranked = {"keyword": keyword}
            if mode != "keyword":
                meaning = embed.nearest(matrix, ids, embed.embed_query(model, doc), len(ids))
                ranked["meaning"] = meaning
                ranked["both"] = embed.fuse(keyword, meaning)
            if not keyword:
                no_words += 1
            for m in modes:
                if rowid in ranked[m]:
                    pos = ranked[m].index(rowid) + 1
                    rr[m].append(1 / pos)
                    hits[m] += pos <= TOP
                else:
                    rr[m].append(0.0)  # not returned at all counts as a miss
        con.close()
        progress(f"group {gi} of {len(groups)}")

    n = len(rr[modes[0]])
    return {
        "queries": n,
        "groups": len(groups),
        "modes": {m: {"mrr": sum(rr[m]) / n, "hit_at_5": hits[m] / n} for m in modes},
        "unparsed_code": sum(how == "unparsed" for _, how in (stripped[i] for g in groups for i in g)),
        "queries_with_no_words": no_words,
    }


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("parquet", nargs="?", default="data/csn_python_test.parquet")
    p.add_argument("--mode", choices=["keyword", "meaning", "both", "all"], default="keyword")
    p.add_argument("--model", default="BAAI/bge-small-en-v1.5")
    a = p.parse_args()
    r = run(Path(a.parquet), a.mode, a.model, progress=lambda m: print(m, flush=True))
    print(f"CodeSearchNet Python, {Path(a.parquet).name}" + (f", model {a.model}" if a.mode != "keyword" else ""))
    print(f"Queries: {r['queries']} in {r['groups']} groups of {GROUP} (1 right answer, 999 distractors), seed {SEED}")
    for m, v in r["modes"].items():
        print(f"{m:8} MRR {v['mrr']:.4f}   hit rate at {TOP}: {v['hit_at_5']:.4f}")
    print(f"Functions that didn't parse (docstring left in): {r['unparsed_code']}")
    print(f"Queries with no keyword matches: {r['queries_with_no_words']}")
