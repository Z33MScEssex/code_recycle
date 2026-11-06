# code_recycle

Search your own code and your own verified sources before you search the web.

Every new project I start, I end up looking for the same things again: how to retry a request,
how to read a settings file, which page had that bootstrap example. Most of the time I've already
solved it in another project, and I've already checked the source. I just can't find it.

Companies have the same problem, with a twist. Pasting internal code or questions into outside
tools is a risk, so the search needs to stay on the machine.

code_recycle indexes your folders and answers "have I already solved this?" with the file and line
numbers. If you keep research notes with a source URL and the code you copied from it, it finds
those too, with the link and what you learned. It runs locally, needs no account and no API key,
and plugs into Claude Code, Codex, Cursor or any MCP client.

## Try it in 5 minutes

Needs Python 3.11 or newer.

```bash
git clone https://github.com/Z33MScEssex/code_recycle
cd code_recycle
pip install .
cd examples/demo
code-recycle index
code-recycle search "read a settings file"
```

The first result is a research note: the Python docs page for `tomllib`, where on the page, what it
taught, and the code copied from it. Try `code-recycle search "try a request again with a wait"`
and you get the `retry` function from `tools/http_utils.py`, lines 14 to 24.

## Use it on your own folders

```bash
code-recycle init          # writes code_recycle.toml here; edit the folders list
code-recycle index         # builds the index and prints what was skipped and why
code-recycle search "parse an iso date"
```

Re-run `code-recycle index` after big changes. It reads everything again; on my laptop that's about
40 seconds for 1,500 files.

## Connect it to an AI coding assistant

The tool is called `search_own_work`. It's read-only. Hosts start it with a near-empty environment,
so give the settings file's full path.

Claude Code:

```bash
claude mcp add code-recycle -e CODE_RECYCLE_SETTINGS=/full/path/to/code_recycle.toml -- code-recycle serve
```

Codex:

```bash
codex mcp add code-recycle --env CODE_RECYCLE_SETTINGS=/full/path/to/code_recycle.toml -- code-recycle serve
```

If the host can't find `code-recycle`, use the full path from `which code-recycle` (or
`where code-recycle` on Windows).

## Research notes it understands

A Markdown section becomes a research entry when it has a URL field. These labels are read, bold
or plain:

```markdown
## Topic 1: Read a TOML settings file

- **URL:** https://docs.python.org/3/library/tomllib.html
- **Where on the page:** "Examples", the first example.
- **What it taught:** the file must be opened in binary mode.
- **Code pattern from source:**
    (a fenced code block)
```

Everything else is still indexed: Python by function, method and class with exact line numbers,
other Markdown by heading, and other text files in overlapping windows of 60 lines.

## How well it works

Measured, not assumed. The test design was written down before the first run, and nothing was
tuned on the test sets. Full write-up: [results/accuracy_2026-11-05.md](results/accuracy_2026-11-05.md).

| Test | What it asks | Result |
|---|---|---|
| CodeSearchNet, Python | Find a function from its docstring among 999 others (Husain et al. 2019) | MRR 0.797, right function in the top 5 87% of the time |
| My own research notes | Find another note that used the same source, from a topic heading | MRR 0.308, top 5 39% of the time, 51 cases |

The second test is the real job, and it's much harder. The same source often gets described in
different words in different projects, and keyword search can't bridge that.

I tried meaning-based search with a small local embedding model. It lifted CodeSearchNet to 0.907,
but it didn't help on my own notes (0.250 against 0.280 at the time), and the rule set beforehand
said it had to improve both. So v0.1 ships keyword search. The embeddings code is in the repo,
switched off and marked experimental: [results/prereg_embeddings.md](results/prereg_embeddings.md).

## Privacy and secrets

- Nothing leaves your machine. There are no network calls, unless you switch on the experimental
  embeddings, which download a model once.
- Files named like secrets (`.env`, `*.pem`, `id_rsa` and others) are never opened.
- Every other file is scanned with [detect-secrets](https://github.com/Yelp/detect-secrets) before
  it's indexed. A flagged file is skipped and listed in the index report. If you've checked it's
  safe, add it to `[secrets] allow`.
- Every result is scanned again before it's returned, for common live key formats (AWS, GitHub,
  Slack, OpenAI-style, Telegram bot tokens, private key blocks). If one matches, the content is
  withheld and only the location is shown.
- If the scanner fails its own self-check (it must spot a planted fake key), nothing is indexed.

Each of these behaviours has a test with fake keys. That isn't a guarantee: a pattern scanner can't
catch every possible secret, so don't point the tool at folders you know hold live credentials.

## Reuse rules

Some folders shouldn't borrow from others. I have one project where every requirement must be
researched fresh, so code from other projects must never be suggested into it.

```toml
[rules]
no_suggest_from = ["private/"]    # never return results from here
no_suggest_into = ["clean-room/"] # searches made from here only see this folder's own code,
                                  # plus a note that other matches exist
```

The MCP tool takes a `from_path`, so the assistant can say where it's working. If it doesn't, the
folder the server was started in is used. The rules are a guard against accidents, not a security
boundary: they trust the path they're given.

## Settings

`code-recycle init` writes a commented example. The settings file is found in this order:
`--settings`, then `$CODE_RECYCLE_SETTINGS`, then `./code_recycle.toml`, then
`~/.config/code_recycle/code_recycle.toml`. Typos are refused with a clear message, because a
misspelt rule silently ignored would be worse.

## Limits

- Python is the only language split by function. Others are searched in windows of lines.
- The index is rebuilt in full each time. Fine for a few thousand files; not built for huge monorepos.
- Search is keyword-based (SQLite FTS5 with stemming), so it finds shared words, not shared ideas.
- So far only I have used it. It has had no outside users yet.

## Development

```bash
pip install -e ".[dev]"
pytest
```

87 tests. The CI workflow runs them on Linux, macOS and Windows with Python 3.11 to 3.13 on every push. How sources were
checked and how accuracy was measured: [METHOD.md](METHOD.md). Benchmarks: [bench/README.md](bench/README.md).

MIT licence.
