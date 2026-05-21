import itertools as it

combos = it.combinations_with_replacement(range(1, 5), 4)
print(list(combos))

