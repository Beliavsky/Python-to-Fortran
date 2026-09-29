from __future__ import annotations

import sys
import subprocess
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import xp2f_batch


def test_expand_inputs_supports_at_list_files(tmp_path: Path, monkeypatch) -> None:
    src_dir = tmp_path / "src"
    src_dir.mkdir()
    a_py = src_dir / "a.py"
    b_py = src_dir / "b.py"
    skip_txt = src_dir / "skip.txt"
    a_py.write_text("print('a')\n", encoding="utf-8")
    b_py.write_text("print('b')\n", encoding="utf-8")
    skip_txt.write_text("not python\n", encoding="utf-8")

    nested_list = tmp_path / "nested_list.txt"
    nested_list.write_text("src/b.py\n", encoding="utf-8")

    file_list = tmp_path / "file_list.txt"
    file_list.write_text(
        "\n".join(
            [
                "# comment",
                "src/a.py",
                "src/skip.txt",
                "@nested_list.txt",
                "",
            ]
        ),
        encoding="utf-8",
    )

    monkeypatch.chdir(tmp_path)
    expanded = xp2f_batch._expand_inputs(["@file_list.txt"])

    assert expanded == [a_py, b_py]


@pytest.mark.parametrize("source, expected", [
    ('"Module docs"\nimport math\ndef f(x):\n    return x\n', True),
    ('class Model:\n    pass\n', True),
    ('# empty\n', True),
    ('x = 3\n', False),
    ('print(3)\n', False),
    ('def main():\n    pass\nif __name__ == "__main__":\n    main()\n', False),
    ('def broken(\n', False),
])
def test_module_only_detection(tmp_path, source, expected):
    path = tmp_path / "source.py"
    path.write_text(source, encoding="utf-8")
    assert xp2f_batch._is_module_only(path) is expected


@pytest.mark.parametrize("name", ["func.py", "nagarch_t_model.py"])
def test_example_modules_are_module_only(name):
    assert xp2f_batch._is_module_only(REPO_ROOT / "examples" / name)


@pytest.mark.parametrize("jobs", [1, 2])
def test_batch_modules_do_not_consume_limit(tmp_path, monkeypatch, capsys, jobs):
    paths = []
    for name, source in [("a", "def f():\n    pass\n"), ("b", "print(1)\n"),
                         ("c", "import math\n"), ("d", "print(2)\n"),
                         ("e", "print(3)\n")]:
        path = tmp_path / f"{name}.py"
        path.write_text(source, encoding="utf-8")
        paths.append(path)
    called = []

    def run(cmd, **kwargs):
        called.append(Path(cmd[2]).name)
        return subprocess.CompletedProcess(cmd, 0, "", "")

    monkeypatch.setattr(xp2f_batch.subprocess, "run", run)
    monkeypatch.setattr(sys, "argv", ["xp2f_batch.py", *map(str, paths),
                                     "--no-compile", "--limit", "2", "--jobs", str(jobs)])
    assert xp2f_batch.main() == 0
    output = capsys.readouterr().out
    assert sorted(called) == ["b.py", "d.py"]
    assert "4 files, 2 pass, 0 fail, 2 skip" in output
    assert "SKIP (module-only: no executable entry point)" in output


@pytest.mark.parametrize("terse", [False, True])
def test_all_modules_skip_without_building_helpers(tmp_path, monkeypatch, capsys, terse):
    path = tmp_path / "module.py"
    path.write_text("def f():\n    pass\n", encoding="utf-8")

    def unexpected(*args, **kwargs):
        pytest.fail("Module-only batch must not launch subprocesses or compile helpers")

    monkeypatch.setattr(xp2f_batch.subprocess, "run", unexpected)
    monkeypatch.setattr(xp2f_batch, "_ensure_parallel_helper_cache", unexpected)
    monkeypatch.setattr(sys, "argv", ["xp2f_batch.py", str(path), "--jobs", "2"]
                        + (["--terse"] if terse else []))
    assert xp2f_batch.main() == 0
    output = capsys.readouterr().out
    assert "1 files, 0 pass, 0 fail, 1 skip" in output
    if terse:
        assert "(no failures)" in output


@pytest.mark.parametrize("mode", ["--strict", "--strict-fix"])
def test_strict_modes_still_process_modules(tmp_path, monkeypatch, capsys, mode):
    path = tmp_path / "module.py"
    path.write_text("def f():\n    pass\n", encoding="utf-8")
    called = []

    def run(cmd, **kwargs):
        called.append(cmd)
        return subprocess.CompletedProcess(cmd, 0, "", "")

    monkeypatch.setattr(xp2f_batch.subprocess, "run", run)
    monkeypatch.setattr(sys, "argv", ["xp2f_batch.py", str(path), mode])
    assert xp2f_batch.main() == 0
    assert len(called) == 1
    assert mode in called[0]
    assert "0 skip" in capsys.readouterr().out


def test_skips_do_not_trigger_maxfail_or_hide_errors(tmp_path, monkeypatch, capsys):
    paths = []
    for name, source in [("a_module", "import math\n"), ("broken", "def broken(\n"),
                         ("later", "print(1)\n")]:
        path = tmp_path / f"{name}.py"
        path.write_text(source, encoding="utf-8")
        paths.append(path)
    called = []

    def run(cmd, **kwargs):
        called.append(Path(cmd[2]).name)
        return subprocess.CompletedProcess(cmd, 1, "Transpile: FAIL (syntax error)", "")

    monkeypatch.setattr(xp2f_batch.subprocess, "run", run)
    monkeypatch.setattr(sys, "argv", ["xp2f_batch.py", *map(str, paths),
                                     "--no-compile", "--maxfail", "1"])
    assert xp2f_batch.main() == 1
    assert called == ["broken.py"]
    assert "2 files, 0 pass, 1 fail, 1 skip" in capsys.readouterr().out
