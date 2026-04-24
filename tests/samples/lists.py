# List operations

nums: list[int] = [1, 2, 3, 4, 5]

# Append
nums.append(6)

# Length
size = len(nums)
print("size =", size)

# Iteration
for n in nums:
    print("num:", n)

# Indexing
first = nums[0]
last = nums[5]
print("first =", first, "last =", last)

# Sum using a loop
total: int = 0
for i in range(len(nums)):
    total += nums[i]
print("total =", total)

# Build a list in a loop
squares: list[int] = []
for i in range(1, 6):
    squares.append(i * i)

for s in squares:
    print("square:", s)
