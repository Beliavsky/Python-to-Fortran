"""Meson's Windows defaults must not mix MSVC linking with GNU libraries."""
from pathlib import Path
import subprocess
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import xpfunc2f


def configure(monkeypatch, targets):
    monkeypatch.setattr(sys, 'platform', 'win32')
    monkeypatch.delenv('CC', raising=False)
    monkeypatch.delenv('FC', raising=False)
    monkeypatch.setattr(xpfunc2f.shutil, 'which', lambda name: name if name in targets else None)
    monkeypatch.setattr(xpfunc2f.subprocess, 'run', lambda command, **kwargs:
                        subprocess.CompletedProcess(command, 0, targets[command[0]], ''))


@pytest.mark.parametrize('targets, expected', [
    ({'clang': 'x86_64-w64-windows-gnu', 'gcc': 'x86_64-w64-mingw32'}, 'clang'),
    ({'clang': 'x86_64-pc-windows-msvc', 'gcc': 'x86_64-w64-mingw32'}, 'gcc'),
    ({'gcc': 'x86_64-w64-mingw32'}, 'gcc'),
])
def test_compatible_windows_default(monkeypatch, targets, expected):
    configure(monkeypatch, targets)
    env = xpfunc2f.f2py_build_environment()
    assert env['CC'] == expected
    assert env['FC'] == 'gfortran'
    assert 'CC' not in xpfunc2f.os.environ


def test_explicit_compilers_preserved(monkeypatch):
    configure(monkeypatch, {})
    monkeypatch.setenv('CC', 'custom-c')
    monkeypatch.setenv('FC', 'custom-fortran')
    env = xpfunc2f.f2py_build_environment()
    assert env['CC'] == 'custom-c'
    assert env['FC'] == 'custom-fortran'


def test_compiler_path_with_spaces(monkeypatch):
    compiler = r'C:\Program Files\LLVM-MinGW\bin\clang.exe'
    configure(monkeypatch, {compiler: 'x86_64-w64-windows-gnu'})
    monkeypatch.setattr(xpfunc2f.shutil, 'which', lambda name: compiler)
    assert xpfunc2f.f2py_build_environment()['CC'] == '"' + compiler + '"'


def test_non_windows_environment_unchanged(monkeypatch):
    configure(monkeypatch, {})
    monkeypatch.setattr(sys, 'platform', 'linux')
    assert xpfunc2f.f2py_build_environment() == dict(xpfunc2f.os.environ)
