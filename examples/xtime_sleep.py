import time
start = time.perf_counter()
print("hello")
time.sleep(5)
print("bye")
print("Elapsed: %.3f seconds" % (time.perf_counter() - start))
