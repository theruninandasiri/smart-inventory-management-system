"""Sample data generator for the Smart Inventory Management System.

Creates a realistic (and deliberately slightly messy) inventory table plus
weekly sales history so that every feature of the app can be demonstrated.
Run `python data_gen.py` to also write inventory.csv and sales.csv.
"""
import numpy as np
import pandas as pd

PRODUCTS = {
    "Electronics": ["Wireless Mouse", "USB-C Cable", "Bluetooth Speaker", "Webcam HD", "Power Bank 10000mAh",
                    "Mechanical Keyboard", "Laptop Stand", "HDMI Adapter", "Noise-Cancelling Earbuds", "LED Desk Lamp"],
    "Office Supplies": ["A4 Paper Ream", "Ballpoint Pens (Box)", "Stapler", "Sticky Notes Pack", "Whiteboard Markers",
                        "File Folders (Pack)", "Desk Organizer", "Highlighters (Set)", "Printer Ink Cartridge", "Notebook A5"],
    "Furniture": ["Ergonomic Chair", "Standing Desk", "Bookshelf", "Filing Cabinet", "Visitor Chair",
                  "Conference Table", "Monitor Arm", "Footrest", "Storage Locker", "Reception Sofa"],
    "Groceries": ["Instant Coffee 200g", "Green Tea Box", "Sugar 1kg", "Bottled Water 1L (Case)", "Biscuits Assorted",
                  "Milk Powder 400g", "Cooking Oil 1L", "Basmati Rice 5kg", "Fruit Juice 1L", "Oat Cereal 500g"],
    "Cleaning": ["Hand Sanitizer 500ml", "Disinfectant Spray", "Floor Cleaner 1L", "Trash Bags (Roll)", "Paper Towels (Pack)",
                 "Dish Soap 750ml", "Glass Cleaner", "Microfiber Cloths", "Mop Set", "Toilet Cleaner"],
    "Hardware": ["Cordless Drill", "Screwdriver Set", "Measuring Tape", "Safety Gloves", "LED Bulb 12W",
                 "Extension Cord 5m", "Adjustable Wrench", "Utility Knife", "Ladder 6ft", "Toolbox 17in"],
}
SUPPLIERS = ["TechSource Ltd", "OfficeWorld Supplies", "Prime Furnishings", "FreshMart Wholesale", "CleanCo Distributors", "BuildRight Traders"]
CAT_SUPPLIER = dict(zip(PRODUCTS.keys(), SUPPLIERS))
PRICE_RANGE = {"Electronics": (8, 90), "Office Supplies": (1, 25), "Furniture": (60, 450),
               "Groceries": (1, 20), "Cleaning": (2, 18), "Hardware": (4, 120)}
WEEKS = 78


def generate(seed: int = 42):
    rng = np.random.default_rng(seed)
    end = pd.Timestamp.today().normalize()
    end = end - pd.Timedelta(days=end.weekday() + 1)  # last Sunday
    weeks = pd.date_range(end=end, periods=WEEKS, freq="W")

    inv_rows, sales_rows = [], []
    pid = 1
    for cat, names in PRODUCTS.items():
        lo, hi = PRICE_RANGE[cat]
        for name in names:
            product_id = f"P{pid:03d}"
            pid += 1
            cost = round(float(rng.uniform(lo, hi)), 2)
            price = round(cost * float(rng.uniform(1.15, 1.6)), 2)
            scale = 1 / (1 + cost / 40)  # cheaper items sell more
            base = max(1.0, float(rng.lognormal(2.2, 0.6)) * (0.4 + 2 * scale))
            trend = float(rng.uniform(-0.004, 0.012))
            phase = float(rng.uniform(0, 2 * np.pi))
            t = np.arange(WEEKS)
            lam = base * (1 + trend * t) * (1 + 0.25 * np.sin(2 * np.pi * t / 52 + phase))
            units = rng.poisson(np.clip(lam, 0.2, None))
            for d, u in zip(weeks, units):
                sales_rows.append((d, product_id, int(u)))

            cover = float(rng.choice([0, 0.5, 1.5, 3, 6, 10, 16, 30, 45], p=[.06, .08, .1, .14, .2, .16, .12, .09, .05]))
            qty = int(round(base * cover))
            inv_rows.append({
                "Product ID": product_id, "Product Name": name, "Category": cat,
                "Quantity in Stock": qty, "Reorder Level": int(np.ceil(base * 3)),
                "Supplier": CAT_SUPPLIER[cat] if rng.random() > 0.15 else str(rng.choice(SUPPLIERS)),
                "Purchase Price": cost, "Selling Price": price,
                "Stock Entry Date": (end - pd.Timedelta(days=int(rng.integers(3, 540)))).strftime("%Y-%m-%d"),
                "Stock Status": "In Stock",
            })

    inv = pd.DataFrame(inv_rows)
    sales = pd.DataFrame(sales_rows, columns=["Date", "Product ID", "Units Sold"])

    # ---- inject realistic data-quality problems for the cleaning step ----
    inv = pd.concat([inv, inv.sample(3, random_state=1)], ignore_index=True)       # duplicates
    inv.loc[rng.choice(len(inv), 3, replace=False), "Supplier"] = np.nan             # missing supplier
    inv.loc[rng.choice(len(inv), 2, replace=False), "Purchase Price"] = np.nan       # missing price
    inv.loc[5, "Quantity in Stock"] = -4                                              # invalid quantity
    inv.loc[[7, 12, 20, 33], "Category"] = inv.loc[[7, 12, 20, 33], "Category"].str.upper().apply(lambda s: f" {s} ")
    inv.loc[40, "Stock Entry Date"] = "N/A"                                           # bad date
    sales = pd.concat([sales, sales.sample(10, random_state=2)], ignore_index=True)  # duplicate sales rows
    sales.loc[rng.choice(len(sales), 5, replace=False), "Units Sold"] = -1           # returns / bad data
    return inv, sales


if __name__ == "__main__":
    i, s = generate()
    i.to_csv("inventory.csv", index=False)
    s.to_csv("sales.csv", index=False)
    print(f"inventory.csv: {i.shape}, sales.csv: {s.shape}")
