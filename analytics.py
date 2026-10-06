"""Inventory analytics: KPIs, product movement, restocking, supplier and trend analysis, insights."""
import numpy as np
import pandas as pd

OVERSTOCK_WEEKS = 26


def kpis(inv: pd.DataFrame) -> dict:
    return {
        "Total Products": len(inv),
        "Total Categories": inv["Category"].nunique(),
        "Available Stock (units)": int(inv["Quantity in Stock"].sum()),
        "Low Stock Products": int(inv["Stock Status"].isin(["Low Stock", "Critical"]).sum()),
        "Out-of-Stock Products": int((inv["Stock Status"] == "Out of Stock").sum()),
        "Inventory Value": float(inv["Stock Value"].sum()),
    }


def recent_weekly_demand(sales, weeks: int = 12) -> pd.Series:
    if sales is None or sales.empty:
        return pd.Series(dtype=float)
    start = sales["Date"].max() - pd.Timedelta(weeks=weeks)
    return sales[sales["Date"] > start].groupby("Product ID")["Units Sold"].sum() / weeks


def movement(inv: pd.DataFrame, sales, overstock_weeks: int = OVERSTOCK_WEEKS) -> pd.DataFrame:
    """Add average weekly demand, weeks of cover, fast/slow classification and overstock flag."""
    m = inv.copy()
    d = recent_weekly_demand(sales).rename("Avg Weekly Demand")
    m = m.merge(d, left_on="Product ID", right_index=True, how="left")
    m["Avg Weekly Demand"] = m["Avg Weekly Demand"].fillna(0.0)
    m["Weeks of Cover"] = np.where(m["Avg Weekly Demand"] > 0, m["Quantity in Stock"] / m["Avg Weekly Demand"].replace(0, np.nan), 999.0)
    m["Weeks of Cover"] = m["Weeks of Cover"].clip(upper=999).round(1)
    pos = m.loc[m["Avg Weekly Demand"] > 0, "Avg Weekly Demand"]
    q75, q25 = (pos.quantile(.75), pos.quantile(.25)) if len(pos) else (np.inf, 0)
    m["Movement"] = np.select([m["Avg Weekly Demand"] >= q75, m["Avg Weekly Demand"] <= q25],
                              ["Fast-moving", "Slow-moving"], "Medium")
    m["Overstocked"] = (m["Weeks of Cover"] > overstock_weeks) & (m["Quantity in Stock"] > 0)
    return m


def restock_plan(m: pd.DataFrame, forecast_weekly: pd.Series | None = None,
                 lead_weeks: int = 2, safety_weeks: int = 2) -> pd.DataFrame:
    r = m.copy()
    fw = r["Product ID"].map(forecast_weekly) if forecast_weekly is not None else np.nan
    r["Forecast Weekly Demand"] = pd.Series(fw, index=r.index).fillna(r["Avg Weekly Demand"]).round(1)
    target = np.maximum(np.ceil(r["Forecast Weekly Demand"] * (lead_weeks + safety_weeks)), r["Reorder Level"])
    r["Target Stock"] = target.astype(int)
    r["Suggested Order Qty"] = np.maximum(0, r["Target Stock"] - r["Quantity in Stock"]).astype(int)
    r["Order Cost"] = (r["Suggested Order Qty"] * r["Purchase Price"]).round(2)
    r["Priority"] = np.select([r["Stock Status"].isin(["Out of Stock", "Critical"]), r["Stock Status"] == "Low Stock"],
                              ["Urgent", "High"], "Normal")
    r = r[r["Suggested Order Qty"] > 0]
    order = {"Urgent": 0, "High": 1, "Normal": 2}
    r = r.assign(_o=r["Priority"].map(order)).sort_values(["_o", "Order Cost"], ascending=[True, False]).drop(columns="_o")
    return r[["Product ID", "Product Name", "Category", "Supplier", "Quantity in Stock", "Reorder Level",
              "Forecast Weekly Demand", "Target Stock", "Suggested Order Qty", "Order Cost", "Priority"]].reset_index(drop=True)


def sales_with_prices(inv: pd.DataFrame, sales: pd.DataFrame) -> pd.DataFrame:
    s = sales.merge(inv[["Product ID", "Product Name", "Category", "Supplier", "Selling Price", "Purchase Price"]], on="Product ID", how="inner")
    s["Revenue"] = s["Units Sold"] * s["Selling Price"]
    s["Profit"] = s["Units Sold"] * (s["Selling Price"] - s["Purchase Price"])
    return s


def monthly_trends(inv: pd.DataFrame, sales) -> tuple[pd.DataFrame, pd.DataFrame]:
    """(monthly sales units/revenue, monthly stock entries)."""
    entries = (inv.assign(Month=inv["Stock Entry Date"].dt.to_period("M").dt.to_timestamp())
               .groupby("Month").agg(**{"Products Added": ("Product ID", "count"), "Units Added": ("Quantity in Stock", "sum")}).reset_index())
    if sales is None or sales.empty:
        return pd.DataFrame(), entries
    s = sales_with_prices(inv, sales)
    s["Month"] = s["Date"].dt.to_period("M").dt.to_timestamp()
    sm = s.groupby("Month").agg(**{"Units Sold": ("Units Sold", "sum"), "Revenue": ("Revenue", "sum")}).reset_index()
    return sm, entries


def top_selling(inv, sales, n: int = 10) -> pd.DataFrame:
    if sales is None or sales.empty:
        return pd.DataFrame()
    s = sales_with_prices(inv, sales)
    return (s.groupby(["Product ID", "Product Name", "Category"]).agg(**{"Units Sold": ("Units Sold", "sum"), "Revenue": ("Revenue", "sum"), "Profit": ("Profit", "sum")})
            .reset_index().sort_values("Units Sold", ascending=False).head(n))


def supplier_performance(m: pd.DataFrame, sales) -> pd.DataFrame:
    g = m.groupby("Supplier").agg(**{
        "Products": ("Product ID", "count"),
        "Units in Stock": ("Quantity in Stock", "sum"),
        "Inventory Value": ("Stock Value", "sum"),
        "Avg Margin %": ("Margin %", "mean"),
        "Stock-outs": ("Stock Status", lambda x: int((x == "Out of Stock").sum())),
        "Low/Critical": ("Stock Status", lambda x: int(x.isin(["Low Stock", "Critical"]).sum())),
    }).reset_index()
    g["Stock Availability %"] = ((1 - g["Stock-outs"] / g["Products"]) * 100).round(1)
    if sales is not None and not sales.empty:
        s = sales_with_prices(m, sales).groupby("Supplier").agg(**{"Units Sold": ("Units Sold", "sum"), "Revenue": ("Revenue", "sum")}).reset_index()
        g = g.merge(s, on="Supplier", how="left")
    g["Avg Margin %"] = g["Avg Margin %"].round(1)
    return g.sort_values("Inventory Value", ascending=False)


def category_performance(m: pd.DataFrame, sales) -> pd.DataFrame:
    g = m.groupby("Category").agg(**{"Products": ("Product ID", "count"), "Units in Stock": ("Quantity in Stock", "sum"),
                                     "Inventory Value": ("Stock Value", "sum"), "Avg Margin %": ("Margin %", "mean"),
                                     "Avg Weeks of Cover": ("Weeks of Cover", lambda x: x.clip(upper=104).mean())}).reset_index()
    if sales is not None and not sales.empty:
        s = sales_with_prices(m, sales).groupby("Category").agg(**{"Units Sold": ("Units Sold", "sum"), "Revenue": ("Revenue", "sum"), "Profit": ("Profit", "sum")}).reset_index()
        g = g.merge(s, on="Category", how="left")
    return g.round(1).sort_values("Inventory Value", ascending=False)


def generate_insights(m: pd.DataFrame, sales, restock: pd.DataFrame) -> list[str]:
    out = []
    oos = m[m["Stock Status"] == "Out of Stock"]
    crit = m[m["Stock Status"] == "Critical"]
    if len(oos):
        out.append(f"🔴 {len(oos)} product(s) are out of stock, including: {', '.join(oos['Product Name'].head(3))}. Sales are being lost on these items.")
    if len(crit):
        out.append(f"🟠 {len(crit)} product(s) are at critical levels (below half of their reorder level) and need immediate ordering.")
    fast = m[m["Movement"] == "Fast-moving"].sort_values("Avg Weekly Demand", ascending=False)
    if len(fast):
        out.append(f"🚀 Fast movers: {', '.join(fast['Product Name'].head(3))}. Keep these well stocked; they drive the bulk of unit sales.")
    over = m[m["Overstocked"]]
    if len(over):
        out.append(f"📦 {len(over)} item(s) hold more than {OVERSTOCK_WEEKS} weeks of stock, tying up ${over['Stock Value'].sum():,.0f} "
                   f"({over['Stock Value'].sum() / max(m['Stock Value'].sum(), 1) * 100:.0f}% of inventory value). Pause reordering and consider promotions.")
    slow = m[(m["Movement"] == "Slow-moving") & (m["Quantity in Stock"] > 0)]
    if len(slow):
        out.append(f"🐢 {len(slow)} slow-moving product(s) hold ${slow['Stock Value'].sum():,.0f} of stock. Review pricing or reduce order sizes.")
    cp = category_performance(m, sales)
    if "Revenue" in cp.columns and cp["Revenue"].notna().any():
        top = cp.sort_values("Revenue", ascending=False).iloc[0]
        out.append(f"🏆 '{top['Category']}' is the top revenue category (${top['Revenue']:,.0f}); '{cp.sort_values('Avg Margin %').iloc[-1]['Category']}' has the best average margin.")
    sp = supplier_performance(m, sales)
    worst = sp.sort_values("Low/Critical", ascending=False).iloc[0]
    if worst["Low/Critical"] + worst["Stock-outs"] > 0:
        out.append(f"🚚 Supplier '{worst['Supplier']}' has the most low/critical items ({int(worst['Low/Critical'])}) and {int(worst['Stock-outs'])} stock-out(s). Review lead times.")
    if len(restock):
        out.append(f"🛒 Recommended restock: {len(restock)} product(s), {int(restock['Suggested Order Qty'].sum()):,} units, "
                   f"estimated cost ${restock['Order Cost'].sum():,.0f}. Order {int((restock['Priority'] == 'Urgent').sum())} urgent item(s) first.")
    return out
