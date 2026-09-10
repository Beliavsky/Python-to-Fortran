from scipy.optimize import brentq
from xbrentq_helpers import f


root = brentq(f, 0.0, 2.0)
print(root)
