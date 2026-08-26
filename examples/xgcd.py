def Gcd(v1, v2):
    a, b = v1, v2
    if a < b:
        a, b = v2, v1
    r = 1
    while r != 0:
        r = a % b
        if r != 0:
            a = b
            b = r
    return b

a = [1, 2]
print(Gcd(12, 18))
