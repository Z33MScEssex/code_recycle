import pytest

from code_recycle import secret_check
from conftest import FAKE_AWS, FAKE_GITHUB


@pytest.mark.parametrize("name", [".env", ".env.local", "sub/dir/.env", "certs/site.pem", "id_rsa", "~/.netrc"[2:]])
def test_secret_names_match_at_any_depth(name):
    assert secret_check.is_secret_name(name)


@pytest.mark.parametrize("name", ["env.py", "environment.md", "keys.py", "README.md"])
def test_ordinary_names_do_not_match(name):
    assert not secret_check.is_secret_name(name)


def test_text_scan_catches_keys_in_results():
    assert secret_check.scan_text(f"key = {FAKE_AWS}") == ["AWS access key"]
    assert secret_check.scan_text(f"token: {FAKE_GITHUB}") == ["GitHub token"]
    assert secret_check.scan_text("-----BEGIN RSA PRIVATE KEY-----") == ["Private key block"]


def test_text_scan_passes_ordinary_code():
    assert secret_check.scan_text("def get_key(d):\n    return d['key']\n") == []


def test_file_scan_finds_nothing_in_plain_code(tmp_path):
    p = tmp_path / "plain.py"
    p.write_text("def add(a, b):\n    return a + b\n")
    assert secret_check.scan_file(p) == []


def test_text_scan_catches_a_telegram_bot_token():
    token = "123456789:" + "AAH" + "x" * 32
    assert secret_check.scan_text(f"TG_BOT_TOKEN={token}") == ["Telegram bot token"]


def test_scanner_refuses_to_run_if_it_cannot_see_a_planted_key(monkeypatch):
    monkeypatch.setattr(secret_check, "NAMED_DETECTORS", ["SlackDetector"])  # AWS detector removed
    with pytest.raises(secret_check.ScannerBroken):
        with secret_check.file_scanner():
            pass
