import math
from scipy.stats import norm


def black_scholes(S, K, T, r, sigma, option="call"):
    """
    Black-Scholes price of a European call or put.

    Parameters
    ----------
    S : float
        Current underlying price.
    K : float
        Strike price.
    T : float
        Time to expiration in years.
    r : float
        Continuously compounded risk-free rate.
    sigma : float
        Annualized volatility.
    option : str
        "call" or "put".

    Returns
    -------
    float
        Option price.
    """
    d1 = (math.log(S / K) + (r + 0.5 * sigma**2) * T) / (
        sigma * math.sqrt(T)
    )
    d2 = d1 - sigma * math.sqrt(T)

    if option.lower() == "call":
        return S * norm.cdf(d1) - K * math.exp(-r * T) * norm.cdf(d2)

    if option.lower() == "put":
        return K * math.exp(-r * T) * norm.cdf(-d2) - S * norm.cdf(-d1)

    raise ValueError("option must be 'call' or 'put'")


# Example
S = 100.0
K = 100.0
T = 1.0
r = 0.05
sigma = 0.20

call_price = black_scholes(S, K, T, r, sigma, "call")
put_price = black_scholes(S, K, T, r, sigma, "put")

print("Call price:", call_price)
print("Put price: ", put_price)
