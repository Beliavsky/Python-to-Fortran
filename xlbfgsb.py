from scipy.optimize import minimize


def objective(x):
    return (x[0] - 1.0) ** 2 + (x[1] - 2.5) ** 2


x0 = [0.0, 0.0]
res = minimize(objective, x0, bounds=[(0, None), (None, None)])
print(res.x[0])
print(res.x[1])
print(res.fun)
