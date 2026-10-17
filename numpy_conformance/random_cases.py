"""Random-number cases for coverage_probe.py (genrandom).

Two families:

stat    Fortran's own generator, without replay: N draws of a distribution
        (default_rng and the legacy np.random API), and the fractions of
        them at or below numpy's 1%, 10%, 50%, 90% and 99% quantiles of
        the same distribution (computed here from a large numpy sample).
        Compared with Python's fractions within 5 standard errors, they
        check the distribution itself: a wrong parameterization (a rate
        for a scale, the other Pareto) or a wrong formula. Replay cannot,
        since most methods replay numpy's finished values.

replay  --rng-replay: numpy's draws replayed exactly, for the call forms
        (size None / int / tuple, keywords, array parameters, dtype=,
        endpoint=, choice's p= and replace=, permutation, shuffle). These
        check how a call is translated: its shape, kind, parameters.
"""

from __future__ import annotations

import re

N = 50000
QUANTILES = (0.01, 0.1, 0.5, 0.9, 0.99)

# name -> positional arguments, for both APIs (Generator and legacy)
DISTS = {
    "normal": "1.0, 2.0", "uniform": "-1.0, 3.0", "standard_normal": "", "random": "",
    "exponential": "2.0", "standard_exponential": "", "lognormal": "0.5, 0.3", "gamma": "2.0, 3.0",
    "standard_gamma": "2.5", "beta": "2.0, 3.0", "chisquare": "3.0", "laplace": "1.0, 2.0",
    "logistic": "1.0, 2.0", "standard_t": "5.0", "triangular": "0.0, 1.0, 3.0", "weibull": "1.5",
    "pareto": "3.0", "rayleigh": "2.0", "poisson": "3.0", "binomial": "10, 0.3", "geometric": "0.3",
    "negative_binomial": "5, 0.4", "hypergeometric": "10, 5, 6", "gumbel": "1.0, 2.0",
    "wald": "1.0, 2.0", "vonmises": "0.5, 2.0", "zipf": "2.5", "logseries": "0.6",
    "standard_cauchy": "", "power": "2.0", "f": "3.0, 5.0", "noncentral_chisquare": "3.0, 2.0",
    "noncentral_f": "3.0, 5.0, 2.0",
}
# Results with a last axis: the first component is checked.
VECTOR_DISTS = {
    "multinomial": "10, [0.2, 0.3, 0.5]",
    "dirichlet": "[1.0, 2.0, 3.0]",
    "multivariate_normal": "[1.0, -1.0], [[1.0, 0.5], [0.5, 2.0]]",
}
GENERATOR_ONLY = {"integers": "0, 10"}
LEGACY_ONLY = {"randint": "0, 10"}


def _draw(api: str, name: str, args: str, size: str) -> str:
    a = ", ".join(x for x in (args, size) if x)
    return f"rng.{name}({a})" if api == "rng" else f"np.random.{name}({a})"


def _seed(api: str) -> str:
    return "rng = np.random.default_rng(7)" if api == "rng" else "np.random.seed(7)"


def stat_cases():
    """(name, stmts, n) for the stat family: r is the vector of fractions."""
    import numpy as np
    out = []
    table = [(api, nm, args, False) for api in ("rng", "np")
             for nm, args in {**DISTS, **(GENERATOR_ONLY if api == "rng" else LEGACY_ONLY)}.items()]
    table += [(api, nm, args, True) for api in ("rng", "np") for nm, args in VECTOR_DISTS.items()]
    big = np.random.default_rng(20261016)
    for api, nm, args, vector in table:
        ref = "integers" if nm == "randint" else nm
        sample = eval(_draw("rng", ref, args, "size=1000000"), {"np": np, "rng": big})
        if vector:
            sample = sample[:, 0]
        qs = [float(q) for q in np.quantile(sample, QUANTILES)]
        stmts = [_seed(api), f"y = {_draw(api, nm, args, f'size={N}')}"]
        if vector:
            stmts.append("z = y[:, 0]")
        v = "z" if vector else "y"
        stmts.append("r = np.array([" + ", ".join(f"np.mean({v} <= {q!r})" for q in qs) + "])")
        out.append((f"stat {api}.{nm}({args})", stmts, N))
    return out


def replay_cases():
    """(name, stmts) for the replay family: r is the result."""
    out = []

    def add(api, call, extra=()):
        out.append((f"replay {call}", [_seed(api), *extra, f"r = {call}"]))

    for api in ("rng", "np"):
        dists = {**DISTS, **(GENERATOR_ONLY if api == "rng" else LEGACY_ONLY)}
        for nm, args in dists.items():
            add(api, _draw(api, nm, args, "size=4"))
            add(api, _draw(api, nm, args, "size=(2, 3)"))
            add(api, _draw(api, nm, args, ""))
            # Integer parameters (rng.normal(0, 1)), as numpy allows.
            iargs = re.sub(r"(?<![\d.])(\d+)\.0\b", r"\1", args)
            if iargs != args and "[" not in args:
                add(api, _draw(api, nm, iargs, "size=4"))
                add(api, _draw(api, nm, iargs, ""))
        for nm, args in VECTOR_DISTS.items():
            add(api, _draw(api, nm, args, "size=3"))
            add(api, _draw(api, nm, args, ""))
    # Keywords, array parameters, dtype, endpoint and the index draws.
    for api in ("rng", "np"):
        p = "rng" if api == "rng" else "np.random"
        for call in (
            f"{p}.normal(loc=1.0, scale=2.0, size=4)", f"{p}.normal(size=4)",
            f"{p}.normal(np.array([0.0, 10.0, 100.0]), 1.0)",
            f"{p}.normal(0.0, np.array([1.0, 2.0, 3.0]), size=3)",
            f"{p}.uniform(low=2.0, high=5.0, size=4)", f"{p}.uniform(size=4)",
            f"{p}.uniform(np.array([0.0, 10.0]), np.array([1.0, 20.0]))",
            f"{p}.exponential(scale=np.array([1.0, 10.0, 100.0]))",
            f"{p}.gamma(np.array([1.0, 2.0, 5.0]), 2.0)",
            f"{p}.poisson(np.array([1.0, 5.0, 20.0]))",
            f"{p}.binomial(np.array([5, 10, 20]), 0.5)",
            f"{p}.choice(5, size=4)", f"{p}.choice(5, size=3, replace=False)",
            f"{p}.choice(5, size=4, p=[0.1, 0.2, 0.3, 0.2, 0.2])",
            f"{p}.choice(np.array([1.5, 2.5, 3.5]), size=4)",
            f"{p}.choice(np.array([10, 20, 30, 40]), size=(2, 2))", f"{p}.choice(5)",
            f"{p}.permutation(6)",
        ):
            add(api, call)
        add(api, f"{p}.permutation(pv)", ["pv = np.array([1.5, 2.5, 3.5, 4.5])"])
        out.append((f"replay {p}.shuffle(y)", [_seed(api), "y = np.arange(6)", f"{p}.shuffle(y)", "r = y"]))
    for call in ("rng.integers(5, size=4)", "rng.integers(1, 7, size=(2, 3))",
                 "rng.integers(1, 6, size=4, endpoint=True)", "rng.integers(0, 100)",
                 "rng.random((2, 2))", "rng.random(size=3)", "rng.standard_normal((2, 2))",
                 "rng.integers(np.array([1, 10, 100]), np.array([5, 20, 200]))"):
        add("rng", call)
    for call in ("np.random.randint(5, size=4)", "np.random.randint(1, 7, size=(2, 3))",
                 "np.random.randint(0, 100)", "np.random.rand(3)", "np.random.rand(2, 2)",
                 "np.random.randn(3)", "np.random.randn(2, 2)", "np.random.random_sample(3)",
                 "np.random.rand()", "np.random.randn()"):
        add("np", call)
    return out
