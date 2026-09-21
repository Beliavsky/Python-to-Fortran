UNBURNT = 0
SMOLDERING = 1
BURNING = 2
BURNT = 3

def fire_spreads ( prob_spread, rng ):

#*****************************************************************************80
#
## fire_spreads() determines whether the fire spreads.
#
#  Licensing:
#
#    This code is distributed under the MIT license.
#
#  Modified:
#
#    16 September 2016
#
#  Author:
#
#    John Burkardt
#
#  Input:
#
#    real PROB_SPREAD, the probability of spreading.
#
#    rng(): the current random number generator.
#
#  Output:
#
#    bool fire_spreads, is TRUE if the fire spreads.
#
  import numpy as np

  u = rng.random ( )

  if ( u < prob_spread ):
    value = True
  else:
    value = False
 
  return value

def forest_burns ( forest_size, forest, prob_spread, rng ):

#*****************************************************************************80
#
## forest_burns() models a single time step of the burning forest.
#
#  Licensing:
#
#    This code is distributed under the MIT license.
#
#  Modified:
#
#    16 September 2016
#
#  Author:
#
#    John Burkardt
#
#  Input:
#
#    integer FOREST_SIZE, the linear dimension of the forest.
#
#    integer FOREST(FOREST_SIZE,FOREST_SIZE), an
#    array with an entry for each tree in the forest.
#
#    real PROB_SPREAD, the probability that the fire will 
#    spread from a burning tree to an unburnt one.
#
#    rng(): the current random number generator.
#
#  Output:
#
#    integer FOREST(FOREST_SIZE,FOREST_SIZE), the updated forest array.
#

#
#  Burning trees burn down;
#  Smoldering trees ignite;
#
  for j in range ( 0, forest_size ):
    for i in range ( 0, forest_size ):
      if ( forest[i,j] == BURNING ):
        forest[i,j] = BURNT
      elif ( forest[i,j] == SMOLDERING ):
        forest[i,j] = BURNING
#
#  Unburnt trees might catch fire.
#
  for j in range ( 0, forest_size ):
    for i in range ( 0, forest_size ):

      if ( forest[i,j] == BURNING ):
#
#  North.
#
        if ( 0 < i ):
          value = fire_spreads ( prob_spread, rng )
          if ( value and forest[i-1,j] == UNBURNT ):
            forest[i-1,j] = SMOLDERING
#
#  South.
#
        if ( i < forest_size - 1 ):
          value = fire_spreads ( prob_spread, rng )
          if ( value and forest[i+1,j] == UNBURNT ):
            forest[i+1,j] = SMOLDERING
#
#  West.
#
        if ( 0 < j ):
          value = fire_spreads ( prob_spread, rng )
          if ( value and forest[i,j-1] == UNBURNT ):
            forest[i,j-1] = SMOLDERING
#
#  East.
#
        if ( j < forest_size - 1 ):
          value = fire_spreads ( prob_spread, rng )
          if ( value and forest[i,j+1] == UNBURNT ):
            forest[i,j+1] = SMOLDERING

  return forest

def forest_initialize ( forest_size ):

#*****************************************************************************80
#
## forest_initialize() initializes the forest values.
#
#  Licensing:
#
#    This code is distributed under the MIT license.
#
#  Modified:
#
#    16 September 2016
#
#  Author:
#
#    John Burkardt
#
#  Input:
#
#    integer FOREST_SIZE, the linear dimension of the forest.
#
#  Output:
#
#    integer FOREST(FOREST_SIZE,FOREST_SIZE), an array
#    with an entry for each tree in the forest.
#
  import numpy as np

  forest = UNBURNT * np.zeros ( [ forest_size, forest_size ] )

  return forest

def forest_is_burning ( forest_size, forest ):

#*****************************************************************************80
#
## forest_is_burning() reports whether any trees in the forest are burning.
#
#  Licensing:
#
#    This code is distributed under the MIT license.
#
#  Modified:
#
#    16 September 2016
#
#  Author:
#
#    John Burkardt
#
#  Input:
#
#    integer FOREST_SIZE, the linear dimension of the forest.
#
#    integer FOREST(FOREST_SIZE,FOREST_SIZE), an array
#    with an entry for each tree in the forest.
#
#  Output:
#
#    bool forest_is_burning, is TRUE if any tree in the forest
#    is in the SMOLDERING or BURNING state.
#
  value = False

  for j in range ( 0, forest_size ):
    for i in range ( 0, forest_size ):
      if ( forest[i,j] == SMOLDERING or forest[i,j] == BURNING ):
        value = True
        return value

  return value

def get_proportion_burned ( forest_size, forest ):

#*****************************************************************************80
#
## get_proportion_burned() computes the proportion of the forest that burned.
#
#  Licensing:
#
#    This code is distributed under the MIT license.
#
#  Modified:
#
#    16 September 2016
#
#  Author:
#
#    John Burkardt
#
#  Input:
#
#    integer FOREST_SIZE, the linear dimension of the forest.
#
#    integer FOREST(FOREST_SIZE,FOREST_SIZE), an array
#    with an entry for each tree in the forest.
#
#  Output:
#
#    real proportion, the proportion of the forest that burned.
#
  total = 0
  for j in range ( 0, forest_size ):
    for i in range ( 0, forest_size ):
      if ( forest[i,j] == BURNT ):
        total = total + 1

  proportion = float ( total ) / float ( forest_size ) / float ( forest_size )

  return proportion

def tree_ignite ( forest_size, forest, i_ignite, j_ignite ):

#*****************************************************************************80
#
## tree_ignite() sets a given tree to the SMOLDERING state.
#
#  Licensing:
#
#    This code is distributed under the MIT license.
#
#  Modified:
#
#    16 September 2016
#
#  Author:
#
#    John Burkardt
#
#  Input:
#
#    integer FOREST_SIZE, the linear dimension of the forest.
#
#    integer FOREST(FOREST_SIZE,FOREST_SIZE), an array
#    with an entry for each tree in the forest.
#
#    integer I_IGNITE, J_IGNITE, the coordinates of the 
#    tree which is to be set to SMOLDERING.
#
#  Output:
#
#    integer FOREST(FOREST_SIZE,FOREST_SIZE), the updated array.
#
  forest[i_ignite,j_ignite] = SMOLDERING

  return forest


def snapshot(case, step, n, forest):
    print('active', case, step, int(forest_is_burning(n, forest)))
    print('fraction', case, step, get_proportion_burned(n, forest))
    for i in range(n):
        for j in range(n):
            print('cell', case, step, i, j, forest[i,j])

def exercise(case, n, prob, row, col):
    from numpy.random import default_rng
    rng = default_rng()
    forest = forest_initialize(n)
    snapshot(case, -1, n, forest)
    if row >= 0:
        forest = tree_ignite(n, forest, row, col)
    step = 0
    snapshot(case, step, n, forest)
    while forest_is_burning(n, forest):
        forest = forest_burns(n, forest, prob, rng)
        step = step + 1
        snapshot(case, step, n, forest)
        if step > 2*n + 2:
            break
    print('steps', case, step)

exercise(0, 1, 0.0, 0, 0)
exercise(1, 1, 1.0, 0, 0)
exercise(2, 2, 0.0, 0, 0)
exercise(3, 2, 1.0, 0, 0)
exercise(4, 5, 0.0, 2, 2)
exercise(5, 5, 1.0, 2, 2)
exercise(6, 5, 0.0, 0, 4)
exercise(7, 5, 1.0, 0, 4)
exercise(8, 4, 1.0, 0, 2)
exercise(9, 4, 0.0, 0, 2)
exercise(10, 3, 1.0, -1, -1)

