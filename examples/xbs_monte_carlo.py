import math
import random


def mean_standard_error_and_ci(
    payoff_sum: float,
    payoff_sum_sq: float,
    num_paths: int,
    discount_factor: float,
) -> tuple[float, float, float, float]:
    """Return discounted mean, standard error, and a 95% confidence interval."""
    mean_payoff = payoff_sum / num_paths
    sample_variance = 0.0
    if num_paths > 1:
        sample_variance = (payoff_sum_sq - num_paths * mean_payoff * mean_payoff) / (num_paths - 1)
        sample_variance = max(sample_variance, 0.0)

    standard_error = discount_factor * math.sqrt(sample_variance / num_paths)
    price = discount_factor * mean_payoff
    ci_half_width = 1.96 * standard_error
    return price, standard_error, price - ci_half_width, price + ci_half_width


def monte_carlo_option_prices(
    spot: float,
    strike: float,
    rate: float,
    volatility: float,
    time_to_maturity: float,
    num_paths: int,
    seed: int = 12345,
) -> dict[str, float]:
    """Estimate European call and put prices under Black-Scholes by Monte Carlo."""
    if spot <= 0.0:
        raise ValueError("spot must be > 0")
    if strike <= 0.0:
        raise ValueError("strike must be > 0")
    if volatility <= 0.0:
        raise ValueError("volatility must be > 0")
    if time_to_maturity <= 0.0:
        raise ValueError("time_to_maturity must be > 0")
    if num_paths <= 0:
        raise ValueError("num_paths must be > 0")

    rng = random.Random(seed)
    drift = (rate - 0.5 * volatility * volatility) * time_to_maturity
    diffusion = volatility * math.sqrt(time_to_maturity)
    discount_factor = math.exp(-rate * time_to_maturity)

    call_payoff_sum = 0.0
    call_payoff_sum_sq = 0.0
    put_payoff_sum = 0.0
    put_payoff_sum_sq = 0.0

    for _ in range(num_paths):
        z = rng.gauss(0.0, 1.0)
        terminal_price = spot * math.exp(drift + diffusion * z)
        call_payoff = max(terminal_price - strike, 0.0)
        put_payoff = max(strike - terminal_price, 0.0)
        call_payoff_sum += call_payoff
        call_payoff_sum_sq += call_payoff * call_payoff
        put_payoff_sum += put_payoff
        put_payoff_sum_sq += put_payoff * put_payoff

    call_price, call_standard_error, call_ci_low, call_ci_high = mean_standard_error_and_ci(
        call_payoff_sum, call_payoff_sum_sq, num_paths, discount_factor
    )
    put_price, put_standard_error, put_ci_low, put_ci_high = mean_standard_error_and_ci(
        put_payoff_sum, put_payoff_sum_sq, num_paths, discount_factor
    )

    return {
        "call_price": call_price,
        "call_standard_error": call_standard_error,
        "call_ci_low": call_ci_low,
        "call_ci_high": call_ci_high,
        "put_price": put_price,
        "put_standard_error": put_standard_error,
        "put_ci_low": put_ci_low,
        "put_ci_high": put_ci_high,
    }


def run_example() -> None:
    """Estimate one call and one put price and verify put-call parity."""
    spot = 100.0
    strike = 100.0
    rate = 0.05
    volatility = 0.20
    time_to_maturity = 1.0
    num_paths = 10_000_000
    seed = 12345

    results = monte_carlo_option_prices(
        spot,
        strike,
        rate,
        volatility,
        time_to_maturity,
        num_paths,
        seed,
    )
    call_price = results["call_price"]
    put_price = results["put_price"]

    parity_left = call_price - put_price
    parity_right = spot - strike * math.exp(-rate * time_to_maturity)
    parity_error = abs(parity_left - parity_right)

    print(f"num_paths:  {num_paths}")
    print(f"seed:       {seed}")
    print(f"call price: {call_price:.10f}")
    print(f"call se:    {results['call_standard_error']:.10f}")
    print(f"call 95% ci:[{results['call_ci_low']:.10f}, {results['call_ci_high']:.10f}]")
    print(f"put price:  {put_price:.10f}")
    print(f"put se:     {results['put_standard_error']:.10f}")
    print(f"put 95% ci: [{results['put_ci_low']:.10f}, {results['put_ci_high']:.10f}]")
    print(f"parity lhs: {parity_left:.10f}")
    print(f"parity rhs: {parity_right:.10f}")
    print(f"abs error:  {parity_error:.10e}")

    tolerance = 5.0e-2
    if parity_error <= tolerance:
        print("put-call parity check passed")
    else:
        raise AssertionError("put-call parity check failed")


if __name__ == "__main__":
    run_example()
