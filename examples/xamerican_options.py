import math


def binomial_tree_option_price(
    spot: float,
    strike: float,
    rate: float,
    dividend_yield: float,
    volatility: float,
    time_to_maturity: float,
    num_steps: int,
    option_type: str,
    exercise_style: str,
) -> float:
    """Price a European or American call or put with a CRR binomial tree."""
    if spot <= 0.0:
        raise ValueError("spot must be > 0")
    if strike <= 0.0:
        raise ValueError("strike must be > 0")
    if volatility <= 0.0:
        raise ValueError("volatility must be > 0")
    if time_to_maturity <= 0.0:
        raise ValueError("time_to_maturity must be > 0")
    if num_steps <= 0:
        raise ValueError("num_steps must be > 0")

    option_kind = option_type.strip().lower()
    if option_kind not in {"call", "put"}:
        raise ValueError("option_type must be 'call' or 'put'")

    style = exercise_style.strip().lower()
    if style not in {"european", "american"}:
        raise ValueError("exercise_style must be 'european' or 'american'")

    dt = time_to_maturity / num_steps
    up = math.exp(volatility * math.sqrt(dt))
    down = 1.0 / up
    discount = math.exp(-rate * dt)
    growth = math.exp((rate - dividend_yield) * dt)
    risk_neutral_prob = (growth - down) / (up - down)

    if not 0.0 < risk_neutral_prob < 1.0:
        raise ValueError("risk-neutral probability must lie strictly between 0 and 1")

    values = []
    for num_down_moves in range(num_steps + 1):
        terminal_price = spot * (up ** (num_steps - num_down_moves)) * (down ** num_down_moves)
        if option_kind == "call":
            values.append(max(terminal_price - strike, 0.0))
        else:
            values.append(max(strike - terminal_price, 0.0))

    for step in range(num_steps - 1, -1, -1):
        next_values = []
        for node in range(step + 1):
            continuation_value = discount * (
                risk_neutral_prob * values[node] + (1.0 - risk_neutral_prob) * values[node + 1]
            )

            if style == "american":
                stock_price = spot * (up ** (step - node)) * (down ** node)
                if option_kind == "call":
                    intrinsic_value = max(stock_price - strike, 0.0)
                else:
                    intrinsic_value = max(strike - stock_price, 0.0)
                next_values.append(max(continuation_value, intrinsic_value))
            else:
                next_values.append(continuation_value)

        values = next_values

    return values[0]


def print_example(dividend_yield: float) -> None:
    """Price European and American calls and puts for one dividend yield."""
    spot = 100.0
    strike = 100.0
    rate = 0.05
    volatility = 0.20
    time_to_maturity = 1.0
    num_steps = 5000

    european_call = binomial_tree_option_price(
        spot, strike, rate, dividend_yield, volatility, time_to_maturity, num_steps, "call", "european"
    )
    american_call = binomial_tree_option_price(
        spot, strike, rate, dividend_yield, volatility, time_to_maturity, num_steps, "call", "american"
    )
    european_put = binomial_tree_option_price(
        spot, strike, rate, dividend_yield, volatility, time_to_maturity, num_steps, "put", "european"
    )
    american_put = binomial_tree_option_price(
        spot, strike, rate, dividend_yield, volatility, time_to_maturity, num_steps, "put", "american"
    )
    discounted_spot = spot * math.exp(-dividend_yield * time_to_maturity)
    discounted_strike = strike * math.exp(-rate * time_to_maturity)
    european_parity_left = european_call - european_put
    european_parity_right = discounted_spot - discounted_strike
    european_parity_error = abs(european_parity_left - european_parity_right)
    american_parity_value = american_call - american_put
    american_parity_lower = discounted_spot - strike
    american_parity_upper = spot - discounted_strike

    print(f"dividend_yield: {dividend_yield:.4f}")
    print(f"num_steps:      {num_steps}")
    print(f"european call:  {european_call:.10f}")
    print(f"american call:  {american_call:.10f}")
    print(f"call premium:   {american_call - european_call:.10f}")
    print(f"european put:   {european_put:.10f}")
    print(f"american put:   {american_put:.10f}")
    print(f"put premium:    {american_put - european_put:.10f}")
    print(f"eu parity lhs:  {european_parity_left:.10f}")
    print(f"eu parity rhs:  {european_parity_right:.10f}")
    print(f"eu abs error:   {european_parity_error:.10e}")
    print(f"am parity val:  {american_parity_value:.10f}")
    print(f"am parity low:  {american_parity_lower:.10f}")
    print(f"am parity high: {american_parity_upper:.10f}")

    if american_call + 1.0e-12 < european_call:
        raise AssertionError("American call price should not be below European call price")
    if american_put + 1.0e-12 < european_put:
        raise AssertionError("American put price should not be below European put price")
    if european_parity_error > 1.0e-10:
        raise AssertionError("European put-call parity check failed")
    if american_parity_value < american_parity_lower - 1.0e-10:
        raise AssertionError("American put-call parity lower bound failed")
    if american_parity_value > american_parity_upper + 1.0e-10:
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
