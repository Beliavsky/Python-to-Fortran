import numpy as np


def backbin_rc(n, reject, n2, choice):
    if n2 == -1:
        choice[0:n] = -1
        n2 = 1
        choice[n2 - 1] = 1
    elif n2 == n or reject:
        while 1 < n2:
            if choice[n2 - 1] == 1:
                choice[n2 - 1] = 0
                break
            choice[n2 - 1] = -1
            n2 = n2 - 1
        if n2 == 1:
            if choice[n2 - 1] == 1:
                choice[n2 - 1] = 0
            else:
                choice[n2 - 1] = -1
                n2 = -1
    else:
        n2 = n2 + 1
        choice[n2 - 1] = 1
    return n2, choice


def main():
    n = 3
    reject = False
    n2 = -1
    choice = np.zeros(n, dtype=np.int32)

    while True:
        n2, choice = backbin_rc(n, reject, n2, choice)

        result = 0
        for i in range(0, n2):
            result = result * 2 + choice[i]

        print(result)
        break


def other_call():
    n = 3
    reject = 0
    n2 = -1
    choice = np.zeros(n, dtype=np.int32)
    n2, choice = backbin_rc(n, reject, n2, choice)
    print(choice[0])


main()
other_call()
