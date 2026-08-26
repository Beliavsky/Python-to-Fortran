"""
demonstrate basic use of the random module
"""

import random

# make results reproducible
random.seed(12345)

# random float in [0.0, 1.0)
print("random():", random.random())

# random integer including both endpoints
print("randint(1, 10):", random.randint(1, 10))

# random integer from range(start, stop, step)
print("randrange(0, 100, 5):", random.randrange(0, 100, 5))

# random float from a uniform distribution
print("uniform(10.0, 20.0):", random.uniform(10.0, 20.0))

# choose one item
colors = ["red", "green", "blue", "yellow"]
print("choice(colors):", random.choice(colors))

# choose several items with replacement
print("choices(colors, k=5):", random.choices(colors, k=5))

# choose several unique items without replacement
print("sample(colors, k=3):", random.sample(colors, k=3))

# shuffle a list in place
numbers = list(range(1, 11))
random.shuffle(numbers)
print("shuffled numbers:", numbers)

# normal distribution
normal_values = [random.gauss(mu=0.0, sigma=1.0) for _ in range(5)]
print("normal values:", normal_values)

# simulate rolling two dice
nrolls = 1000
count_seven = 0

for _ in range(nrolls):
    die1 = random.randint(1, 6)
    die2 = random.randint(1, 6)
    if die1 + die2 == 7:
        count_seven += 1

print("number of rolls:", nrolls)
print("number of sums equal to 7:", count_seven)
print("estimated probability:", count_seven / nrolls)
