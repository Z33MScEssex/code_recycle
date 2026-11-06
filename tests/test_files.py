from code_recycle import files, settings
from conftest import FAKE_AWS, FAKE_GITHUB


def _walk(make_tree, write_settings, tree, extra=""):
    root = make_tree(tree)
    p = write_settings(f'[index]\nfolders = ["."]\n{extra}')
    w = files.walk(settings.load(p))
    included = {rel for _, rel in w.included}
    skipped = {s.path: s.reason for s in w.skipped}
    return included, skipped


def test_plain_code_goes_in(make_tree, write_settings):
    inc, _ = _walk(make_tree, write_settings, {"src/app.py": "def add(a, b):\n    return a + b\n"})
    assert "src/app.py" in inc


def test_secret_file_names_are_never_read_even_if_allowed(make_tree, write_settings, monkeypatch):
    opened = []
    monkeypatch.setattr(files, "_is_binary", lambda p: opened.append(p.name) or False)  # records any read
    inc, skip = _walk(make_tree, write_settings,
                      {".env": "X=1\n", "deploy/server.pem": "pem\n", "id_rsa": "k\n", "ok.py": "x = 1\n"},
                      '[secrets]\nallow = [".env"]\n')
    for name in (".env", "deploy/server.pem", "id_rsa"):
        assert name not in inc and skip[name] == "secret file name (never read)"
    assert ".env" not in opened and "id_rsa" not in opened


def test_a_file_with_a_key_inside_is_skipped_and_reported(make_tree, write_settings):
    inc, skip = _walk(make_tree, write_settings,
                      {"config.py": f'KEY = "{FAKE_AWS}"\n', "token.py": f'T = "{FAKE_GITHUB}"\n'})
    assert "config.py" not in inc and "AWS Access Key" in skip["config.py"]
    assert "token.py" not in inc and "GitHub Token" in skip["token.py"]


def test_the_user_can_allow_a_flagged_file_by_name(make_tree, write_settings):
    inc, _ = _walk(make_tree, write_settings, {"tests/fixture.py": 'password = "not-a-real-one"\n'},
                   '[secrets]\nallow = ["tests/fixture.py"]\n')
    assert "tests/fixture.py" in inc


def test_skip_rules_gitignore_and_built_in_skips(make_tree, write_settings):
    inc, skip = _walk(make_tree, write_settings, {
        ".gitignore": "build/\n*.log\n",
        "build/out.py": "x = 1\n",
        "run.log": "log\n",
        "node_modules/lib/index.js": "x\n",
        ".git/config": "x\n",
        "keep.py": "x = 1\n",
    }, 'skip = ["node_modules/"]\n')
    assert inc == {"keep.py"}  # .gitignore itself isn't a code or text type
    assert skip["build/"] == ".gitignore" and skip["run.log"] == ".gitignore"
    assert skip["node_modules/"] == "skip rule" and skip[".git/"] == "skip rule"
    assert not any(k.startswith("build/out") for k in skip)  # the folder was pruned, never entered


def test_gitignore_can_be_switched_off(make_tree, write_settings):
    inc, _ = _walk(make_tree, write_settings, {".gitignore": "notes.md\n", "notes.md": "hi\n"},
                   "use_gitignore = false\n")
    assert "notes.md" in inc


def test_binary_empty_and_oversized_files_are_skipped(make_tree, write_settings):
    inc, skip = _walk(make_tree, write_settings, {
        "img.txt": b"\x89PNG\x00\x00data", "empty.py": "", "big.txt": "a" * 3000, "ok.py": "x = 1\n",
    }, "max_file_kb = 2\n")
    assert inc == {"ok.py"}
    assert skip["img.txt"] == "binary" and skip["empty.py"] == "empty" and skip["big.txt"] == "over 2 KB"


def test_report_lists_flagged_files_by_name_and_counts_the_rest(make_tree, write_settings):
    root = make_tree({"config.py": f'KEY = "{FAKE_AWS}"\n', "a.log": "x\n", "b.log": "x\n", "ok.py": "x = 1\n"})
    w = files.walk(settings.load(write_settings('[index]\nfolders = ["."]\nskip = ["*.log"]\n')))
    text = files.report(w)
    assert "Indexed 1 file." in text  # ok.py; the settings file is always skipped
    assert "config.py (possible secret: AWS Access Key)" in text
    assert "skip rule: 3" in text  # two .log files and the settings file


def test_only_code_and_text_types_go_in_by_default(make_tree, write_settings):
    inc, skip = _walk(make_tree, write_settings, {"a.py": "x = 1\n", "b.json": "{}\n", "c.ipynb": "{}\n", "Dockerfile": "FROM x\n"})
    assert inc == {"a.py", "Dockerfile"}
    assert skip["b.json"] == "file type not included"


def test_include_setting_replaces_the_default_list(make_tree, write_settings):
    inc, _ = _walk(make_tree, write_settings, {"a.py": "x = 1\n", "b.json": "{}\n"}, 'include = ["*.json"]\n')
    assert inc == {"b.json"}


def test_any_virtualenv_folder_is_skipped(make_tree, write_settings):
    inc, skip = _walk(make_tree, write_settings, {".eyes-venv/lib/x.py": "x = 1\n", "app.py": "x = 1\n"})
    assert inc == {"app.py"} and skip[".eyes-venv/"] == "skip rule"


HASH_LINE = 'digest = "' + "9f86d081884c7d659a2feaa0c55ad015a3bf4f1b2b0b822cd15d6c15b0f00a08" + '"\n'


def test_random_looking_text_is_not_flagged_by_default(make_tree, write_settings):
    inc, _ = _walk(make_tree, write_settings, {"hashes.py": HASH_LINE})
    assert "hashes.py" in inc


def test_strict_mode_flags_random_looking_text(make_tree, write_settings):
    inc, skip = _walk(make_tree, write_settings, {"hashes.py": HASH_LINE}, "[secrets]\nstrict = true\n")
    assert "hashes.py" not in inc and "High Entropy" in skip["hashes.py"]


def test_parallel_scan_gives_the_same_answer_as_the_single_process_scan(make_tree, write_settings, monkeypatch):
    tree = {f"m{i}.py": f"x = {i}\n" for i in range(60)}
    tree["leak.py"] = f'KEY = "{FAKE_AWS}"\n'
    inc_parallel, skip_parallel = _walk(make_tree, write_settings, tree)  # 61 files, over the parallel threshold
    monkeypatch.setattr(files, "PARALLEL_FROM", 10_000)
    inc_single, skip_single = _walk(make_tree, write_settings, tree)
    assert inc_parallel == inc_single and skip_parallel == skip_single
    assert "leak.py" in skip_parallel and len(inc_parallel) == 60
