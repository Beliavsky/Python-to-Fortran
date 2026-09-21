# Original solver and matrix-vector routines from Burkardt (MIT license).
# Functions are unchanged; only the deterministic driver is new.
def tridiagonal_mv ( a, b, c, x ):

#*****************************************************************************80
#
## tridiagonal_mv() multiplies a tridiagonal matrix times a vector.
#
#  Discussion:
#
#    There are M rows in the matrix, but at most three nonzero entries.
#    The subdiagonal is stored in A, the diagonal in B, the superdiagonal in C.
#
#    | b(1)    c(1)    ....  ....    ....    ....   |
#    | a(2)    b(2)    c(2)  ....    ....    ....   |
#    | ....    a(3)    b(3)  c(3)    ....    ....   |
#    | ....    ....    ....  ......  ....    ....   |
#    | ....    ....    ....  a(n-1)  b(n-1)  c(n-1) |
#    | ....    ....    ....  ......  a(n)    b(n)   |
#
#  Licensing:
#
#    This code is distributed under the MIT license.
#
#  Modified:
#
#    15 October 2022
#
#  Author:
#
#    John Burkardt
#
#  Reference:
#
#    https://en.wikipedia.org/wiki/Tridiagonal_matrix_algorithm
#
#  Input:
#
#    real A(N), B(N), C(N), the matrix entries.
#    A(1) and C(N) are not used.
#
#    real X(N,:), the vector to be multiplied.
#
#  Output:
#
#    real RHS(N,:), the product.
#
  import numpy as np

  if ( x.ndim == 1 ):
    x = np.atleast_2d ( x )
    x = x.T

  m, n = x.shape

  rhs = np.zeros ( [ m, n ] )

  for j in range ( 0, n ):
    rhs[0:m,j]   =                b[0:m]   * x[0:m,j]
    rhs[1:m,j]   = rhs[1:m,j]   + a[1:m]   * x[0:m-1,j]
    rhs[0:m-1,j] = rhs[0:m-1,j] + c[0:m-1] * x[1:m,j] 

  return rhs

def tridiagonal_solver ( a, b, c, d ):

#*****************************************************************************80
#
## tridiagonal_solver() solves a tridiagonal linear system.
#
#  Discussion:
#
#    There are N equations in a tridiagonal system.
#
#    Equation 1 is:
#                      b(1) * x(1) + c(1) * x(2)   = d(1)
#    Equation i, for 1 < i < n, is:
#      a(i) * x(i-1) + b(i) * x(i) + c(i) * x(i+1) = d(i)
#    Equation N is:
#      a(n) * x(n-1) + b(n) * x(n)                 = d(n)
#
#  Licensing:
#
#    This code is distributed under the MIT license.
#
#  Modified:
#
#    15 October 2022
#
#  Author:
#
#    John Burkardt
#
#  Reference:
#
#    https://en.wikipedia.org/wiki/Tridiagonal_matrix_algorithm
#
#  Input:
#
#    real A(N), B(N), C(N), the matrix entries.
#    A(1) and C(N) are not used.
#
#    real D(N), the right hand side.
#
#  Output:
#
#    real X(N), the solution.
#
  import numpy as np

# if ( d.ndim == 1 ):
#   d = np.atleast_2d ( d )
#   d = d.T

# m, n = d.shape
  m = len ( d )

  for i in range ( 1, m ):
    s = a[i] / b[i-1]
    b[i] = b[i] - s * c[i-1]
    d[i] = d[i] - s * d[i-1]

  x = d.copy()

  for i in range ( m - 1, -1, -1 ):

    if ( b[i] == 0.0 ):
      print ( '' )
      print ( 'tridiagonal_solver(): Fatal error!' )
      print ( '  b(', i, ') = 0' )
      raise Exception ( 'tridiagonal_solver(): Fatal error!' )

    if ( i == m - 1 ):
      x[i] = x[i] / b[i]
    else:
      x[i] = ( x[i] - c[i] * x[i+1] ) / b[i]

  return x

def exercise(m):
    import numpy as np
    a = np.full(m, -0.75)
    b = np.full(m, 4.0)
    c = np.full(m, 0.5)
    exact = np.zeros([m, 2])
    for i in range(m):
        b[i] = b[i] + 0.125 * i
        exact[i, 0] = 0.25 * i - 1.0
        exact[i, 1] = i + 1.0
        if i % 2 != 0:
            exact[i, 1] = -exact[i, 1]
    rhs = tridiagonal_mv(a, b, c, exact)
    d1 = rhs[:, 0].copy()
    d2 = rhs.copy()
    b1 = b.copy()
    b2 = b.copy()
    x1 = tridiagonal_solver(a, b1, c, d1)
    x2 = tridiagonal_solver(a, b2, c, d2)
    for i in range(m):
        print('vector', m, i, x1[i])
        for j in range(2):
            print('rhs', m, i, j, rhs[i, j])
            print('matrix', m, i, j, x2[i, j])

exercise(1)
exercise(2)
exercise(5)
exercise(9)
