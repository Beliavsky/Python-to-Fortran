import numpy as np


def simulate_nagarch_noise(n, omega, alpha, theta, beta, rng):
    """Generate n zero-mean innovations from a NAGARCH(1,1) process.

    `rng` is passed explicitly (unlike ../xarma_nagarch_fit.py, which
    reads a bare module-level `rng` global) because real Python module
    scoping does NOT let a function defined in this sibling module see
    a global defined only in the importing main script -- that's true
    of ordinary Python regardless of xpfunc2f.py, so the faithful way to
    modularize this dependency is to pass rng through like
    ../xequicorr_turnover.py's simulate_turnover already does.
    """
    h = np.empty(n)
    eps = np.empty(n)

    denom = 1.0 - beta - alpha * (1.0 + theta**2)
    h[0] = omega / denom
    z0 = rng.standard_normal()
    eps[0] = np.sqrt(h[0]) * z0

    for t in range(1, n):
        h[t] = (
            omega
            + alpha * (eps[t - 1] - theta * np.sqrt(h[t - 1]))**2
            + beta * h[t - 1]
        )
        zt = rng.standard_normal()
        eps[t] = np.sqrt(h[t]) * zt

    return eps
