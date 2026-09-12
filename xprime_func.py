"""Count primes up to n"""

def is_prime(n):
    if n < 2:
        return False
    if n == 2:
        return True
    if n % 2 == 0:
        return False
    d = 3
    while d * d <= n:
        if n % d == 0:
            return False
        d += 2
    return True

def count_primes(limit):
    nprime = 0
    max_prime = None
    for n in range(2, limit + 1):
        if is_prime(n):
            nprime += 1
            max_prime = n
    return nprime, max_prime
    
limit = 10**6
nprime, max_prime = count_primes(limit)
print("upper bound:", limit)
print("number of primes:", nprime)
print("largest prime:", max_prime)
