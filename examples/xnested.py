def nested_polynomial(a, b, c):
    def f(x):
        return a * x ** 2 + b * x + c

    print("nested polynomial:", f(1), f(2), f(3))

a = 3.0
b = 4.0
c = 5.0

nested_polynomial(a, b, c)
