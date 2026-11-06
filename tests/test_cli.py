from code_recycle import cli


def test_init_index_and_search_end_to_end(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "projects").mkdir()
    (tmp_path / "projects" / "csv_tools.py").write_text('def read_rows(path):\n    """Read a CSV file into rows."""\n    pass\n')
    assert cli.main(["init"]) == 0
    toml = tmp_path / "code_recycle.toml"
    toml.write_text(toml.read_text().replace("~/projects", "projects"))
    assert cli.main(["index"]) == 0
    assert "Indexed 1 file." in capsys.readouterr().out
    assert cli.main(["search", "read", "csv", "file"]) == 0
    assert "read_rows (function)" in capsys.readouterr().out


def test_init_never_overwrites(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "code_recycle.toml").write_text("mine")
    assert cli.main(["init"]) == 1
    assert (tmp_path / "code_recycle.toml").read_text() == "mine"


def test_a_settings_mistake_is_one_clear_line_not_a_traceback(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "code_recycle.toml").write_text('[index]\nfolders = ["missing"]\n')
    assert cli.main(["index"]) == 2
    err = capsys.readouterr().err
    assert err.startswith("code-recycle: These folders don't exist") and "Traceback" not in err


def test_settings_file_from_environment_variable(tmp_path, monkeypatch):
    (tmp_path / "code").mkdir()
    s = tmp_path / "elsewhere.toml"
    s.write_text('[index]\nfolders = ["code"]\n')
    monkeypatch.setenv("CODE_RECYCLE_SETTINGS", str(s))
    monkeypatch.chdir(tmp_path)
    assert cli.find_settings(None) == s
