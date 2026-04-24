def fibonacci(n: int) -> int:
    if n <= 0:
        return 0
    if n == 1:
        return 1
    return fibonacci(n - 1) + fibonacci(n - 2)

# Print the first 15 Fibonacci numbers
for i in range(15):
    print("fib(", i, ") =", fibonacci(i))
