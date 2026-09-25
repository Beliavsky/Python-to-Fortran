def gauss_plu ( A, wait = 0 ):

#*****************************************************************************80
#
## gauss_plu() uses Gauss eliminiation to find the PLU factors of a matrix.
#
#  Discussion:
#
#    The desired factorization is A = P' * L * U
#    * P is a permutation matrix
#    * L is a unit lower triangular matrix
#    * U is an upper triangular matrix.
#
#  Licensing:
#
#    This code is distributed under the MIT license.
#
#  Modified:
#
#    14 September 2022
#
#  Author:
#
#    John Burkardt
#
#  Input:
#
#    real A(m,n), the system matrix.
#
#    logical wait:
#    0: no extra printout
#    1: extra printout, but no pause.
#    2: extra printout, and pausing.
#
#  Output:
#
#    global real P(m,m), L(m,m), U(m,n), the PLU factors.
#
  import numpy as np

  m, n = A.shape
#
#  PLU initialize.
#
  P = np.identity ( m )
  L = np.identity ( m )
  U = A.copy()

  info = 0

  for j in range ( 0, n - 1 ):
#
#  Choose the pivot row P for variable J.
#
    p = np.argmax ( np.abs ( U[j:n,j] ) )
    p = p + j - 1

    if ( U[p,j] == 0.0 ):
      continue
#
#  Swap rows P and J.
#
    if ( p != j ):
      T      = P[j,:].copy()
      P[j,:] = P[p,:]
      P[p,:] = T

      T      = U[j,:].copy()
      U[j,:] = U[p,:]
      U[p,:] = T

      T        = L[j,1:j].copy()
      L[j,1:j] = L[p,1:j]
      L[p,1:j] = T
#
#  Eliminate U(i,j), and store multiplier in L(i,j).
#
    for i in range ( j + 1, n ):
      s = U[i,j] / U[j,j]
      U[i,:] = U[i,:] - s * U[j,:]
      U[i,j] = 0.0
      L[i,j] = s
#
#  Show that it's still true that P' * L * U = A.
#
    if ( 0 < wait ):
      print ( '' )
      print ( '  After processing column ', j )
      print ( '' )
      print ( '  P:' )
      print ( '' )
      print ( P )
      print ( '' )
      print ( '  L:' )
      print ( '' )
      print ( L )
      print ( '' )
      print ( '  U:' )
      print ( '' )
      print ( U )
      t = np.linalg.norm ( A - np.matmul ( P.T, np.matmul ( L, U ) ) )
      print ( '  |A-P\'*L*U| = ', t )
      if ( 1 < wait ):
        input ( )

  return P, L, U

import numpy as np
A = np.array([[1.0, 2.0, 3.0], [4.0, 5.0, 8.0], [7.0, 8.0, 9.0]])
P, L, U = gauss_plu(A)
print(np.linalg.norm(A - P.T @ L @ U))
print(P)
