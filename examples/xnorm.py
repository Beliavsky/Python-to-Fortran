from numpy.linalg import norm
from numpy import array
arr1 = array([1,2,3,4])
nrm = norm(arr1)
print(nrm)

arr2 = array([[1,2,3,4],[4,3,2,1]])
nrm2 = norm(arr2, axis=1)
print(nrm)
