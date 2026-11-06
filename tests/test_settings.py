import pytest

from code_recycle import settings


def test_example_settings_file_is_valid(tmp_path):
    # The example we hand to new users must load, once its folder exists
    (tmp_path / "projects").mkdir()
    p = tmp_path / "code_recycle.toml"
    p.write_text(settings.EXAMPLE.replace("~/projects", "projects"))
    s = settings.load(p)
    assert s.folders == [(tmp_path / "projects").resolve()]
    assert s.use_gitignore is True and s.max_file_kb == 1024


def test_relative_paths_are_read_from_the_settings_file_not_the_working_directory(tmp_path, monkeypatch):
    (tmp_path / "code").mkdir()
    p = tmp_path / "code_recycle.toml"
    p.write_text('[index]\nfolders = ["code"]\nindex_path = "idx.db"\n')
    monkeypatch.chdir("/")  # an MCP host may start us from anywhere
    s = settings.load(p)
    assert s.folders == [(tmp_path / "code").resolve()]
    assert s.index_path == (tmp_path / "idx.db").resolve()


@pytest.mark.parametrize("body, message", [
    ('[index]\nfolders = ["x"]\nno_sugest_into = []\n', "Unknown setting 'no_sugest_into'"),
    ('[indx]\nfolders = ["x"]\n', "Unknown section [indx]"),
    ('[index]\nfolders = []\n', "folders is empty"),
    ('[index]\nfolders = ["does_not_exist"]\n', "don't exist"),
    ('[index]\nfolders = "x"\n', "must be a list of strings"),
    ('[index]\nfolders = ["x"]\nuse_gitignore = "yes"\n', "true or false"),
    ('[index]\nfolders = ["x"]\nmax_file_kb = true\n', "whole number"),
    ('[index]\nfolders = ["x"]\nmax_file_kb = 0\n', "whole number"),
    ('[index\nfolders = ["x"]\n', "not valid TOML"),
    ('[index]\nfolders = ["x"]\ninclude = []\n', "include is empty"),
    ('[index]\nfolders = ["x"]\n[secrets]\nstrict = 1\n', "true or false"),
])
def test_mistakes_are_refused_with_a_clear_message(tmp_path, body, message):
    (tmp_path / "x").mkdir()
    p = tmp_path / "code_recycle.toml"
    p.write_text(body)
    with pytest.raises(settings.SettingsError, match=message.replace("[", r"\[")):
        settings.load(p)


def test_missing_file_says_how_to_make_one(tmp_path):
    with pytest.raises(settings.SettingsError, match="code-recycle init"):
        settings.load(tmp_path / "nope.toml")
