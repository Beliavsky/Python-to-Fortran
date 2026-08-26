import math


def solve_tridiagonal(lower: list[float], diag: list[float], upper: list[float], rhs: list[float]) -> list[float]:
    """Solve a tridiagonal linear system with the Thomas algorithm."""
    n = len(diag)
    c_prime = [0.0] * n
    d_prime = [0.0] * n

    c_prime[0] = upper[0] / diag[0]
    d_prime[0] = rhs[0] / diag[0]

    for i in range(1, n):
        denominator = diag[i] - lower[i] * c_prime[i - 1]
        c_prime[i] = upper[i] / denominator if i < n - 1 else 0.0
        d_prime[i] = (rhs[i] - lower[i] * d_prime[i - 1]) / denominator

    solution = [0.0] * n
    solution[-1] = d_prime[-1]
    for i in range(n - 2, -1, -1):
        solution[i] = d_prime[i] - c_prime[i] * solution[i + 1]

    return solution


def finite_difference_option_price(
    spot: float,
    strike: float,
    rate: float,
    dividend_yield: float,
    volatility: float,
    time_to_maturity: float,
    num_asset_steps: int,
    num_time_steps: int,
    option_type: str,
    exercise_style: str,
    spot_max_multiplier: float = 3.0,
) -> float:
    """Price a European or American option with a Crank-Nicolson PDE solver."""
    if spot <= 0.0:
        raise ValueError("spot must be > 0")
    if strike <= 0.0:
        raise ValueError("strike must be > 0")
    if volatility <= 0.0:
        raise ValueError("volatility must be > 0")
    if time_to_maturity <= 0.0:
        raise ValueError("time_to_maturity must be > 0")
    if num_asset_steps < 3:
        raise ValueError("num_asset_steps must be >= 3")
    if num_time_steps <= 0:
        raise ValueError("num_time_steps must be > 0")
    if spot_max_multiplier <= 1.0:
        raise ValueError("spot_max_multiplier must be > 1")

    option_kind = option_type.strip().lower()
    if option_kind not in {"call", "put"}:
        raise ValueError("option_type must be 'call' or 'put'")

    style = exercise_style.strip().lower()
    if style not in {"european", "american"}:
        raise ValueError("exercise_style must be 'european' or 'american'")

    spot_max = spot_max_multiplier * max(spot, strike)
    d_spot = spot_max / num_asset_steps
    dt = time_to_maturity / num_time_steps
    spots = [i * d_spot for i in range(num_asset_steps + 1)]

    if option_kind == "call":
        values = [max(s - strike, 0.0) for s in spots]
    else:
        values = [max(strike - s, 0.0) for s in spots]

    interior_size = num_asset_steps - 1
    for step in range(num_time_steps - 1, -1, -1):
        current_time = step * dt
        next_time = (step + 1) * dt
        current_tau = time_to_maturity - current_time
        next_tau = time_to_maturity - next_time

        if option_kind == "call":
            left_boundary_current = 0.0
            left_boundary_next = 0.0
            european_right_current = (
                spot_max * math.exp(-dividend_yield * current_tau)
                - strike * math.exp(-rate * current_tau)
            )
            european_right_next = (
                spot_max * math.exp(-dividend_yield * next_tau)
                - strike * math.exp(-rate * next_tau)
            )
            if style == "american":
                right_boundary_current = max(spot_max - strike, european_right_current)
                right_boundary_next = max(spot_max - strike, european_right_next)
            else:
                right_boundary_current = european_right_current
                right_boundary_next = european_right_next
        else:
            right_boundary_current = 0.0
            right_boundary_next = 0.0
            european_left_current = strike * math.exp(-rate * current_tau)
            european_left_next = strike * math.exp(-rate * next_tau)
            if style == "american":
                left_boundary_current = strike
                left_boundary_next = strike
            else:
                left_boundary_current = european_left_current
                left_boundary_next = european_left_next

        lower = [0.0] * interior_size
        diag = [0.0] * interior_size
        upper = [0.0] * interior_size
        rhs = [0.0] * interior_size
        for i in range(1, num_asset_steps):
            alpha = 0.5 * dt * (volatility * volatility * i * i - (rate - dividend_yield) * i)
            beta = dt * (volatility * volatility * i * i + rate)
            gamma = 0.5 * dt * (volatility * volatility * i * i + (rate - dividend_yield) * i)

            index = i - 1
            lower[index] = -0.5 * alpha if i > 1 else 0.0
            diag[index] = 1.0 + 0.5 * beta
            upper[index] = -0.5 * gamma if i < num_asset_steps - 1 else 0.0

            rhs_value = (1.0 - 0.5 * beta) * values[i]
            if i > 1:
                rhs_value += 0.5 * alpha * values[i - 1]
            else:
                rhs_value += 0.5 * alpha * left_boundary_next
                rhs_value -= lower[index] * left_boundary_current
            if i < num_asset_steps - 1:
                rhs_value += 0.5 * gamma * values[i + 1]
            else:
                rhs_value += 0.5 * gamma * right_boundary_next
                rhs_value -= upper[index] * right_boundary_current
            rhs[index] = rhs_value

        interior_values = solve_tridiagonal(lower, diag, upper, rhs)
        values = [left_boundary_current] + interior_values + [right_boundary_current]

        if style == "american":
            for i, stock_price in enumerate(spots):
                if option_kind == "call":
                    intrinsic_value = max(stock_price - strike, 0.0)
                else:
                    intrinsic_value = max(strike - stock_price, 0.0)
                values[i] = max(values[i], intrinsic_value)

        values[0] = left_boundary_current
        values[-1] = right_boundary_current

    spot_index = spot / d_spot
    lower_index = int(math.floor(spot_index))
    upper_index = min(lower_index + 1, num_asset_steps)

    if upper_index == lower_index:
        return values[lower_index]

    weight = spot_index - lower_index
    return (1.0 - weight) * values[lower_index] + weight * values[upper_index]


def print_example(dividend_yield: float) -> None:
    """Price European and American calls and puts for one dividend yield."""
    spot = 100.0
    strike = 100.0
    rate = 0.05
    volatility = 0.20
    time_to_maturity = 1.0
    num_asset_steps = 800
    num_time_steps = 800

    european_call = finite_difference_option_price(
        spot,
        strike,
        rate,
        dividend_yield,
        volatility,
        time_to_maturity,
        num_asset_steps,
        num_time_steps,
        "call",
        "european",
    )
    american_call = finite_difference_option_price(
        spot,
        strike,
        rate,
        dividend_yield,
        volatility,
        time_to_maturity,
        num_asset_steps,
        num_time_steps,
        "call",
        "american",
    )
    european_put = finite_difference_option_price(
        spot,
        strike,
        rate,
        dividend_yield,
        volatility,
        time_to_maturity,
        num_asset_steps,
        num_time_steps,
        "put",
        "european",
    )
    american_put = finite_difference_option_price(
        spot,
        strike,
        rate,
        dividend_yield,
        volatility,
        time_to_maturity,
        num_asset_steps,
        num_time_steps,
        "put",
        "american",
    )

    discounted_spot = spot * math.exp(-dividend_yield * time_to_maturity)
    discounted_strike = strike * math.exp(-rate * time_to_maturity)
    european_parity_left = european_call - european_put
    european_parity_right = discounted_spot - discounted_strike
    european_parity_error = abs(european_parity_left - european_parity_right)
    american_parity_value = american_call - american_put
    american_parity_lower = discounted_spot - strike
    american_parity_upper = spot - discounted_strike

    print(f"dividend_yield:   {dividend_yield:.4f}")
    print(f"num_asset_steps:  {num_asset_steps}")
    print(f"num_time_steps:   {num_time_steps}")
    print(f"european call:    {european_call:.10f}")
    print(f"american call:    {american_call:.10f}")
    print(f"call premium:     {american_call - european_call:.10f}")
    print(f"european put:     {european_put:.10f}")
    print(f"american put:     {american_put:.10f}")
    print(f"put premium:      {american_put - european_put:.10f}")
    print(f"eu parity lhs:    {european_parity_left:.10f}")
    print(f"eu parity rhs:    {european_parity_right:.10f}")
    print(f"eu abs error:     {european_parity_error:.10e}")
    print(f"am parity val:    {american_parity_value:.10f}")
    print(f"am parity low:    {american_parity_lower:.10f}")
    print(f"am parity high:   {american_parity_upper:.10f}")

    if american_call + 1.0e-8 < european_call:
        raise AssertionError("American call price should not be below European call price")
    if american_put + 1.0e-8 < european_put:
        raise AssertionError("American put price should not be below European put price")
    if european_parity_error > 5.0e-2:
        raise AssertionError("European put-call parity check failed")
    if american_parity_value < american_parity_lower - 5.0e-2:
        raise AssertionError("American put-call parity lower bound failed")
    if american_parity_value > american_parity_upper + 5.0e-2:
        raise AssertionError("American put-call parity upper bound failed")

    print("American prices are at least as large as European prices")
    print("European parity equality and American parity bounds passed")


def run_example() -> None:
    """Show no-dividend and dividend-paying examples."""
    print_example(dividend_yield=0.00)
    print()
    print_example(dividend_yield=0.08)


if __name__ == "__main__":
    run_example()
