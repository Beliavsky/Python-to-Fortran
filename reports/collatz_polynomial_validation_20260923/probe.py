import numpy as np


def grow(p):
    result = np.zeros(len(p) + 1)
    result[:len(p)] = p
    result[-1] = 7.0
    return result


def shrink(p):
    return p[1:].copy()


def show(p):
    print(len(p))
    for i in range(len(p)):
        print(p[i])


def evolve(p):
    for repeat in range(2):
        p = grow(p)
    p = shrink(p)
    show(p)


def mutate(p):
    p[0] += 3.0


original = np.array([1, 2, 3])
evolve(original)
show(original)
evolve(original[1:])
show(original)
evolve(original + 1)
evolve(np.array([8, 9]))
real_original = np.array([1.0, 2.0, 3.0])
evolve(real_original)
show(real_original)
mutate(real_original)
show(real_original)
