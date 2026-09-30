"""Purity contracts for side-effect-free runtime helper chains."""
from pathlib import Path
import re
import shutil
import subprocess

import pytest

ROOT = Path(__file__).resolve().parents[1]
PURE_HELPERS = """
    grow_and_set_char insert_char py_str_int32 py_str_int64 py_str_real
    str_format_real_fixed py_str_logical py_str_char vm_integral
    np_insert_real_1d bincount_int searchsorted_left_int searchsorted_right_int
    searchsorted_left_int_scalar searchsorted_right_int_scalar setdiff1d_int lexsort2_int
    lexsort2_real ravel_multi_index_2d unravel_index_2d kron_2d
    histogram_real_edges histogram_int_edges histogram2d_real_edges reduceat_add_real
    reduceat_add_int reduceat_mul_real reduceat_mul_int reduceat_min_real
    reduceat_min_int reduceat_max_real reduceat_max_int reduceat_logical_and
    reduceat_logical_or median_high_int mode_real str_lstrip
    str_rstrip str_strip str_ljust str_rjust
    str_join tile_int tile_int_2d cumprod_int
    repeat_int repeat_int_axis0_2d repeat_int_axis1_2d repeat_real
    repeat_real_axis0_2d repeat_real_axis1_2d repeat_logical repeat_logical_axis0_2d
    repeat_logical_axis1_2d tile_real tile_real_2d eye_real
    cumprod_real gradient_1d unwrap_1d interp_1d
    linalg_eigvals_complex leggauss quantile_linear quantile_linear_vec
    statistics_quantiles_real unique_int_counts tri_int tri_real
    moveaxis3_int moveaxis3_real moveaxis3_logical pad2d_int
    pad2d_real allclose_real allclose_integer lfilter_real
    detrend_real find_peaks_int fft_dft_forward fft_dft_inverse
    fft_radix2_inplace fft_fft_real fft_fft_complex fft_ifft
    fft_rfft fft_irfft fft_fftfreq fft_rfftfreq
    itertools_product2_int itertools_combinations_int itertools_combinations_wr_int itertools_permutations_int
    sys_argv_delete complex_amin complex_amax dcpabs
    dcsqrt dceigv dcbal dcorth
    dcbabk dcmqr2 where_pair_2d lexsort_keys_int
    lexsort_keys_real lexsort_packed_int lexsort_packed_real
""".split()


def test_runtime_purity_declarations():
    source = (ROOT / "python.f90").read_text(encoding="utf-8")
    # py_str_int is a generic over py_str_int32 and py_str_int64.
    assert len(PURE_HELPERS) == 108
    for name in PURE_HELPERS:
        assert re.search(
            rf"^\s*pure\s+[^\n]*\b(?:function|subroutine)\s+{name}\s*\(",
            source, re.MULTILINE | re.IGNORECASE,
        ), name


@pytest.mark.skipif(shutil.which("gfortran") is None, reason="gfortran required")
def test_runtime_helpers_from_pure_caller(tmp_path):
    source = tmp_path / "pure_helpers.f90"
    source.write_text("""program main
use python_mod
use, intrinsic :: iso_fortran_env, only: dp => real64
implicit none
call check_helpers()
contains
pure subroutine check_helpers()
character(:), allocatable :: strings(:), text
integer, allocatable :: u(:), counts(:), pairs(:,:), h(:)
real(dp), allocatable :: nodes(:), weights(:), edges(:)
complex(dp), allocatable :: spectrum(:), restored(:), eigenvalues(:)
complex(dp) :: a(2,2)
real(dp) :: samples(4)
integer :: n

text = py_str_int(42)
if (text /= '42') error stop 'integer formatting'
text = str_format_real_fixed(1.25_dp, 2)
if (text /= '1.25') error stop 'real formatting'
if (str_strip('  abc  ') /= 'abc') error stop 'strip'
call grow_and_set_char(strings, 1, 'a')
call insert_char(strings, 0, 'long')
if (size(strings) /= 2 .or. len(strings) /= 4) error stop 'character growth'
if (strings(1) /= 'long' .or. strings(2) /= 'a') error stop 'insert'
call sys_argv_delete(strings, 1)
if (size(strings) /= 1 .or. strings(1) /= 'a') error stop 'delete'
call sys_argv_delete(strings, 1)
if (size(strings) /= 0) error stop 'delete last'

call unique_int_counts([2,1,2], u, counts)
if (any(u /= [1,2]) .or. any(counts /= [1,2])) error stop 'counts'
pairs = where_pair_2d([1], [0,2])
if (any(pairs(1,:) /= [1,1]) .or. any(pairs(2,:) /= [0,2])) error stop 'paired indices'
u = bincount_int([0,2,2])
if (any(u /= [1,0,2])) error stop 'bincount'
u = repeat_int([1,2], 2)
if (any(u /= [1,1,2,2])) error stop 'repeat'
u = tile_int([1,2], 2)
if (any(u /= [1,2,1,2])) error stop 'tile'
u = lexsort_keys(reshape([2,1,1,1,0,2], [2,3]))
if (any(u /= [1,0,2])) error stop 'lexsort'
if (abs(quantile_linear([1.0_dp,3.0_dp,2.0_dp], 0.5_dp)-2.0_dp) > 1e-12_dp) error stop 'quantile'
call histogram_real_edges([0.0_dp,0.5_dp,1.0_dp], [0.0_dp,0.5_dp,1.0_dp], h, edges)
if (any(h /= [1,2])) error stop 'histogram'
call leggauss(3, nodes, weights)
if (abs(sum(weights*nodes**4)-0.4_dp) > 1e-12_dp) error stop 'quadrature'

samples = [1.0_dp,2.0_dp,3.0_dp,4.0_dp]
! Three points uses direct DFT; four uses the radix-2 worker.
do n = 3, 4
    spectrum = fft_fft(samples(:n))
    restored = fft_ifft(spectrum)
    if (maxval(abs(restored-cmplx(samples(:n),0.0_dp,dp))) > 1e-12_dp) error stop 'FFT'
end do
a = cmplx(0.0_dp,0.0_dp,dp)
a(1,1) = cmplx(1.0_dp,2.0_dp,dp)
a(2,2) = cmplx(3.0_dp,-1.0_dp,dp)
eigenvalues = linalg_eigvals(a)
if (minval(abs(eigenvalues-a(1,1))) > 1e-12_dp) error stop 'eigenvalue 1'
if (minval(abs(eigenvalues-a(2,2))) > 1e-12_dp) error stop 'eigenvalue 2'
end subroutine
end program
""", encoding="utf-8")
    exe = tmp_path / "pure_helpers.exe"
    build = subprocess.run(
        ["gfortran", "-fcheck=all", "-fbacktrace", str(ROOT / "python.f90"),
         str(ROOT / "lapack_d.f90"), str(source), "-o", str(exe)],
        cwd=tmp_path, capture_output=True, text=True, timeout=300,
    )
    assert build.returncode == 0, build.stdout + build.stderr
    run = subprocess.run([str(exe)], cwd=tmp_path, capture_output=True, text=True, timeout=60)
    assert run.returncode == 0, run.stdout + run.stderr
