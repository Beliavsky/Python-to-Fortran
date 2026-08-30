"""
Branches from xequicorr.py: simulate correlated stock returns from an
equicorrelation matrix, then study how much trading (turnover) is needed
each period to rebalance a portfolio back to equal weight after returns
have let the weights drift apart.

Turnover convention: after a period's returns, dollar position i has
drifted to d_i. Rebalancing back to equal weight means moving every
position to target = (sum of d_i) / p. One-way turnover for the period
is defined as half the total absolute dollar amount traded, expressed as
a fraction of portfolio value -- the standard convention (a buy in one
name is exactly offset by a sell in another, so dividing by 2 avoids
double-counting the same rebalancing trade).
"""

import numpy as np

rng = np.random.default_rng(12345)

n = 10000  # trading periods
p = 20  # number of assets
xsd = 0.02  # per-period return volatility, in percent
rho = 0.4  # base-case equicorrelation


def equicorr_cov(rho, xsd, p):
    corr = np.full((p, p), rho)
    np.fill_diagonal(corr, 1.0)
    return xsd**2 * corr


def simulate_turnover(rho, xsd, p, n, rng):
    """Equal-weight-rebalanced portfolio: returns per-period turnover
    (fraction of portfolio value traded to get back to equal weight)."""
    cov = equicorr_cov(rho, xsd, p)
    rets = rng.multivariate_normal(mean=np.zeros(p), cov=cov, size=n) / 100.0
    d = np.full(p, 1.0 / p)  # dollar positions, starting at equal weight, $1 total
    turnover = np.zeros(n)
    for t in range(n):
        d_new = d * (1.0 + rets[t])
        v_new = d_new.sum()
        target = v_new / p
        trade = target - d_new
        turnover[t] = np.abs(trade).sum() / (2.0 * v_new)
        d = np.full(p, target)  # back to equal weight for the next period
    return turnover


print("xsd, rho =", xsd, rho)
print("n, p =", n, p)

turnover = simulate_turnover(rho, xsd, p, n, rng)

print("\nPer-period turnover (fraction of portfolio value)")
print(f"{'mean':>10s} {'std':>10s} {'min':>10s} {'max':>10s} {'total':>10s} {'ann. avg':>10s}")
print(
    f"{turnover.mean():10.6f} {turnover.std(ddof=1):10.6f} {turnover.min():10.6f} "
    f"{turnover.max():10.6f} {turnover.sum():10.4f} {turnover.mean() * 252.0:10.4f}"
)

print("\nMean turnover vs equicorrelation (higher correlation -> stocks move")
print("together -> relative weights drift less -> less rebalancing trade needed)")
print(f"{'rho':>6s} {'mean turnover':>15s}")
for i, rho_i in enumerate([0.0, 0.2, 0.4, 0.6, 0.8]):
    rng_i = np.random.default_rng(12345 + i)
    turnover_i = simulate_turnover(rho_i, xsd, p, n, rng_i)
    print(f"{rho_i:6.2f} {turnover_i.mean():15.6f}")
