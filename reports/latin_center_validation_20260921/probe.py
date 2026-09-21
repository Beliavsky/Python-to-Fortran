def latin_center ( dim_num, point_num ):

#*****************************************************************************80
#
## latin_center() returns center points in a Latin square.
#
#  Discussion:
#
#    In each spatial dimension, there will be exactly one
#    point with the coordinate value
#
#      ( 1, 3, 5, ..., 2*point_num-1 ) / ( 2 * point_num )
#
#  Licensing:
#
#    This code is distributed under the MIT license.
#
#  Modified:
#
#    14 October 2022
#
#  Author:
#
#    John Burkardt
#
#  Input:
#
#    integer dim_num: the spatial dimension.
#
#    integer point_num: the number of points.
#
#  Output:
#
#    real x(point_num,dim_num,point_num): the points.
#
  from numpy.random import default_rng
  import numpy as np

  rng = default_rng ( )

  x = np.zeros ( [ point_num, dim_num ] )

  for j in range ( 0, dim_num ):

    perm = rng.permutation ( point_num )

    for i in range ( 0, point_num ):
      x[i,j] = ( 2.0 * perm[i] + 1.0 ) / ( 2.0 * point_num )

  return x


def exercise(case, dim_num, point_num):
    import numpy as np
    x = latin_center(dim_num, point_num)
    print('shape', case, x.shape[0], x.shape[1])
    for i in range(point_num):
        for j in range(dim_num):
            print('value', case, i, j, x[i, j])
    ordered = x[np.lexsort(x.T[::-1])]
    for i in range(point_num):
        for j in range(dim_num):
            print('sorted', case, i, j, ordered[i, j])

for repeat in range(3):
    exercise(repeat * 7, 1, 1)
    exercise(repeat * 7 + 1, 5, 1)
    exercise(repeat * 7 + 2, 1, 17)
    exercise(repeat * 7 + 3, 2, 10)
    exercise(repeat * 7 + 4, 7, 31)
    exercise(repeat * 7 + 5, 3, 0)
    exercise(repeat * 7 + 6, 4, 100)

