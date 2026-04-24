# Control flow constructs

x: int = 15

# If / elif / else
if x > 20:
    print("big")
elif x > 10:
    print("medium")
else:
    print("small")

# While loop
count: int = 0
while count < 5:
    print("count =", count)
    count += 1

# For loop with range
total: int = 0
for i in range(10):
    total += i
print("sum 0..9 =", total)

# For loop with range(start, stop)
for i in range(5, 10):
    print("i =", i)

# For loop with range(start, stop, step)
for i in range(0, 20, 3):
    print("step i =", i)

# Nested if inside loop
for i in range(10):
    if i % 2 == 0:
        print(i, "is even")
    else:
        print(i, "is odd")
