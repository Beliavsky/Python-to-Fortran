def apply_once(f, x0):
    y = f(x0)
    return y


def f1(i):
    table = [1, 2, 0]
    return table[i]


def f2(i):
    return ((5 * i) + 1) % 7


print(apply_once(f1, 0))
print(apply_once(f2, 3))
