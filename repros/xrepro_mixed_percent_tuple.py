names = ["A", "B"]
values = [1.25, 2.50]

for i in range(2):
    s = '"%s",%6.2f\n' % (names[i], values[i])
    print(s)

