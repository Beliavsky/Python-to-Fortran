"""
Single-file Python test program based on the Fortran-lang Python/Fortran
Rosetta Stone. It exercises array operations, slicing, masks, matrix
multiplication, math, complex numbers, formatting, nested functions,
callbacks, loop control, Mandelbrot iteration, and least-squares fitting.

The only external dependency is NumPy.
"""

from math import cos, sin, pi, e
import numpy as np

__all__ = ["module_i", "module_f"]

module_i = 5


def module_f(x):
    return x + 5


def module_g(x):
    return x - 5


def print_section(title):
    print("")
    print("=" * 60)
    print(title)
    print("=" * 60)


def arrays_1d():
    print_section("1d arrays, shape, size, min, max, sum")

    a = np.array([1, 2, 3])
    print("a =", a)
    print("shape(a) =", np.shape(a))
    print("size(a) =", np.size(a))
    print("max(a) =", np.max(a))
    print("min(a) =", np.min(a))
    print("sum(a) =", np.sum(a))


def reshape_and_2d_arrays():
    print_section("reshape order and 2d arrays")

    a = np.reshape([1, 2, 3, 4, 5, 6], (2, 3))
    b = np.reshape([1, 2, 3, 4, 5, 6], (2, 3), order="F")

    print("C-order reshape:")
    print(a)
    print("a[0, :] =", a[0, :])
    print("a[1, :] =", a[1, :])

    print("Fortran-order reshape:")
    print(b)
    print("b[0, :] =", b[0, :])
    print("b[1, :] =", b[1, :])

    c = np.array([[1, 2, 3], [4, 5, 6]])
    print("c shape =", np.shape(c))
    print("size(c, axis=0) =", np.size(c, 0))
    print("size(c, axis=1) =", np.size(c, 1))
    print("max(c) =", np.max(c))
    print("min(c) =", np.min(c))
    print("row 0 =", c[0, 0], c[0, 1], c[0, 2])
    print("row 1 =", c[1, 0], c[1, 1], c[1, 2])
    print(c)


def logical_reductions_and_masks():
    print_section("all, any, Boolean masks, where-like assignment")

    i = np.array([1, 2, 3])
    print("all(i == [1, 2, 3]) =", np.all(i == [1, 2, 3]))
    print("any(i == [2, 2, 3]) =", np.any(i == [2, 2, 3]))

    a = np.array([1, 2, 3, 4, 5, 6, 7, 8, 9, 10])
    b = np.empty(10, dtype=int)

    b[:] = 0
    b[a > 2] = 1
    b[a > 5] = a[a > 5] - 3
    print("masked assignment b =", b)

    c = np.empty(10, dtype=int)
    for k in range(len(a)):
        if a[k] > 5:
            c[k] = a[k] - 3
        elif a[k] > 2:
            c[k] = 1
        else:
            c[k] = 0
    print("loop assignment c   =", c)

    mask = (a > 2) & (a < 6)
    ones = np.ones(np.size(a), dtype=int)
    print("sum(a) =", np.sum(a))
    print("sum(a[mask]) =", np.sum(a[mask]))
    print("count(mask) =", np.sum(ones[mask]))
    print("np.count_nonzero(mask) =", np.count_nonzero(mask))


def matrix_operations():
    print_section("element-wise multiplication and matrix multiplication")

    a = np.array([[1, 2], [3, 4]])
    b = np.array([[2, 3], [4, 5]])

    print("a * b =")
    print(a * b)

    print("np.dot(a, b) =")
    print(np.dot(a, b))

    print("a @ b =")
    print(a @ b)


def array_constructors():
    print_section("array constructors and comprehensions")

    a = np.array([i for i in range(1, 7)])
    b = np.array([(2 * i * pi + 1) / 2 for i in range(1, 7)])
    c = np.array([i for i in range(1, 7) for j in range(1, 4)])

    print("a =", a)
    print("b =", b)
    print("c =", c)


def indexing_examples():
    print_section("indexing and slicing examples")

    a = np.array([1, 2, 3])
    b = a

    print("a[:] =", a[:])
    print("b[:] =", b[:])
    print("a[:2] =", a[:2])
    print("b[:2] =", b[:2])

    x = np.array([10, 20, 30, 40, 50, 60, 70, 80, 90, 100])
    n = 3
    i = 2
    j = 6

    print("x =", x)
    print("first n elements x[:n] =", x[:n])
    print("last n elements x[-n:] =", x[-n:])
    print("elements i through j inclusive x[i:j+1] =", x[i:j + 1])
    print("n elements starting with index i x[i:i+n] =", x[i:i + n])

    r = 1
    for k in range(len(x)):
        r *= x[k]
    print("product over whole array =", r)

    r = 1
    for k in range(3, 8):
        r *= x[k]
    print("product for k in range(3, 8) =", r)

    s = "abcdefghijklmnopqrstuvwxyz"
    i = 5
    j = 12
    print("string part 1 =", s[:i])
    print("string part 2 =", s[i:j])
    print("string part 3 =", s[j:])


def laplace_update():
    print_section("2d stencil / Laplace update")

    u = np.arange(25, dtype=float).reshape((5, 5))
    dx2 = 0.25
    dy2 = 0.50

    print("u before:")
    print(u)

    u[1:-1, 1:-1] = (
        ((u[2:, 1:-1] + u[:-2, 1:-1]) * dy2
        + (u[1:-1, 2:] + u[1:-1, :-2]) * dx2)
        / (2 * (dx2 + dy2))
    )

    print("u after:")
    print(u)


def module_like_features():
    print_section("module-like global variables and functions")

    print("module_f(3) =", module_f(3))
    print("module_g(3) =", module_g(3))
    print("module_i =", module_i)
    print("__all__ =", __all__)


def floating_point_examples():
    print_section("floating point precision examples")

    f32 = np.float32(1.1)
    f64 = np.float64(1.1)

    print("np.float32(1.1) =", f32)
    print("np.float64(1.1) =", f64)

    f = 1.1
    print("f = 1.1 ->", f)

    f = 1e8
    print("f = 1e8 ->", f)

    f = float(1) / 2
    print("float(1) / 2 ->", f)

    f = float(1 // 2)
    print("float(1 // 2) ->", f)

    f = float(5)
    print("float(5) ->", f)


def math_and_complex_examples():
    print_section("math and complex numbers")

    imaginary_unit = 1j

    print("e**(1j*pi) + 1 =", e ** (imaginary_unit * pi) + 1)
    print("cos(pi) =", cos(pi))
    print("4 + 5j =", 4 + 5j)
    print("4 + 5*imaginary_unit =", 4 + 5 * imaginary_unit)


def string_and_formatting_examples():
    print_section("strings and formatting")

    print("Integer", 5, "and float", 5.5, "works fine.")
    print("Integer " + str(5) + " and float " + str(5.5) + ".")
    print("Integer %d and float %f." % (5, 5.5))

    print("%3d" % 5)
    print("%03d" % 5)
    print("%s" % "text")
    print("%15.7f" % 5.5)
    print("%23.16e" % -5.5)

    print("{:3d}".format(5))
    print("{:03d}".format(5))
    print("{:s}".format("text"))
    print("{:15.7f}".format(5.5))
    print("{:23.16e}".format(-5.5))


def nested_polynomial(a, b, c):
    def f(x):
        return a * x ** 2 + b * x + c

    print("nested polynomial:", f(1), f(2), f(3))


def simpson(f, a, b):
    return (b - a) / 6 * (f(a) + 4 * f((a + b) / 2) + f(b))


def nested_callback_example(a, k):
    def f(x):
        return a * sin(k * x)

    print("simpson 0 to pi    =", simpson(f, 0.0, pi))
    print("simpson 0 to 2*pi  =", simpson(f, 0.0, 2 * pi))


def nested_functions_and_callbacks():
    print_section("nested functions and callbacks")

    nested_polynomial(1, 2, 1)
    nested_polynomial(2, 2, 1)

    nested_callback_example(0.5, 1.0)
    nested_callback_example(0.5, 2.0)


def loop_control():
    print_section("break and continue in loops")

    print("break example:")
    for i in range(1, 9):
        if i > 2:
            break
        print(i)

    print("continue example:")
    for i in range(1, 9):
        if i % 2 == 0:
            continue
        print(i)

    print("nested break example:")
    total = 0
    for i in range(1, 5):
        for j in range(1, 5):
            if i * j > 6:
                break
            total += i * j
    print("total =", total)


def mandelbrot_example():
    print_section("small Mandelbrot-style masked complex iteration")

    iterations = 8
    density = 12
    x_min, x_max = -2.68, 1.32
    y_min, y_max = -1.5, 1.5

    x, y = np.meshgrid(
        np.linspace(x_min, x_max, density),
        np.linspace(y_min, y_max, density),
    )

    c = x + 1j * y
    z = c.copy()
    fractal = np.zeros(z.shape, dtype=np.uint8) + 255

    for n in range(iterations):
        mask = np.abs(z) <= 10
        z[mask] *= z[mask]
        z[mask] += c[mask]
        fractal[(fractal == 255) & (~mask)] = int(254.0 * n / iterations)

    log_fractal = np.log(fractal.astype(float))
    coord = np.array([x_min, x_max, y_min, y_max])

    print("fractal shape =", fractal.shape)
    print("fractal min/max =", np.min(fractal), np.max(fractal))
    print("log_fractal[0, :4] =", log_fractal[0, :4])
    print("coord =", coord)


def expression(x, pars):
    a, b, c = pars
    return a * x * np.log(b + c * x)


def residuals(data_x, data_y, expr, pars):
    return data_y - expr(data_x, pars)


def sse(data_x, data_y, expr, pars):
    r = residuals(data_x, data_y, expr, pars)
    return float(np.sum(r * r))


def numerical_jacobian(data_x, expr, pars):
    nobs = np.size(data_x)
    npar = np.size(pars)
    jac = np.zeros((nobs, npar), dtype=float)
    eps = 1.0e-6

    for j in range(npar):
        step = eps * max(1.0, abs(pars[j]))
        p0 = pars.copy()
        p1 = pars.copy()
        p0[j] -= step
        p1[j] += step
        jac[:, j] = (expr(data_x, p1) - expr(data_x, p0)) / (2.0 * step)

    return jac


def find_fit(data_x, data_y, expr, pars):
    data_x = np.array(data_x, dtype=float)
    data_y = np.array(data_y, dtype=float)
    pars = np.array(pars, dtype=float)

    max_iter = 100
    tol = 1.0e-10
    lam = 1.0e-3

    best_sse = sse(data_x, data_y, expr, pars)

    for _ in range(max_iter):
        yhat = expr(data_x, pars)
        r = data_y - yhat
        jac = numerical_jacobian(data_x, expr, pars)

        lhs = jac.T @ jac + lam * np.eye(np.size(pars))
        rhs = jac.T @ r

        try:
            step = np.linalg.solve(lhs, rhs)
        except np.linalg.LinAlgError:
            break

        new_pars = pars + step

        if np.any(1.0 + new_pars[2] * data_x <= 0.0):
            lam *= 10.0
            continue

        new_sse = sse(data_x, data_y, expr, new_pars)

        if new_sse < best_sse:
            if abs(best_sse - new_sse) < tol:
                pars = new_pars
                break

            pars = new_pars
            best_sse = new_sse
            lam *= 0.5
        else:
            lam *= 10.0

    return pars


def least_squares_example():
    print_section("least-squares fitting without scipy")

    y = [
        2, 3, 5, 7, 11,
        13, 17, 19, 23, 29,
        31, 37, 41, 43, 47,
        53, 59, 61, 67, 71,
    ]

    pars = [1.0, 1.0, 1.0]
    x = range(1, np.size(y) + 1)
    pars = find_fit(x, y, expression, pars)

    x_arr = np.array(list(x), dtype=float)
    y_arr = np.array(y, dtype=float)

    print("pars =", pars)
    print("sse  =", sse(x_arr, y_arr, expression, pars))


def main():
    arrays_1d()
    reshape_and_2d_arrays()
    logical_reductions_and_masks()
    matrix_operations()
    array_constructors()
    indexing_examples()
    laplace_update()
    module_like_features()
    floating_point_examples()
    math_and_complex_examples()
    string_and_formatting_examples()
    nested_functions_and_callbacks()
    loop_control()
    mandelbrot_example()
    least_squares_example()


if __name__ == "__main__":
    main()
