"""
simulate correlated stock prices with a momentum effect: each stock has a
higher expected return when its price is above a fixed state moving
average window than when it is below. test long-short strategies based
on whether stocks are above or below moving averages for several k
values, compare all strategies on the common sample period where the
longest moving average is available, include signal persistence and
one-way proportional transaction costs based on turnover, print key
simulation parameters, and report elapsed time at the end.
"""

import time
import numpy as np

state_ma_window = 100
pairwise_corr = 0.30
t_cost_one_way = 0.001
signal_persistence_days = 3
k_list = np.array([50, 100, 150], dtype=int)


def moving_average(prices, window):
    """return rolling mean with nan before the window is available."""
    ma = np.full(prices.shape, np.nan, dtype=float)
    csum = np.cumsum(prices, axis=0, dtype=float)
    ma[window - 1] = csum[window - 1] / window
    ma[window:] = (csum[window:] - csum[:-window]) / window
    return ma


def simulate_prices(
    n_days=2000,
    n_stocks=40,
    s0=100.0,
    mu_above=0.0008,
    mu_below=-0.0002,
    sigma=0.02,
    rho=pairwise_corr,
    ma_state_window=state_ma_window,
    seed=1234,
):
    """simulate correlated prices with state-dependent drift."""
    rng = np.random.default_rng(seed)

    prices = np.empty((n_days, n_stocks), dtype=float)
    prices[0] = s0

    corr = np.full((n_stocks, n_stocks), rho, dtype=float)
    np.fill_diagonal(corr, 1.0)
    chol = np.linalg.cholesky(corr)

    init_mu = 0.5 * (mu_above + mu_below)

    for t in range(1, n_days):
        z = rng.standard_normal(n_stocks)
        shocks = chol @ z

        if t >= ma_state_window:
            ma = prices[t - ma_state_window:t].mean(axis=0)
            drift = np.where(prices[t - 1] > ma, mu_above, mu_below)
        else:
            drift = np.full(n_stocks, init_mu)

        log_ret = drift + sigma * shocks
        prices[t] = prices[t - 1] * np.exp(log_ret)

    return prices


def persistent_states(prices, k, persistence_days):
    """return long-short states using signal persistence."""
    ma = moving_average(prices, k)
    n_periods = prices.shape[0] - 1
    n_stocks = prices.shape[1]

    states = np.zeros((n_periods, n_stocks), dtype=int)
    streak_sign = np.zeros(n_stocks, dtype=int)
    streak_len = np.zeros(n_stocks, dtype=int)

    for d in range(n_periods):
        cur = states[d - 1].copy() if d > 0 else np.zeros(n_stocks, dtype=int)

        valid = ~np.isnan(ma[d])
        raw = np.zeros(n_stocks, dtype=int)
        raw[valid & (prices[d] > ma[d])] = 1
        raw[valid & (prices[d] < ma[d])] = -1

        same_mask = raw != 0
        reset_mask = (~valid) | (raw == 0)

        same_nonzero_as_before = same_mask & (raw == streak_sign)
        new_nonzero_signal = same_mask & (raw != streak_sign)

        streak_len[same_nonzero_as_before] += 1
        streak_len[new_nonzero_signal] = 1
        streak_len[reset_mask] = 0

        streak_sign[new_nonzero_signal] = raw[new_nonzero_signal]
        streak_sign[reset_mask] = 0

        long_ready = valid & (raw == 1) & (streak_len >= persistence_days)
        short_ready = valid & (raw == -1) & (streak_len >= persistence_days)

        cur[long_ready] = 1
        cur[short_ready] = -1

        states[d] = cur

    return states


def strategy_weights(prices, k, persistence_days):
    """return daily portfolio weights for the k-day ma strategy."""
    states = persistent_states(prices, k, persistence_days)
    n_periods = states.shape[0]
    n_stocks = states.shape[1]
    weights = np.zeros((n_periods, n_stocks), dtype=float)

    for d in range(n_periods):
        long_mask = states[d] > 0
        short_mask = states[d] < 0

        n_long = int(long_mask.sum())
        n_short = int(short_mask.sum())

        if n_long > 0 and n_short > 0:
            weights[d, long_mask] = 0.5 / n_long
            weights[d, short_mask] = -0.5 / n_short

    return weights


def strategy_returns_with_costs(prices, k, common_start, t_cost, persistence_days):
    """return gross and net returns for the k-day ma strategy."""
    asset_rets = prices[1:] / prices[:-1] - 1.0
    weights = strategy_weights(prices, k, persistence_days)

    weights_test = weights[common_start:]
    rets_test = asset_rets[common_start:]

    gross = np.sum(weights_test * rets_test, axis=1)

    turnover = np.empty(weights_test.shape[0], dtype=float)
    turnover[0] = np.sum(np.abs(weights_test[0]))
    if weights_test.shape[0] > 1:
        turnover[1:] = np.sum(np.abs(weights_test[1:] - weights_test[:-1]), axis=1)

    cost = t_cost * turnover
    net = gross - cost

    return gross, net, turnover, cost


def summary_stats(rets):
    """compute basic return summary statistics."""
    mean_daily = rets.mean()
    vol_daily = rets.std(ddof=1)
    ann_ret = 252.0 * mean_daily
    ann_vol = np.sqrt(252.0) * vol_daily
    sharpe = ann_ret / ann_vol if ann_vol > 0.0 else np.nan
    growth = np.prod(1.0 + rets)
    hit_rate = np.mean(rets > 0.0)
    return np.array([mean_daily, vol_daily, ann_ret, ann_vol, sharpe, growth, hit_rate])


def avg_offdiag_corr(asset_rets):
    """return the average off-diagonal sample correlation."""
    corr = np.corrcoef(asset_rets.T)
    n = corr.shape[0]
    return (corr.sum() - np.trace(corr)) / (n * (n - 1))


def monte_carlo(
    n_sims=50,
    n_days=2000,
    n_stocks=40,
    s0=100.0,
    mu_above=0.0008,
    mu_below=-0.0002,
    sigma=0.02,
    rho=pairwise_corr,
    ma_state_window=state_ma_window,
    k_values=k_list,
    t_cost=t_cost_one_way,
    persistence_days=signal_persistence_days,
    seed=1234,
):
    """repeat the experiment and collect sharpe ratios."""
    common_start = max(ma_state_window, int(np.max(k_values))) - 1

    sharpe_vals = {int(k): np.empty((n_sims, 2), dtype=float) for k in k_values}
    corr_vals = np.empty(n_sims, dtype=float)

    for i in range(n_sims):
        prices = simulate_prices(
            n_days=n_days,
            n_stocks=n_stocks,
            s0=s0,
            mu_above=mu_above,
            mu_below=mu_below,
            sigma=sigma,
            rho=rho,
            ma_state_window=ma_state_window,
            seed=seed + i,
        )
        asset_rets = prices[1:] / prices[:-1] - 1.0
        corr_vals[i] = avg_offdiag_corr(asset_rets)

        for k in k_values:
            gross, net, turnover, cost = strategy_returns_with_costs(
                prices=prices,
                k=int(k),
                common_start=common_start,
                t_cost=t_cost,
                persistence_days=persistence_days,
            )
            sharpe_gross = summary_stats(gross)[4]
            sharpe_net = summary_stats(net)[4]
            sharpe_vals[int(k)][i, 0] = sharpe_gross
            sharpe_vals[int(k)][i, 1] = sharpe_net

    return sharpe_vals, corr_vals


def print_table(sharpe_vals):
    """print average sharpe ratios across simulations."""
    print("average sharpe ratios across simulations")
    print("k".ljust(6) + "before_t_costs".rjust(18) + "after_t_costs".rjust(18))

    for k in sorted(sharpe_vals):
        mean_before = sharpe_vals[k][:, 0].mean()
        mean_after = sharpe_vals[k][:, 1].mean()
        print(f"{k:<6d}{mean_before:18.6f}{mean_after:18.6f}")


def print_simulation_parameters(
    n_days,
    n_stocks,
    n_sims,
    s0,
    mu_above,
    mu_below,
    sigma,
    rho,
    ma_state_window,
    k_values,
    t_cost,
    persistence_days,
):
    """print the main simulation parameters."""
    common_start = max(ma_state_window, int(np.max(k_values))) - 1
    n_test_returns = (n_days - 1) - common_start

    ann_ret_above = np.exp(252.0 * mu_above) - 1.0
    ann_ret_below = np.exp(252.0 * mu_below) - 1.0

    print("simulation parameters")
    print(f"n_days: {n_days}")
    print(f"n_stocks: {n_stocks}")
    print(f"n_sims: {n_sims}")
    print(f"initial_price: {s0:.6f}")
    print(f"state_ma_window: {ma_state_window}")
    print(f"strategy_k_list: {k_values.tolist()}")
    print(f"pairwise_correlation: {rho:.6f}")
    print(f"signal_persistence_days: {persistence_days}")
    print(f"t_cost_one_way: {t_cost:.6f}")
    print(f"daily_sigma: {sigma:.6f}")
    print(f"daily_mu_above: {mu_above:.6f}")
    print(f"daily_mu_below: {mu_below:.6f}")
    print(f"annualized_return_above: {ann_ret_above:.6f}")
    print(f"annualized_return_below: {ann_ret_below:.6f}")
    print(f"common_start_index: {common_start}")
    print(f"n_returns_in_test_period: {n_test_returns}")


def main():
    t0 = time.perf_counter()

    n_days = 2000
    n_stocks = 40
    n_sims = 50
    s0 = 100.0
    mu_above = 0.0008
    mu_below = -0.0002
    sigma = 0.02

    print_simulation_parameters(
        n_days=n_days,
        n_stocks=n_stocks,
        n_sims=n_sims,
        s0=s0,
        mu_above=mu_above,
        mu_below=mu_below,
        sigma=sigma,
        rho=pairwise_corr,
        ma_state_window=state_ma_window,
        k_values=k_list,
        t_cost=t_cost_one_way,
        persistence_days=signal_persistence_days,
    )
    print()

    prices = simulate_prices(
        n_days=n_days,
        n_stocks=n_stocks,
        s0=s0,
        mu_above=mu_above,
        mu_below=mu_below,
        sigma=sigma,
        rho=pairwise_corr,
        ma_state_window=state_ma_window,
        seed=1234,
    )
    asset_rets = prices[1:] / prices[:-1] - 1.0

    print(f"single_run_average_pairwise_stock_return_correlation: {avg_offdiag_corr(asset_rets):.4f}")

    common_start = max(state_ma_window, int(np.max(k_list))) - 1
    print(f"common_strategy_start_index: {common_start}")
    print(f"common_strategy_sample_length: {asset_rets.shape[0] - common_start}")
    print()

    print("single-run sharpe ratios")
    print("k".ljust(6) + "before_t_costs".rjust(18) + "after_t_costs".rjust(18))

    for k in k_list:
        gross, net, turnover, cost = strategy_returns_with_costs(
            prices=prices,
            k=int(k),
            common_start=common_start,
            t_cost=t_cost_one_way,
            persistence_days=signal_persistence_days,
        )
        sharpe_gross = summary_stats(gross)[4]
        sharpe_net = summary_stats(net)[4]
        print(f"{int(k):<6d}{sharpe_gross:18.6f}{sharpe_net:18.6f}")

    sharpe_vals, corr_vals = monte_carlo(
        n_sims=n_sims,
        n_days=n_days,
        n_stocks=n_stocks,
        s0=s0,
        mu_above=mu_above,
        mu_below=mu_below,
        sigma=sigma,
        rho=pairwise_corr,
        ma_state_window=state_ma_window,
        k_values=k_list,
        t_cost=t_cost_one_way,
        persistence_days=signal_persistence_days,
        seed=1234,
    )

    print()
    print(f"monte_carlo_mean_pairwise_stock_return_correlation: {corr_vals.mean():.4f}")
    print_table(sharpe_vals)
    print()
    print(f"elapsed_time_seconds: {time.perf_counter() - t0:.3f}")


if __name__ == "__main__":
    main()
