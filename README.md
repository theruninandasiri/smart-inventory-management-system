# 📦 Smart Inventory Management System

A Data Science dashboard that helps a business monitor stock, spot shortages, forecast demand and
generate restocking recommendations. Built for **Sqrock IT Solutions – Data-Science Internship, Phase 2, Task 3**.

## Features (mapped to the task brief)

| # | Requirement | Where |
|---|-------------|-------|
| 1 | Inventory dataset management | `data_gen.py` (sample data), upload your own CSV/Excel in the sidebar |
| 2 | Cleaning & preprocessing | `processing.py`, shown on the **Data Preparation** page with a full log |
| 3 | Inventory dashboard (KPI cards) | **Dashboard** page |
| 4 | Analysis & visualisation | **Analysis** page (stock, category, monthly trends, value Pareto, suppliers, top sellers) |
| 5 | Low-stock alert system | **Stock Alerts** page (out-of-stock / critical / low) |
| 6 | Demand forecasting | `forecasting.py`, **Demand Forecast** page (Moving Average, Linear Regression, Random Forest + back-test) |
| 7 | Insights & recommendations | **Insights & Restocking** page (fast/slow movers, overstock, purchase plan) |
| 8 | Report generation | **Reports** page (HTML report + Excel workbook) |
| 9 | Search & filter | **Inventory Explorer** page |
| 10 | User-friendly interface | Sidebar navigation, KPI cards, charts, tables, alert banners |

## Project structure

```
app.py          Streamlit UI (all pages)
data_gen.py     Sample inventory + weekly sales generator (with injected data-quality issues)
processing.py   Cleaning, validation, derived features, stock status
analytics.py    KPIs, movement analysis, restock plan, supplier/category analysis, insights
forecasting.py  Demand forecasting models and back-testing
reporting.py    HTML report and Excel export
requirements.txt
```

## Run locally

```bash
pip install -r requirements.txt
streamlit run app.py
```

## Using your own data

Choose **Upload my own** in the sidebar.

* Inventory file columns: `Product ID, Product Name, Category, Quantity in Stock, Supplier, Purchase Price, Selling Price, Stock Entry Date` (optional `Reorder Level`)
* Sales file columns (optional, needed for forecasting): `Date, Product ID, Units Sold`

## How it works

* **Stock status** is derived: `Out of Stock` (0 units), `Critical` (≤ 50% of reorder level, adjustable), `Low Stock` (≤ reorder level), otherwise `In Stock`.
* **Movement**: average weekly demand over the last 12 weeks. Top 25% = fast-moving, bottom 25% = slow-moving. Over 26 weeks of cover = overstocked (adjustable).
* **Forecasting**: weekly sales are turned into lagged features (previous 4 weeks) and forecast recursively. Each model is back-tested on the most recent unseen weeks (MAE, RMSE, WAPE).
* **Restocking**: `target stock = forecast weekly demand × (lead time + safety weeks)`, never below the reorder level; order quantity = target − current stock.

## Deploy (free) on Streamlit Community Cloud

1. Push this folder to a GitHub repository.
2. Go to <https://share.streamlit.io>, click **New app**, choose the repo and set the main file to `app.py`.
3. Copy the live URL for your submission.

## Submission checklist

- [ ] Source code on GitHub
- [ ] Live deployed link
- [ ] LinkedIn post with screenshots, technologies used, learnings, tagging **Sqrock IT Solutions**

## Technologies

Python · Pandas · NumPy · Plotly · Scikit-learn · Streamlit · OpenPyXL
