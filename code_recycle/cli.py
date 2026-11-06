"""The code-recycle command: init, index, search and serve.

Installed as a command by [project.scripts] in pyproject.toml (research plan Topic 12).
"""
import argparse  # reads the command-line options
import os  # the CODE_RECYCLE_SETTINGS environment variable
import sys  # exit codes and error output
from pathlib import Path  # paths that work on every platform

from . import __version__, files, index, search, settings as settings_mod

DEFAULT_NAME = "code_recycle.toml"


def find_settings(given):
    """Which settings file to use: --settings, then $CODE_RECYCLE_SETTINGS, then ./code_recycle.toml,
    then ~/.config/code_recycle/code_recycle.toml."""
    if given:
        return Path(given)
    if os.environ.get("CODE_RECYCLE_SETTINGS"):
        return Path(os.environ["CODE_RECYCLE_SETTINGS"])
    local = Path.cwd() / DEFAULT_NAME
    if local.exists():
        return local
    return Path.home() / ".config" / "code_recycle" / DEFAULT_NAME


def main(argv=None):
    p = argparse.ArgumentParser(prog="code-recycle", description="Search your own code and verified sources before the web.")
    p.add_argument("--version", action="version", version=f"code-recycle {__version__}")
    p.add_argument("--settings", help="settings file (default: ./code_recycle.toml, then ~/.config/code_recycle/)")
    sub = p.add_subparsers(dest="command", required=True)
    sub.add_parser("init", help="write an example settings file in this folder")
    sub.add_parser("index", help="build or rebuild the index and print the index report")
    q = sub.add_parser("search", help="search from the command line")
    q.add_argument("query", nargs="+", help="what you're looking for, in plain words")
    q.add_argument("--from", dest="from_path", help="the file or folder you're working in, for reuse rules")
    q.add_argument("-n", "--limit", type=int, default=5)
    sub.add_parser("serve", help="run the MCP server over stdio (what an MCP client launches)")
    a = p.parse_args(argv)

    if a.command == "init":
        target = Path(a.settings or DEFAULT_NAME)
        if target.exists():
            print(f"{target} already exists; not overwriting it.", file=sys.stderr)
            return 1
        target.write_text(settings_mod.EXAMPLE)
        print(f"Wrote {target}. Edit the folders list, then run: code-recycle index")
        return 0

    path = find_settings(a.settings)
    try:
        s = settings_mod.load(path)
        if a.command == "index":
            walked = index.build(s)
            print(files.report(walked))
        elif a.command == "search":
            print(search.format_answer(search.search(s, " ".join(a.query), from_path=a.from_path, limit=a.limit)))
        elif a.command == "serve":
            from .server import build_server  # imported here so the other commands don't need the MCP SDK loaded
            build_server(path).run()  # blocks, speaking MCP over stdin and stdout
    except (settings_mod.SettingsError, index.IndexBuildError) as e:
        print(f"code-recycle: {e}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
