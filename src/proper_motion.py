import pandas as pd


def add_pm_columns(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["pm_total"] = (df["pmra"] ** 2 + df["pmdec"] ** 2) ** 0.5
    df["cor_w1w2"] = df["w1mpro"] - df["w2mpro"]
    if {"sigpmra", "sigpmdec"} <= set(df.columns):
        # Propagacao de erro de sqrt(pmra^2 + pmdec^2).
        sig = ((df["pmra"] * df["sigpmra"]) ** 2 + (df["pmdec"] * df["sigpmdec"]) ** 2) ** 0.5 / df["pm_total"]
        df["pm_signif"] = df["pm_total"] / sig
    return df
