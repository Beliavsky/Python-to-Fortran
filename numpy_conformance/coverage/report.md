# numpy coverage probe

528 functions.

| status | count |
|---|---|
| DIFF | 6 |
| BUILD-FAIL | 2 |
| XLATE-FAIL | 47 |
| NOARGS | 58 |
| MATCH | 415 |

## BUILD-FAIL

- `np.percentile`: Rank mismatch in argument 'q' at (1) (rank-1 and rank-2)
- `np.roll`: 'shift' argument of 'cshift' intrinsic at (1) must be a scalar

## XLATE-FAIL

- `np.array_split`: r = np.split(...) is a list of arrays: use its parts (r[0], ...), unpack it, or loop over it
- `np.block`: unsupported call: np.block(x)
- `np.broadcast_arrays`: unsupported call: np.broadcast_arrays(x)
- `np.broadcast_shapes`: unsupported assign: r0, r1, r2, r3 = np.broadcast_shapes(xi)
- `np.choose`: unsupported call: np.choose(b, b)
- `np.column_stack`: column_stack requires tuple/list input
- `np.concat`: concatenate requires tuple/list input
- `np.concatenate`: concatenate requires tuple/list input
- `np.diag_indices`: unsupported assign: r0, r1 = np.diag_indices(0.7)
- `np.histogramdd`: unsupported assign: r0, r1 = np.histogramdd(x)
- `np.hsplit`: r = np.split(...) is a list of arrays: use its parts (r[0], ...), unpack it, or loop over it
- `np.hstack`: hstack requires tuple/list input
- `np.ix_`: unsupported call: np.ix_(x)
- `np.kaiser`: np.kaiser: M must be an integer
- `np.lexsort`: np.lexsort expects a key matrix or a tuple of vectors
- `np.linalg.multi_dot`: np.linalg.multi_dot requires a literal list/tuple of at least 2 matrices
- `np.linalg.tensorsolve`: unsupported call: np.linalg.tensorsolve(0.7, 0.4)
- `np.matvec`: unsupported call: np.matvec(m, m)
- `np.meshgrid`: unsupported call: np.meshgrid(x)
- `np.nanpercentile`: np.nanpercentile: q must be a scalar or a vector
- `np.polynomial.chebyshev.chebgrid2d`: chebgrid2d: the coefficients must have 2 dimensions
- `np.polynomial.chebyshev.chebval2d`: chebval2d: the coefficients must have 2 dimensions
- `np.polynomial.hermite.hermgrid2d`: hermgrid2d: the coefficients must have 2 dimensions
- `np.polynomial.hermite.hermval2d`: hermval2d: the coefficients must have 2 dimensions
- `np.polynomial.hermite_e.hermegrid2d`: hermegrid2d: the coefficients must have 2 dimensions
- `np.polynomial.hermite_e.hermeval2d`: hermeval2d: the coefficients must have 2 dimensions
- `np.polynomial.laguerre.laggrid2d`: laggrid2d: the coefficients must have 2 dimensions
- `np.polynomial.laguerre.lagval2d`: lagval2d: the coefficients must have 2 dimensions
- `np.polynomial.legendre.leggrid2d`: leggrid2d: the coefficients must have 2 dimensions
- `np.polynomial.legendre.legval2d`: legval2d: the coefficients must have 2 dimensions
- `np.polynomial.polynomial.polygrid2d`: polygrid2d: the coefficients must have 2 dimensions
- `np.polynomial.polynomial.polyval2d`: polyval2d: the coefficients must have 2 dimensions
- `np.select`: np.select currently requires condlist and choicelist as literal lists at the call site
- `np.split`: r = np.split(...) is a list of arrays: use its parts (r[0], ...), unpack it, or loop over it
- `np.stack`: np.stack requires tuple/list inputs
- `np.tri`: np.tri: N, M and k must be integers
- `np.tril_indices`: unsupported assign: r0, r1 = np.tril_indices(0.7)
- `np.triu_indices`: unsupported assign: r0, r1 = np.triu_indices(0.7)
- `np.unstack`: unsupported assign: r0, r1, r2, r3 = np.unstack(x)
- `np.vecmat`: unsupported call: np.vecmat(m, m)
- `np.vstack`: vstack requires tuple/list input

## Known differences

- `np.argpartition` (XLATE-FAIL): numpy's introselect order is not reproduced
- `np.bartlett` (XLATE-FAIL): the probe's float M is rejected (M must be an integer)
- `np.blackman` (XLATE-FAIL): the probe's float M is rejected (M must be an integer)
- `np.hamming` (XLATE-FAIL): the probe's float M is rejected (M must be an integer)
- `np.hanning` (XLATE-FAIL): the probe's float M is rejected (M must be an integer)
- `np.linalg.eig` (DIFF): always complex in the translation
- `np.linalg.eigvals` (DIFF): always complex in the translation
- `np.partition` (XLATE-FAIL): numpy's introselect order is not reproduced
- `np.polynomial.chebyshev.chebroots` (DIFF): always complex in the translation
- `np.polynomial.hermite.hermroots` (DIFF): always complex in the translation
- `np.polynomial.hermite_e.hermeroots` (DIFF): always complex in the translation
- `np.polynomial.laguerre.lagroots` (DIFF): always complex in the translation

## NOARGS

`np.asmatrix`, `np.astype`, `np.atleast_3d`, `np.bmat`, `np.cross`, `np.dsplit`, `np.dstack`, `np.einsum`, `np.expand_dims`, `np.fromfunction`, `np.histogram2d`, `np.in1d`, `np.indices`, `np.insert`, `np.isnat`, `np.linalg.cross`, `np.linalg.tensorinv`, `np.mask_indices`, `np.moveaxis`, `np.polyfit`, `np.polynomial.chebyshev.chebfit`, `np.polynomial.chebyshev.chebgrid3d`, `np.polynomial.chebyshev.chebinterpolate`, `np.polynomial.chebyshev.chebval3d`, `np.polynomial.chebyshev.chebvander2d`, `np.polynomial.chebyshev.chebvander3d`, `np.polynomial.hermite.hermfit`, `np.polynomial.hermite.hermgrid3d`, `np.polynomial.hermite.hermval3d`, `np.polynomial.hermite.hermvander2d`, `np.polynomial.hermite.hermvander3d`, `np.polynomial.hermite_e.hermefit`, `np.polynomial.hermite_e.hermegrid3d`, `np.polynomial.hermite_e.hermeval3d`, `np.polynomial.hermite_e.hermevander2d`, `np.polynomial.hermite_e.hermevander3d`, `np.polynomial.laguerre.lagfit`, `np.polynomial.laguerre.laggrid3d`, `np.polynomial.laguerre.lagval3d`, `np.polynomial.laguerre.lagvander2d`, `np.polynomial.laguerre.lagvander3d`, `np.polynomial.legendre.legfit`, `np.polynomial.legendre.leggrid3d`, `np.polynomial.legendre.legval3d`, `np.polynomial.legendre.legvander2d`, `np.polynomial.legendre.legvander3d`, `np.polynomial.polynomial.polyfit`, `np.polynomial.polynomial.polygrid3d`, `np.polynomial.polynomial.polyval3d`, `np.polynomial.polynomial.polyvander2d`, `np.polynomial.polynomial.polyvander3d`, `np.reshape`, `np.row_stack`, `np.swapaxes`, `np.take_along_axis`, `np.trapz`, `np.unpackbits`, `np.vsplit`
