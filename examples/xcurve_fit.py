import numpy as np
from scipy.optimize import curve_fit


def model(x, a, b, c):
    return a * np.exp(-b * x) + c


xdata = [0.0, 0.5, 1.0, 1.5, 2.0, 2.5, 3.0, 3.5, 4.0, 4.5]
ydata = [
    2.98, 2.51, 2.14, 1.83, 1.62, 1.49, 1.36, 1.29, 1.23, 1.19,
]
p0 = [2.0, 1.0, 1.0]

popt, pcov = curve_fit(model, xdata, ydata, p0)
print(popt[0])
print(popt[1])
print(popt[2])
