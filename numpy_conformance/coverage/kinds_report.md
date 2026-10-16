# numpy coverage probe: kinds of results

1259 cases.

| status | count |
|---|---|
| KIND | 3 |
| BUILD-FAIL | 35 |
| XLATE-FAIL | 3 |
| MATCH | 1218 |

## KIND

- `def fn652(a, scale=2): /     return a * scale; y = fn652(x); print(y); r = fn652(xi)`: py=[ 1. 3. -4. 6.5] [6 2 8 2] | ft=1.0000000000000000 3.0000000000000000 -4.0000000000000000 6.5000000000000000 6.0
- `def fn653(a, scale=2): /     return a * scale; y = fn653(xi); print(y); r = fn653(x)`: py=[6 2 8 2] [ 1. 3. -4. 6.5] | ft=6.0000000000000000 2.0000000000000000 8.0000000000000000 2.0000000000000000 1.00
- `r = max(xi[0], 2.5)`: py=3 | ft=3.0000000000000000

## BUILD-FAIL

- `def fn452(a): /     return np.cumsum(a); y = fn452(3); print(y); r = fn452(xi)`: Rank mismatch in argument 'x' at (1) (rank-1 and scalar)
- `def fn453(a): /     return np.cumsum(a); y = fn453(2.5); print(y); r = fn453(xi)`: Rank mismatch in argument 'x' at (1) (rank-1 and scalar)
- `def fn457(a): /     return np.cumsum(a); y = fn457(3); print(y); r = fn457(x)`: Rank mismatch in argument 'x' at (1) (rank-1 and scalar)
- `def fn458(a): /     return np.cumsum(a); y = fn458(2.5); print(y); r = fn458(x)`: Rank mismatch in argument 'x' at (1) (rank-1 and scalar)
- `def fn462(a): /     return np.cumsum(a); y = fn462(3); print(y); r = fn462(b)`: Rank mismatch in argument 'x' at (1) (rank-1 and scalar)
- `def fn463(a): /     return np.cumsum(a); y = fn463(2.5); print(y); r = fn463(b)`: Rank mismatch in argument 'x' at (1) (rank-1 and scalar)
- `def fn465(a): /     return np.cumsum(a); y = fn465(xi); print(y); r = fn465(3)`: Rank mismatch in argument 'x' at (1) (rank-1 and scalar)
- `def fn466(a): /     return np.cumsum(a); y = fn466(x); print(y); r = fn466(3)`: Rank mismatch in argument 'x' at (1) (rank-1 and scalar)
- `def fn467(a): /     return np.cumsum(a); y = fn467(b); print(y); r = fn467(3)`: Rank mismatch in argument 'x' at (1) (rank-1 and scalar)
- `def fn468(a): /     return np.cumsum(a); y = fn468(2.5); print(y); r = fn468(3)`: Rank mismatch in argument 'x' at (1) (rank-1 and scalar)
- `def fn469(a): /     return np.cumsum(a); y = fn469(m); print(y); r = fn469(3)`: Rank mismatch in argument 'x' at (1) (rank-1 and scalar)
- `def fn470(a): /     return np.cumsum(a); y = fn470(xi); print(y); r = fn470(2.5)`: Rank mismatch in argument 'x' at (1) (rank-1 and scalar)
- `def fn471(a): /     return np.cumsum(a); y = fn471(x); print(y); r = fn471(2.5)`: Rank mismatch in argument 'x' at (1) (rank-1 and scalar)
- `def fn472(a): /     return np.cumsum(a); y = fn472(b); print(y); r = fn472(2.5)`: Rank mismatch in argument 'x' at (1) (rank-1 and scalar)
- `def fn473(a): /     return np.cumsum(a); y = fn473(3); print(y); r = fn473(2.5)`: Rank mismatch in argument 'x' at (1) (rank-1 and scalar)
- `def fn474(a): /     return np.cumsum(a); y = fn474(m); print(y); r = fn474(2.5)`: Rank mismatch in argument 'x' at (1) (rank-1 and scalar)
- `def fn478(a): /     return np.cumsum(a); y = fn478(3); print(y); r = fn478(m)`: Rank mismatch in argument 'x' at (1) (rank-1 and scalar)
- `def fn479(a): /     return np.cumsum(a); y = fn479(2.5); print(y); r = fn479(m)`: Rank mismatch in argument 'x' at (1) (rank-1 and scalar)
- `def fn571(a): /     return np.where(a > 1, a, 0); y = fn571(b); print(y); r = fn571(xi)`: 'fsource' argument of 'merge' intrinsic at (1) must be the same type and kind as 'tsource'
- `def fn576(a): /     return np.where(a > 1, a, 0); y = fn576(b); print(y); r = fn576(x)`: 'fsource' argument of 'merge' intrinsic at (1) must be the same type and kind as 'tsource'
- `def fn580(a): /     return np.where(a > 1, a, 0); y = fn580(xi); print(y); r = fn580(b)`: 'fsource' argument of 'merge' intrinsic at (1) must be the same type and kind as 'tsource'
- `def fn581(a): /     return np.where(a > 1, a, 0); y = fn581(x); print(y); r = fn581(b)`: 'fsource' argument of 'merge' intrinsic at (1) must be the same type and kind as 'tsource'
- `def fn582(a): /     return np.where(a > 1, a, 0); y = fn582(3); print(y); r = fn582(b)`: 'fsource' argument of 'merge' intrinsic at (1) must be the same type and kind as 'tsource'
- `def fn583(a): /     return np.where(a > 1, a, 0); y = fn583(2.5); print(y); r = fn583(b)`: 'fsource' argument of 'merge' intrinsic at (1) must be the same type and kind as 'tsource'
- `def fn584(a): /     return np.where(a > 1, a, 0); y = fn584(m); print(y); r = fn584(b)`: 'fsource' argument of 'merge' intrinsic at (1) must be the same type and kind as 'tsource'
- `def fn587(a): /     return np.where(a > 1, a, 0); y = fn587(b); print(y); r = fn587(3)`: 'fsource' argument of 'merge' intrinsic at (1) must be the same type and kind as 'tsource'
- `def fn592(a): /     return np.where(a > 1, a, 0); y = fn592(b); print(y); r = fn592(2.5)`: 'fsource' argument of 'merge' intrinsic at (1) must be the same type and kind as 'tsource'
- `def fn597(a): /     return np.where(a > 1, a, 0); y = fn597(b); print(y); r = fn597(m)`: 'fsource' argument of 'merge' intrinsic at (1) must be the same type and kind as 'tsource'
- `def fn629(a, c): /     return np.maximum(a, c); y = fn629(xi, xi); print(y); r = fn629(m, x[:2])`: Incompatible ranks in elemental procedure (1 and 2) at (1)
- `def fn636(a, c): /     return np.where(a > 1, a, c); y = fn636(xi, b); print(y); r = fn636(b, xi)`: 'fsource' argument of 'merge' intrinsic at (1) must be the same type and kind as 'tsource'
- `def fn637(a, c): /     return np.where(a > 1, a, c); y = fn637(xi, xi); print(y); r = fn637(m, x[:2])`: Incompatible ranks in arguments 'tsource' and 'fsource' for intrinsic 'merge' (2 and 1) at (1)
- `r = np.triu(xi.reshape(2, 2))`: Syntax error in IF-clause after (1)
- `y = 0; y += True; r = y`: Operands of binary numeric operator '+' at (1) are INTEGER(4)/LOGICAL(4)
- `y = np.empty(3, dtype=int); y[0] = 1.9; y[1] = -1.9; y[2] = 0; r = y`: Element in REAL(8) array constructor at (1) is INTEGER(4)
- `y = np.zeros(2, dtype=bool); y[0] = 2.5; r = y`: Cannot convert REAL(8) to LOGICAL(4) at (1)

## XLATE-FAIL

- `def fn655(a, scale=2): /     return a * scale; y = fn655(b); print(y); r = fn655(xi)`: function 'fn655' is called with arguments of different kinds (int here, logical in its signature) and is not specialized for them: use separate functions
- `r = divmod(7, 2)[0]`: unsupported call: divmod(7, 2)
- `y = xi.copy(); y = y * 2.5; r = y`: rebinding 'y_0' from int to real in terms of itself (y_0 = y_0 * 2.5) is not supported: use a new name for the real value
