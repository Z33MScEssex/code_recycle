"""Read and check the settings file.

Source: Python docs, tomllib, "Examples" (research plan Topic 8).
The layout of the file is original applied work (project plan, "Original design").
"""
import tomllib  # standard-library TOML reader, built in from Python 3.11
from dataclasses import dataclass, field  # a plain record type for the checked settings
from pathlib import Path  # path handling that works the same on Linux, macOS and Windows

# Every key the settings file may use, per section. Anything else is a typo and is refused,
# because a misspelt rule (say "no_sugest_into") would otherwise be silently ignored.
ALLOWED = {
    "index": {"folders", "include", "skip", "use_gitignore", "max_file_kb", "index_path"},
    "rules": {"no_suggest_from", "no_suggest_into"},
    "secrets": {"allow", "strict"},
    "embeddings": {"model"},
}

# Code and text file types indexed when the settings file doesn't say. Data files (JSON, CSV),
# notebooks and logs are left out on purpose: they are big, noisy and rarely worth reusing.
DEFAULT_INCLUDE = [
    "*.py", "*.pyi", "*.md", "*.rst", "*.txt", "*.toml", "*.yaml", "*.yml", "*.cfg", "*.ini",
    "*.sh", "*.bash", "*.ps1", "*.sql", "*.js", "*.mjs", "*.ts", "*.tsx", "*.jsx", "*.java",
    "*.kt", "*.go", "*.rs", "*.c", "*.h", "*.cpp", "*.hpp", "*.cs", "*.rb", "*.php", "*.r", "*.R",
    "*.swift", "*.scala", "*.lua", "*.html", "*.css", "Dockerfile", "Makefile", "*.mk",
]

EXAMPLE = """\
# code_recycle settings. Paths may start with ~ or be relative to this file.

[index]
folders = ["~/projects"]          # folders to search; each one is indexed separately
# include = ["*.py", "*.md"]      # file types to index; leave out to use the built-in list of code and text types
skip = ["node_modules/", "*.min.js", "data/"]  # gitignore-style patterns, relative to each folder
use_gitignore = true              # also honour the .gitignore at the top of each folder
max_file_kb = 1024                # bigger files are skipped and listed in the index report
index_path = ".code_recycle/index.db"  # where the index is stored

[rules]
# Patterns are relative to each indexed folder, in gitignore style.
no_suggest_from = []              # never return results that live here
no_suggest_into = []              # searches made from here only say "matches exist elsewhere"

[secrets]
allow = []                        # files the secret scanner flagged that you have checked and allow
strict = false                    # true also flags random-looking text: safer, but many false alarms

[embeddings]
# Search by meaning as well as by keyword. Needs: pip install "code-recycle[embed]"
# The model (about 67 MB) downloads once, then everything runs offline.
model = ""                        # "" for keyword only, or "BAAI/bge-small-en-v1.5"
"""


class SettingsError(ValueError):
    """The settings file is missing, unreadable or has a mistake. The message says what to fix."""


@dataclass
class Settings:
    folders: list[Path]  # absolute folders to index
    skip: list[str] = field(default_factory=list)  # extra gitignore-style skip patterns
    use_gitignore: bool = True  # honour each folder's top-level .gitignore
    max_file_kb: int = 1024  # size limit per file, in kilobytes
    index_path: Path = Path(".code_recycle/index.db")  # absolute path of the index file
    no_suggest_from: list[str] = field(default_factory=list)  # results never come from here
    no_suggest_into: list[str] = field(default_factory=list)  # queries from here get no suggestions
    secrets_allow: list[str] = field(default_factory=list)  # scanner-flagged files the user allows
    secrets_strict: bool = False  # also run the high-entropy detectors
    include: list[str] = field(default_factory=lambda: list(DEFAULT_INCLUDE))  # file types to index
    embed_model: str = ""  # "" means keyword search only


def _str_list(value, name):
    # A list of strings is the only shape a pattern or folder list may take
    if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
        raise SettingsError(f"'{name}' must be a list of strings, for example [\"src/\"]")
    return value


def _resolve(raw, base):
    # Expand ~ and make a relative path relative to the settings file, not the working directory,
    # because an MCP host starts the tool from its own working directory
    p = Path(raw).expanduser()
    return p if p.is_absolute() else (base / p).resolve()


def load(path):
    """Read a settings file and return checked Settings, or raise SettingsError saying what is wrong."""
    path = Path(path).expanduser().resolve()  # absolute, so error messages name the real file
    try:
        with open(path, "rb") as f:  # tomllib needs the file opened in binary mode
            data = tomllib.load(f)  # parse the TOML into plain dicts and lists
    except FileNotFoundError:
        raise SettingsError(f"No settings file at {path}. Run 'code-recycle init' to write an example.")
    except tomllib.TOMLDecodeError as e:
        raise SettingsError(f"{path} is not valid TOML: {e}")

    for section, keys in data.items():  # refuse unknown sections and keys, so typos are caught
        if section not in ALLOWED:
            raise SettingsError(f"Unknown section [{section}] in {path}. Allowed: {', '.join(ALLOWED)}")
        if not isinstance(keys, dict):
            raise SettingsError(f"[{section}] in {path} must be a table of settings")
        for key in keys:
            if key not in ALLOWED[section]:
                raise SettingsError(f"Unknown setting '{key}' in [{section}]. Allowed: {', '.join(sorted(ALLOWED[section]))}")

    index = data.get("index", {})  # the only section that must exist, because folders are required
    rules = data.get("rules", {})
    secrets = data.get("secrets", {})
    base = path.parent  # relative paths are read from the settings file's own folder

    folders = [_resolve(f, base) for f in _str_list(index.get("folders", []), "folders")]
    if not folders:
        raise SettingsError("[index] folders is empty. List at least one folder to search.")
    missing = [str(f) for f in folders if not f.is_dir()]  # a folder that doesn't exist is a mistake
    if missing:
        raise SettingsError(f"These folders don't exist: {', '.join(missing)}")

    use_gitignore = index.get("use_gitignore", True)
    if not isinstance(use_gitignore, bool):  # TOML true/false only, not "yes"
        raise SettingsError("'use_gitignore' must be true or false")
    max_kb = index.get("max_file_kb", 1024)
    if not isinstance(max_kb, int) or isinstance(max_kb, bool) or max_kb <= 0:  # bool is an int in Python
        raise SettingsError("'max_file_kb' must be a whole number above 0")
    strict = secrets.get("strict", False)
    if not isinstance(strict, bool):
        raise SettingsError("'strict' must be true or false")
    include = _str_list(index.get("include", DEFAULT_INCLUDE), "include")
    if not include:
        raise SettingsError("[index] include is empty. Leave it out to use the built-in list.")
    embed_model = data.get("embeddings", {}).get("model", "")
    if not isinstance(embed_model, str):
        raise SettingsError("[embeddings] model must be a model name in quotes, or \"\" for keyword only")
    index_path = index.get("index_path", ".code_recycle/index.db")
    if not isinstance(index_path, str):
        raise SettingsError("'index_path' must be a path in quotes")

    return Settings(
        folders=folders,
        skip=_str_list(index.get("skip", []), "skip"),
        use_gitignore=use_gitignore,
        max_file_kb=max_kb,
        index_path=_resolve(index_path, base),
        no_suggest_from=_str_list(rules.get("no_suggest_from", []), "no_suggest_from"),
        no_suggest_into=_str_list(rules.get("no_suggest_into", []), "no_suggest_into"),
        secrets_allow=_str_list(secrets.get("allow", []), "allow"),
        secrets_strict=strict,
        include=list(include),
        embed_model=embed_model,
    )
