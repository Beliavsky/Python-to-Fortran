# Unsupported examples

These programs are valid Python, but `xp2f.py` cannot currently translate them to Fortran. They were moved out of `examples/` so that batch runs over `examples/*.py` measure what is supported. They are kept as test cases for features that may be added later.

Most use pandas for data structures beyond the DataFrame subset `xp2f.py` supports: numeric columns read from CSV, with statistics and simple display. One needs a dataclass result combined with SciPy optimizers.

| Program | What it does | What blocks translation |
|---|---|---|
| `xconcat.py` | Demonstrates `pd.concat` on small DataFrames and Series: rows, columns, differing or common columns, keys, and resetting the index | DataFrames built from dicts with string columns (`pd.DataFrame({"name": ["Alice", "Bob"], ...})`), and `pd.concat` of such frames. It uses nothing but pandas. |
| `xreturn_stats.py` | Reads ETF prices from `asset_class_etf_prices.csv`, computes returns, and prints statistics and the date range | Date handling on pandas timestamps, such as `date_min.date()` |
| `xreturn_stats_simple.py` | A shorter version: per-asset return statistics as a DataFrame | A DataFrame built from a list of per-column dicts (`pd.DataFrame([return_stats(...) for j in ...], index=price_names)`) and printed with `.round(6)`. It translates, but the generated Fortran does not compile. |
| `xarma_aic.py` | Fits ARMA models of several orders by Gaussian likelihood and selects one by AIC (a translation of an R script) | A `@dataclass` result (`ArmaFit`) with array, float, bool and string fields, built with keyword arguments. The fits also use `scipy.optimize.minimize` with `L-BFGS-B`, retried with `Powell`, and `scipy.signal.lfilter`. |
| `xmix_full.py` | Simulates and fits a univariate normal mixture by EM, then compares the true and fitted parameters | The final comparison table: `pd.concat` of a dict of DataFrames (`pd.concat({"true": ..., "fit": ..., "diff": ...}, axis=1)`) |
| `xmix_ic.py` | Fits normal mixtures with different numbers of components by EM and compares them by AIC and BIC | A DataFrame built from a list of row dicts, `pd.DataFrame(rows).set_index("n_components")` |

In `xmix_full.py` and `xmix_ic.py` only the reporting at the end needs pandas. The simulation and EM fitting are the same numerical code that `examples/xmix.py` and `examples/xmix_mv.py` translate. Printing those tables without pandas, or supporting these DataFrame constructors, would make them translatable.

## Running them

Run from the repository root. The two `xreturn_stats` programs read `asset_class_etf_prices.csv` from the current directory, and that file is in the root:

```console
python xp2f.py unsupported_examples/xmix_ic.py
```

Each command reports the construct that stops the translation. The table above records those results as of September 2026. As `xp2f.py` gains features, a program that translates, compiles and matches Python's output under `--run-diff` can move back to `examples/`.
