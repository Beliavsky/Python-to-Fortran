"""FORD summaries stay attached to their declarations during extraction."""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from xextract_fortran_lib import add_ford_api_summaries, parse

ROOT = Path(__file__).resolve().parents[1]

SOURCE = '''module sample
implicit none
private
public :: foo !@pyapi lib=math desc="Compute a useful quantity."
interface foo
module procedure foo_real
end interface
contains
pure function foo_real(x, &
    & scale) result(y)
real, intent(in) :: x, scale
real :: y
y = x * scale
end function foo_real
end module sample
'''


def test_summaries_follow_complete_headers_and_survive_parse():
    documented = add_ford_api_summaries(SOURCE)
    assert 'interface foo\n   !! Compute a useful quantity.' in documented
    assert '& scale) result(y)\n       !! Compute a useful quantity.' in documented
    _, _, _, _, interfaces, tags, procedures, _ = parse(documented)
    assert interfaces['foo'][0][1].strip() == '!! Compute a useful quantity.'
    assert procedures['foo_real'][2].strip() == '!! Compute a useful quantity.'
    assert tags['foo'] == parse(SOURCE)[5]['foo']
    assert add_ford_api_summaries(documented) == documented


def test_preserve_authored_docs_and_implementation_comments():
    for replacement in (
        'interface foo !! Authored inline summary',
        'interface foo\n!! Authored summary',
        '!> Authored summary\ninterface foo',
        'interface foo\n!* Authored block summary',
    ):
        documented = add_ford_api_summaries(SOURCE.replace('interface foo\n', replacement + '\n', 1))
        assert documented.count('!! Compute a useful quantity.') == 1  # specific only
        assert 'Authored' in documented
    documented = add_ford_api_summaries(SOURCE.replace('real :: y', '! implementation note\nreal :: y'))
    assert '\n! implementation note\n' in documented


def test_runtime_summaries_are_current_and_only_add_comments():
    source = (ROOT / 'python.f90').read_text(encoding='utf-8')
    assert add_ford_api_summaries(source) == source
    assert '!! Runtime helpers for Python-to-Fortran' in source


def test_builder_stages_only_selected_module(tmp_path, monkeypatch):
    import xbuild_fortran_docs as builder
    calls = []

    def run(command, **kwargs):
        calls.append(command)
        if '-m' in command:
            staging = Path(command[command.index('--src_dir') + 1])
            assert [p.name for p in staging.iterdir()] == ['python.f90']
            assert (staging / 'python.f90').read_bytes() == (ROOT / 'python.f90').read_bytes()
        from types import SimpleNamespace
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(builder.subprocess, 'run', run)
    monkeypatch.setattr(sys, 'argv', ['xbuild_fortran_docs.py', '--output', str(tmp_path / 'html')])
    assert builder.main() == 0
    assert len(calls) == 1
    assert calls[0][-1] == str(tmp_path / 'html')
