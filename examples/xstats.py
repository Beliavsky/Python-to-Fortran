"""
demonstrate basic use of the statistics module
"""

import statistics as stats

x = [12, 15, 15, 18, 20, 22, 25, 25, 25, 30]

print("data:", x)

# measures of center
print("mean:", stats.mean(x))
print("median:", stats.median(x))
print("mode:", stats.mode(x))

# measures of dispersion
print("population variance:", stats.pvariance(x))
print("sample variance:", stats.variance(x))

print("population standard deviation:", stats.pstdev(x))
print("sample standard deviation:", stats.stdev(x))

# quantiles
print("quartiles:", stats.quantiles(x, n=4))

# geometric and harmonic means require positive values
print("geometric mean:", stats.geometric_mean(x))
print("harmonic mean:", stats.harmonic_mean(x))
