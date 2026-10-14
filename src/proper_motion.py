import pandas as pd


def add_pm_columns(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["pm_total"] = (df["pmra"] ** 2 + df["pmdec"] ** 2) ** 0.5
    df["cor_w1w2"] = df["w1mpro"] - df["w2mpro"]
    return df
