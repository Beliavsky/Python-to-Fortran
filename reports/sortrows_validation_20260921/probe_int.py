# sortrows copied unchanged from John Burkardt's MIT-licensed sortrows.py.
def sortrows ( x ):
  import numpy as np
  x = x[ np.lexsort ( x.T[::-1] ) ]
  return x


def exercise(case, x):
    import numpy as np
    rows, cols = x.shape
    y = sortrows(x)
    order = np.lexsort(x.T[::-1])
    print('shape', case, y.shape[0], y.shape[1])
    for i in range(rows):
        print('order', case, i, order[i])
        for j in range(cols):
            print('sorted', case, i, j, y[i,j])
            print('original', case, i, j, x[i,j])


import numpy as np
exercise(0, np.array([[2, 0, 9], [1, 4, 2], [1, 3, 8],
                      [1, 3, 7], [2, -1, 5], [1, 3, 7]], dtype=np.int64))
exercise(1, np.array([[-2, 5], [-1, -4], [-2, -3], [0, -9]], dtype=np.int64))
exercise(2, np.array([[3], [-2], [3], [0], [-2]], dtype=np.int64))
exercise(3, np.array([[4, -2, 1]], dtype=np.int64))
exercise(4, np.zeros((0, 3), dtype=np.int64))
exercise(5, np.array([[1, 1], [1, 1], [1, 1]], dtype=np.int64))
exercise(6, np.array([[0, 2], [0, 9], [0, -1], [0, 8]], dtype=np.int64))
exercise(7, np.array([[3, 1], [2, 2], [1, 3], [0, 4]], dtype=np.int64))
