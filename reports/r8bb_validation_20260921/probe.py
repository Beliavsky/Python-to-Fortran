def r8bb_fa ( n1, n2, ml, mu, a ):

#*****************************************************************************80
#
## R8BB_FA factors a R8BB matrix.
#
#  Discussion:
#
#    Note that in C++ and FORTRAN, we can look at A as an abstract
#    vector, but then look at parts of A as storing a two dimensional
#    array.  MATLAB assigns an inherent dimensionality to a data object,
#    and gets very unhappy when you try to manipulate the data yourself.
#    This means that the MATLAB implementation of this routine requires
#    the use of temporary 2D arrays.
#
#    The R8BB storage format is for a border banded matrix.  Such a
#    matrix has the logical form:
#
#      A1 | A2
#      ---+---
#      A3 | A4
#
#    with A1 a (usually large) N1 by N1 banded matrix, while A2, A3 and A4
#    are dense rectangular matrices of orders N1 by N2, N2 by N1, and N2 by N2,
#    respectively.
#
#    A should be defined as a vector.  The user must then store
#    the entries of the four blocks of the matrix into the vector A.
#    Each block is stored by columns.
#
#    A1, the banded portion of the matrix, is stored in
#    the first (2*ML+MU+1)*N1 entries of A, using standard LINPACK
#    general band format.  The reason for the factor of 2 in front of
#    ML is to allocate space that may be required if pivoting occurs.
#
#    The following formulas should be used to determine how to store
#    the entry corresponding to row I and column J in the original matrix:
#
#    Entries of A1:
#
#      1 <= I <= N1, 1 <= J <= N1, (J-I) <= MU and (I-J) <= ML.
#
#      Store the I, J entry into location
#      (I-J+ML+MU+1)+(J-1)*(2*ML+MU+1).
#
#    Entries of A2:
#
#      1 <= I <= N1, N1+1 <= J <= N1+N2.
#
#      Store the I, J entry into location
#      (2*ML+MU+1)*N1+(J-N1-1)*N1+I.
#
#    Entries of A3:
#
#      N1+1 <= I <= N1+N2, 1 <= J <= n1.
#
#      Store the I, J entry into location
#      (2*ML+MU+1)*N1+N1*N2+(J-1)*N2+(I-N1).
#
#    Entries of A4:
#
#      N1+1 <= I <= N1+N2, N1+1 <= J <= N1+N2
#
#      Store the I, J entry into location
#      (2*ML+MU+1)*N1+N1*N2+(J-1)*N2+(I-N1).
#      (same formula used for A3).
#
#    Once the matrix has been factored by R8BB_FA, R8BB_SL may be called
#    to solve linear systems involving the matrix.
#
#    R8BB_FA uses LINPACK routines to carry out the factorization.
#
#
#    The linear system must be border banded, of the form:
#
#      ( A1 A2 ) (X1) = (B1)
#      ( A3 A4 ) (X2)   (B2)
#
#    where A1 is a (usually big) banded square matrix, A2 and A3 are
#    column and row strips which may be nonzero, and A4 is a dense
#    square matrix.
#
#    The algorithm rewrites the system as:
#
#         X1 + inv(A1) A2 X2 = inv(A1) B1
#
#      A3 X1 +         A4 X2 = B2
#
#    and then rewrites the second equation as
#
#      ( A4 - A3 inv(A1) A2 ) X2 = B2 - A3 inv(A1) B1
#
#  Licensing:
#
#    This code is distributed under the MIT license.
#
#  Modified:
#
#    14 July 2016
#
#  Author:
#
#    John Burkardt
#
#  Input:
#
#    integer N1, N2, the order of the banded and dense blocks.
#    N1 and N2 must be nonnegative, and at least one must be positive.
#
#    integer ML, MU, the lower and upper bandwidths.
#    ML and MU must be nonnegative and no greater than N1-1.
#
#    real A( (2*ML+MU+1)*N1 + 2*N1*N2 + N2*N2 ), the border-banded 
#    matrix to be factored.
#
#  Output:
#
#    real A_LU( (2*ML+MU+1)*N1 + 2*N1*N2 + N2*N2 ).
#    Information describing a partial factorization
#    of the original coefficient matrix.  This information is required
#    by R8BB_SL in order to solve linear systems associated with that
#    matrix.
#
#    integer PIVOT(N1+N2), contains pivoting information.
#
#    integer INFO, singularity flag.
#    0, no singularity detected.
#    nonzero, the factorization failed on the INFO-th step.
#
  import numpy as np

  nband = ( 2 * ml + mu + 1 ) * n1

  a_lu = a.copy ( )
  pivot = np.zeros ( n1 + n2, dtype = np.int32 )
#
#  Copy the (2*ML+MU+1 x N1 ) A1 band matrix out of A.
#
#  Factor the A1 band matrix, overwriting A1 by its factors.
#
  if ( 0 < n1 ):

    a1 = r8vec_to_r8gb ( n1, n1, ml, mu, a[0:nband] )

    a1_lu, pivot[0:n1], info = r8gb_fa ( n1, ml, mu, a1 )

    if ( info != 0 ):
      print ( '' )
      print ( 'R8BB_FA - Fatal error!' )
      print ( '  R8GB_FA returned INFO = %d' % ( info ) )
      print ( '  Factoring failed for column INFO.' )
      print ( '  The band matrix A1 is singular.' )
      print ( '  This algorithm cannot continue!' )
      raise Exception ( 'R8BB_FA(): Fatal error!' )

    a_lu[0:nband] = r8gb_to_r8vec ( n1, n1, ml, mu, a1_lu )

  if ( 0 < n1 and 0 < n2 ):
#
#  Solve A1 * x = -A2 for x, and overwrite A2 by the results.
#
    job = 0

    for j in range ( 0, n2 ):
      b2 = - a[nband+j*n1:nband+j*n1+n1]
      x2 = r8gb_sl ( n1, ml, mu, a1_lu, pivot, b2, job )
      a_lu[nband+j*n1:nband+j*n1+n1] = x2[0:n1]
#
#  A4 := A4 + A3 * A2.
#
    for i in range ( 0, n2 ):
      for j in range ( 0, n1 ):
        ij = nband + n1 * n2 + j * n2 + i
        for k in range ( 0, n2 ):
          ik = nband + 2 * n1 * n2 + k * n2 + i
          jk = nband + k * n1 + j
          temp = a_lu[ik]
          a_lu[ik] = a_lu[ik] + a_lu[ij] * a_lu[jk]
#
#  Factor A4.
#
  if ( 0 < n2 ):

    a4 = r8vec_to_r8ge ( n2, n2, a_lu[nband+2*n1*n2:nband+2*n1*n2+n2*n2] )

    a4_lu, pivot2, info = r8ge_fa ( n2, a4 )

    pivot[n1:n1+n2] = pivot2[0:n2]

    if ( info != 0 ):
      print ( '' )
      print ( 'R8BB_FA - Fatal error!' )
      print ( '  R8GE_FA returned INFO = %d' % (info ) )
      print ( '  This indicates singularity in column INFO.' )
      print ( '  of the A4 submatrix, which is column %d' % ( n1 + info ) )
      print ( '  of the full matrix.' )
      print ( '' )
      print ( '  It is possible that the full matrix is' )
      print ( '  nonsingular, but the algorithm R8BB_FA may' )
      print ( '  not be used for this matrix.' )
      exit ( )

    a_lu[nband+2*n1*n2:nband+2*n1*n2+n2*n2] = r8ge_to_r8vec ( n2, n2, a4_lu )

  return a_lu, pivot, info

def r8bb_get ( n1, n2, ml, mu, a, i, j ):

#*****************************************************************************80
#
## r8bb_get() returns an entry of a R8BB matrix.
#
#  Discussion:
#
#    The R8BB storage format is for a border banded matrix.  Such a
#    matrix has the logical form:
#
#      A1 | A2
#      ---+---
#      A3 | A4
#
#    with A1 a (usually large) N1 by N1 banded matrix, while A2, A3 and A4
#    are dense rectangular matrices of orders N1 by N2, N2 by N1, and N2 by N2,
#    respectively.
#
#    A should be defined as a vector.  The user must then store
#    the entries of the four blocks of the matrix into the vector A.
#    Each block is stored by columns.
#
#    A1, the banded portion of the matrix, is stored in
#    the first (2*ML+MU+1)*N1 entries of A, using standard LINPACK
#    general band format.  The reason for the factor of 2 in front of
#    ML is to allocate space that may be required if pivoting occurs.
#
#    The following formulas should be used to determine how to store
#    the entry corresponding to row I and column J in the original matrix:
#
#    Entries of A1:
#
#      1 <= I <= N1, 1 <= J <= N1, (J-I) <= MU and (I-J) <= ML.
#
#      Store the I, J entry into location
#      (I-J+ML+MU+1)+(J-1)*(2*ML+MU+1).
#
#    Entries of A2:
#
#      1 <= I <= N1, N1+1 <= J <= N1+N2.
#
#      Store the I, J entry into location
#      (2*ML+MU+1)*N1+(J-N1-1)*N1+I.
#
#    Entries of A3:
#
#      N1+1 <= I <= N1+N2, 1 <= J <= n1.
#
#      Store the I, J entry into location
#      (2*ML+MU+1)*N1+N1*N2+(J-1)*N2+(I-N1).
#
#    Entries of A4:
#
#      N1+1 <= I <= N1+N2, N1+1 <= J <= N1+N2
#
#      Store the I, J entry into location
#      (2*ML+MU+1)*N1+N1*N2+(J-1)*N2+(I-N1).
#      (same formula used for A3).
#
#  Licensing:
#
#    This code is distributed under the MIT license.
#
#  Modified:
#
#    12 July 2016
#
#  Author:
#
#    John Burkardt
#
#  Input:
#
#    integer N1, N2, the order of the banded and dense blocks.
#    N1 and N2 must be nonnegative, and at least one must be positive.
#    integer ML, MU, the lower and upper bandwidths.
#    ML and MU must be nonnegative, and no greater than N1-1.
#
#    real A((2*ML+MU+1)*N1+2*N1*N2+N2*N2), the R8BB matrix.
#
#    integer I, J, the row and column of the entry to be retrieved.
#
#  Output:
#
#    real VALUE, the value of the (I,J) entry.
#
  value = 0.0

  if ( i < 0 or n1 + n2 <= i ):
    print ( '' )
    print ( 'R8BB_GET - Fatal error!' )
    print ( '  Illegal input value of row index I = %d' % ( i ) )
    raise Exception ( 'R8BB_GET - Fatal error!' )

  if ( j < 0 or n1 + n2 <= j ):
    print ( '' )
    print ( 'R8BB_GET - Fatal error!' )
    print ( '  Illegal input value of colum index J = %d' % ( j ) )
    raise Exception ( 'R8BB_GET - Fatal error!' )
#
#  The A1 block of the matrix.
#
#  Check for out of band problems.
#
#  Normally, we would check the condition MU < (J-I), but the storage
#  format requires extra entries be set aside in case of pivoting, which
#  means that the condition becomes MU+ML < (J-I).
#
  if ( i < n1 and j < n1 ):

    if ( mu + ml < j - i or ml < i - j ):
      value = 0.0
      return value
    else:
      ij = ( i - j + ml + mu ) + j * ( 2 * ml + mu + 1 )
#
#  The A2 block of the matrix.
#
  elif ( i < n1 and n1 <= j ):
    ij = ( 2 * ml + mu + 1 ) * n1 + ( j - n1 ) * n1 + i
#
#  The A3 and A4 blocks of the matrix.
#
  elif ( n1 <= i ):
    ij = ( 2 * ml + mu + 1 ) * n1 + n2 * n1 + j * n2 + ( i - n1 )

  value = a[ij]

  return value

def r8bb_mtv ( n1, n2, ml, mu, a, x ):

#*****************************************************************************80
#
## R8BB_MTV multiplies a vector by a R8BB matrix.
#
#  Discussion:
#
#    The R8BB storage format is for a border banded matrix.  Such a
#    matrix has the logical form:
#
#      A1 | A2
#      ---+---
#      A3 | A4
#
#    with A1 a (usually large) N1 by N1 banded matrix, while A2, A3 and A4
#    are dense rectangular matrices of orders N1 by N2, N2 by N1, and N2 by N2,
#    respectively.
#
#    A should be defined as a vector.  The user must then store
#    the entries of the four blocks of the matrix into the vector A.
#    Each block is stored by columns.
#
#    A1, the banded portion of the matrix, is stored in
#    the first (2*ML+MU+1)*N1 entries of A, using standard LINPACK
#    general band format.  The reason for the factor of 2 in front of
#    ML is to allocate space that may be required if pivoting occurs.
#
#    The following formulas should be used to determine how to store
#    the entry corresponding to row I and column J in the original matrix:
#
#    Entries of A1:
#
#      1 <= I <= N1, 1 <= J <= N1, (J-I) <= MU and (I-J) <= ML.
#
#      Store the I, J entry into location
#      (I-J+ML+MU+1)+(J-1)*(2*ML+MU+1).
#
#    Entries of A2:
#
#      1 <= I <= N1, N1+1 <= J <= N1+N2.
#
#      Store the I, J entry into location
#      (2*ML+MU+1)*N1+(J-N1-1)*N1+I.
#
#    Entries of A3:
#
#      N1+1 <= I <= N1+N2, 1 <= J <= N1.
#
#      Store the I, J entry into location
#      (2*ML+MU+1)*N1+N1*N2+(J-1)*N2+(I-N1).
#
#    Entries of A4:
#
#      N1+1 <= I <= N1+N2, N1+1 <= J <= N1+N2
#
#      Store the I, J entry into location
#      (2*ML+MU+1)*N1+N1*N2+(J-1)*N2+(I-N1).
#      (same formula used for A3).
#
#  Licensing:
#
#    This code is distributed under the MIT license.
#
#  Modified:
#
#    12 July 2016
#
#  Author:
#
#    John Burkardt
#
#  Input:
#
#    integer N1, N2, the order of the banded and dense blocks
#    N1 and N2 must be nonnegative, and at least one must be positive.
#
#    integer ML, MU, the lower and upper bandwidths.
#    ML and MU must be nonnegative and no greater than N1-1.
#
#    real A((2*ML+MU+1)*N1 + 2*N1*N2 + N2*N2), the R8BB matrix.
#
#    real X(N1+N2), the vector to multiply A.
#
#  Output:
#
#    real B(N1+N2), the product X times A.
#
  import numpy as np
#
#  Initialize B.
#
  b = np.zeros ( n1 + n2 )
#
#  Multiply by A1.
#
  for i in range ( 0, n1 ):
    jlo = max ( i - ml, 0 )
    jhi = min ( i + mu, n1 - 1 )
    for j in range ( jlo, jhi + 1 ):
      aij = r8bb_get ( n1, n2, ml, mu, a, i, j )
      b[j] = b[j] + x[i] * aij
#
#  Multiply by A2.
#
  for i in range ( 0, n1 ):
    for j in range ( n1, n1 + n2 ):
      aij = r8bb_get ( n1, n2, ml, mu, a, i, j )
      b[j] = b[j] + x[i] * aij
#
#  Multiply by A3.
#
  for i in range ( n1, n1 + n2 ):
    for j in range ( 0, n1 ):
      aij = r8bb_get ( n1, n2, ml, mu, a, i, j )
      b[j] = b[j] + x[i] * aij
#
#  Multiply by A4.
#
  for i in range ( n1, n1 + n2 ):
    for j in range ( n1, n1 + n2 ):
      aij = r8bb_get ( n1, n2, ml, mu, a, i, j )
      b[j] = b[j] + x[i] * aij

  return b

def r8bb_mv ( n1, n2, ml, mu, a, x ):

#*****************************************************************************80
#
## R8BB_MV multiplies a R8BB matrix times a vector.
#
#  Discussion:
#
#    The R8BB storage format is for a border banded matrix.  Such a
#    matrix has the logical form:
#
#      A1 | A2
#      ---+---
#      A3 | A4
#
#    with A1 a (usually large) N1 by N1 banded matrix, while A2, A3 and A4
#    are dense rectangular matrices of orders N1 by N2, N2 by N1, and N2 by N2,
#    respectively.
#
#    A should be defined as a vector.  The user must then store
#    the entries of the four blocks of the matrix into the vector A.
#    Each block is stored by columns.
#
#    A1, the banded portion of the matrix, is stored in
#    the first (2*ML+MU+1)*N1 entries of A, using standard LINPACK
#    general band format.  The reason for the factor of 2 in front of
#    ML is to allocate space that may be required if pivoting occurs.
#
#    The following formulas should be used to determine how to store
#    the entry corresponding to row I and column J in the original matrix:
#
#    Entries of A1:
#
#      1 <= I <= N1, 1 <= J <= N1, (J-I) <= MU and (I-J) <= ML.
#
#      Store the I, J entry into location
#      (I-J+ML+MU+1)+(J-1)*(2*ML+MU+1).
#
#    Entries of A2:
#
#      1 <= I <= N1, N1+1 <= J <= N1+N2.
#
#      Store the I, J entry into location
#      (2*ML+MU+1)*N1+(J-N1-1)*N1+I.
#
#    Entries of A3:
#
#      N1+1 <= I <= N1+N2, 1 <= J <= n1.
#
#      Store the I, J entry into location
#      (2*ML+MU+1)*N1+N1*N2+(J-1)*N2+(I-N1).
#
#    Entries of A4:
#
#      N1+1 <= I <= N1+N2, N1+1 <= J <= N1+N2
#
#      Store the I, J entry into location
#      (2*ML+MU+1)*N1+N1*N2+(J-1)*N2+(I-N1).
#      (same formula used for A3).
#
#  Licensing:
#
#    This code is distributed under the MIT license.
#
#  Modified:
#
#    12 July 2016
#
#  Author:
#
#    John Burkardt
#
#  Input:
#
#    integer N1, N2, the order of the banded and dense blocks
#    N1 and N2 must be nonnegative, and at least one must be positive.
#
#    integer ML, MU, the lower and upper bandwidths.
#    ML and MU must be nonnegative and no greater than N1-1.
#
#    real A((2*ML+MU+1)*N1+2*N1*N2+N2*N2), the R8BB matrix.
#
#    real X(N1+N2), the vector to be multiplied by A.
#
#  Output:
#
#    real B(N1+N2), the result of multiplying A by X.
#
  import numpy as np
#
#  Initialize B.
#
  b = np.zeros ( n1 + n2 )
#
#  Multiply by A1.
#
  for i in range ( 0, n1 ):
    jlo = max ( i - ml, 0 )
    jhi = min ( i + mu, n1 - 1 )
    for j in range ( jlo, jhi + 1 ):
      aij = r8bb_get ( n1, n2, ml, mu, a, i, j )
      b[i] = b[i] + aij * x[j]
#
#  Multiply by A2.
#
  for i in range ( 0, n1 ):
    for j in range ( n1, n1 + n2 ):
      aij = r8bb_get ( n1, n2, ml, mu, a, i, j )
      b[i] = b[i] + aij * x[j]
#
#  Multiply by A3.
#
  for i in range ( n1, n1 + n2 ):
    for j in range ( 0, n1 ):
      aij = r8bb_get ( n1, n2, ml, mu, a, i, j )
      b[i] = b[i] + aij * x[j]
#
#  Multiply by A4.
#
  for i in range ( n1, n1 + n2 ):
    for j in range ( n1, n1 + n2 ):
      aij = r8bb_get ( n1, n2, ml, mu, a, i, j )
      b[i] = b[i] + aij * x[j]

  return b

def r8bb_sl ( n1, n2, ml, mu, a_lu, pivot, b ):

#*****************************************************************************80
#
## R8BB_SL solves a R8BB system factored by R8BB_FA.
#
#  Discussion:
#
#    Note that in C++ and FORTRAN, we can look at A as an abstract
#    vector, but then look at parts of A as storing a two dimensional
#    array.  MATLAB assigns an inherent dimensionality to a data object,
#    and gets very unhappy when you try to manipulate the data yourself.
#    This means that the MATLAB implementation of this routine requires
#    the use of temporary 2D arrays.
#
#    The R8BB storage format is for a border banded matrix.  Such a
#    matrix has the logical form:
#
#      A1 | A2
#      ---+---
#      A3 | A4
#
#    with A1 a (usually large) N1 by N1 banded matrix, while A2, A3 and A4
#    are dense rectangular matrices of orders N1 by N2, N2 by N1, and N2 by N2,
#    respectively.
#
#    A should be defined as a vector.  The user must then store
#    the entries of the four blocks of the matrix into the vector A.
#    Each block is stored by columns.
#
#    A1, the banded portion of the matrix, is stored in
#    the first (2*ML+MU+1)*N1 entries of A, using standard LINPACK
#    general band format.  The reason for the factor of 2 in front of
#    ML is to allocate space that may be required if pivoting occurs.
#
#    The following formulas should be used to determine how to store
#    the entry corresponding to row I and column J in the original matrix:
#
#    Entries of A1:
#
#      1 <= I <= N1, 1 <= J <= N1, (J-I) <= MU and (I-J) <= ML.
#
#      Store the I, J entry into location
#      (I-J+ML+MU+1)+(J-1)*(2*ML+MU+1).
#
#    Entries of A2:
#
#      1 <= I <= N1, N1+1 <= J <= N1+N2.
#
#      Store the I, J entry into location
#      (2*ML+MU+1)*N1+(J-N1-1)*N1+I.
#
#    Entries of A3:
#
#      N1+1 <= I <= N1+N2, 1 <= J <= N1.
#
#      Store the I, J entry into location
#      (2*ML+MU+1)*N1+N1*N2+(J-1)*N2+(I-N1).
#
#    Entries of A4:
#
#      N1+1 <= I <= N1+N2, N1+1 <= J <= N1+N2
#
#      Store the I, J entry into location
#      (2*ML+MU+1)*N1+N1*N2+(J-1)*N2+(I-N1).
#      (same formula used for A3).
#
#    The linear system A * x = b is decomposable into the block system:
#
#      ( A1 A2 ) * (X1) = (B1)
#      ( A3 A4 )   (X2)   (B2)
#
#    All the arguments except B are input quantities only, which are
#    not changed by the routine.  They should have exactly the same values
#    they had on exit from R8BB_FA.
#
#    If more than one right hand side is to be solved, with the same matrix,
#    R8BB_SL should be called repeatedly.  However, R8BB_FA only needs to be
#    called once to create the factorization.
#
#  Licensing:
#
#    This code is distributed under the MIT license.
#
#  Modified:
#
#    12 July 2016
#
#  Author:
#
#    John Burkardt
#
#  Input:
#
#    integer N1, N2, the order of the banded and dense blocks.
#    N1 and N2 must be nonnegative, and at least one must be positive.
#
#    integer ML, MU, the lower and upper bandwidths.
#    ML and MU must be nonnegative and no greater than N1-1.
#
#    real A_LU( (2*ML+MU+1)*N1 + 2*N1*N2 + N2*N2), the factor information
#    computed by R8BB_FA.
#
#    integer PIVOT(N1+N2), the pivoting information from R8BB_FA.
#
#    real B(N1+N2), the right hand side of the linear system.
#
#  Output:
#
#    real X(N1+N2), the solution.
#
  import numpy as np

  x = np.zeros ( n1 + n2 )

  nband = ( 2 * ml + mu + 1 ) * n1
#
#  Set B1 := inverse(A1) * B1.
#  Copy the banded matrix out of A_LU and into A1_LU.
#
  if ( 0 < n1 ):

    a1_lu = r8vec_to_r8gb ( n1, n1, ml, mu, a_lu[0:nband] )

    job = 0

    x[0:n1] = r8gb_sl ( n1, ml, mu, a1_lu, pivot[0:n1], b[0:n1], job )
#
#  Modify the right hand side of the second linear subsystem.
#  Set B2 := B2 - A3*B1.
#
  for i in range ( 0, n2 ):
    for j in range ( 0, n1 ):
      ij = nband + n1 * n2 + j * n2 + i
      b[n1+i] = b[n1+i] - a_lu[ij] * x[j]
#
#  Set B2 := inverse(A4) * B2.
#  Copy the dense matrix out of A_LU and into A4_LU.
#
  if ( 0 < n2 ):

    a4_lu = r8vec_to_r8ge ( n2, n2, a_lu[nband+2*n1*n2:nband+2*n1*n2+n2*n2] )

    job = 0
    x[n1:n1+n2] = r8ge_sl ( n2, a4_lu, pivot[n1:n1+n2], b[n1:n1+n2], job )
#
#  Modify the first subsolution.
#  Set B1 := B1 + A2*B2.
#
  for i in range ( 0, n1 ):
    for j in range ( 0, n2 ):
      ij = nband + j * n1 + i
      x[i] = x[i] + a_lu[ij] * x[n1+j]

  return x

def r8bb_to_r8ge ( n1, n2, ml, mu, a ):

#*****************************************************************************80
#
## R8BB_TO_R8GE copies a R8BB matrix to a R8GE matrix.
#
#  Discussion:
#
#    The R8BB storage format is for a border banded matrix.  Such a
#    matrix has the logical form:
#
#      A1 | A2
#      ---+---
#      A3 | A4
#
#    with A1 a (usually large) N1 by N1 banded matrix, while A2, A3 and A4
#    are dense rectangular matrices of orders N1 by N2, N2 by N1, and N2 by N2,
#    respectively.
#
#    A should be defined as a vector.  The user must then store
#    the entries of the four blocks of the matrix into the vector A.
#    Each block is stored by columns.
#
#    A1, the banded portion of the matrix, is stored in
#    the first (2*ML+MU+1)*N1 entries of A, using standard LINPACK
#    general band format.  The reason for the factor of 2 in front of
#    ML is to allocate space that may be required if pivoting occurs.
#
#    The following formulas should be used to determine how to store
#    the entry corresponding to row I and column J in the original matrix:
#
#    Entries of A1:
#
#      1 <= I <= N1, 1 <= J <= N1, (J-I) <= MU and (I-J) <= ML.
#
#      Store the I, J entry into location
#      (I-J+ML+MU+1)+(J-1)*(2*ML+MU+1).
#
#    Entries of A2:
#
#      1 <= I <= N1, N1+1 <= J <= N1+N2.
#
#      Store the I, J entry into location
#      (2*ML+MU+1)*N1+(J-N1-1)*N1+I.
#
#    Entries of A3:
#
#      N1+1 <= I <= N1+N2, 1 <= J <= n1.
#
#      Store the I, J entry into location
#      (2*ML+MU+1)*N1+N1*N2+(J-1)*N2+(I-N1).
#
#    Entries of A4:
#
#      N1+1 <= I <= N1+N2, N1+1 <= J <= N1+N2
#
#      Store the I, J entry into location
#      (2*ML+MU+1)*N1+N1*N2+(J-1)*N2+(I-N1).
#      (same formula used for A3).
#
#  Licensing:
#
#    This code is distributed under the MIT license.
#
#  Modified:
#
#    12 July 2016
#
#  Author:
#
#    John Burkardt
#
#  Input:
#
#    integer N1, N2, the order of the banded and dense blocks.
#    N1 and N2 must be nonnegative, and at least one must be positive.
#
#    integer ML, MU, the lower and upper bandwidths.
#    ML and MU must be nonnegative, and no greater than N1-1.
#
#    real A((2*ML+MU+1)*N1+2*N1*N2+N2*N2), the R8BB matrix.
#
#  Output:
#
#    real B(N1+N2,N1+N2), the R8GE matrix.
#
  import numpy as np

  b = np.zeros ( [ n1 + n2, n1 + n2 ] )
#
#  Fill in band matrix.
#
  for i in range ( 0, n1 ):
    for j in range ( 0, n1 ):
      if ( i - ml <= j and j <= i + mu ):
        b[i,j] = r8bb_get ( n1, n2, ml, mu, a, i, j )
#
#  Fill in right border vector.
#
  for i in range ( 0, n1 ):
    for j in range ( n1, n1 + n2 ):
      b[i,j] = r8bb_get ( n1, n2, ml, mu, a, i, j )
#
#  Fill in lower border vector.
#
  for i in range ( n1, n1 + n2 ):
    for j in range ( 0, n1 ):
      b[i,j] = r8bb_get ( n1, n2, ml, mu, a, i, j )
#
#  Fill in lower right dense matrix.
#
  for i in range ( n1, n1 + n2 ):
    for j in range ( n1, n1 + n2 ):
      b[i,j] = r8bb_get ( n1, n2, ml, mu, a, i, j )

  return b

def r8gb_fa ( n, ml, mu, a ):

#*****************************************************************************80
#
## r8gb_fa() performs a LINPACK-style PLU factorization of a R8GB matrix.
#
#  Discussion:
#
#    An M by N banded matrix A with lower bandwidth ML and upper bandwidth MU
#    is assumed to be entirely zero, except for the main diagonal, and
#    entries in the ML nearest subdiagonals, and MU nearest superdiagonals.
#
#    LINPACK and LAPACK "R8GB" storage for such a matrix generally includes
#    room for ML extra superdiagonals, which may be required to store
#    nonzero entries generated during Gaussian elimination.
#
#    The original M by N matrix is "collapsed" downward, so that diagonals
#    become rows of the storage array, while columns are preserved.  The
#    collapsed array is logically 2*ML+MU+1 by N.
#
#    The following program segment will set up the input.
#
#      m = ml + mu + 1
#      do j = 1, n
#        i1 = max ( 1, j-mu )
#        i2 = min ( n, j+ml )
#        do i = i1, i2
#          k = i - j + m
#          a(k,j) = afull(i,j)
#        end do
#      end do
#
#    This uses rows ML+1 through 2*ML+MU+1 of the array A.
#    In addition, the first ML rows in the array are used for
#    elements generated during the triangularization.
#    The total number of rows needed in A is 2*ML+MU+1.
#    The ML+MU by ML+MU upper left triangle and the
#    ML by ML lower right triangle are not referenced.
#
#  Licensing:
#
#    This code is distributed under the MIT license.
#
#  Modified:
#
#    21 June 2016
#
#  Author:
#
#    John Burkardt.
#
#  Reference:
#
#    Dongarra, Bunch, Moler, Stewart,
#    LINPACK User's Guide,
#    SIAM, 1979.
#
#  Input:
#
#    integer N, the order of the matrix.
#    N must be positive.
#
#    integer ML, MU, the lower and upper bandwidths.
#    ML and MU must be nonnegative, and no greater than N-1.
#
#    real A(2*ML+MU+1,N), the matrix in band storage.  The
#    columns of the matrix are stored in the columns of the array,
#    and the diagonals of the matrix are stored in rows ML+1 through
#    2*ML+MU+1.
#
#  Output:
#
#    real ALU(2*ML+MU+1,N), the LU factors in band storage.  
#    The L and U matrices are stored in a single array.
#
#    integer PIVOT(N), the pivot vector.
#
#    integer INFO, singularity flag.
#    0, no singularity detected.
#    nonzero, the factorization failed on the INFO-th step.
#
  import numpy as np

  alu = a.copy ( )
  pivot = np.zeros ( n, dtype = np.int32 )

  m = ml + mu + 1
  info = 0
#
#  Zero out the initial fill-in columns.
#
  j0 = mu + 2
  j1 = min ( n, m ) - 1

  for jz in range ( j0, j1 + 1 ):
    i0 = m + 1 - jz
    for i in range ( i0, ml + 1 ):
      alu[i-1,jz-1] = 0.0

  jz = j1
  ju = 0

  for k in range ( 1, n ):
#
#  Zero out the next fill-in column.
#
    jz = jz + 1

    if ( jz <= n ):
      for i in range ( 1, ml + 1 ):
        alu[i-1,jz-1] = 0.0
#
#  Find L = pivot index.
#
    lm = min ( ml, n - k )

    l = m

    for j in range ( m + 1, m + lm + 1 ):
      if ( abs ( alu[l-1,k-1] ) < abs ( alu[j-1,k-1] ) ):
        l = j

    pivot[k-1] = l + k - m
#
#  Zero pivot implies this column already triangularized.
#
    if ( alu[l-1,k-1] == 0.0 ):
      info = k
      print ( '' )
      print ( 'R8GB_FA - Fatal error!' )
      print ( '  Zero pivot on step %d' % ( info ) )
      return alu, pivot, info
#
#  Interchange if necessary.
#
    t = alu[l-1,k-1]
    alu[l-1,k-1] = alu[m-1,k-1]
    alu[m-1,k-1] = t
#
#  Compute multipliers.
#
    for i in range ( m + 1, m + lm + 1 ):
      alu[i-1,k-1] = - alu[i-1,k-1] / alu[m-1,k-1]
#
#  Row elimination with column indexing.
#
    ju = max ( ju, mu + pivot[k-1] )
    ju = min ( ju, n )
    mm = m

    for j in range ( k + 1, ju + 1 ):

      l = l - 1
      mm = mm - 1

      if ( l != mm ):
        t = alu[l-1,j-1]
        alu[l-1,j-1] = alu[mm-1,j-1]
        alu[mm-1,j-1] = t

      for i in range ( 0, lm ):
        alu[mm+i,j-1] = alu[mm+i,j-1] + alu[mm-1,j-1] * alu[m+i,k-1]

  pivot[n-1] = n

  if ( alu[m-1,n-1] == 0.0 ):
    info = n
    print ( '' )
    print ( 'R8GB_FA - Fatal error!' )
    print ( '  Zero pivot on step %d' % ( info ) )

  return alu, pivot, info

def r8gb_sl ( n, ml, mu, a_lu, pivot, b, job ):

#*****************************************************************************80
#
## r8gb_sl() solves a system factored by R8GB_FA.
#
#  Discussion:
#
#    An M by N banded matrix A with lower bandwidth ML and upper bandwidth MU
#    is assumed to be entirely zero, except for the main diagonal, and
#    entries in the ML nearest subdiagonals, and MU nearest superdiagonals.
#
#    LINPACK and LAPACK "R8GB" storage for such a matrix generally includes
#    room for ML extra superdiagonals, which may be required to store
#    nonzero entries generated during Gaussian elimination.
#
#    The original M by N matrix is "collapsed" downward, so that diagonals
#    become rows of the storage array, while columns are preserved.  The
#    collapsed array is logically 2*ML+MU+1 by N.
#
#  Licensing:
#
#    This code is distributed under the MIT license.
#
#  Modified:
#
#    20 June 2016
#
#  Author:
#
#    John Burkardt.
#
#  Reference:
#
#    Dongarra, Bunch, Moler, Stewart,
#    LINPACK User's Guide,
#    SIAM, 1979.
#
#  Input:
#
#    integer N, the order of the matrix.
#    N must be positive.
#
#    integer ML, MU, the lower and upper bandwidths.
#    ML and MU must be nonnegative, and no greater than N-1.
#
#    real A_LU(2*ML+MU+1,N), the LU factors from R8GB_FA.
#
#    integer PIVOT(N), the pivot vector from R8GB_FA.
#
#    real B(N), the right hand side vector.
#
#    integer JOB.
#    0, solve A * x = b.
#    nonzero, solve A' * x = b.
#
#  Output:
#
#    real X(N), the solution.
#
  x = b.copy ( )

  m = mu + ml + 1
#
#  Solve A * x = b.
#
  if ( job == 0 ):
#
#  Solve L * Y = B.
#
    if ( 1 <= ml ):

      for k in range ( 1, n ):

        lm = min ( ml, n - k )
        l = pivot[k-1]

        if ( l != k ):
          t      = x[l-1]
          x[l-1] = x[k-1]
          x[k-1] = t
        
        for i in range ( 1, lm + 1 ):
          x[k+i-1] = x[k+i-1] + x[k-1] * a_lu[m+i-1,k-1]
#
#  Solve U * X = Y.
#
    for k in range ( n, 0, -1 ):

      x[k-1] = x[k-1] / a_lu[m-1,k-1]
      lm = min ( k, m ) - 1
      la = m - lm
      lb = k - lm

      for i in range ( 0, lm ):
        x[lb+i-1] = x[lb+i-1] - x[k-1] * a_lu[la+i-1,k-1]
#
#  Solve A' * X = B.
#
  else:
#
#  Solve U' * Y = B.
#
    for k in range ( 1, n + 1 ):
      lm = min ( k, m ) - 1
      la = m - lm
      lb = k - lm
      for i in range ( 0, lm ):
        x[k-1] = x[k-1] - a_lu[la+i-1,k-1] * x[lb+i-1]
      x[k-1] = x[k-1] / a_lu[m-1,k-1]
#
#  Solve L' * X = Y.
#
    if ( 1 <= ml ):

      for k in range ( n - 1, 0, -1 ):

        lm = min ( ml, n - k )

        for i in range ( 1, lm + 1 ):
          x[k-1] = x[k-1] + a_lu[m+i-1,k-1] * x[k+i-1]
        l = pivot[k-1]

        if ( l != k ):
          t      = x[l-1]
          x[l-1] = x[k-1]
          x[k-1] = t

  return x

def r8gb_to_r8vec ( m, n, ml, mu, a ):

#*****************************************************************************80
#
## r8gb_to_r8vec() copies a R8GB matrix to an R8VEC.
#
#  Discussion:
#
#    In C++  and FORTRAN, this routine is not really needed.  In MATLAB,
#    a data item carries its dimensionality implicitly, and so cannot be
#    regarded sometimes as a vector and sometimes as an array.
#
#  Licensing:
#
#    This code is distributed under the MIT license.
#
#  Modified:
#
#    20 June 2016
#
#  Author:
#
#    John Burkardt
#
#  Input:
#
#    integer M, N, the number of rows and columns in the array.
#
#    integer ML, MU, the lower and upper bandwidths.
#
#    real A(2*ML+MU+1,N), the array to be copied.
#
#  Output:
#
#    real X((2*ML+MU+1)*N), the vector.
#
  import numpy as np

  x = np.zeros ( ( 2 * ml + mu + 1 ) * n )

  for j in range ( 1, n + 1 ):

    ihi = min ( ml + mu, ml + mu + 1 - j )
    for i in range ( 1, ihi + 1 ):
      x[i+(j-1)*(2*ml+mu+1)-1] = 0.0

    ilo = max ( ihi + 1, 1 )
    ihi = min ( 2 * ml + mu + 1, ml + mu + m + 1 - j )
    for i in range ( ilo, ihi + 1 ):
      x[i+(j-1)*(2*ml+mu+1)-1] = a[i-1,j-1]

    ilo = ihi + 1
    ihi = 2 * ml + mu + 1
    for i in range ( ilo, ihi + 1 ):
      x[i+(j-1)*(2*ml+mu+1)-1] = 0.0

  return x

def r8ge_fa ( n, a ):

#*****************************************************************************80
#
## r8ge_fa() performs a LINPACK style PLU factorization of a R8GE matrix.
#
#  Discussion:
#
#    The R8GE storage format is used for a general M by N matrix.  A storage 
#    space is made for each logical entry.  The two dimensional logical
#    array is mapped to a vector, in which storage is by columns.
#
#    r8ge_fa is a simplified version of the LINPACK routine R8GEFA.
#
#  Licensing:
#
#    This code is distributed under the MIT license.
#
#  Modified:
#
#    06 July 2015
#
#  Author:
#
#    John Burkardt
#
#  Reference:
#
#    Dongarra, Bunch, Moler, Stewart,
#    LINPACK User's Guide,
#    SIAM, 1979
#
#  Input:
#
#    integer N, the order of the matrix.
#    N must be positive.
#
#    real A(N,N), the matrix to be factored.
#
#  Output:
#
#    real A_LU(N,N), an upper triangular matrix and 
#    the multipliers used to obtain it.  The factorization 
#    can be written A = L * U, where L is a product of 
#    permutation and unit lower triangular matrices and U 
#    is upper triangular.
#
#    integer PIVOT(N), a vector of pivot indices.
#
#    integer INFO, singularity flag.
#    0, no singularity detected.
#    nonzero, the factorization failed on the INFO-th step.
#
  import numpy as np

  a_lu = r8ge_zeros ( n, n )

  for j in range ( 0, n ):
    for i in range ( 0, n ):
      a_lu[i,j] = a[i,j]

  info = 0

  pivot = np.zeros ( n, dtype = np.int32 )

  for k in range ( 0, n - 1 ):
#
#  Find L, the index of the pivot row.
#
    l = k
    for i in range ( k + 1, n ):
      if ( abs ( a_lu[l,k] ) < abs ( a_lu[i,k] ) ):
        l = i

    pivot[k] = l
#
#  If the pivot index is zero, the algorithm has failed.
#
    if ( a_lu[l,k] == 0.0 ):
      info = k
      return a_lu, pivot, info
#
#  Interchange rows L and K if necessary.
#
    if ( l != k ):
      t         = a_lu[l,k]
      a_lu[l,k] = a_lu[k,k]
      a_lu[k,k] = t
#
#  Normalize the values that lie below the pivot entry A(K,K).
#
    for i in range ( k + 1, n ):
      a_lu[i,k] = - a_lu[i,k] / a_lu[k,k]
#
#  Row elimination with column indexing.
#
    for j in range ( k + 1, n ):

      if ( l != k ):
        t         = a_lu[l,j]
        a_lu[l,j] = a_lu[k,j]
        a_lu[k,j] = t

      for i in range ( k + 1, n ):
        a_lu[i,j] = a_lu[i,j] + a_lu[i,k] * a_lu[k,j]

  pivot[n-1] = n - 1

  if ( a_lu[n-1,n-1] == 0.0 ):
    info = n - 1

  return a_lu, pivot, info

def r8ge_sl ( n, a_lu, pivot, b, job ):

#*****************************************************************************80
#
## r8ge_sl() solves a system factored by r8ge_fa.
#
#  Discussion:
#
#    The R8GE storage format is used for a general M by N matrix.  A storage 
#    space is made for each logical entry.  The two dimensional logical
#    array is mapped to a vector, in which storage is by columns.
#
#    r8ge_sl is a simplified version of the LINPACK routine R8GESL.
#
#  Licensing:
#
#    This code is distributed under the MIT license.
#
#  Modified:
#
#    06 July 2015
#
#  Author:
#
#    John Burkardt
#
#  Input:
#
#    integer N, the order of the matrix.
#    N must be positive.
#
#    real A_LU(N,N), the LU factors from r8ge_fa.
#
#    integer PIVOT(N), the pivot vector from r8ge_fa.
#
#    real B(N), the right hand side vector.
#
#    integer JOB, specifies the operation.
#    0, solve A * x = b.
#    nonzero, solve A' * x = b.
#
#  Output:
#
#    real X(N), the solution vector.
#
  import numpy as np

  x = np.zeros ( n )

  for i in range ( 0, n ):
    x[i] = b[i]
#
#  Solve A * x = b.
#
  if ( job == 0 ):
#
#  Solve PL * Y = B.
#
    for k in range ( 0, n - 1 ):

      l = pivot[k]

      if ( l != k ):
        t    = x[l]
        x[l] = x[k]
        x[k] = t

      for i in range ( k + 1, n ):
        x[i] = x[i] + a_lu[i,k] * x[k]
#
#  Solve U * X = Y.
#
    for k in range ( n - 1, -1, -1 ):
      x[k] = x[k] / a_lu[k,k]
      for i in range ( 0, k ):
        x[i] = x[i] - a_lu[i,k] * x[k]
#
#  Solve A' * X = B.
#
  else:
#
#  Solve U' * Y = B.
#
    for k in range ( 0, n ):
      for i in range ( 0, k ):
        x[k] = x[k] - x[i] * a_lu[i,k]
      x[k] = x[k] / a_lu[k,k]
#
#  Solve ( PL )' * X = Y.
#
    for k in range ( n - 2, -1, -1 ):
      for i in range ( k + 1, n ):
        x[k] = x[k] + x[i] * a_lu[i,k]

      l = pivot[k]

      if ( l != k ):
        t    = x[l]
        x[l] = x[k]
        x[k] = t

  return x

def r8ge_to_r8vec ( m, n, a ):

#*****************************************************************************80
#
## r8ge_to_r8vec() copies an R8GE matrix to an R8VEC.
#
#  Discussion:
#
#    In C++ and FORTRAN, this routine is not really needed.  In MATLAB,
#    a data item carries its dimensionality implicitly, and so cannot be
#    regarded sometimes as a vector and sometimes as an array.
#
#  Licensing:
#
#    This code is distributed under the MIT license.
#
#  Modified:
#
#    07 February 2016
#
#  Author:
#
#    John Burkardt
#
#  Input:
#
#    integer M, N, the number of rows and columns in the array.
#
#    real A(M,N), the array to be copied.
#
#  Output:
#
#    real X(M*N), the vector.
#
  import numpy as np

  x = np.zeros ( m * n )

  k = 0
  for j in range ( 0, n ):
    for i in range ( 0, m ):
      x[k] = a[i,j]
      k = k + 1

  return x

def r8ge_zeros ( m, n ):

#*****************************************************************************80
#
## r8ge_zeros() zeroes an R8GE matrix.
#
#  Discussion:
#
#    The R8GE storage format is used for a general M by N matrix.  A storage 
#    space is made for each logical entry.  The two dimensional logical
#    array is mapped to a vector, in which storage is by columns.
#
#  Licensing:
#
#    This code is distributed under the MIT license. 
#
#  Modified:
#
#    01 August 2015
#
#  Author:
#
#    John Burkardt
#
#  Input:
#
#    integer M, N, the order of the matrix.
#    N must be positive.
#
#  Output:
#
#    real A(M,N), the zeroed out matrix.
#
  import numpy as np

  a = np.zeros ( [ m, n ] )

  return a

def r8vec_to_r8gb ( m, n, ml, mu, x ):

#*****************************************************************************80
#
## r8vec_to_r8gb() copies an R8VEC into a R8GB matrix.
#
#  Discussion:
#
#    In C++  and FORTRAN, this routine is not really needed.  In MATLAB,
#    a data item carries its dimensionality implicitly, and so cannot be
#    regarded sometimes as a vector and sometimes as an array.
#
#  Licensing:
#
#    This code is distributed under the MIT license.
#
#  Modified:
#
#    16 July 2016
#
#  Author:
#
#    John Burkardt
#
#  Input:
#
#    integer M, N, the number of rows and columns in the array.
#
#    integer ML, MU, the lower and upper bandwidths.
#
#    real X((2*ML+MU+1)*N), the vector to be copied into the array.
#
#  Output:
#
#    real A(2*ML+MU+1,N), the array.
#
  import numpy as np

  a = np.zeros ( [ 2 * ml + mu + 1, n ] )

  for j in range ( 0, n ):
    for i in range ( 0, 2 * ml + mu + 1 ):

      if ( 0 <= i + j - ml - mu and i + j - ml - mu <= m - 1 ):
        a[i,j] = x[i+j*(2*ml+mu+1)]

  return a

def r8vec_to_r8ge ( m, n, x ):

#*****************************************************************************80
#
## r8vec_to_r8ge() copies an R8VEC into a R8GE matrix.
#
#  Discussion:
#
#    In C++  and FORTRAN, this routine is not really needed.  In MATLAB,
#    a data item carries its dimensionality implicitly, and so cannot be
#    regarded sometimes as a vector and sometimes as an array.
#
#  Licensing:
#
#    This code is distributed under the MIT license.
#
#  Modified:
#
#    08 February 2016
#
#  Author:
#
#    John Burkardt
#
#  Input:
#
#    integer M, N, the number of rows and columns in the array.
#
#    real X(M*N), the vector to be copied into the array.
#
#  Output:
#
#    real A(M,N), the array.
#
  import numpy as np

  a = np.zeros ( [ m, n ] )
  
  k = 0
  for j in range ( 0, n ):
    for i in range ( 0, m ):
      a[i,j] = x[k]
      k = k + 1

  return a


def exercise(case, n1, n2, ml, mu, pivot_case):
    import numpy as np
    n = n1 + n2
    dense = np.zeros((n, n))
    for i in range(n):
        for j in range(n):
            if i >= n1 or j >= n1 or (i-j <= ml and j-i <= mu):
                if i == j:
                    dense[i,j] = 8.0 + i
                else:
                    dense[i,j] = 0.125 * (1 + 2*i - j)
    if pivot_case:
        dense[0,0] = 0.125
        dense[1,0] = 3.0
    nb = (2*ml+mu+1)*n1
    packed = np.zeros(nb + 2*n1*n2 + n2*n2)
    for j in range(n):
        for i in range(n):
            if i < n1 and j < n1:
                if i-j <= ml and j-i <= mu:
                    packed[i-j+ml+mu+j*(2*ml+mu+1)] = dense[i,j]
            elif i < n1:
                packed[nb+(j-n1)*n1+i] = dense[i,j]
            else:
                packed[nb+n1*n2+j*n2+i-n1] = dense[i,j]
    exact = np.zeros(n)
    for i in range(n):
        exact[i] = (i+1.0)*(-1.0)**i
    rhs = dense @ exact
    mv = r8bb_mv(n1,n2,ml,mu,packed,exact)
    trans = r8bb_mtv(n1,n2,ml,mu,packed,exact)
    unpacked = r8bb_to_r8ge(n1,n2,ml,mu,packed)
    lu, piv, info = r8bb_fa(n1,n2,ml,mu,packed)
    work = rhs.copy()
    solution = r8bb_sl(n1,n2,ml,mu,lu,piv,work)
    print('info',case,info)
    for i in range(n):
        print('rhs',case,i,rhs[i])
        print('mv',case,i,mv[i])
        print('trans',case,i,trans[i])
        print('solution',case,i,solution[i])
        print('pivot',case,i,piv[i])
        for j in range(n):
            print('dense',case,i,j,unpacked[i,j])

if __name__ == '__main__':
    exercise(0,4,2,1,2,False)
    exercise(1,5,0,2,1,False)
    exercise(2,0,3,0,0,False)
    exercise(3,1,1,0,0,False)
    exercise(4,3,2,0,0,False)
    exercise(5,4,2,1,1,True)
