# numpy coverage probe: edge values

470 cases.

| status | count |
|---|---|
| XLATE-FAIL | 2 |
| MATCH | 468 |

## XLATE-FAIL

- `x = np.array([1.0, np.nan, -2.0, 3.0]); r = np.maximum.accumulate(x)`: unsupported call: np.maximum.accumulate(x_2)
- `x = np.array([1.0, np.nan, -2.0, 3.0]); r = sorted(x.tolist())`: sorted(...) is currently supported only in for-loops
