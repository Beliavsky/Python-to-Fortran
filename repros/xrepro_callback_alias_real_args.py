def solve(a, b, f):
    sa = a
    fa = f(sa)
    sb = b
    fb = f(sb)
    return 0.5 * (sa + sb) + fa - fb

def f(x):
    return x * x - 2.0

print(solve(0.0, 2.0, f))
