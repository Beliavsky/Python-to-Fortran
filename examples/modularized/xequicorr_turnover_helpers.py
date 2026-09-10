import numpy as np


def equicorr_cov(rho, xsd, p):
    corr = np.full((p, p), rho)
    np.fill_diagonal(corr, 1.0)
    return xsd**2 * corr
