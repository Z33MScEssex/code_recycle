"""Shared test helpers. Every key below is fake, built at run time so this file holds no key-shaped text."""
import pytest

# Built from pieces so secret scanners (including ours) don't flag the test source itself
FAKE_AWS = "AKIA" + "IOSFODNN7" + "EXAMPLE"  # AWS's own documented example key
FAKE_GITHUB = "ghp_" + "a1B2c3D4e5F6g7H8i9J0" + "k1L2m3N4o5P6q7R8"  # right shape, not a real token


@pytest.fixture
def make_tree(tmp_path):
    """Write a dict of {relative path: text} under a temp folder and return the folder."""
    def _make(files):
        for rel, text in files.items():
            p = tmp_path / rel
            p.parent.mkdir(parents=True, exist_ok=True)  # create any sub-folders
            if isinstance(text, bytes):
                p.write_bytes(text)
            else:
                p.write_text(text)
        return tmp_path
    return _make


@pytest.fixture
def write_settings(tmp_path):
    """Write a settings file next to the tree and return its path."""
    def _write(body):
        p = tmp_path / "code_recycle.toml"
        p.write_text(body)
        return p
    return _write
