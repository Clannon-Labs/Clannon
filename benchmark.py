import numpy as np
import time

N = 1_000_000_000

start = time.perf_counter()

a = np.arange(N, dtype=np.uint64)
result = ((a * 17) ^ (a >> 3)).sum(dtype=np.uint64)

end = time.perf_counter()

print("Python:\n")
print("sum =", int(result))
print("time =", end - start)