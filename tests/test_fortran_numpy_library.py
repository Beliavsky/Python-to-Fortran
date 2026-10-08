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
