"""Keep secrets out of the index and out of every result.

The policy is original applied work (research plan Topic 10, after the GPT check). It promises
only what the tests prove:
1. Files with a known secret name are never opened.
2. Every other file is scanned with detect-secrets before it is read in. A flagged file is
   skipped and listed in the index report, unless the user allows it by name.
3. Every field returned to a client is scanned again with a small built-in pattern list.

Source for step 2: detect-secrets README, "Usage in Other Python Scripts", "Basic Use" and
"More Advanced Configuration" (choosing detectors with plugins_used).
By default only named-credential detectors run. The two "high entropy" detectors flag any
random-looking text (hashes, logs, notebook images), so they only run with strict = true.
"""
import os  # removing the canary file
import re  # the built-in patterns for step 3
import tempfile  # a throwaway file for the canary check
from contextlib import contextmanager  # lets one scanner set-up serve a whole walk
from pathspec import GitIgnoreSpec  # gitignore-style matching, research plan Topic 9
from detect_secrets import SecretsCollection  # holds whatever one scan finds
from detect_secrets.settings import transient_settings  # run the scanner with a chosen set of detectors

# Step 1: names that hold secrets by convention. Never opened, and allow-listing can't override this.
SECRET_NAMES = GitIgnoreSpec.from_lines([
    ".env", ".env.*", "*.pem", "*.key", "*.p12", "*.pfx", "id_rsa", "id_dsa", "id_ecdsa", "id_ed25519",
    ".netrc", ".pypirc", ".npmrc", "credentials.json", "*.keystore", "*.jks",
])

# Step 3: patterns for the commonest live credentials. Short on purpose; the file scan is the main
# defence and this is the second line. Each entry: (name shown to the user, compiled pattern).
TEXT_PATTERNS = [
    ("AWS access key", re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b")),
    ("GitHub token", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{36,}\b")),
    ("GitHub fine-grained token", re.compile(r"\bgithub_pat_[A-Za-z0-9_]{22,}\b")),
    ("Slack token", re.compile(r"\bxox[abprs]-[A-Za-z0-9-]{10,}\b")),
    ("OpenAI-style key", re.compile(r"\bsk-[A-Za-z0-9_-]{20,}\b")),
    ("Private key block", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
    ("Telegram bot token", re.compile(r"\b\d{8,10}:[A-Za-z0-9_-]{35}\b")),
]

# Step 2 detectors, named as in detect-secrets 1.5.0 (pinned in pyproject.toml).
NAMED_DETECTORS = [
    "ArtifactoryDetector", "AWSKeyDetector", "AzureStorageKeyDetector", "BasicAuthDetector",
    "CloudantDetector", "DiscordBotTokenDetector", "GitHubTokenDetector", "GitLabTokenDetector",
    "IbmCloudIamDetector", "IbmCosHmacDetector", "JwtTokenDetector", "KeywordDetector",
    "MailchimpDetector", "NpmDetector", "OpenAIDetector", "PrivateKeyDetector", "PypiTokenDetector",
    "SendGridDetector", "SlackDetector", "SoftlayerDetector", "SquareOAuthDetector", "StripeDetector",
    "TelegramBotTokenDetector", "TwilioKeyDetector",
]
ENTROPY_DETECTORS = ["Base64HighEntropyString", "HexHighEntropyString"]  # only with strict = true


def is_secret_name(relpath):
    """True if this path's name marks it as a secrets file (step 1)."""
    return SECRET_NAMES.match_file(relpath)  # matches the name at any depth, as .gitignore would


@contextmanager
def file_scanner(strict=False):
    """Set the scanner up once and yield a function that scans one file (step 2).

    The function returns the names of detectors that fired; an empty list means nothing was found.
    """
    names = NAMED_DETECTORS + (ENTROPY_DETECTORS if strict else [])
    with transient_settings({"plugins_used": [{"name": n} for n in names]}):  # only these detectors run
        def scan(path):
            found = SecretsCollection()  # a fresh collection per file, so results never mix
            found.scan_file(str(path))  # scans the file's lines; it never changes the file
            return sorted({hit["type"] for hits in found.json().values() for hit in hits})  # unique names
        _canary(scan)  # fail closed: refuse to run if the scanner can't see a planted fake key
        yield scan


class ScannerBroken(RuntimeError):
    """The secret scanner missed a planted fake key, so nothing is indexed rather than risk a leak."""


def _canary(scan):
    # AWS's documented example key, built from pieces so this file holds no key-shaped text
    fake = "AKIA" + "IOSFODNN7" + "EXAMPLE"
    fd, path = tempfile.mkstemp(suffix=".py")
    try:
        with os.fdopen(fd, "w") as f:
            f.write(f'key = "{fake}"\n')
        if "AWS Access Key" not in scan(path):
            raise ScannerBroken("The secret scanner failed its self-check. Nothing was indexed.")
    finally:
        os.remove(path)


def scan_file(path, strict=False):
    """Scan a single file. For many files, use file_scanner so set-up happens once."""
    with file_scanner(strict) as scan:
        return scan(path)


def scan_text(text):
    """Pattern names that match this text (step 3). An empty list means it's safe to return."""
    return [name for name, pattern in TEXT_PATTERNS if pattern.search(text)]
