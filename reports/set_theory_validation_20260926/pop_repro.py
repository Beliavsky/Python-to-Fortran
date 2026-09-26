"""Regression example: pop must execute inside the loop, not before it."""


def show():
    values = {1, 2, 3}
    for i in range(3):
        print(values.pop())


show()
