# numpy coverage probe: random numbers

428 cases.

| status | count |
|---|---|
| XLATE-FAIL | 9 |
| MATCH | 419 |

## XLATE-FAIL

- `replay np.random.binomial(np.array([5, 10, 20]), 0.5)`: random binomial with array-valued parameters is not supported
- `replay np.random.exponential(scale=np.array([1.0, 10.0, 100.0]))`: random exponential with array-valued parameters is not supported
- `replay np.random.gamma(np.array([1.0, 2.0, 5.0]), 2.0)`: random gamma with array-valued parameters is not supported
- `replay np.random.poisson(np.array([1.0, 5.0, 20.0]))`: random poisson with array-valued parameters is not supported
- `replay rng.binomial(np.array([5, 10, 20]), 0.5)`: random binomial with array-valued parameters is not supported
- `replay rng.exponential(scale=np.array([1.0, 10.0, 100.0]))`: random exponential with array-valued parameters is not supported
- `replay rng.gamma(np.array([1.0, 2.0, 5.0]), 2.0)`: random gamma with array-valued parameters is not supported
- `replay rng.integers(np.array([1, 10, 100]), np.array([5, 20, 200]))`: random integers with array-valued bounds is not supported
- `replay rng.poisson(np.array([1.0, 5.0, 20.0]))`: random poisson with array-valued parameters is not supported
