# Changelog

## 0.1.0 (2026-11-06)

First release.

- Index folders: Python split by function, method and class with line numbers; Markdown research
  notes read as structured entries (URL, where on the page, what it taught, copied code); other
  Markdown by heading; other text in 60-line windows.
- Keyword search with SQLite FTS5: stemming, camelCase splitting, per-field weights, identical
  copies shown once.
- MCP tool `search_own_work`, read-only, over stdio.
- Command `code-recycle`: `init`, `index`, `search`, `serve`.
- Settings file with typo checking, skip rules, `.gitignore` support and a file-type list.
- Secrets: secret-named files never opened, every file scanned before indexing, every result
  scanned before returning, and a self-check that stops indexing if the scanner can't see a
  planted fake key.
- Reuse rules: `no_suggest_from` and `no_suggest_into`. Rules apply before duplicate copies are
  removed, and the MCP tool falls back to the folder it was started in when no `from_path` is given.
- Accuracy published: CodeSearchNet Python MRR 0.797; own research notes MRR 0.308.
- Experimental, off by default: meaning search with local embeddings (`pip install "code-recycle[embed]"`).
  Tested and not adopted; see `results/prereg_embeddings.md`.
