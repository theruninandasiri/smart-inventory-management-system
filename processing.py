"""Data cleaning, validation and preprocessing for inventory and sales data."""
import numpy as np
import pandas as pd

REQUIRED = ["Product ID", "Product Name", "Category", "Quantity in Stock", "Supplier",
            "Purchase Price", "Selling Price", "Stock Entry Date"]
DEFAULT_REORDER = 20


def clean_inventory(raw: pd.DataFrame):
    """Return (clean_df, log) where log lists every preprocessing action taken."""
    log = []
    df = raw.copy()
    df.columns = [str(c).strip() for c in df.columns]
    missing = [c for c in REQUIRED if c not in df.columns]
    if missing:
        raise ValueError("Missing required column(s): " + ", ".join(missing))
    log.append(f"Loaded {len(df)} rows x {df.shape[1]} columns.")

    # --- text formatting -------------------------------------------------
    for c in ["Product ID", "Product Name", "Category", "Supplier"]:
        df[c] = df[c].apply(lambda x: x.strip() if isinstance(x, str) else x).replace("", np.nan)
    df["Category"] = df["Category"].apply(lambda x: x.title() if isinstance(x, str) else x)
    df["Product ID"] = df["Product ID"].apply(lambda x: x.upper() if isinstance(x, str) else x)
    log.append("Formatting: trimmed whitespace and standardised Category/Product ID casing.")

    # --- duplicates --------------------------------------------------------
    n = len(df)
    df = df.drop_duplicates()
    df = df.dropna(subset=["Product ID"])
    df = df.drop_duplicates(subset=["Product ID"], keep="last").reset_index(drop=True)
    if n - len(df):
        log.append(f"Duplicates: removed {n - len(df)} duplicate / ID-less record(s).")

    # --- missing values & validation --------------------------------------
    for c, fill in [("Category", "Uncategorized"), ("Supplier", "Unknown"), ("Product Name", "Unnamed Product")]:
        k = int(df[c].isna().sum())
        if k:
            df[c] = df[c].fillna(fill)
            log.append(f"Missing values: filled {k} blank '{c}' value(s) with '{fill}'.")

    for c in ["Quantity in Stock", "Purchase Price", "Selling Price"]:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    for c in ["Purchase Price", "Selling Price"]:
        bad = df[c].isna() | (df[c] <= 0)
        if bad.any():
            med = df.loc[~bad].groupby("Category")[c].transform("median")
            overall = df.loc[~bad, c].median()
            df.loc[bad, c] = df.loc[bad, "Category"].map(df.loc[~bad].groupby("Category")[c].median()).fillna(overall)
            log.append(f"Validation: replaced {int(bad.sum())} missing/invalid '{c}' value(s) with the category median.")
    q_bad = df["Quantity in Stock"].isna() | (df["Quantity in Stock"] < 0)
    if q_bad.any():
        log.append(f"Validation: set {int(q_bad.sum())} missing/negative quantity value(s) to 0.")
    df["Quantity in Stock"] = df["Quantity in Stock"].where(~q_bad, 0).round().astype(int)

    sell_lt_cost = int((df["Selling Price"] < df["Purchase Price"]).sum())
    if sell_lt_cost:
        log.append(f"Validation warning: {sell_lt_cost} product(s) are priced below cost (kept, flagged in Margin %).")

    df["Stock Entry Date"] = pd.to_datetime(df["Stock Entry Date"], errors="coerce")
    bad_d = int(df["Stock Entry Date"].isna().sum())
    if bad_d:
        df["Stock Entry Date"] = df["Stock Entry Date"].fillna(df["Stock Entry Date"].median())
        log.append(f"Formatting: {bad_d} unreadable date(s) replaced with the median entry date.")

    if "Reorder Level" in df.columns:
        df["Reorder Level"] = pd.to_numeric(df["Reorder Level"], errors="coerce").fillna(DEFAULT_REORDER).clip(lower=0).round().astype(int)
    else:
        df["Reorder Level"] = DEFAULT_REORDER
        log.append(f"Feature: no 'Reorder Level' column found, default of {DEFAULT_REORDER} units used.")

    # --- derived features / feature selection -----------------------------
    df["Stock Value"] = (df["Quantity in Stock"] * df["Purchase Price"]).round(2)
    df["Retail Value"] = (df["Quantity in Stock"] * df["Selling Price"]).round(2)
    df["Margin %"] = ((df["Selling Price"] - df["Purchase Price"]) / df["Selling Price"] * 100).round(1)
    keep = ["Product ID", "Product Name", "Category", "Supplier", "Quantity in Stock", "Reorder Level",
            "Purchase Price", "Selling Price", "Stock Entry Date", "Stock Value", "Retail Value", "Margin %"]
    df = df[keep]
    log.append("Feature selection: kept 9 core columns and derived Stock Value, Retail Value, Margin %.")

    df = assign_status(df)
    log.append("Stock Status recalculated from quantity vs reorder level (consistent for every record).")
    log.append(f"Final clean dataset: {len(df)} products.")
    return df, log


def assign_status(df: pd.DataFrame, critical_ratio: float = 0.5) -> pd.DataFrame:
    df = df.copy()
    q, r = df["Quantity in Stock"], df["Reorder Level"]
    df["Stock Status"] = np.select([q <= 0, q <= r * critical_ratio, q <= r],
                                   ["Out of Stock", "Critical", "Low Stock"], "In Stock")
    return df


def clean_sales(raw: pd.DataFrame, inv: pd.DataFrame):
    """Clean sales history (Date, Product ID, Units Sold)."""
    log = []
    df = raw.copy()
    df.columns = [str(c).strip() for c in df.columns]
    need = ["Date", "Product ID", "Units Sold"]
    miss = [c for c in need if c not in df.columns]
    if miss:
        raise ValueError("Sales file is missing column(s): " + ", ".join(miss))
    df = df[need]
    n = len(df)
    df["Product ID"] = df["Product ID"].astype(str).str.strip().str.upper()
    df["Date"] = pd.to_datetime(df["Date"], errors="coerce")
    df["Units Sold"] = pd.to_numeric(df["Units Sold"], errors="coerce")
    df = df.dropna()
    df = df[df["Units Sold"] >= 0]
    log.append(f"Sales: removed {n - len(df)} invalid (missing date/units or negative) row(s).")
    n = len(df)
    df = df.drop_duplicates()
    log.append(f"Sales: removed {n - len(df)} duplicate row(s).")
    n = len(df)
    df = df[df["Product ID"].isin(inv["Product ID"])]
    if n - len(df):
        log.append(f"Sales: dropped {n - len(df)} row(s) for products not in the inventory.")
    df["Units Sold"] = df["Units Sold"].astype(int)
    log.append(f"Sales: {len(df)} clean records covering {df['Date'].min():%d %b %Y} - {df['Date'].max():%d %b %Y}.")
    return df.reset_index(drop=True), log
