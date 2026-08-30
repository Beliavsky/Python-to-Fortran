"""Numerical methods suite (batch 2): finite-difference derivatives.

Central-difference gradient of a fixed scalar function of two
variables, and a central-difference Jacobian of a fixed 2-vector
function of two variables, both compared against their known
closed-form (analytic) derivatives.
"""
import numpy as np


def f(v):
    x, y = v[0], v[1]
    return x**2 * y + np.sin(x * y)


def grad_f_exact(v):
    x, y = v[0], v[1]
    return np.array([2.0 * x * y + y * np.cos(x * y), x**2 + x * np.cos(x * y)])


def g(v):
    x, y = v[0], v[1]
    return np.array([x**2 - y, x * y**2])


def jac_g_exact(v):
    x, y = v[0], v[1]
    return np.array([[2.0 * x, -1.0], [y**2, 2.0 * x * y]])


def fd_gradient(func, v, h):
    n = v.shape[0]
    grad = np.zeros(n)
    for i in range(n):
        vp = v.copy()
        vm = v.copy()
        vp[i] = vp[i] + h
        vm[i] = vm[i] - h
        grad[i] = (func(vp) - func(vm)) / (2.0 * h)
    return grad


def fd_jacobian(func, v, h):
    n = v.shape[0]
    fv = func(v)
    m = fv.shape[0]
    J = np.zeros((m, n))
    for i in range(n):
        vp = v.copy()
        vm = v.copy()
        vp[i] = vp[i] + h
        vm[i] = vm[i] - h
        J[:, i] = (func(vp) - func(vm)) / (2.0 * h)
    return J


v0 = np.array([1.3, 0.7])
h = 1.0e-5

grad_fd = fd_gradient(f, v0, h)
grad_exact = grad_f_exact(v0)
print("fd grad =", grad_fd[0], grad_fd[1])
print("exact grad =", grad_exact[0], grad_exact[1])
print("grad abs error =", abs(grad_fd[0] - grad_exact[0]), abs(grad_fd[1] - grad_exact[1]))

J_fd = fd_jacobian(g, v0, h)
J_exact = jac_g_exact(v0)
print("fd jac =", J_fd[0, 0], J_fd[0, 1], J_fd[1, 0], J_fd[1, 1])
print("exact jac =", J_exact[0, 0], J_exact[0, 1], J_exact[1, 0], J_exact[1, 1])
