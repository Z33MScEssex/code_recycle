"""Search by meaning: local embeddings through fastembed, stored in the same SQLite index.

Sources: fastembed README, "Quickstart" and "Dense text embeddings"; fastembed's own
TextEmbedding.query_embed docstring for the query form (research plan Topic 4).
Vectors live in a plain SQLite table and are compared with numpy, so no vector database is needed
(Topic 5: about 25,000 pieces of 384 numbers is under 40 MB). Combining with keyword results uses
Reciprocal Rank Fusion, k = 60 (Cormack et al. 2009, Topic 6).

fastembed is an optional install: pip install "code-recycle[embed]". Without it, search is keyword only.
"""
MAX_CHARS = 400  # each piece is cut to this before embedding (results/prereg_embeddings.md, amendment 1)
EMBEDDED_KINDS = {"function", "method", "class", "module", "research_entry"}  # sections and text windows stay keyword only
RRF_K = 60  # from the RRF paper; not tuned


class EmbeddingsUnavailable(RuntimeError):
    """Embeddings are switched on in settings but fastembed isn't installed."""


def load_model(name):
    try:
        from fastembed import TextEmbedding  # imported here, so keyword-only installs never need it
    except ImportError:
        raise EmbeddingsUnavailable(
            'Embeddings are on in settings, but fastembed is not installed. Run: pip install "code-recycle[embed]"'
        )
    return TextEmbedding(model_name=name)  # downloads the model on first use, then works offline


def piece_text(name, text, taught="", where="", code=""):
    """What gets embedded for one piece (results/prereg_embeddings.md, amendment 1).

    Code pieces: the name, then the piece's own text. Research entries: the heading, what it
    taught, where on the page, then the copied code. Cut to MAX_CHARS.
    """
    parts = (name, taught, where, code) if (taught or where or code) else (name, text)
    return "\n".join(p for p in parts if p)[:MAX_CHARS]


def embed_pieces(model, texts):
    """Document vectors, unit length, as one float32 numpy array (one row per text)."""
    import numpy as np  # installed with fastembed
    v = np.array(list(model.embed(texts)), dtype=np.float32)
    return v / np.maximum(np.linalg.norm(v, axis=1, keepdims=True), 1e-12)  # unit length, so a dot product is cosine


def embed_query(model, text):
    import numpy as np
    v = np.array(list(model.query_embed([text]))[0], dtype=np.float32)  # the model's query form
    return v / max(float(np.linalg.norm(v)), 1e-12)


def nearest(matrix, rowids, qvec, n):
    """The n rowids whose vectors are closest in meaning to the query, best first."""
    import numpy as np
    scores = matrix @ qvec  # cosine similarity, because every vector is unit length
    n = min(n, len(rowids))
    top = np.argpartition(-scores, n - 1)[:n]  # the n best, unordered (fast)
    return [rowids[i] for i in top[np.argsort(-scores[top])]]  # then ordered


def fuse(*rankings, k=RRF_K):
    """Reciprocal Rank Fusion: each item scores the sum of 1 / (k + rank) over the rankings it appears in."""
    score = {}
    for ranking in rankings:
        for rank, item in enumerate(ranking, start=1):
            score[item] = score.get(item, 0.0) + 1.0 / (k + rank)
    return sorted(score, key=lambda item: -score[item])
