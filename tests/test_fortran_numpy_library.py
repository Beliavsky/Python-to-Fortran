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

CASES = ROOT / "tests" / "fortran_numpy"
POLYNOMIAL_PROGRAM = (CASES / "polynomial_series.f90").read_text(encoding="utf-8").replace(
    "use numpy_fortran", "use python_mod")


@pytest.mark.skipif(shutil.which("gfortran") is None, reason="gfortran required")
def test_polynomial_series_routines_called_from_fortran(tmp_path: Path) -> None:
    (tmp_path / "direct.f90").write_text(POLYNOMIAL_PROGRAM, encoding="utf-8")
    build = subprocess.run(["gfortran", "-O0", "-fcheck=all", str(ROOT / "python.f90"), str(ROOT / "lapack_d.f90"),
                            "direct.f90", "-o", "direct.exe"], cwd=tmp_path, capture_output=True, text=True,
                           timeout=900)
    assert build.returncode == 0, build.stdout + build.stderr
    run = subprocess.run([str(tmp_path / "direct.exe")], cwd=tmp_path, capture_output=True, text=True, check=True)
    assert_series_output(run.stdout)


def assert_series_output(stdout):
    got = [float(v) for v in stdout.split()]
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


POLYNOMIAL_PROGRAM_2 = (CASES / "polynomial_roots.f90").read_text(encoding="utf-8").replace(
    "use numpy_fortran", "use python_mod")


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
    assert_roots_output(run.stdout)


def assert_roots_output(stdout):
    got = [float(v) for v in stdout.split()]
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


EXTRACTED_PROGRAM = (ROOT / "tests" / "fortran_numpy" / "standalone.f90").read_text(encoding="utf-8")


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
    output = subprocess.run([str(out / "use_lib.exe")], capture_output=True, text=True, check=True).stdout
    assert_standalone_output(output)


def assert_standalone_output(stdout):
    got = [[float(v) for v in line.split()] for line in stdout.splitlines()]
    x = np.array([0.0, 0.25, 0.5, 0.75, 1.0])
    c = np.array([1.0, -2.0, 0.5])
    f = np.fft.fft2(np.array([[1.0, 3.0, 5.0], [2.0, 4.0, 6.0]]))
    want = [C.chebval(x, c), C.chebfit(x, C.chebval(x, c), 2),
            np.concatenate([f.real.T.ravel(), f.imag.T.ravel()]), np.pad(x[:3], (2, 1), mode="reflect"),
            [L.legval2d(0.3, -0.2, np.array([[1.0, -1.0], [0.5, 2.0]]))]]
    assert len(got) == len(want)
    for g, w in zip(got, want):
        assert g == pytest.approx(list(np.ravel(w)), rel=1e-10, abs=1e-12)
