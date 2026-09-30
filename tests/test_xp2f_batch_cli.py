from __future__ import annotations

import sys
import subprocess
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import xp2f_batch


@pytest.mark.parametrize("kind", [None, "int32", "int64"])
@pytest.mark.parametrize("mode", [[], ["--no-compile"], ["--no-run"], ["--run-both"], ["--strict"], ["--strict-fix"]])
@pytest.mark.parametrize("jobs", [1, 2])
def test_batch_forwards_integer_kind(tmp_path, monkeypatch, capsys, kind, mode, jobs):
    paths = [tmp_path / "first.py", tmp_path / "second.py"]
    for path in paths:
        path.write_text("print(1)\n", encoding="utf-8")
    called = []

    def run(cmd, **kwargs):
        called.append(cmd)
        return subprocess.CompletedProcess(cmd, 0, "", "")

    monkeypatch.setattr(xp2f_batch.subprocess, "run", run)
    monkeypatch.setattr(xp2f_batch, "_ensure_parallel_helper_cache", lambda *args: 0)
    monkeypatch.setattr(sys, "argv", ["xp2f_batch.py", *map(str, paths), "--jobs", str(jobs), *mode]
                        + (["--int-kind", kind] if kind else []))
    assert xp2f_batch.main() == 0
    assert len(called) == 2
    for cmd in called:
        if kind:
            assert cmd.count("--int-kind") == 1
            assert cmd[cmd.index("--int-kind") + 1] == kind
        else:
            assert "--int-kind" not in cmd
    assert f"Integer kind: {kind or 'compiler default (no --int-kind)'}" in capsys.readouterr().out


def test_batch_rejects_invalid_integer_kind(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["xp2f_batch.py", "unused.py", "--int-kind", "int16"])
    with pytest.raises(SystemExit) as exc:
        xp2f_batch.main()
    assert exc.value.code == 2


def test_batch_integer_kind_real_translation_and_tee(tmp_path):
    src = tmp_path / "xinteger.py"
    src.write_text("n = 3\nprint(n)\n", encoding="utf-8")
    log = tmp_path / "batch.txt"
    proc = subprocess.run([sys.executable, str(REPO_ROOT / "xp2f_batch.py"), str(src),
                           "--no-compile", "--int-kind", "int64", "--terse", "--tee", str(log)],
                          cwd=tmp_path, capture_output=True, text=True)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "Integer kind: int64" in proc.stdout
    assert "Integer kind: int64" in log.read_text(encoding="utf-8")
    generated = (tmp_path / "xinteger_p.f90").read_text(encoding="utf-8")
    assert "ikind = int64" in generated
    assert "integer(kind=ikind)" in generated


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


@pytest.mark.parametrize('mode', ['--no-compile', '--time-summary', '--strict-fix'])
@pytest.mark.parametrize('explicit', [False, True])
def test_batch_work_dir_preserves_input_paths(tmp_path, monkeypatch, capsys, mode, explicit):
    source_dir = tmp_path / 'examples'
    source_dir.mkdir()
    source = source_dir / 'case.py'
    source.write_text('print(1)\n', encoding='utf-8')
    data_dir = tmp_path / 'data space'
    data_dir.mkdir()
    calls = []

    def run(cmd, **kwargs):
        calls.append((cmd, Path(kwargs['cwd'])))
        return subprocess.CompletedProcess(cmd, 0, '', '')

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(xp2f_batch.subprocess, 'run', run)
    args = ['xp2f_batch.py', 'examples/case.py', mode, '--helpers', 'helper.f90']
    if explicit:
        args += ['--work-dir', 'data space']
    if mode == '--strict-fix':
        args += ['--out-python-dir', 'fixed']
    monkeypatch.setattr(sys, 'argv', args)
    assert xp2f_batch.main() == 0
    assert Path.cwd() == tmp_path
    assert calls
    for cmd, cwd in calls:
        assert cwd == (data_dir if explicit else source_dir)
        assert str(source) in cmd
        if str(xp2f_batch.Path(xp2f_batch.__file__).with_name('xp2f.py').resolve()) in cmd:
            assert str(tmp_path / 'helper.f90') in cmd
        if '--out-python' in cmd:
            assert Path(cmd[cmd.index('--out-python') + 1]) == tmp_path / 'fixed/examples/case_strict.py'


def test_batch_work_dir_must_exist(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(sys, 'argv', ['xp2f_batch.py', 'unused.py', '--work-dir', str(tmp_path / 'missing')])
    assert xp2f_batch.main() == 1
    assert 'not an existing directory' in capsys.readouterr().out


def test_parallel_prebuild_uses_work_dir(tmp_path, monkeypatch):
    work = tmp_path / 'work'
    work.mkdir()
    (tmp_path / 'python.f90').write_text('module python_mod\nend module\n', encoding='utf-8')
    (tmp_path / 'lapack_d.f90').write_text('! helper\n', encoding='utf-8')
    calls = []
    def run(cmd, **kwargs):
        calls.append((cmd, kwargs['cwd']))
        return subprocess.CompletedProcess(cmd, 0, '', '')
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(xp2f_batch.subprocess, 'run', run)
    assert xp2f_batch._ensure_parallel_helper_cache('gfortran', work) == 0
    assert len(calls) == 2
    assert all(cwd == work and Path(cmd[2]).is_absolute() for cmd, cwd in calls)


def test_helper_cache_is_checked_in_selected_work_dir(tmp_path, monkeypatch):
    source = tmp_path / 'helper.f90'
    source.write_text('module helper_mod\nend module\n', encoding='utf-8')
    work = tmp_path / 'work'
    work.mkdir()
    monkeypatch.chdir(tmp_path)
    for name in ('helper.o', 'helper_mod.mod'):
        (tmp_path / name).write_text('cached', encoding='utf-8')
    assert xp2f_batch._helper_cache_ok(source)
    assert not xp2f_batch._helper_cache_ok(source, work)
    for name in ('helper.o', 'helper_mod.mod'):
        (work / name).write_text('cached', encoding='utf-8')
    assert xp2f_batch._helper_cache_ok(source, work)
