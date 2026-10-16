# numpy coverage probe: methods, operators, indexing

6293 cases.

| status | count |
|---|---|
| DIFF | 5 |
| BUILD-FAIL | 24 |
| XLATE-FAIL | 28 |
| MATCH | 6236 |

## BUILD-FAIL

- `r = m.clip(min=0) [complex]`: 'a1' argument of 'max' intrinsic at (1) must be INTEGER, REAL or CHARACTER
- `r = m[[0, 1], [1, 0]] [3d]`: Rank mismatch in array reference at (1) (2/3)
- `r = mr != x[:3] [one]`: Shapes for operands at (1) and (2) are not conformable
- `r = mr % x[:3] [one]`: Different shape for arguments 'a' and 'p' for intrinsic 'modulo' at (1) on dimension 2 (3 and 1)
- `r = mr * x[:3] [one]`: Shapes for operands at (1) and (2) are not conformable
- `r = mr + x[:3] [one]`: Shapes for operands at (1) and (2) are not conformable
- `r = mr - x[:3] [one]`: Shapes for operands at (1) and (2) are not conformable
- `r = mr / x[:3] [one]`: Shapes for operands at (1) and (2) are not conformable
- `r = mr // x[:3] [one]`: Different shape for elemental procedure at (1) on dimension 2 (1 and 3)
- `r = mr < x[:3] [one]`: Shapes for operands at (1) and (2) are not conformable
- `r = mr <= x[:3] [one]`: Shapes for operands at (1) and (2) are not conformable
- `r = mr == x[:3] [one]`: Shapes for operands at (1) and (2) are not conformable
- `r = mr > x[:3] [one]`: Shapes for operands at (1) and (2) are not conformable
- `r = mr >= x[:3] [one]`: Shapes for operands at (1) and (2) are not conformable
- `r = mr.clip(min=0) [complex]`: 'a1' argument of 'max' intrinsic at (1) must be INTEGER, REAL or CHARACTER
- `r = mr[[0, 1], [1, 0]] [3d]`: Rank mismatch in array reference at (1) (2/3)
- `r = x.clip(min=0) [complex]`: 'a1' argument of 'max' intrinsic at (1) must be INTEGER, REAL or CHARACTER
- `y = x.copy(); y[xi % 4] = 2; r = y [base]`: Elements with the same value at (1) and (2) in vector subscript in a variable definition context (assignment)
- `y = x.copy(); y[xi % 4] = 2; r = y [complex]`: Elements with the same value at (1) and (2) in vector subscript in a variable definition context (assignment)
- `y = x.copy(); y[xi % 4] = 2; r = y [int]`: Elements with the same value at (1) and (2) in vector subscript in a variable definition context (assignment)
- `y = x.copy(); y[xi % 4] = 2; r = y [nan]`: Elements with the same value at (1) and (2) in vector subscript in a variable definition context (assignment)
- `y = x.copy(); y[xi % 4] = 2; r = y [ties]`: Elements with the same value at (1) and (2) in vector subscript in a variable definition context (assignment)
- `y = xi.copy(); y[xi % 4] = 2; r = y [base]`: Elements with the same value at (1) and (2) in vector subscript in a variable definition context (assignment)
- `y = xi.copy(); y[xi % 4] = 2; r = y [ties]`: Elements with the same value at (1) and (2) in vector subscript in a variable definition context (assignment)

## XLATE-FAIL

- `r = m.squeeze() [complex]`: np.squeeze of a matrix needs axis= (the result's rank would depend on its shape)
- `r = m.squeeze() [nan]`: np.squeeze of a matrix needs axis= (the result's rank would depend on its shape)
- `r = m.squeeze() [ties]`: np.squeeze of a matrix needs axis= (the result's rank would depend on its shape)
- `r = m[:, [True, False]] [base]`: unsupported expr: Slice
- `r = m[:, [True, False]] [complex]`: unsupported expr: Slice
- `r = m[:, [True, False]] [empty]`: unsupported expr: Slice
- `r = m[:, [True, False]] [int]`: unsupported expr: Slice
- `r = m[:, [True, False]] [nan]`: unsupported expr: Slice
- `r = m[:, [True, False]] [ties]`: unsupported expr: Slice
- `r = mr.squeeze() [base]`: np.squeeze of a matrix needs axis= (the result's rank would depend on its shape)
- `r = mr.squeeze() [complex]`: np.squeeze of a matrix needs axis= (the result's rank would depend on its shape)
- `r = mr.squeeze() [empty]`: np.squeeze of a matrix needs axis= (the result's rank would depend on its shape)
- `r = mr.squeeze() [int]`: np.squeeze of a matrix needs axis= (the result's rank would depend on its shape)
- `r = mr.squeeze() [nan]`: np.squeeze of a matrix needs axis= (the result's rank would depend on its shape)
- `r = mr.squeeze() [one]`: np.squeeze of a matrix needs axis= (the result's rank would depend on its shape)
- `r = mr.squeeze() [ties]`: np.squeeze of a matrix needs axis= (the result's rank would depend on its shape)
- `y = m.copy(); z = y.reshape(-1); z[0] = 3; r = y [base]`: modifying 'z_0' in place also changes 'y_0' in numpy, because they share memory ('z_0' and 'y_0' are the same array or views of it, e.g. a slice, row, column, .
- `y = m.copy(); z = y.reshape(-1); z[0] = 3; r = y [complex]`: modifying 'z_0' in place also changes 'y_0' in numpy, because they share memory ('z_0' and 'y_0' are the same array or views of it, e.g. a slice, row, column, .
- `y = m.copy(); z = y.reshape(-1); z[0] = 3; r = y [int]`: modifying 'z_0' in place also changes 'y_0' in numpy, because they share memory ('z_0' and 'y_0' are the same array or views of it, e.g. a slice, row, column, .
- `y = m.copy(); z = y.reshape(-1); z[0] = 3; r = y [nan]`: modifying 'z_0' in place also changes 'y_0' in numpy, because they share memory ('z_0' and 'y_0' are the same array or views of it, e.g. a slice, row, column, .
- `y = m.copy(); z = y.reshape(-1); z[0] = 3; r = y [one]`: modifying 'z_0' in place also changes 'y_0' in numpy, because they share memory ('z_0' and 'y_0' are the same array or views of it, e.g. a slice, row, column, .
- `y = m.copy(); z = y.reshape(-1); z[0] = 3; r = y [ties]`: modifying 'z_0' in place also changes 'y_0' in numpy, because they share memory ('z_0' and 'y_0' are the same array or views of it, e.g. a slice, row, column, .
- `y = x.copy(); z = y[::-1]; z[0] = 7; r = y [base]`: modifying 'z_0' in place also changes 'y_0' in numpy, because they share memory ('z_0' and 'y_0' are the same array or views of it, e.g. a slice, row, column, .
- `y = x.copy(); z = y[::-1]; z[0] = 7; r = y [complex]`: modifying 'z_0' in place also changes 'y_0' in numpy, because they share memory ('z_0' and 'y_0' are the same array or views of it, e.g. a slice, row, column, .
- `y = x.copy(); z = y[::-1]; z[0] = 7; r = y [int]`: modifying 'z_0' in place also changes 'y_0' in numpy, because they share memory ('z_0' and 'y_0' are the same array or views of it, e.g. a slice, row, column, .
- `y = x.copy(); z = y[::-1]; z[0] = 7; r = y [nan]`: modifying 'z_0' in place also changes 'y_0' in numpy, because they share memory ('z_0' and 'y_0' are the same array or views of it, e.g. a slice, row, column, .
- `y = x.copy(); z = y[::-1]; z[0] = 7; r = y [one]`: modifying 'z_0' in place also changes 'y_0' in numpy, because they share memory ('z_0' and 'y_0' are the same array or views of it, e.g. a slice, row, column, .
- `y = x.copy(); z = y[::-1]; z[0] = 7; r = y [ties]`: modifying 'z_0' in place also changes 'y_0' in numpy, because they share memory ('z_0' and 'y_0' are the same array or views of it, e.g. a slice, row, column, .

## Known differences

- `r = np.unravel_index(np.argsort(mr, axis=None), mr.shape)[1] [3d]` (DIFF): the order of ties: numpy's default sort is not stable (the translation's is)
- `r = np.unravel_index(np.argsort(mr, axis=None), mr.shape)[1] [base]` (DIFF): the order of ties: numpy's default sort is not stable (the translation's is)
- `r = np.unravel_index(np.argsort(mr, axis=None), mr.shape)[1] [int]` (DIFF): the order of ties: numpy's default sort is not stable (the translation's is)
- `r = np.unravel_index(np.argsort(mr, axis=None), mr.shape)[1] [ties]` (DIFF): the order of ties: numpy's default sort is not stable (the translation's is)
- `r = xi.argsort() [ties]` (DIFF): the order of ties: numpy's default sort is not stable (the translation's is)
