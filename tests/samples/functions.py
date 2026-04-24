# Functions with type annotations

def add(a: int, b: int) -> int:
    return a + b

def greet(name: str) -> str:
    return "Hello, " + name + "!"

def factorial(n: int) -> int:
    if n <= 1:
        return 1
    return n * factorial(n - 1)

def fibonacci(n: int) -> int:
    if n <= 0:
        return 0
    if n == 1:
        return 1
    return fibonacci(n - 1) + fibonacci(n - 2)

def is_even(n: int) -> bool:
    return n % 2 == 0

def absolute_value(x: float) -> float:
    if x < 0.0:
        return -x
    return x

# Use the functions
result = add(3, 7)
print("3 + 7 =", result)

message = greet("World")
print(message)

print("5! =", factorial(5))
print("fib(10) =", fibonacci(10))
print("is_even(4) =", is_even(4))
print("abs(-3.5) =", absolute_value(-3.5))
