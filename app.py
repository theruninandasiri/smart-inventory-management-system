import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from analytics import (generate_insights, category_performance, kpis, monthly_trends, movement,
                       restock_plan, supplier_performance, top_selling)
from data_gen import generate
from forecasting import METHODS, forecast, forecast_all, weekly_series
from processing import assign_status, clean_inventory, clean_sales
from reporting import build_excel, build_html

st.set_page_config(page_title="Smart Inventory", page_icon="📦", layout="wide")

STATUS_COLORS = {"In Stock": "#10b981", "Low Stock": "#f59e0b", "Critical": "#f97316", "Out of Stock": "#ef4444"}

# ----------------------------------------------------------------------------- look & feel
# Change these to restyle the whole app.
FONT = "'Times New Roman', Times, serif"
BG_COLOR = "#e8f3f1"          # main page background (soft mint)
SIDEBAR_COLOR = "#cfe6e1"     # sidebar background
TEXT_COLOR = "#1f2937"
ACCENT = "#0f766e"

st.markdown(f"""<style>
.stApp {{ background-color: {BG_COLOR}; }}
[data-testid="stSidebar"] {{ background-color: {SIDEBAR_COLOR}; }}
[data-testid="stHeader"] {{ background: transparent; }}
.block-container {{ padding-top: 1.6rem; }}

/* Times New Roman for text (icons are left alone so they keep rendering) */
html, body, .stApp, .stApp p, .stApp li, .stApp label, .stApp h1, .stApp h2, .stApp h3, .stApp h4,
.stApp button, .stApp input, .stApp textarea, .stApp table, .stApp th, .stApp td,
[data-testid="stMetricLabel"] *, [data-testid="stMetricValue"], [data-testid="stCaptionContainer"] *,
[data-testid="stSidebar"] p, [data-testid="stSidebar"] label, [data-testid="stSidebar"] h1,
[data-baseweb="tab"] p, [data-baseweb="select"] div, [data-testid="stAlert"] p {{
    font-family: {FONT} !important;
}}
.stApp, .stApp p, .stApp li, .stApp label, .stApp h1, .stApp h2, .stApp h3, .stApp h4 {{ color: {TEXT_COLOR}; }}
[data-testid="stMetricValue"] {{ font-size: 1.6rem; color: {ACCENT}; }}
[data-testid="stVerticalBlockBorderWrapper"] {{ background-color: rgba(255,255,255,0.55); }}
</style>""", unsafe_allow_html=True)

# Make every Plotly chart use the same font and a transparent background
import plotly.io as pio
from streamlit.delta_generator import DeltaGenerator

pio.templates["inventory"] = go.layout.Template(layout=dict(
    font=dict(family="Times New Roman, Times, serif", size=14, color=TEXT_COLOR),
    paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(255,255,255,0.6)"))
pio.templates.default = "inventory"
_orig_plotly_chart = DeltaGenerator.plotly_chart


def _plotly_chart(self, fig, *args, **kwargs):
    kwargs.setdefault("theme", None)  # keep our template instead of Streamlit's own fonts
    return _orig_plotly_chart(self, fig, *args, **kwargs)


DeltaGenerator.plotly_chart = _plotly_chart


#Data Loading
@st.cache_data(show_spinner=False)
def load_sample():
    return generate()


@st.cache_data(show_spinner=False)
def prepare(inv_raw, sales_raw):
    inv, inv_log = clean_inventory(inv_raw)
    if sales_raw is not None:
        sales, sales_log = clean_sales(sales_raw, inv)
    else:
        sales, sales_log = None, []
    return inv, inv_log, sales, sales_log


@st.cache_data(show_spinner=False)
def cached_forecast_all(sales, horizon, method):
    return forecast_all(sales, horizon, method)


def read_any(file):
    return pd.read_excel(file) if file.name.lower().endswith(("xlsx", "xls")) else pd.read_csv(file)


st.sidebar.title("Smart Inventory Management System")
source = st.sidebar.radio("Data source", ["Sample dataset", "Upload my own"], horizontal=True)
inv_raw = sales_raw = None
if source == "Sample dataset":
    inv_raw, sales_raw = load_sample()
else:
    f_inv = st.sidebar.file_uploader("Inventory file (CSV / Excel)", type=["csv", "xlsx", "xls"])
    f_sales = st.sidebar.file_uploader("Sales history (optional)", type=["csv", "xlsx", "xls"],
                                       help="Columns: Date, Product ID, Units Sold. Needed for forecasting and movement analysis.")
    if f_inv is None:
        st.title("Smart Inventory Management System")
        st.info("Upload an inventory file to begin. Required columns: " + ", ".join(
            ["Product ID", "Product Name", "Category", "Quantity in Stock", "Supplier", "Purchase Price", "Selling Price", "Stock Entry Date"])
            + " (optional: Reorder Level).")
        st.stop()
    inv_raw = read_any(f_inv)
    sales_raw = read_any(f_sales) if f_sales is not None else None

try:
    inv, inv_log, sales, sales_log = prepare(inv_raw, sales_raw)
except ValueError as e:
    st.error(f"Could not process the uploaded data: {e}")
    st.stop()

with st.sidebar.expander("🌣 Alert & planning settings"):
    critical_ratio = st.slider("Critical level (% of reorder level)", 10, 90, 50, 5) / 100
    lead_weeks = st.number_input("Supplier lead time (weeks)", 1, 12, 2)
    safety_weeks = st.number_input("Safety stock (weeks of demand)", 0, 12, 2)
    overstock_weeks = st.number_input("Overstock threshold (weeks of cover)", 8, 104, 26)

inv = assign_status(inv, critical_ratio)
m = movement(inv, sales, overstock_weeks)
has_sales = sales is not None and not sales.empty
n_alerts = int((inv["Stock Status"] != "In Stock").sum())

PAGES = ["⊞ Dashboard", "֎ Analysis", "⚠ Stock Alerts", "🗲 Demand Forecast", "➯ Insights & Restocking",
         "⌕ Inventory Explorer", "🛠 Data Preparation", "🗁 Reports"]
page = st.sidebar.radio("Navigation", PAGES)
st.sidebar.metric("Active stock alerts", n_alerts)
st.sidebar.caption(f"{len(inv)} products · {inv['Category'].nunique()} categories")


def forecast_weekly_series(horizon=8, method="Linear Regression"):
    if not has_sales:
        return None
    fa = cached_forecast_all(sales, horizon, method)
    return fa.set_index("Product ID")["Forecast Weekly Demand"]


#Dashboard
if page == PAGES[0]:
    st.title("Inventory Dashboard")
    k = kpis(inv)
    cols = st.columns(6)
    for col, (label, val) in zip(cols, k.items()):
        with col, st.container(border=True):
            st.metric(label, f"${val:,.0f}" if label == "Inventory Value" else f"{val:,}")

    c1, c2 = st.columns([1, 1.4])
    with c1:
        sc = inv["Stock Status"].value_counts().reset_index()
        sc.columns = ["Status", "Products"]
        fig = px.pie(sc, names="Status", values="Products", hole=.55, color="Status", color_discrete_map=STATUS_COLORS,
                     title="Stock status breakdown")
        st.plotly_chart(fig)
    with c2:
        cv = inv.groupby("Category")["Stock Value"].sum().sort_values().reset_index()
        fig = px.bar(cv, x="Stock Value", y="Category", orientation="h", title="Inventory value by category",
                     color="Stock Value", color_continuous_scale="Teal")
        fig.update_layout(coloraxis_showscale=False)
        st.plotly_chart(fig)

    c3, c4 = st.columns(2)
    with c3:
        t = inv.nlargest(10, "Stock Value").sort_values("Stock Value")
        st.plotly_chart(px.bar(t, x="Stock Value", y="Product Name", orientation="h", title="Top 10 products by inventory value",
                               color_discrete_sequence=["#0f766e"]))
    with c4:
        st.subheader("🚨 Needs attention")
        a = inv[inv["Stock Status"] != "In Stock"].sort_values("Quantity in Stock").head(8)
        if a.empty:
            st.success("All products are healthy.")
        for _, r in a.iterrows():
            msg = f"**{r['Product Name']}** — {r['Quantity in Stock']} left (reorder at {r['Reorder Level']})"
            (st.error if r["Stock Status"] in ("Out of Stock", "Critical") else st.warning)(f"{r['Stock Status']}: {msg}")

#Analysis
elif page == PAGES[1]:
    st.title("Inventory Analysis & Visualisation")
    tabs = st.tabs(["Product stock", "Category", "Monthly trends", "Inventory value", "Suppliers", "Top sellers"])
    with tabs[0]:
        n = st.slider("Products to show", 5, len(inv), min(20, len(inv)))
        order = st.radio("Order by", ["Highest stock", "Lowest stock"], horizontal=True)
        d = inv.sort_values("Quantity in Stock", ascending=(order == "Lowest stock")).head(n)
        fig = px.bar(d, x="Product Name", y="Quantity in Stock", color="Stock Status", color_discrete_map=STATUS_COLORS,
                     title="Product-wise stock distribution")
        st.plotly_chart(fig)
        st.plotly_chart(px.histogram(inv, x="Quantity in Stock", nbins=20, title="Distribution of stock quantities",
                                     color_discrete_sequence=["#0f766e"]))
    with tabs[1]:
        cp = category_performance(m, sales)
        c1, c2 = st.columns(2)
        c1.plotly_chart(px.bar(cp, x="Category", y="Units in Stock", color="Category", title="Units in stock by category"))
        c2.plotly_chart(px.treemap(inv, path=["Category", "Product Name"], values="Stock Value", title="Inventory value treemap"))
        st.dataframe(cp, hide_index=True)
    with tabs[2]:
        sm, entries = monthly_trends(inv, sales)
        if not sm.empty:
            fig = go.Figure()
            fig.add_bar(x=sm["Month"], y=sm["Units Sold"], name="Units sold", marker_color="#14b8a6")
            fig.add_scatter(x=sm["Month"], y=sm["Revenue"], name="Revenue ($)", yaxis="y2", line=dict(color="#f59e0b", width=3))
            fig.update_layout(title="Monthly sales trend", yaxis2=dict(overlaying="y", side="right", title="Revenue ($)"), yaxis_title="Units")
            st.plotly_chart(fig)
        else:
            st.info("Upload sales history to see sales trends.")
        st.plotly_chart(px.bar(entries, x="Month", y="Units Added", title="Monthly stock entries (units by stock entry date)",
                               color_discrete_sequence=["#0f766e"]))
    with tabs[3]:
        v = inv.sort_values("Stock Value", ascending=False).reset_index(drop=True)
        v["Cumulative %"] = v["Stock Value"].cumsum() / v["Stock Value"].sum() * 100
        fig = go.Figure()
        fig.add_bar(x=v["Product Name"], y=v["Stock Value"], name="Stock value", marker_color="#14b8a6")
        fig.add_scatter(x=v["Product Name"], y=v["Cumulative %"], name="Cumulative %", yaxis="y2", line=dict(color="#ef4444"))
        fig.update_layout(title="Inventory value Pareto (ABC view)", yaxis2=dict(overlaying="y", side="right", range=[0, 105], title="%"))
        st.plotly_chart(fig)
        a_items = int((v["Cumulative %"] <= 80).sum()) + 1
        st.caption(f"{a_items} products ({a_items / len(v) * 100:.0f}%) make up about 80% of inventory value — the 'A' items to track closely.")
        c1, c2 = st.columns(2)
        c1.metric("Total cost value", f"${inv['Stock Value'].sum():,.0f}")
        c2.metric("Potential retail value", f"${inv['Retail Value'].sum():,.0f}")
    with tabs[4]:
        sp = supplier_performance(m, sales)
        c1, c2 = st.columns(2)
        c1.plotly_chart(px.bar(sp, x="Supplier", y="Inventory Value", color="Supplier", title="Inventory value by supplier"))
        c2.plotly_chart(px.bar(sp, x="Supplier", y="Stock Availability %", color="Supplier", title="Stock availability by supplier (%)", range_y=[0, 100]))
        st.dataframe(sp, hide_index=True)
    with tabs[5]:
        ts = top_selling(inv, sales, 10)
        if ts.empty:
            st.info("Upload sales history to see top-selling products.")
        else:
            st.plotly_chart(px.bar(ts.sort_values("Units Sold"), x="Units Sold", y="Product Name", orientation="h",
                                   color="Category", title="Top 10 selling products (units)"))
            st.dataframe(ts, hide_index=True)

#Alerts
elif page == PAGES[2]:
    st.title("Low Stock Alert System")
    alerts = inv[inv["Stock Status"] != "In Stock"].copy()
    counts = alerts["Stock Status"].value_counts()
    c1, c2, c3 = st.columns(3)
    c1.metric("🔴 Out of stock", int(counts.get("Out of Stock", 0)))
    c2.metric("🟠 Critical", int(counts.get("Critical", 0)))
    c3.metric("🟡 Low stock", int(counts.get("Low Stock", 0)))
    if alerts.empty:
        st.success("No stock alerts. Inventory levels are healthy.")
    else:
        for status, fn in [("Out of Stock", st.error), ("Critical", st.error), ("Low Stock", st.warning)]:
            sub = alerts[alerts["Stock Status"] == status]
            if len(sub):
                fn(f"**{status}** ({len(sub)}): " + ", ".join(sub["Product Name"].head(6)) + ("…" if len(sub) > 6 else ""))
        sel = st.multiselect("Filter by status", ["Out of Stock", "Critical", "Low Stock"], default=["Out of Stock", "Critical", "Low Stock"])
        cat = st.multiselect("Filter by category", sorted(alerts["Category"].unique()))
        view = alerts[alerts["Stock Status"].isin(sel)]
        if cat:
            view = view[view["Category"].isin(cat)]
        view = view.assign(Shortfall=(view["Reorder Level"] - view["Quantity in Stock"]).clip(lower=0))
        st.dataframe(view[["Product ID", "Product Name", "Category", "Supplier", "Quantity in Stock", "Reorder Level", "Shortfall", "Stock Status"]]
                     .sort_values("Shortfall", ascending=False), hide_index=True)
        st.download_button("🡻 Download alert list (CSV)", view.to_csv(index=False), "stock_alerts.csv", "text/csv")
        fig = px.bar(view.sort_values("Shortfall", ascending=False).head(15), x="Product Name", y=["Quantity in Stock", "Reorder Level"],
                     barmode="group", title="Current stock vs reorder level (most urgent)")
        st.plotly_chart(fig)

#Forecast
elif page == PAGES[3]:
    st.title("Demand Forecasting")
    if not has_sales:
        st.info("Demand forecasting needs sales history. Upload a sales file (Date, Product ID, Units Sold) or use the sample dataset.")
        st.stop()
    c1, c2, c3 = st.columns([2, 1.2, 1])
    labels = ["All products (total demand)"] + [f"{r['Product ID']} · {r['Product Name']}" for _, r in inv.iterrows()]
    choice = c1.selectbox("Forecast scope", labels)
    method = c2.selectbox("Model", METHODS, index=1)
    horizon = c3.slider("Weeks ahead", 4, 26, 8)
    pid = None if choice == labels[0] else choice.split(" · ")[0]
    series = weekly_series(sales, pid)
    if len(series) < 8:
        st.warning("Not enough history for this product to forecast reliably.")
        st.stop()
    res = forecast(series, horizon, method)
    fc, bt, mt = res["forecast"], res["backtest"], res["metrics"]

    fig = go.Figure()
    fig.add_scatter(x=series.index, y=series.values, name="Historical weekly sales", line=dict(color="#0f766e"))
    if bt is not None:
        fig.add_scatter(x=bt.index, y=bt["Predicted"], name="Back-test prediction", line=dict(color="#a78bfa", dash="dot"))
    fig.add_scatter(x=fc.index, y=fc.values, name="Forecast", line=dict(color="#f59e0b", dash="dash", width=3))
    fig.update_layout(title=f"Weekly demand — {method}", yaxis_title="Units", hovermode="x unified")
    st.plotly_chart(fig)

    m1, m2, m3, m4 = st.columns(4)
    m1.metric(f"Forecast units ({horizon}w)", f"{fc.sum():,.0f}")
    m2.metric("Avg weekly forecast", f"{fc.mean():,.1f}")
    m3.metric("Back-test MAE", f"{mt['MAE']:.2f}" if not np.isnan(mt["MAE"]) else "n/a")
    m4.metric("Back-test error (WAPE)", f"{mt['WAPE %']:.1f}%" if not np.isnan(mt["WAPE %"]) else "n/a")
    st.caption("Back-test: the model is trained on earlier weeks and asked to predict the most recent weeks it has not seen.")

    if pid:
        row = inv[inv["Product ID"] == pid].iloc[0]
        need = int(np.ceil(fc.sum()))
        gap = need - row["Quantity in Stock"]
        if gap > 0:
            st.warning(f"Forecast demand over {horizon} weeks is **{need}** units but only **{row['Quantity in Stock']}** are in stock — "
                       f"plan to order about **{gap}** more (≈ ${gap * row['Purchase Price']:,.0f}).")
        else:
            st.success(f"Current stock ({row['Quantity in Stock']}) covers the forecast demand of {need} units over {horizon} weeks.")
    out = fc.reset_index()
    out.columns = ["Week ending", "Forecast units"]
    out["Forecast units"] = out["Forecast units"].round(1)
    st.dataframe(out, hide_index=True)
    st.download_button("🡻 Download forecast (CSV)", out.to_csv(index=False), "demand_forecast.csv", "text/csv")

    with st.expander("Compare models for this selection"):
        rows = []
        for mm in METHODS:
            r = forecast(series, horizon, mm)["metrics"]
            rows.append({"Model": mm, "MAE": round(r["MAE"], 2), "RMSE": round(r["RMSE"], 2), "WAPE %": round(r["WAPE %"], 1)})
        st.dataframe(pd.DataFrame(rows), hide_index=True)

#Insights
elif page == PAGES[4]:
    st.title("Insights & Restocking Recommendations")
    fw = forecast_weekly_series()
    restock = restock_plan(m, fw, lead_weeks, safety_weeks)
    for line in generate_insights(m, sales, restock):
        st.markdown(f"- {line}")
    if not has_sales:
        st.info("Add sales history for movement analysis and demand-based restocking.")
    t1, t2, t3, t4, t5 = st.tabs(["Restocking plan", "Fast-moving", "Slow-moving", "Overstocked", "Category performance"])
    cols = ["Product ID", "Product Name", "Category", "Quantity in Stock", "Avg Weekly Demand", "Weeks of Cover", "Stock Value"]
    with t1:
        if restock.empty:
            st.success("No restocking needed right now.")
        else:
            c1, c2, c3 = st.columns(3)
            c1.metric("Products to order", len(restock))
            c2.metric("Units to order", f"{restock['Suggested Order Qty'].sum():,}")
            c3.metric("Estimated cost", f"${restock['Order Cost'].sum():,.0f}")
            st.dataframe(restock, hide_index=True)
            st.caption(f"Target stock = forecast weekly demand × (lead time {lead_weeks}w + safety {safety_weeks}w), never below the reorder level.")
            st.download_button("🡻 Download purchase list (CSV)", restock.to_csv(index=False), "restock_plan.csv", "text/csv")
    with t2:
        st.dataframe(m[m["Movement"] == "Fast-moving"].sort_values("Avg Weekly Demand", ascending=False)[cols], hide_index=True)
    with t3:
        st.dataframe(m[m["Movement"] == "Slow-moving"].sort_values("Stock Value", ascending=False)[cols], hide_index=True)
    with t4:
        o = m[m["Overstocked"]].sort_values("Stock Value", ascending=False)
        st.metric("Capital tied up in overstock", f"${o['Stock Value'].sum():,.0f}")
        st.dataframe(o[cols], hide_index=True)
    with t5:
        cp = category_performance(m, sales)
        st.dataframe(cp, hide_index=True)
        if "Revenue" in cp.columns:
            st.plotly_chart(px.scatter(cp, x="Avg Margin %", y="Revenue", size="Inventory Value", color="Category",
                                       title="Category performance: margin vs revenue (bubble = inventory value)"))

#Explorer
elif page == PAGES[5]:
    st.title("Inventory Explorer")
    c1, c2, c3 = st.columns([2, 2, 2])
    q = c1.text_input("🔍︎ Search product name or ID")
    cats = c2.multiselect("Category", sorted(inv["Category"].unique()))
    stat = c3.multiselect("Stock status", list(STATUS_COLORS))
    c4, c5, c6 = st.columns(3)
    sort_by = c4.selectbox("Sort by", ["Quantity in Stock", "Stock Value", "Selling Price", "Product Name", "Stock Entry Date"])
    asc = c5.radio("Order", ["Descending", "Ascending"], horizontal=True) == "Ascending"
    sup = c6.multiselect("Supplier", sorted(inv["Supplier"].unique()))
    v = inv.copy()
    if q:
        v = v[v["Product Name"].str.contains(q, case=False, na=False) | v["Product ID"].str.contains(q, case=False, na=False)]
    if cats:
        v = v[v["Category"].isin(cats)]
    if stat:
        v = v[v["Stock Status"].isin(stat)]
    if sup:
        v = v[v["Supplier"].isin(sup)]
    v = v.sort_values(sort_by, ascending=asc)
    st.caption(f"{len(v)} of {len(inv)} products · value ${v['Stock Value'].sum():,.0f}")
    st.dataframe(v, hide_index=True, column_config={
        "Stock Entry Date": st.column_config.DateColumn(format="YYYY-MM-DD"),
        "Purchase Price": st.column_config.NumberColumn(format="$%.2f"),
        "Selling Price": st.column_config.NumberColumn(format="$%.2f"),
        "Stock Value": st.column_config.NumberColumn(format="$%.2f"),
        "Retail Value": st.column_config.NumberColumn(format="$%.2f"),
    })
    st.download_button("🡻 Download filtered view (CSV)", v.to_csv(index=False), "inventory_filtered.csv", "text/csv")

#Data Preperation
elif page == PAGES[6]:
    st.title("Data Cleaning & Preprocessing")
    c1, c2 = st.columns(2)
    c1.metric("Raw inventory rows", len(inv_raw))
    c2.metric("Clean inventory rows", len(inv))
    st.subheader("Preprocessing log")
    for line in inv_log + sales_log:
        st.markdown(f"- {line}")
    t1, t2, t3 = st.tabs(["Raw data", "Clean data", "Data quality"])
    t1.dataframe(inv_raw, hide_index=True)
    t2.dataframe(inv, hide_index=True)
    with t3:
        mv = inv_raw.isna().sum().rename("Missing values").to_frame()
        mv["Raw data type"] = inv_raw.dtypes.astype(str)
        st.dataframe(mv)
        st.write(f"Duplicate rows in raw data: **{int(inv_raw.duplicated().sum())}**")

#Reports
else:
    st.title("Report Generation")
    sections = st.multiselect("Include sections", ["Inventory Summary", "Product Analysis", "Forecast Results", "Stock Alerts", "Business Recommendations"],
                              default=["Inventory Summary", "Product Analysis", "Forecast Results", "Stock Alerts", "Business Recommendations"])
    horizon = st.slider("Forecast horizon (weeks)", 4, 26, 8)
    fw = forecast_weekly_series(horizon)
    restock = restock_plan(m, fw, lead_weeks, safety_weeks)
    alerts = inv[inv["Stock Status"] != "In Stock"].sort_values("Quantity in Stock")
    top = top_selling(inv, sales, 10)
    cats = category_performance(m, sales)
    fdf = None
    if has_sales:
        fdf = cached_forecast_all(sales, horizon, "Linear Regression").merge(inv[["Product ID", "Product Name", "Quantity in Stock"]], on="Product ID")
        fdf = fdf[["Product ID", "Product Name", "Quantity in Stock", "Forecast Weekly Demand", f"Forecast Units ({horizon}w)"]].round(1)
        fdf = fdf.sort_values(f"Forecast Units ({horizon}w)", ascending=False)
    insights = generate_insights(m, sales, restock)
    report_html = build_html(kpis(inv), inv, alerts, top, cats, fdf, restock, insights, sections)

    c1, c2, c3 = st.columns(3)
    c1.download_button("🡻 HTML report", report_html, "inventory_report.html", "text/html")
    sheets = {"Inventory": inv, "Alerts": alerts, "Restock Plan": restock, "Forecast": fdf, "Categories": cats, "Top Sellers": top}
    c2.download_button("🡻 Excel workbook", build_excel(sheets), "inventory_report.xlsx",
                       "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    c3.download_button("🡻 Inventory CSV", inv.to_csv(index=False), "inventory_clean.csv", "text/csv")
    st.subheader("Preview")
    if hasattr(st, "iframe"):  # newer Streamlit; components.v1.html is deprecated there
        st.iframe(report_html, height=700)
    else:
        import streamlit.components.v1 as components
        components.html(report_html, height=700, scrolling=True)
