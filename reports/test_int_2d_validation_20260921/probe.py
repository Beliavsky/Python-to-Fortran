def p03_fun ( x, y ):

#*****************************************************************************80
#
## p03_fun() evaluates the integrand for problem 3.
#
#  Licensing:
#
#    This code is distributed under the MIT license.
#
#  Modified:
#
#    26 June 2025
#
#  Author:
#
#    John Burkardt
#
#  Reference:
#
#    Gwynne Evans,
#    Practical Numerical Integration,
#    Wiley, 1993,
#    ISBN: 047193898X,
#    LC: QA299.3E93.
#
#  Input:
#
#    real x(*), y(*): the evaluation points.
#
#  Output:
#
#    real fx(*): the integrand values.
#
  import numpy as np
  fx = np.zeros_like ( x )
  i = np.where ( np.sqrt ( 2.0 - x - y != 0.0 ) )
  fx[i] = 1.0 / np.sqrt ( 2.0 - x[i] - y[i] )

  return fx

def p04_fun ( x, y ):

#*****************************************************************************80
#
## p04_fun() evaluates the integrand for problem 4.
#
#  Licensing:
#
#    This code is distributed under the MIT license.
#
#  Modified:
#
#    26 June 2025
#
#  Author:
#
#    John Burkardt
#
#  Reference:
#
#    Gwynne Evans,
#    Practical Numerical Integration,
#    Wiley, 1993,
#    ISBN: 047193898X,
#    LC: QA299.3E93.
#
#  Input:
#
#    real x(*), y(*): the evaluation points.
#
#  Output:
#
#    real fx(*): the integrand values.
#
  import numpy as np

  fx = np.zeros_like ( x )
  i = np.where ( np.sqrt ( 3.0 - x - 2.0 * y != 0.0 ) )
  fx[i] = 1.0 / np.sqrt ( 3.0 - x[i] - 2.0 * y[i] )

  return fx


import numpy as np
x = np.array([0.0, 0.25, 0.5, 1.0])
y = np.array([0.0, 0.5, 0.25, 1.0])
a = p03_fun(x, y)
b = p04_fun(x, y)
for j in range(4):
    print('values', j, a[j], b[j])
mask = np.sqrt(x != 0.0)
indices = np.where(mask)[0]
for j in range(len(indices)):
    print('index', j, indices[j])
