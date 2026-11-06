# Embeddings: decided before any accuracy run (2026-11-05)

Written before any embedding result was seen. The keyword-only baseline is
`results/accuracy_2026-11-05.md` and is frozen.

## What is being tried

Search by meaning, using a small local embedding model through fastembed (no GPU, no server),
combined with the existing keyword search by Reciprocal Rank Fusion (k = 60, from the paper; not
tuned).

Two candidate models, chosen before testing:
1. `BAAI/bge-small-en-v1.5`: general English text, 384 dimensions, 67 MB, MIT. fastembed's default.
2. `jinaai/jina-embeddings-v2-base-code`: trained on code and English, 768 dimensions, 640 MB, Apache 2.0.

Queries use the model's query form (`query_embed`) and indexed pieces its document form (`embed`).
Each piece is embedded as its name, then its "what it taught" text if any, then its text, cut to
2,000 characters.

## How the model is chosen

On the CodeSearchNet **validation** split only (a different set of repositories from the test
split, so the test is never used to choose). Same protocol as the baseline: groups of 1,000, seed
2026. For each model, three ways are scored: keyword only, meaning only, and both combined. The
best MRR on validation wins. If a model is too slow to index my project folder in under 5 minutes on
this laptop, it's ruled out whatever its score.

## How the result is judged

The chosen setup is then run once on:
- the CodeSearchNet **test** split, and
- my 49 own-entry cases.

Embeddings go into v0.1 only if both hold:
- own-entries MRR is above the keyword baseline of 0.280, and
- CodeSearchNet test MRR is no more than 0.01 below the keyword baseline of 0.797.

Otherwise v0.1 ships keyword search only, and the result is published either way. Nothing is
re-run with different settings after the test numbers are seen.

## Amendment 1 (2026-11-05, before any accuracy run)

Speed measured first, as the rule above requires. On this laptop (Intel i5-1335U, running at about
1.2 GHz), embedding 2,000-character pieces runs at about 6 per second for bge-small, so my
24,000 pieces would take about 68 minutes. jina-code ran at 1 per second, about 7 hours. Both fail
the 5-minute rule as first written. More threads and all-core mode made no difference.

No accuracy number has been seen. The design changes so meaning search fits the time limit:
- Only bge-small is tried. jina-code is ruled out on speed.
- Only these pieces are embedded: functions, methods, classes and module docstrings (name plus the
  first 400 characters of the piece), and research entries (heading, what it taught, where on the
  page, then the code, cut to 400 characters). Markdown sections and plain-text windows stay keyword
  only, and keep their keyword ranking in the combined list.
- Speed is re-measured on my project folder with this rule. It must still finish in under 5 minutes, or
  v0.1 ships keyword only.
- The validation step, the decision rule and the "no re-runs after the test numbers" rule are
  unchanged.

## Validation result and choice (2026-11-05, before any test run)

CodeSearchNet Python validation split, 23,000 queries, bge-small (`results/csn_validation_2026-11-05.txt`):

| Mode | MRR | Top 5 |
|---|---|---|
| keyword | 0.8067 | 88.2% |
| meaning | 0.9037 | 95.0% |
| both (RRF) | 0.8799 | 94.1% |

By the rule above, **meaning only** is chosen, and it is the setup run on both test sets.

Noted before the test run: in the real tool only code and research entries have meaning vectors
(amendment 1). With meaning only, Markdown sections and text windows could only be found by keyword
search. That is a product question for after the tests, and doesn't change what is tested.

## Test result and decision (2026-11-05)

Run once, with the chosen setup (meaning only, bge-small). Not re-run.

| Test | Keyword baseline | Meaning only | Rule | Passed? |
|---|---|---|---|---|
| My 49 own entries, MRR | 0.280 | 0.250 | must be above 0.280 | **No** |
| CodeSearchNet Python test, MRR | 0.797 | 0.907 | no more than 0.01 below 0.797 | Yes |

Top 5: own entries 36.7% to 30.6%; CodeSearchNet 87.3% to 95.3%. Own entries not found at all in the
top 200: 11 to 16.

**Decision: embeddings fail the rule, so v0.1 ships keyword search only.** The embeddings code stays
in the repository, switched off by default, and is described as experimental with these numbers.

What it shows: on the public benchmark, meaning search is clearly better. On the job the tool was
built for, it is slightly worse on 49 cases, which is a small sample. A general-purpose small model
reading a research heading doesn't match how the same source was described elsewhere in my
notes any better than shared keywords do. Any later attempt needs a new pre-registration and fresh
cases, because these 49 have now been used twice.
