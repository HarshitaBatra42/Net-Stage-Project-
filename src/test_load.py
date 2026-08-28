import pandas as pd

df = pd.read_csv("../data/cases.csv")
print("Loaded", len(df), "cases")
print(df.head())