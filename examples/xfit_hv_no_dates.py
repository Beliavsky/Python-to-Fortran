#!/usr/bin/env python3
"""
fit a + b*hv to future realized volatility for each asset and horizon.

the script reads a csv of prices with a header row of asset names and no
date column, computes log returns, computes 20-day historical volatility
using either equal or linearly declining weights, then fits the linear
predictor a + b*hv for future realized volatility. all calculations and
file handling are done without pandas.
"""

import argparse
import csv
import numpy as np


def make_weights(window, scheme):
    """return normalized weights for the hv window."""
    scheme = scheme.lower()
    if scheme == "equal":
        w = np.ones(window, dtype=float)
    elif scheme in {"linear", "linearly_declining", "declining"}:
        w = np.arange(1, window + 1, dtype=float)
    else:
        raise ValueError(f"unknown weighting scheme: {scheme}")
    return w / w.sum()


def read_price_csv(path):
    """read a csv with asset names in row 1 and prices only below it."""
    with open(path, newline="", encoding="utf-8-sig") as f:
        rows = list(csv.reader(f))

    if not rows:
        raise ValueError("empty csv file")

    header = [name.strip() for name in rows[0] if name.strip()]
    if not header:
        raise ValueError("expected first row to contain asset names")

    n_assets = len(header)
    data_rows = rows[1:]
    if not data_rows:
        raise ValueError("csv file has header but no data rows")

    prices_list = []
    for i, row in enumerate(data_rows, start=2):
        if len(row) != n_assets:
            raise ValueError(
                f"row {i} has {len(row)} fields but expected {n_assets}"
            )
        try:
            prices_list.append([float(x) for x in row])
        except ValueError as exc:
            raise ValueError(f"non-numeric price found in row {i}") from exc

    prices = np.array(prices_list, dtype=float)
    return header, prices


def compute_hv(ret, window, scheme, annualization):
    """compute annualized historical volatility from log returns."""
    w = make_weights(window, scheme)
    windows = np.lib.stride_tricks.sliding_window_view(ret, window_shape=window, axis=0)
    hv2 = np.sum((windows ** 2) * w[None, None, :], axis=2)
    return np.sqrt(annualization * hv2)


def compute_future_vol(ret, horizon, annualization):
    """compute annualized realized future volatility over a fixed horizon."""
    windows = np.lib.stride_tricks.sliding_window_view(ret, window_shape=horizon, axis=0)
    fv2 = np.mean(windows ** 2, axis=2)
    return np.sqrt(annualization * fv2)


def fit_line(x, y):
    """fit y = a + b*x by ordinary least squares."""
    mask = np.isfinite(x) & np.isfinite(y)
    x = x[mask]
    y = y[mask]

    if x.size < 2:
        return np.nan, np.nan, np.nan, np.nan, np.nan, x.size

    xmat = np.column_stack((np.ones(x.size, dtype=float), x))
    coef, _, _, _ = np.linalg.lstsq(xmat, y, rcond=None)
    yhat = xmat @ coef

    ss_res = np.sum((y - yhat) ** 2)
    ss_tot = np.sum((y - y.mean()) ** 2)
    r2 = np.nan if ss_tot == 0.0 else 1.0 - ss_res / ss_tot
    corr = np.corrcoef(x, y)[0, 1] if x.size > 1 else np.nan
    rmse = np.sqrt(np.mean((y - yhat) ** 2))

    return coef[0], coef[1], r2, corr, rmse, x.size


def analyze_file(path, lookback, horizons, weights, annualization):
    """read prices, compute hv/future vol, and fit a + b*hv."""
    asset_names, prices = read_price_csv(path)

    if prices.ndim != 2:
        raise ValueError("expected a 2d table of prices")

    if np.any(~np.isfinite(prices)):
        raise ValueError("price table contains non-finite values")

    if np.any(prices <= 0.0):
        raise ValueError("all prices must be positive to compute log returns")

    ret = np.diff(np.log(prices), axis=0)
    n_dates, n_assets = prices.shape

    if lookback >= n_dates:
        raise ValueError("lookback must be smaller than the number of price rows")

    hv = compute_hv(ret, window=lookback, scheme=weights, annualization=annualization)

    results = []
    for horizon in horizons:
        if lookback + horizon >= n_dates:
            raise ValueError(
                f"lookback + horizon must be smaller than the number of price rows; "
                f"got lookback={lookback}, horizon={horizon}, n_dates={n_dates}"
            )

        fv = compute_future_vol(ret, horizon=horizon, annualization=annualization)

        count = n_dates - lookback - horizon
        x = hv[:count, :]
        y = fv[lookback:, :]

        for j in range(n_assets):
            a, b, r2, corr, rmse, nobs = fit_line(x[:, j], y[:, j])
            results.append(
                {
                    "asset": asset_names[j],
                    "horizon": int(horizon),
                    "a": float(a),
                    "b": float(b),
                    "r2": float(r2),
                    "corr": float(corr),
                    "rmse": float(rmse),
                    "nobs": int(nobs),
                }
            )

    return results


def format_float(x):
    """format floats for display."""
    if np.isnan(x):
        return "nan"
    return f"{x:0.6f}"


def print_results(results):
    """print regression results in aligned columns."""
    headers = ["asset", "horizon", "a", "b", "r2", "corr", "rmse", "nobs"]
    widths = {
        "asset": max(len("asset"), max(len(row["asset"]) for row in results)),
        "horizon": len("horizon"),
        "a": len("a"),
        "b": len("b"),
        "r2": len("r2"),
        "corr": len("corr"),
        "rmse": len("rmse"),
        "nobs": len("nobs"),
    }

    for key in ["horizon", "nobs"]:
        widths[key] = max(widths[key], max(len(str(row[key])) for row in results))
    for key in ["a", "b", "r2", "corr", "rmse"]:
        widths[key] = max(widths[key], max(len(format_float(row[key])) for row in results))

    print(" ".join([
        f"{headers[0]:<{widths['asset']}}",
        f"{headers[1]:>{widths['horizon']}}",
        f"{headers[2]:>{widths['a']}}",
        f"{headers[3]:>{widths['b']}}",
        f"{headers[4]:>{widths['r2']}}",
        f"{headers[5]:>{widths['corr']}}",
        f"{headers[6]:>{widths['rmse']}}",
        f"{headers[7]:>{widths['nobs']}}",
    ]))

    for row in results:
        print(" ".join([
            f"{row['asset']:<{widths['asset']}}",
            f"{row['horizon']:>{widths['horizon']}}",
            f"{format_float(row['a']):>{widths['a']}}",
            f"{format_float(row['b']):>{widths['b']}}",
            f"{format_float(row['r2']):>{widths['r2']}}",
            f"{format_float(row['corr']):>{widths['corr']}}",
            f"{format_float(row['rmse']):>{widths['rmse']}}",
            f"{row['nobs']:>{widths['nobs']}}",
        ]))


def write_results_csv(path, results):
    """write regression results to a csv file."""
    fieldnames = ["asset", "horizon", "a", "b", "r2", "corr", "rmse", "nobs"]
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in results:
            writer.writerow(row)


def main():
    parser = argparse.ArgumentParser(
        description=(
            "read a csv of prices with no date column, compute hv from log returns, "
            "and fit future_vol = a + b*hv for each asset and horizon"
        )
    )
    parser.add_argument(
        "csv_file",
        nargs="?",
        default="prices_no_dates.csv",
        help="csv file of prices; first row must contain asset names and no date column",
    )
    parser.add_argument(
        "--lookback",
        type=int,
        default=20,
        help="number of trading days in the hv window",
    )
    parser.add_argument(
        "--weights",
        choices=["equal", "linear"],
        default="equal",
        help="hv weighting scheme",
    )
    parser.add_argument(
        "--horizons",
        type=int,
        nargs="+",
        default=[5, 10, 21, 42, 63],
        help="forward realized-volatility horizons in trading days",
    )
    parser.add_argument(
        "--annualization",
        type=float,
        default=252.0,
        help="annualization factor",
    )
    parser.add_argument(
        "--output",
        default="hv_fit_results.csv",
        help="output csv for regression results",
    )
    args = parser.parse_args()

    results = analyze_file(
        path=args.csv_file,
        lookback=args.lookback,
        horizons=args.horizons,
        weights=args.weights,
        annualization=args.annualization,
    )

    print()
    print(f"weights = {args.weights}")
    print(f"lookback = {args.lookback}")
    print(f"horizons = {args.horizons}")
    print()
    print_results(results)

    write_results_csv(args.output, results)
    print()
    print(f"wrote {args.output}")


if __name__ == "__main__":
    main()
