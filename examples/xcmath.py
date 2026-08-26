import cmath

z1 = 3 + 4j
z2 = 1 - 2j
z3 = -1 + 0j
z4 = 0.5 + 0.5j

print("constants")
print("cmath.pi =", cmath.pi)
print("cmath.e =", cmath.e)
print("cmath.tau =", cmath.tau)
print()

print("basic complex numbers")
print("z1 =", z1)
print("z2 =", z2)
print("z3 =", z3)
print("z4 =", z4)
print()

print("magnitude and angle")
print("abs(z1) =", abs(z1))
print("cmath.phase(z1) =", cmath.phase(z1))
print("cmath.polar(z1) =", cmath.polar(z1))
print("cmath.rect(5.0, 0.9272952180016122) =", cmath.rect(5.0, 0.9272952180016122))
print()

print("roots, exponentials, logarithms")
print("cmath.sqrt(z1) =", cmath.sqrt(z1))
print("cmath.exp(z2) =", cmath.exp(z2))
print("cmath.log(z1) =", cmath.log(z1))
print("cmath.log(z1, 2.0) =", cmath.log(z1, 2.0))
print("cmath.log10(z1) =", cmath.log10(z1))
print()

print("circular trig functions")
print("cmath.sin(z2) =", cmath.sin(z2))
print("cmath.cos(z2) =", cmath.cos(z2))
print("cmath.tan(z2) =", cmath.tan(z2))
print("cmath.asin(z4) =", cmath.asin(z4))
print("cmath.acos(z4) =", cmath.acos(z4))
print("cmath.atan(z4) =", cmath.atan(z4))
print()

print("hyperbolic functions")
print("cmath.sinh(z2) =", cmath.sinh(z2))
print("cmath.cosh(z2) =", cmath.cosh(z2))
print("cmath.tanh(z2) =", cmath.tanh(z2))
print("cmath.asinh(z4) =", cmath.asinh(z4))
print("cmath.acosh(2 + 1j) =", cmath.acosh(2 + 1j))
print("cmath.atanh(0.2 + 0.1j) =", cmath.atanh(0.2 + 0.1j))
print()

print("classification")
print("cmath.isfinite(z1) =", cmath.isfinite(z1))
print("cmath.isinf(z1) =", cmath.isinf(z1))
print("cmath.isnan(z1) =", cmath.isnan(z1))
print("cmath.isclose(z1, 3 + 4.0000000001j) =", cmath.isclose(z1, 3 + 4.0000000001j))
print()

print("special values")
zinf = complex(float("inf"), 0.0)
znan = complex(float("nan"), 0.0)
print("zinf =", zinf)
print("znan =", znan)
print("cmath.isinf(zinf) =", cmath.isinf(zinf))
print("cmath.isnan(znan) =", cmath.isnan(znan))
print()

print("branch cut example")
print("cmath.sqrt(-1) =", cmath.sqrt(-1))
print("cmath.log(-1) =", cmath.log(-1))
