# How this was built

## Sources first, then code

Each design decision has a source, found and checked before that part was built. For each
requirement there's a research note: the page's URL, where on the page, what it taught, and the
code copied from it word for word. During the research, a script checked each copied snippet
against the downloaded page, so a quote that didn't match the page was caught. Where no source
exists (the settings layout, the reuse rules, the secrets policy, the research-note parser), the
design is marked as my own and has its own tests.

The full research plan stays private, because it holds code copied from other people's pages. The
main sources:

| Part | Source |
|---|---|
| MCP server and testing | MCP Python SDK docs and examples (v2, pinned to 2.3.0) |
| Registering with clients | MCP SDK "Connect to a real host"; OpenAI Codex MCP docs |
| Splitting Python code | Python docs, `ast` |
| Keyword search | SQLite FTS5 docs (bm25 column weights, porter stemming, UNINDEXED columns) |
| Combining rankings | Cormack, Clarke and Büttcher (2009), Reciprocal Rank Fusion |
| Scoring | Mean reciprocal rank; CodeSearchNet (Husain et al. 2019) |
| Settings | Python docs, `tomllib` |
| Skip rules | `pathspec` (Git's own .gitignore behaviour) |
| Secrets | `detect-secrets` (Yelp) |
| Packaging and CI | Python Packaging User Guide; GitHub Actions docs |

## A second opinion

Before building, the plan was given to a different AI model (GPT, through the Codex CLI, read-only)
and asked to attack it: what would make it look like a tutorial clone, what was missing, what to
cut. Its points were treated as opinions and checked before anything changed. It cut the first
release down, made the accuracy test fairer, and narrowed the secrets promise to what tests can
prove.

## Measuring accuracy

- The test design was written down before the first run.
- The keyword baseline was frozen before anything else was tried.
- Embeddings were chosen on a validation split and then run once on the test sets, against a rule
  set in advance. They didn't meet the rule, so they're not in v0.1. That result is published too.
- One change was made to that plan before any accuracy run: this laptop embeds about 6 pieces a
  second, so only code and research notes are embedded, cut to 400 characters. It's recorded with
  the reason.
- Leak checks: the CodeSearchNet test was re-run with the docstring deliberately left in the code
  (MRR 0.988, against 0.797) to prove that removing it works, and with function names hidden (0.763)
  to show the result doesn't rest on names alone.
