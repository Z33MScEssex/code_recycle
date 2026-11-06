"""Walk the indexed folders, deciding which files go in and recording why the rest don't.

Skip rules use pathspec's GitIgnoreSpec (research plan Topic 9). The order of checks and the
index report are original applied work.
"""
import os  # os.walk, so whole skipped folders are never entered
from dataclasses import dataclass, field  # plain records for the walk's results
from concurrent.futures import ProcessPoolExecutor  # spreads the slow secret scan over every CPU core
from pathlib import Path  # path handling that works on every platform
from pathspec import GitIgnoreSpec  # Git's own .gitignore behaviour, edge cases included

from . import secret_check as secrets  # the secrets policy (Topic 10); not named secrets.py, which is a standard-library module

ALWAYS_SKIP = [  # never useful to search
    ".git/", ".hg/", ".svn/", "__pycache__/", "*venv/", "node_modules/", "site-packages/",
    ".pytest_cache/", ".mypy_cache/", ".ruff_cache/", ".tox/", ".code_recycle/",
    "code_recycle.toml",  # the settings file itself
]


@dataclass
class Skipped:
    path: str  # path relative to its indexed folder
    reason: str  # plain-words reason shown in the index report


@dataclass
class Walk:
    included: list = field(default_factory=list)  # (folder, relative path) pairs to index
    skipped: list = field(default_factory=list)  # Skipped records for the index report


def _spec(lines):
    return GitIgnoreSpec.from_lines(lines)  # compile once, match many times


def _is_binary(path):
    # Original rule: a zero byte in the first 8 KB means it isn't text worth searching
    with open(path, "rb") as f:
        return b"\0" in f.read(8192)


def walk(settings):
    """Every file under each folder, sorted into included and skipped, with a reason for each skip.

    Two passes: cheap checks first, then the slow secret scan on what's left, spread over every CPU core.
    """
    out = Walk()
    user_skip = _spec(ALWAYS_SKIP + settings.skip)  # built-in skips plus the user's own
    allow = _spec(settings.secrets_allow)  # files the user checked and allowed despite a scanner flag
    include = _spec(settings.include)  # file types worth indexing
    candidates = []  # (folder, relative path, full path, needs a secret scan), in walk order
    for folder in settings.folders:
        gitignore = _spec([])  # empty unless the folder has its own .gitignore
        gi = folder / ".gitignore"
        if settings.use_gitignore and gi.is_file():
            with open(gi, encoding="utf-8", errors="replace") as f:
                gitignore = _spec(f)  # a file object works as the list of lines
        for root, dirs, names in os.walk(folder):
            rel_root = Path(root).relative_to(folder).as_posix()  # posix slashes, so patterns match on Windows too
            prefix = "" if rel_root == "." else rel_root + "/"
            # Prune skipped folders here so os.walk never goes inside them. Patterns ending in "/"
            # only match folders, so each name is tested with a trailing slash.
            kept = []
            for d in sorted(dirs):
                rel = prefix + d + "/"
                if user_skip.match_file(rel):
                    out.skipped.append(Skipped(rel, "skip rule"))
                elif gitignore.match_file(rel):
                    out.skipped.append(Skipped(rel, ".gitignore"))
                else:
                    kept.append(d)
            dirs[:] = kept  # changing the list in place is how os.walk is told not to descend
            for name in sorted(names):
                rel = prefix + name
                full = Path(root) / name
                reason = _cheap_check(full, rel, settings, user_skip, gitignore, include)
                if reason:
                    out.skipped.append(Skipped(rel, reason))
                else:
                    candidates.append((folder, rel, full, not allow.match_file(rel)))
    to_scan = [full for _, _, full, needs in candidates if needs]
    found = dict(zip(to_scan, _scan_all(to_scan, settings.secrets_strict)))  # full path -> detector names
    for folder, rel, full, needs in candidates:
        if needs and found[full]:
            out.skipped.append(Skipped(rel, "possible secret: " + ", ".join(found[full])))
        else:
            out.included.append((folder, rel))
    return out


def _cheap_check(full, rel, settings, user_skip, gitignore, include):
    # Every check that doesn't need the secret scanner, cheapest first. Returns a reason or None.
    if secrets.is_secret_name(rel):
        return "secret file name (never read)"
    if user_skip.match_file(rel):
        return "skip rule"
    if gitignore.match_file(rel):
        return ".gitignore"
    if not include.match_file(rel):
        return "file type not included"
    if full.is_symlink():
        return "symbolic link"  # a link could point outside the folder the user chose
    size = full.stat().st_size
    if size > settings.max_file_kb * 1024:
        return f"over {settings.max_file_kb} KB"
    if size == 0:
        return "empty"
    if _is_binary(full):
        return "binary"
    return None


PARALLEL_FROM = 50  # below this many files, starting worker processes costs more than it saves
_worker_ctx = None  # each worker keeps its scanner's with-block open; if this were dropped, the block would close
_worker_scan = None  # and the scanner would silently run with no detectors (caught by a test)


def _init_worker(strict):
    global _worker_ctx, _worker_scan
    _worker_ctx = secrets.file_scanner(strict)  # the scanner's settings live inside a with-block
    _worker_scan = _worker_ctx.__enter__()  # entered once and kept open for the worker's life


def _scan_in_worker(path):
    return _worker_scan(path)


def _scan_all(paths, strict):
    """Secret-scan every path, in order. Uses every CPU core when there are enough files."""
    if len(paths) < PARALLEL_FROM:
        with secrets.file_scanner(strict) as scan:
            return [scan(p) for p in paths]
    with ProcessPoolExecutor(initializer=_init_worker, initargs=(strict,)) as pool:  # one worker per core
        return list(pool.map(_scan_in_worker, paths, chunksize=16))  # map keeps the input order


def report(result):
    """A plain-words index report: what went in, what didn't, and why."""
    n = len(result.included)
    lines = [f"Indexed {n} file{'' if n == 1 else 's'}. Skipped {len(result.skipped)}."]
    flagged = [s for s in result.skipped if s.reason.startswith("possible secret")]
    if flagged:
        lines.append("")
        lines.append("Skipped because they may hold a secret. Check each one; if it's safe, add it to [secrets] allow:")
        lines += [f"  {s.path} ({s.reason})" for s in flagged]
    counts = {}
    for s in result.skipped:
        if not s.reason.startswith("possible secret"):
            counts[s.reason] = counts.get(s.reason, 0) + 1
    if counts:
        lines.append("")
        lines.append("Other skips:")
        lines += [f"  {reason}: {n}" for reason, n in sorted(counts.items())]
    return "\n".join(lines)
