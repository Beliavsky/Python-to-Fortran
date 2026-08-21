import numpy as np
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
    d1 = (np.log(S / K) + (r + 0.5 * sigma**2) * T) / (
        sigma * np.sqrt(T)
    )
    d2 = d1 - sigma * np.sqrt(T)

    if option.lower() == "call":
        return S * norm.cdf(d1) - K * np.exp(-r * T) * norm.cdf(d2)

    if option.lower() == "put":
        return K * np.exp(-r * T) * norm.cdf(-d2) - S * norm.cdf(-d1)

    raise ValueError("option must be 'call' or 'put'")


# Example: vector of strikes and a matching vector of vols (a "smile")
S = 100.0
K = np.array([90.0, 100.0, 110.0])
T = 1.0
r = 0.05
sigma = np.array([0.25, 0.20, 0.22])

call_price = black_scholes(S, K, T, r, sigma, "call")
put_price = black_scholes(S, K, T, r, sigma, "put")

print("Call price:", call_price)
print("Put price: ", put_price)
