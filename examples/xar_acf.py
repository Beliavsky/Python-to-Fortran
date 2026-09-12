import numpy as np


def acf(x, nacf):
    """Calculate the first nacf sample autocorrelations."""
    x = np.asarray(x, dtype=float)
    x = x - x.mean()

    denom = np.dot(x, x)

    return np.array([
        np.dot(x[k:], x[:-k]) / denom
        for k in range(1, nacf + 1)
    ])

# Simulate an AR(1): x[t] = phi*x[t-1] + eps[t]
rng = np.random.default_rng(12345)

n = 100000
phi = 0.8
nacf = 10
print("#obs:", n)
print("phi:", phi, end="\n\n")
x = np.empty(n)
x[0] = rng.normal() / np.sqrt(1.0 - phi**2)

for t in range(1, n):
    x[t] = phi * x[t - 1] + rng.normal()

# Sample ACF
rho_hat = acf(x, nacf)

# Theoretical AR(1) ACF: rho(k) = phi**k
rho_true = phi ** np.arange(1, nacf + 1)

fmt_s = "%10s"
print(fmt_s%"lag", fmt_s%"sample", fmt_s%"true")
for iacf in range(nacf):
    print("%10d"%(iacf+1), "%10.4f"%rho_hat[iacf], "%10.4f"%rho_true[iacf])
