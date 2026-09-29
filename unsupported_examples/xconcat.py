import pandas as pd

# --------------------------------------------------
# 1. Concatenate rows
# --------------------------------------------------

df1 = pd.DataFrame({
    "name": ["Alice", "Bob"],
    "score": [90, 85]
})

df2 = pd.DataFrame({
    "name": ["Carol", "Dave"],
    "score": [88, 92]
})

print("1. Concatenate rows:")
print(pd.concat([df1, df2]))
print()


# --------------------------------------------------
# 2. Concatenate rows and reset the index
# --------------------------------------------------

print("2. Concatenate rows with ignore_index=True:")
print(pd.concat([df1, df2], ignore_index=True))
print()


# --------------------------------------------------
# 3. Concatenate columns
# --------------------------------------------------

a = pd.DataFrame({
    "name": ["Alice", "Bob"]
})

b = pd.DataFrame({
    "age": [25, 30]
})

print("3. Concatenate columns:")
print(pd.concat([a, b], axis=1))
print()


# --------------------------------------------------
# 4. Concatenate DataFrames with different columns
# --------------------------------------------------

df3 = pd.DataFrame({
    "name": ["Alice", "Bob"],
    "score": [90, 85]
})

df4 = pd.DataFrame({
    "name": ["Carol", "Dave"],
    "age": [28, 32]
})

print("4. Different columns:")
print(pd.concat([df3, df4], ignore_index=True))
print()


# --------------------------------------------------
# 5. Keep only columns common to both DataFrames
# --------------------------------------------------

print("5. Keep only common columns:")
print(pd.concat([df3, df4], join="inner", ignore_index=True))
print()


# --------------------------------------------------
# 6. Add keys to identify the source DataFrame
# --------------------------------------------------

print("6. Concatenate with keys:")
print(pd.concat([df1, df2], keys=["first", "second"]))
print()


# --------------------------------------------------
# 7. Concatenate Series
# --------------------------------------------------

s1 = pd.Series([10, 20, 30], name="x")
s2 = pd.Series([40, 50, 60], name="y")

print("7. Concatenate Series as columns:")
print(pd.concat([s1, s2], axis=1))
print()


# --------------------------------------------------
# 8. Concatenate several DataFrames at once
# --------------------------------------------------

df5 = pd.DataFrame({"x": [1, 2]})
df6 = pd.DataFrame({"x": [3, 4]})
df7 = pd.DataFrame({"x": [5, 6]})

print("8. Concatenate several DataFrames:")
print(pd.concat([df5, df6, df7], ignore_index=True))
