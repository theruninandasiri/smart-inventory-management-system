"""Report generation: self-contained HTML report and multi-sheet Excel export."""
import html
import io
from datetime import datetime

import pandas as pd

CSS = """body{font-family:"Times New Roman",Times,serif;background:#e8f3f1;max-width:1000px;margin:30px auto;color:#1f2937;padding:0 16px}
h1{color:#0f766e}h2{border-bottom:2px solid #0f766e;padding-bottom:4px;margin-top:32px}
.cards{display:flex;gap:12px;flex-wrap:wrap}.card{background:#f0fdfa;border:1px solid #99f6e4;border-radius:8px;padding:10px 16px;min-width:140px}
.card b{display:block;font-size:20px;color:#0f766e}table{border-collapse:collapse;width:100%;font-size:13px;margin:8px 0}
th{background:#0f766e;color:#fff;text-align:left}th,td{padding:6px 8px;border:1px solid #e5e7eb}tr:nth-child(even){background:#f9fafb}"""


def _table(df: pd.DataFrame, n: int = 25) -> str:
    if df is None or df.empty:
        return "<p><i>No records.</i></p>"
    return df.head(n).to_html(index=False, border=0, float_format=lambda x: f"{x:,.2f}")


def build_html(kpi: dict, inv: pd.DataFrame, alerts: pd.DataFrame, top: pd.DataFrame, cats: pd.DataFrame,
               forecast_df: pd.DataFrame | None, restock: pd.DataFrame, insights: list[str], sections: list[str]) -> str:
    p = [f"<html><head><meta charset='utf-8'><title>Inventory Report</title><style>{CSS}</style></head><body>",
         "<h1>Smart Inventory Management Report</h1>", f"<p>Generated {datetime.now():%d %b %Y, %H:%M}</p>"]
    if "Inventory Summary" in sections:
        cards = "".join(f"<div class='card'>{html.escape(k)}<b>{v:,.0f}</b></div>" if k != "Inventory Value"
                        else f"<div class='card'>{k}<b>${v:,.0f}</b></div>" for k, v in kpi.items())
        p += ["<h2>Inventory Summary</h2>", f"<div class='cards'>{cards}</div>", "<h3>Category overview</h3>", _table(cats)]
    if "Product Analysis" in sections:
        p += ["<h2>Product Analysis</h2>", "<h3>Top-selling products</h3>", _table(top, 10),
              "<h3>Highest inventory value</h3>", _table(inv.sort_values("Stock Value", ascending=False)[["Product ID", "Product Name", "Category", "Quantity in Stock", "Stock Value"]], 10)]
    if "Forecast Results" in sections:
        p += ["<h2>Forecast Results</h2>", _table(forecast_df, 20)]
    if "Stock Alerts" in sections:
        p += ["<h2>Stock Alerts</h2>", _table(alerts[["Product ID", "Product Name", "Category", "Supplier", "Quantity in Stock", "Reorder Level", "Stock Status"]], 40)]
    if "Business Recommendations" in sections:
        p += ["<h2>Business Recommendations</h2>", "<ul>" + "".join(f"<li>{html.escape(i)}</li>" for i in insights) + "</ul>",
              "<h3>Restocking plan</h3>", _table(restock, 25)]
    p.append("</body></html>")
    return "\n".join(p)


def build_excel(sheets: dict[str, pd.DataFrame]) -> bytes:
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as xw:
        for name, df in sheets.items():
            if df is not None and not df.empty:
                df.to_excel(xw, sheet_name=name[:31], index=False)
                ws = xw.sheets[name[:31]]
                for col in ws.columns:
                    ws.column_dimensions[col[0].column_letter].width = min(40, max(len(str(c.value or "")) for c in col) + 2)
    return buf.getvalue()
