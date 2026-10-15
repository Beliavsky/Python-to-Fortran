# numpy coverage probe: methods, operators, indexing

6021 cases.

| status | count |
|---|---|
| DIFF | 4 |
| KIND | 8 |
| BUILD-FAIL | 97 |
| XLATE-FAIL | 62 |
| MATCH | 5850 |

## BUILD-FAIL

- `r = abs(b) [base]`: 'a' argument of 'abs' intrinsic at (1) must have a numeric type
- `r = abs(b) [empty]`: 'a' argument of 'abs' intrinsic at (1) must have a numeric type
- `r = abs(b) [int]`: 'a' argument of 'abs' intrinsic at (1) must have a numeric type
- `r = abs(b) [nan]`: 'a' argument of 'abs' intrinsic at (1) must have a numeric type
- `r = abs(b) [one]`: 'a' argument of 'abs' intrinsic at (1) must have a numeric type
- `r = abs(b) [ties]`: 'a' argument of 'abs' intrinsic at (1) must have a numeric type
- `r = abs(xi > 2) [base]`: 'a' argument of 'abs' intrinsic at (1) must have a numeric type
- `r = abs(xi > 2) [empty]`: 'a' argument of 'abs' intrinsic at (1) must have a numeric type
- `r = abs(xi > 2) [int]`: 'a' argument of 'abs' intrinsic at (1) must have a numeric type
- `r = abs(xi > 2) [nan]`: 'a' argument of 'abs' intrinsic at (1) must have a numeric type
- `r = abs(xi > 2) [one]`: 'a' argument of 'abs' intrinsic at (1) must have a numeric type
- `r = abs(xi > 2) [ties]`: 'a' argument of 'abs' intrinsic at (1) must have a numeric type
- `r = b % b [empty]`: 'a' argument of 'modulo' intrinsic at (1) must be INTEGER or REAL
- `r = b % b [one]`: 'a' argument of 'modulo' intrinsic at (1) must be INTEGER or REAL
- `r = b * b [base]`: Operands of binary numeric operator '*' at (1) are LOGICAL(4)/LOGICAL(4)
- `r = b * b [empty]`: Operands of binary numeric operator '*' at (1) are LOGICAL(4)/LOGICAL(4)
- `r = b * b [int]`: Operands of binary numeric operator '*' at (1) are LOGICAL(4)/LOGICAL(4)
- `r = b * b [nan]`: Operands of binary numeric operator '*' at (1) are LOGICAL(4)/LOGICAL(4)
- `r = b * b [one]`: Operands of binary numeric operator '*' at (1) are LOGICAL(4)/LOGICAL(4)
- `r = b * b [ties]`: Operands of binary numeric operator '*' at (1) are LOGICAL(4)/LOGICAL(4)
- `r = b ** b [base]`: Operands of binary numeric operator '**' at (1) are LOGICAL(4)/LOGICAL(4)
- `r = b ** b [empty]`: Operands of binary numeric operator '**' at (1) are LOGICAL(4)/LOGICAL(4)
- `r = b ** b [int]`: Operands of binary numeric operator '**' at (1) are LOGICAL(4)/LOGICAL(4)
- `r = b ** b [nan]`: Operands of binary numeric operator '**' at (1) are LOGICAL(4)/LOGICAL(4)
- `r = b ** b [one]`: Operands of binary numeric operator '**' at (1) are LOGICAL(4)/LOGICAL(4)
- `r = b ** b [ties]`: Operands of binary numeric operator '**' at (1) are LOGICAL(4)/LOGICAL(4)
- `r = b + b [base]`: Operands of binary numeric operator '+' at (1) are LOGICAL(4)/LOGICAL(4)
- `r = b + b [empty]`: Operands of binary numeric operator '+' at (1) are LOGICAL(4)/LOGICAL(4)
- `r = b + b [int]`: Operands of binary numeric operator '+' at (1) are LOGICAL(4)/LOGICAL(4)
- `r = b + b [nan]`: Operands of binary numeric operator '+' at (1) are LOGICAL(4)/LOGICAL(4)
- `r = b + b [one]`: Operands of binary numeric operator '+' at (1) are LOGICAL(4)/LOGICAL(4)
- `r = b + b [ties]`: Operands of binary numeric operator '+' at (1) are LOGICAL(4)/LOGICAL(4)
- `r = b / b [empty]`: 'a' argument of 'real' intrinsic at (1) must have a numeric type
- `r = b / b [one]`: 'a' argument of 'real' intrinsic at (1) must have a numeric type
- `r = b // b [empty]`: Type mismatch in argument 'x' at (1); passed LOGICAL(4) to INTEGER(4)
- `r = b // b [one]`: Type mismatch in argument 'x' at (1); passed LOGICAL(4) to INTEGER(4)
- `r = b @ b [base]`: Cannot convert LOGICAL(4) to REAL(8) at (1)
- `r = b @ b [empty]`: Cannot convert LOGICAL(4) to REAL(8) at (1)
- `r = b @ b [int]`: Cannot convert LOGICAL(4) to REAL(8) at (1)
- `r = b @ b [nan]`: Cannot convert LOGICAL(4) to REAL(8) at (1)
- `r = b @ b [one]`: Cannot convert LOGICAL(4) to REAL(8) at (1)
- `r = b @ b [ties]`: Cannot convert LOGICAL(4) to REAL(8) at (1)
- `r = b.clip(0, 2) [base]`: 'a1' argument of 'max' intrinsic at (1) must be INTEGER, REAL or CHARACTER
- `r = b.clip(0, 2) [empty]`: 'a1' argument of 'max' intrinsic at (1) must be INTEGER, REAL or CHARACTER
- `r = b.clip(0, 2) [int]`: 'a1' argument of 'max' intrinsic at (1) must be INTEGER, REAL or CHARACTER
- `r = b.clip(0, 2) [nan]`: 'a1' argument of 'max' intrinsic at (1) must be INTEGER, REAL or CHARACTER
- `r = b.clip(0, 2) [one]`: 'a1' argument of 'max' intrinsic at (1) must be INTEGER, REAL or CHARACTER
- `r = b.clip(0, 2) [ties]`: 'a1' argument of 'max' intrinsic at (1) must be INTEGER, REAL or CHARACTER
- `r = b.clip(min=0) [base]`: 'a1' argument of 'max' intrinsic at (1) must be INTEGER, REAL or CHARACTER
- `r = b.clip(min=0) [empty]`: 'a1' argument of 'max' intrinsic at (1) must be INTEGER, REAL or CHARACTER
- `r = b.clip(min=0) [int]`: 'a1' argument of 'max' intrinsic at (1) must be INTEGER, REAL or CHARACTER
- `r = b.clip(min=0) [nan]`: 'a1' argument of 'max' intrinsic at (1) must be INTEGER, REAL or CHARACTER
- `r = b.clip(min=0) [one]`: 'a1' argument of 'max' intrinsic at (1) must be INTEGER, REAL or CHARACTER
- `r = b.clip(min=0) [ties]`: 'a1' argument of 'max' intrinsic at (1) must be INTEGER, REAL or CHARACTER
- `r = b.round() [base]`: 'a' argument of 'real' intrinsic at (1) must have a numeric type
- `r = b.round() [empty]`: 'a' argument of 'real' intrinsic at (1) must have a numeric type
- `r = b.round() [int]`: 'a' argument of 'real' intrinsic at (1) must have a numeric type
- `r = b.round() [nan]`: 'a' argument of 'real' intrinsic at (1) must have a numeric type
- `r = b.round() [one]`: 'a' argument of 'real' intrinsic at (1) must have a numeric type
- `r = b.round() [ties]`: 'a' argument of 'real' intrinsic at (1) must have a numeric type
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
- `y = b.copy(); y.sort(); r = y [base]`: There is no specific subroutine for the generic 'sort_vec' at (1)
- `y = b.copy(); y.sort(); r = y [empty]`: There is no specific subroutine for the generic 'sort_vec' at (1)
- `y = b.copy(); y.sort(); r = y [int]`: There is no specific subroutine for the generic 'sort_vec' at (1)
- `y = b.copy(); y.sort(); r = y [nan]`: There is no specific subroutine for the generic 'sort_vec' at (1)
- `y = b.copy(); y.sort(); r = y [one]`: There is no specific subroutine for the generic 'sort_vec' at (1)
- `y = b.copy(); y.sort(); r = y [ties]`: There is no specific subroutine for the generic 'sort_vec' at (1)
- `y = m.copy(); y.T[0] = 4; r = y [base]`: Unclassifiable statement at (1)
- `y = m.copy(); y.T[0] = 4; r = y [empty]`: Unclassifiable statement at (1)
- `y = m.copy(); y.T[0] = 4; r = y [int]`: Unclassifiable statement at (1)
- `y = m.copy(); y.T[0] = 4; r = y [nan]`: Unclassifiable statement at (1)
- `y = m.copy(); y.T[0] = 4; r = y [one]`: Unclassifiable statement at (1)
- `y = m.copy(); y.T[0] = 4; r = y [ties]`: Unclassifiable statement at (1)
- `y = mr.copy(); y.T[0] = 4; r = y [base]`: Unclassifiable statement at (1)
- `y = mr.copy(); y.T[0] = 4; r = y [int]`: Unclassifiable statement at (1)
- `y = mr.copy(); y.T[0] = 4; r = y [nan]`: Unclassifiable statement at (1)
- `y = mr.copy(); y.T[0] = 4; r = y [one]`: Unclassifiable statement at (1)
- `y = mr.copy(); y.T[0] = 4; r = y [ties]`: Unclassifiable statement at (1)
- `y = x.copy(); y[xi % 4] = 2; r = y [base]`: Elements with the same value at (1) and (2) in vector subscript in a variable definition context (assignment)
- `y = x.copy(); y[xi % 4] = 2; r = y [int]`: Elements with the same value at (1) and (2) in vector subscript in a variable definition context (assignment)
- `y = x.copy(); y[xi % 4] = 2; r = y [nan]`: Elements with the same value at (1) and (2) in vector subscript in a variable definition context (assignment)
- `y = x.copy(); y[xi % 4] = 2; r = y [ties]`: Elements with the same value at (1) and (2) in vector subscript in a variable definition context (assignment)
- `y = xi.copy(); y[xi % 4] = 2; r = y [base]`: Elements with the same value at (1) and (2) in vector subscript in a variable definition context (assignment)
- `y = xi.copy(); y[xi % 4] = 2; r = y [int]`: Elements with the same value at (1) and (2) in vector subscript in a variable definition context (assignment)
- `y = xi.copy(); y[xi % 4] = 2; r = y [nan]`: Elements with the same value at (1) and (2) in vector subscript in a variable definition context (assignment)
- `y = xi.copy(); y[xi % 4] = 2; r = y [ties]`: Elements with the same value at (1) and (2) in vector subscript in a variable definition context (assignment)

## XLATE-FAIL

- `r = m.squeeze() [nan]`: np.squeeze of a matrix needs axis= (the result's rank would depend on its shape)
- `r = m.squeeze() [ties]`: np.squeeze of a matrix needs axis= (the result's rank would depend on its shape)
- `r = m[..., 0] [base]`: unsupported constant
- `r = m[..., 0] [empty]`: unsupported constant
- `r = m[..., 0] [int]`: unsupported constant
- `r = m[..., 0] [nan]`: unsupported constant
- `r = m[..., 0] [one]`: unsupported constant
- `r = m[..., 0] [ties]`: unsupported constant
- `r = m[0, ...] [base]`: unsupported constant
- `r = m[0, ...] [int]`: unsupported constant
- `r = m[0, ...] [nan]`: unsupported constant
- `r = m[0, ...] [one]`: unsupported constant
- `r = m[0, ...] [ties]`: unsupported constant
- `r = m[:, [True, False]] [base]`: unsupported expr: Slice
- `r = m[:, [True, False]] [empty]`: unsupported expr: Slice
- `r = m[:, [True, False]] [int]`: unsupported expr: Slice
- `r = m[:, [True, False]] [nan]`: unsupported expr: Slice
- `r = m[:, [True, False]] [ties]`: unsupported expr: Slice
- `r = mr.squeeze() [base]`: np.squeeze of a matrix needs axis= (the result's rank would depend on its shape)
- `r = mr.squeeze() [empty]`: np.squeeze of a matrix needs axis= (the result's rank would depend on its shape)
- `r = mr.squeeze() [int]`: np.squeeze of a matrix needs axis= (the result's rank would depend on its shape)
- `r = mr.squeeze() [nan]`: np.squeeze of a matrix needs axis= (the result's rank would depend on its shape)
- `r = mr.squeeze() [one]`: np.squeeze of a matrix needs axis= (the result's rank would depend on its shape)
- `r = mr.squeeze() [ties]`: np.squeeze of a matrix needs axis= (the result's rank would depend on its shape)
- `r = mr[..., 0] [base]`: unsupported constant
- `r = mr[..., 0] [int]`: unsupported constant
- `r = mr[..., 0] [nan]`: unsupported constant
- `r = mr[..., 0] [one]`: unsupported constant
- `r = mr[..., 0] [ties]`: unsupported constant
- `r = mr[0, ...] [base]`: unsupported constant
- `r = mr[0, ...] [empty]`: unsupported constant
- `r = mr[0, ...] [int]`: unsupported constant
- `r = mr[0, ...] [nan]`: unsupported constant
- `r = mr[0, ...] [one]`: unsupported constant
- `r = mr[0, ...] [ties]`: unsupported constant
- `y = m.copy(); z = y.T; z[0, 1] = 8; r = y [base]`: modifying 'z_0' in place also changes 'y_0' in numpy, because they share memory ('z_0' and 'y_0' are the same array or views of it, e.g. a slice, row, column, .
- `y = m.copy(); z = y.T; z[0, 1] = 8; r = y [int]`: modifying 'z_0' in place also changes 'y_0' in numpy, because they share memory ('z_0' and 'y_0' are the same array or views of it, e.g. a slice, row, column, .
- `y = m.copy(); z = y.T; z[0, 1] = 8; r = y [nan]`: modifying 'z_0' in place also changes 'y_0' in numpy, because they share memory ('z_0' and 'y_0' are the same array or views of it, e.g. a slice, row, column, .
- `y = m.copy(); z = y.T; z[0, 1] = 8; r = y [ties]`: modifying 'z_0' in place also changes 'y_0' in numpy, because they share memory ('z_0' and 'y_0' are the same array or views of it, e.g. a slice, row, column, .
- `y = m.copy(); z = y.reshape(-1); z[0] = 3; r = y [base]`: modifying 'z_0' in place also changes 'y_0' in numpy, because they share memory ('z_0' and 'y_0' are the same array or views of it, e.g. a slice, row, column, .
- `y = m.copy(); z = y.reshape(-1); z[0] = 3; r = y [int]`: modifying 'z_0' in place also changes 'y_0' in numpy, because they share memory ('z_0' and 'y_0' are the same array or views of it, e.g. a slice, row, column, .
- `y = m.copy(); z = y.reshape(-1); z[0] = 3; r = y [nan]`: modifying 'z_0' in place also changes 'y_0' in numpy, because they share memory ('z_0' and 'y_0' are the same array or views of it, e.g. a slice, row, column, .
- `y = m.copy(); z = y.reshape(-1); z[0] = 3; r = y [one]`: modifying 'z_0' in place also changes 'y_0' in numpy, because they share memory ('z_0' and 'y_0' are the same array or views of it, e.g. a slice, row, column, .
- `y = m.copy(); z = y.reshape(-1); z[0] = 3; r = y [ties]`: modifying 'z_0' in place also changes 'y_0' in numpy, because they share memory ('z_0' and 'y_0' are the same array or views of it, e.g. a slice, row, column, .
- `y = m.copy(); z = y[0]; z[1] = 42; r = y [base]`: modifying 'z_0' in place also changes 'y_0' in numpy, because they share memory ('z_0' and 'y_0' are the same array or views of it, e.g. a slice, row, column, .
- `y = m.copy(); z = y[0]; z[1] = 42; r = y [int]`: modifying 'z_0' in place also changes 'y_0' in numpy, because they share memory ('z_0' and 'y_0' are the same array or views of it, e.g. a slice, row, column, .
- `y = m.copy(); z = y[0]; z[1] = 42; r = y [nan]`: modifying 'z_0' in place also changes 'y_0' in numpy, because they share memory ('z_0' and 'y_0' are the same array or views of it, e.g. a slice, row, column, .
- `y = m.copy(); z = y[0]; z[1] = 42; r = y [ties]`: modifying 'z_0' in place also changes 'y_0' in numpy, because they share memory ('z_0' and 'y_0' are the same array or views of it, e.g. a slice, row, column, .
- `y = x.copy(); z = y; z[0] = -5; r = y [base]`: modifying 'z_0' in place also changes 'y_0' in numpy, because they share memory ('z_0' and 'y_0' are the same array or views of it, e.g. a slice, row, column, .
- `y = x.copy(); z = y; z[0] = -5; r = y [int]`: modifying 'z_0' in place also changes 'y_0' in numpy, because they share memory ('z_0' and 'y_0' are the same array or views of it, e.g. a slice, row, column, .
- `y = x.copy(); z = y; z[0] = -5; r = y [nan]`: modifying 'z_0' in place also changes 'y_0' in numpy, because they share memory ('z_0' and 'y_0' are the same array or views of it, e.g. a slice, row, column, .
- `y = x.copy(); z = y; z[0] = -5; r = y [one]`: modifying 'z_0' in place also changes 'y_0' in numpy, because they share memory ('z_0' and 'y_0' are the same array or views of it, e.g. a slice, row, column, .
- `y = x.copy(); z = y; z[0] = -5; r = y [ties]`: modifying 'z_0' in place also changes 'y_0' in numpy, because they share memory ('z_0' and 'y_0' are the same array or views of it, e.g. a slice, row, column, .
- `y = x.copy(); z = y[1:3]; z[0] = 99; r = y [base]`: modifying 'z_0' in place also changes 'y_0' in numpy, because they share memory ('z_0' and 'y_0' are the same array or views of it, e.g. a slice, row, column, .
- `y = x.copy(); z = y[1:3]; z[0] = 99; r = y [int]`: modifying 'z_0' in place also changes 'y_0' in numpy, because they share memory ('z_0' and 'y_0' are the same array or views of it, e.g. a slice, row, column, .
- `y = x.copy(); z = y[1:3]; z[0] = 99; r = y [nan]`: modifying 'z_0' in place also changes 'y_0' in numpy, because they share memory ('z_0' and 'y_0' are the same array or views of it, e.g. a slice, row, column, .
- `y = x.copy(); z = y[1:3]; z[0] = 99; r = y [ties]`: modifying 'z_0' in place also changes 'y_0' in numpy, because they share memory ('z_0' and 'y_0' are the same array or views of it, e.g. a slice, row, column, .
- `y = x.copy(); z = y[::-1]; z[0] = 7; r = y [base]`: modifying 'z_0' in place also changes 'y_0' in numpy, because they share memory ('z_0' and 'y_0' are the same array or views of it, e.g. a slice, row, column, .
- `y = x.copy(); z = y[::-1]; z[0] = 7; r = y [int]`: modifying 'z_0' in place also changes 'y_0' in numpy, because they share memory ('z_0' and 'y_0' are the same array or views of it, e.g. a slice, row, column, .
- `y = x.copy(); z = y[::-1]; z[0] = 7; r = y [nan]`: modifying 'z_0' in place also changes 'y_0' in numpy, because they share memory ('z_0' and 'y_0' are the same array or views of it, e.g. a slice, row, column, .
- `y = x.copy(); z = y[::-1]; z[0] = 7; r = y [one]`: modifying 'z_0' in place also changes 'y_0' in numpy, because they share memory ('z_0' and 'y_0' are the same array or views of it, e.g. a slice, row, column, .
- `y = x.copy(); z = y[::-1]; z[0] = 7; r = y [ties]`: modifying 'z_0' in place also changes 'y_0' in numpy, because they share memory ('z_0' and 'y_0' are the same array or views of it, e.g. a slice, row, column, .

## Known differences

- `r = np.apply_along_axis(np.sort, 0, m) [int]` (KIND): one wrapper of a numpy function passed as an argument per program (real when real arrays use it too)
- `r = np.apply_along_axis(np.sort, 0, mr) [int]` (KIND): one wrapper of a numpy function passed as an argument per program (real when real arrays use it too)
- `r = np.apply_along_axis(np.sort, 1, m) [int]` (KIND): one wrapper of a numpy function passed as an argument per program (real when real arrays use it too)
- `r = np.apply_along_axis(np.sort, 1, mr) [int]` (KIND): one wrapper of a numpy function passed as an argument per program (real when real arrays use it too)
- `r = np.apply_along_axis(np.sum, 0, m) [int]` (KIND): one wrapper of a numpy function passed as an argument per program (real when real arrays use it too)
- `r = np.apply_along_axis(np.sum, 0, mr) [int]` (KIND): one wrapper of a numpy function passed as an argument per program (real when real arrays use it too)
- `r = np.apply_along_axis(np.sum, 1, m) [int]` (KIND): one wrapper of a numpy function passed as an argument per program (real when real arrays use it too)
- `r = np.apply_along_axis(np.sum, 1, mr) [int]` (KIND): one wrapper of a numpy function passed as an argument per program (real when real arrays use it too)
- `r = np.unravel_index(np.argsort(mr, axis=None), mr.shape)[1] [base]` (DIFF): the order of ties: numpy's default sort is not stable (the translation's is)
- `r = np.unravel_index(np.argsort(mr, axis=None), mr.shape)[1] [int]` (DIFF): the order of ties: numpy's default sort is not stable (the translation's is)
- `r = np.unravel_index(np.argsort(mr, axis=None), mr.shape)[1] [ties]` (DIFF): the order of ties: numpy's default sort is not stable (the translation's is)
- `r = xi.argsort() [ties]` (DIFF): the order of ties: numpy's default sort is not stable (the translation's is)
