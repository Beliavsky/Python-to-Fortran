"""Portable character-result declarations in the shared Fortran runtime."""
from pathlib import Path
import shutil
import subprocess

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize('compiler', ['gfortran', 'ifx'])
def test_case_helpers_preserve_length_and_purity(tmp_path, compiler):
    if shutil.which(compiler) is None:
        pytest.skip(f'{compiler} required')
    source = tmp_path / 'xcase_helpers.f90'
    source.write_text('''program xcase_helpers
   use python_mod, only: to_lower, to_upper
   implicit none
   if (to_lower('Ab C!?') /= 'ab c!?') error stop 1
   if (to_upper('Ab c!?') /= 'AB C!?') error stop 2
   if (len(to_lower('Ab  ')) /= 4) error stop 3
   if (len(to_upper('Ab  ')) /= 4) error stop 4
   if (len(to_lower('')) /= 0) error stop 5
   if (len(to_upper('')) /= 0) error stop 6
   if (round_trip('ABC   ') /= 'abc   ') error stop 7
   print *, 'PASS'
contains
   pure function round_trip(s) result(answer)
      character(len=*), intent(in) :: s
      character(len=len(s)) :: answer
      answer = to_lower(to_upper(s))
   end function round_trip
end program xcase_helpers
''', encoding='utf-8')
    exe = tmp_path / 'xcase_helpers.exe'
    flags = ['-ffree-line-length-none'] if compiler == 'gfortran' else []
    build = subprocess.run([compiler, *flags, str(ROOT / 'python.f90'),
                            str(ROOT / 'lapack_d.f90'), str(source), '-o', str(exe)],
                           cwd=tmp_path, capture_output=True, text=True, timeout=180)
    assert build.returncode == 0, build.stdout + build.stderr
    run = subprocess.run([str(exe)], cwd=tmp_path, capture_output=True, text=True, timeout=30)
    assert run.returncode == 0, run.stdout + run.stderr
    assert run.stdout.strip() == 'PASS'
