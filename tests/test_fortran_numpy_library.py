"""The numerical routines in python.f90 called directly from Fortran (the
library use, independent of the translator), checked against numpy."""
from pathlib import Path
import shutil
import subprocess

import numpy as np
import pytest
from numpy.polynomial import chebyshev as C, hermite as H, hermite_e as HE, laguerre as LA, legendre as L
from numpy.polynomial import polynomial as P

ROOT = Path(__file__).resolve().parents[1]

POLYNOMIAL_PROGRAM = """program direct
   ! Calling the np.polynomial routines directly from Fortran.
   use python_mod, only: chebval, chebfit, chebder, chebint, chebvander, legval, legfit, hermval, hermeval, &
      lagval, powval, powfit, powder, powint, lagfit, hermfit, hermefit, legder, legint, hermder, hermint, &
      hermeder, hermeint, lagder, lagint
   implicit none
   integer, parameter :: dp = kind(1.0d0)
   real(dp) :: x(7), y(7), c(4), v(7, 4)
   integer :: i
   x = [(-1.0_dp + 2.0_dp * (i - 1) / 6.0_dp, i = 1, 7)]
   y = exp(x) * cos(3.0_dp * x)
   c = [0.5_dp, -1.0_dp, 2.0_dp, 0.25_dp]
   print "(*(es24.16))", chebval(0.3_dp, c), legval(0.3_dp, c), hermval(0.3_dp, c), hermeval(0.3_dp, c), &
      lagval(0.3_dp, c), powval(0.3_dp, c)
   print "(*(es24.16))", chebval(x, c)
   print "(*(es24.16))", chebfit(x, y, 3), legfit(x, y, 4), powfit(x, y, 2)
   print "(*(es24.16))", hermfit(x, y, 3), hermefit(x, y, 3), lagfit(x, y, 3)
   print "(*(es24.16))", chebder(c), chebint(c), chebint(c, m=2, k=[1.0_dp, 2.0_dp], lbnd=0.5_dp, scl=2.0_dp)
   print "(*(es24.16))", legder(c, 2), legint(c), hermder(c), hermint(c, k=[3.0_dp]), hermeder(c, scl=3.0_dp)
   print "(*(es24.16))", hermeint(c, m=2), lagder(c), lagint(c, lbnd=1.0_dp), powder(c), powint(c, m=3)
   v = chebvander(x, 3)
   print "(*(es24.16))", v(3, :), sum(v)
   print "(*(es24.16))", chebfit(x, y, 2, w=[(1.0_dp + i, i = 1, 7)])
end program direct
"""


@pytest.mark.skipif(shutil.which("gfortran") is None, reason="gfortran required")
def test_polynomial_series_routines_called_from_fortran(tmp_path: Path) -> None:
    (tmp_path / "direct.f90").write_text(POLYNOMIAL_PROGRAM, encoding="utf-8")
    build = subprocess.run(["gfortran", "-O0", "-fcheck=all", str(ROOT / "python.f90"), str(ROOT / "lapack_d.f90"),
                            "direct.f90", "-o", "direct.exe"], cwd=tmp_path, capture_output=True, text=True,
                           timeout=900)
    assert build.returncode == 0, build.stdout + build.stderr
    run = subprocess.run([str(tmp_path / "direct.exe")], cwd=tmp_path, capture_output=True, text=True, check=True)
    got = [float(v) for v in run.stdout.split()]
    x = -1.0 + 2.0 * np.arange(7) / 6.0
    y = np.exp(x) * np.cos(3 * x)
    c = np.array([0.5, -1.0, 2.0, 0.25])
    w = 1.0 + np.arange(1, 8)
    ref = [C.chebval(0.3, c), L.legval(0.3, c), H.hermval(0.3, c), HE.hermeval(0.3, c), LA.lagval(0.3, c),
           P.polyval(0.3, c), *C.chebval(x, c), *C.chebfit(x, y, 3), *L.legfit(x, y, 4), *P.polyfit(x, y, 2),
           *H.hermfit(x, y, 3), *HE.hermefit(x, y, 3), *LA.lagfit(x, y, 3),
           *C.chebder(c), *C.chebint(c), *C.chebint(c, m=2, k=[1.0, 2.0], lbnd=0.5, scl=2.0),
           *L.legder(c, 2), *L.legint(c), *H.hermder(c), *H.hermint(c, k=[3.0]), *HE.hermeder(c, scl=3.0),
           *HE.hermeint(c, m=2), *LA.lagder(c), *LA.lagint(c, lbnd=1.0), *P.polyder(c), *P.polyint(c, m=3),
           *C.chebvander(x, 3)[2], C.chebvander(x, 3).sum(), *C.chebfit(x, y, 2, w=w)]
    assert got == pytest.approx(ref, rel=1e-13, abs=1e-14)


POLYNOMIAL_PROGRAM_2 = """program d2
   use python_mod
   implicit none
   integer, parameter :: dp = kind(1.0d0)
   real(dp) :: c(4), c2(3)
   real(dp), allocatable :: x(:), w(:), q(:), r(:)
   complex(dp), allocatable :: z(:)
   c = [0.5_dp, -1.0_dp, 2.0_dp, 0.25_dp]
   c2 = [1.0_dp, 3.0_dp, -2.0_dp]
   z = powroots(c); print "(*(es24.16))", z
   z = chebroots(c); print "(*(es24.16))", z
   z = legroots(c); print "(*(es24.16))", z
   z = hermroots(c); print "(*(es24.16))", z
   z = hermeroots(c); print "(*(es24.16))", z
   z = lagroots(c); print "(*(es24.16))", z
   print "(*(es24.16))", chebcompanion(c), legcompanion(c), hermcompanion(c), hermecompanion(c), lagcompanion(c), powcompanion(c)
   call chebgauss(5, x, w); print "(*(es24.16))", x, w
   call hermgauss(6, x, w); print "(*(es24.16))", x, w
   call hermegauss(5, x, w); print "(*(es24.16))", x, w
   call laggauss(5, x, w); print "(*(es24.16))", x, w
   print "(*(es24.16))", powfromroots([1.0_dp, -2.0_dp, 3.0_dp]), chebfromroots([0.5_dp, -0.25_dp, 0.75_dp, 0.1_dp]), &
      legfromroots([1.0_dp, 2.0_dp]), hermfromroots([0.3_dp, -0.7_dp, 1.1_dp]), hermefromroots([1.0_dp]), &
      lagfromroots([0.5_dp, 2.0_dp, 4.0_dp])
   print "(*(es24.16))", powmulx(c), chebmulx(c), legmulx(c), hermmulx(c), hermemulx(c), lagmulx(c)
   print "(*(es24.16))", powadd(c, c2), chebsub(c2, c), powmul(c, c2), chebmul(c, c2), legmul(c, c2), hermmul(c, c2), &
      hermemul(c, c2), lagmul(c, c2)
   call powdiv(c, c2, q, r); print "(*(es24.16))", q, r
   call chebdiv(c, c2, q, r); print "(*(es24.16))", q, r
   call legdiv(c, c2, q, r); print "(*(es24.16))", q, r
   call hermdiv(c, c2, q, r); print "(*(es24.16))", q, r
   call hermediv(c, c2, q, r); print "(*(es24.16))", q, r
   call lagdiv(c, c2, q, r); print "(*(es24.16))", q, r
   print "(*(es24.16))", powpow(c2, 3), chebpow(c2, 3), legpow(c2, 2), hermpow(c2, 2), hermepow(c2, 2), lagpow(c2, 3)
   print "(*(es24.16))", powline(1.5_dp, 2.0_dp), hermline(1.5_dp, 2.0_dp), lagline(1.5_dp, 2.0_dp), chebline(3.0_dp, 0.0_dp)
   print "(*(es24.16))", cheb2poly(c), poly2cheb(c), leg2poly(c), poly2leg(c), herm2poly(c), poly2herm(c), &
      herme2poly(c), poly2herme(c), lag2poly(c), poly2lag(c)
   print "(*(es24.16))", chebpts1(5), chebpts2(5), chebtrim([1.0_dp, 2.0_dp, 1.0e-12_dp, 0.0_dp], 1.0e-10_dp), powtrim([3.0_dp, 0.0_dp])
   print "(*(es24.16))", chebrealroots(chebfromroots([-0.5_dp, 0.25_dp, 0.75_dp])), powrealroots([2.0_dp, 0.0_dp, 1.0_dp]), &
      chebrealroots(c, lo=-1.0_dp, hi=1.0_dp)
end program d2
"""


@pytest.mark.skipif(shutil.which("gfortran") is None, reason="gfortran required")
def test_polynomial_roots_gauss_arithmetic_called_from_fortran(tmp_path: Path) -> None:
    # Roots (complex), companion matrices, Gauss rules, fromroots, mulx,
    # add/sub/mul/div/pow/line, conversions, Chebyshev points, trim and
    # the real-roots convenience routine.
    (tmp_path / "d2.f90").write_text(POLYNOMIAL_PROGRAM_2, encoding="utf-8")
    build = subprocess.run(["gfortran", "-O0", "-fcheck=all", str(ROOT / "python.f90"), str(ROOT / "lapack_d.f90"),
                            "d2.f90", "-o", "d2.exe"], cwd=tmp_path, capture_output=True, text=True, timeout=900)
    assert build.returncode == 0, build.stdout + build.stderr
    run = subprocess.run([str(tmp_path / "d2.exe")], cwd=tmp_path, capture_output=True, text=True, check=True)
    got = [float(v) for v in run.stdout.split()]
    c = np.array([0.5, -1.0, 2.0, 0.25])
    c2 = np.array([1.0, 3.0, -2.0])
    fams = [(P, "poly"), (C, "cheb"), (L, "leg"), (H, "herm"), (HE, "herme"), (LA, "lag")]

    def cx(z):
        return [v for zz in np.asarray(z, dtype=complex) for v in (zz.real, zz.imag)]

    def realr(z, lo=None, hi=None):
        z = np.asarray(z)
        v = np.sort(z[np.abs(z.imag) <= 1e-8 * np.maximum(1, np.abs(z))].real)
        if lo is not None:
            v = v[v >= lo]
        if hi is not None:
            v = v[v <= hi]
        return list(v)
    ref = []
    for M, pre in fams:
        ref += cx(getattr(M, pre + "roots")(c))
    for M, pre in fams[1:] + fams[:1]:
        ref += list(getattr(M, pre + "companion")(c).T.ravel())
    for M, pre, n in [(C, "cheb", 5), (H, "herm", 6), (HE, "herme", 5), (LA, "lag", 5)]:
        x, w = getattr(M, pre + "gauss")(n)
        ref += list(x) + list(w)
    ref += list(P.polyfromroots([1, -2, 3])) + list(C.chebfromroots([0.5, -0.25, 0.75, 0.1]))         + list(L.legfromroots([1, 2])) + list(H.hermfromroots([0.3, -0.7, 1.1])) + list(HE.hermefromroots([1.0]))         + list(LA.lagfromroots([0.5, 2, 4]))
    for M, pre in fams:
        ref += list(getattr(M, pre + "mulx")(c))
    ref += list(P.polyadd(c, c2)) + list(C.chebsub(c2, c)) + list(P.polymul(c, c2)) + list(C.chebmul(c, c2))         + list(L.legmul(c, c2)) + list(H.hermmul(c, c2)) + list(HE.hermemul(c, c2)) + list(LA.lagmul(c, c2))
    for M, pre in fams:
        q, r = getattr(M, pre + "div")(c, c2)
        ref += list(q) + list(r)
    ref += list(P.polypow(c2, 3)) + list(C.chebpow(c2, 3)) + list(L.legpow(c2, 2)) + list(H.hermpow(c2, 2))         + list(HE.hermepow(c2, 2)) + list(LA.lagpow(c2, 3))
    ref += list(P.polyline(1.5, 2)) + list(H.hermline(1.5, 2)) + list(LA.lagline(1.5, 2)) + list(C.chebline(3, 0))
    for M, pre in fams[1:]:
        ref += list(getattr(M, pre + "2poly")(c)) + list(getattr(M, "poly2" + pre)(c))
    ref += list(C.chebpts1(5)) + list(C.chebpts2(5)) + list(C.chebtrim([1, 2, 1e-12, 0], 1e-10)) + list(P.polytrim([3, 0]))
    ref += realr(C.chebroots(C.chebfromroots([-0.5, 0.25, 0.75]))) + realr(P.polyroots([2, 0, 1]))         + realr(C.chebroots(c), -1, 1)
    assert got == pytest.approx(ref, rel=1e-12, abs=1e-13)


EXTRACTED_PROGRAM = """program use_lib
   ! The routines of the extracted, standalone module (no python_mod).
   use numpy_fortran
   implicit none
   integer, parameter :: dp = kind(1.0d0)
   real(dp) :: x(5), c(3), m(2, 3)
   complex(dp), allocatable :: f(:,:)
   x = [0.0_dp, 0.25_dp, 0.5_dp, 0.75_dp, 1.0_dp]
   c = [1.0_dp, -2.0_dp, 0.5_dp]
   print "(*(es24.16))", chebval(x, c)
   print "(*(es24.16))", chebfit(x, chebval(x, c), 2)
   m = reshape([1.0_dp, 2.0_dp, 3.0_dp, 4.0_dp, 5.0_dp, 6.0_dp], [2, 3])
   f = fft2(m)
   print "(*(es24.16))", real(f), aimag(f)
   print "(*(es24.16))", np_pad_vec(x(1:3), 2, 1, 3)
   print "(*(es24.16))", legval2d(0.3_dp, -0.2_dp, reshape([1.0_dp, 0.5_dp, -1.0_dp, 2.0_dp], [2, 2]))
end program use_lib
"""


@pytest.mark.skipif(shutil.which("gfortran") is None, reason="gfortran required")
def test_extracted_fortran_library_standalone(tmp_path: Path) -> None:
    # xextract_fortran_lib.py writes a module of the lib=-tagged routines
    # that compiles without python_mod; a program using it (linked with
    # LAPACK for the fits) agrees with numpy.
    out = tmp_path / "lib"
    proc = subprocess.run(["python", str(ROOT / "xextract_fortran_lib.py"), "--out", str(out)], capture_output=True,
                          text=True, check=False)
    assert proc.returncode == 0 and "compile: PASS" in proc.stdout, proc.stdout + proc.stderr
    assert (out / "ROUTINES.md").read_text(encoding="utf-8").count("| `") > 50
    (out / "use_lib.f90").write_text(EXTRACTED_PROGRAM, encoding="utf-8")
    subprocess.run(["gfortran", "-c", str(ROOT / "lapack_d.f90"), "-o", "lapack_d.o"], cwd=out, check=True)
    subprocess.run(["gfortran", "numpy_fortran.f90", "use_lib.f90", "lapack_d.o", "-o", "use_lib.exe"], cwd=out,
                   check=True)
    got = [[float(v) for v in line.split()] for line in
           subprocess.run([str(out / "use_lib.exe")], capture_output=True, text=True, check=True).stdout.splitlines()]
    x = np.array([0.0, 0.25, 0.5, 0.75, 1.0])
    c = np.array([1.0, -2.0, 0.5])
    f = np.fft.fft2(np.array([[1.0, 3.0, 5.0], [2.0, 4.0, 6.0]]))
    want = [C.chebval(x, c), C.chebfit(x, C.chebval(x, c), 2),
            np.concatenate([f.real.T.ravel(), f.imag.T.ravel()]), np.pad(x[:3], (2, 1), mode="reflect"),
            [L.legval2d(0.3, -0.2, np.array([[1.0, -1.0], [0.5, 2.0]]))]]
    for g, w in zip(got, want):
        assert g == pytest.approx(list(np.ravel(w)), rel=1e-10, abs=1e-12)
