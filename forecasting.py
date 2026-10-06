"""Demand forecasting: moving average, linear regression and random forest on lagged weekly sales."""
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestRegressor
from sklearn.linear_model import LinearRegression

METHODS = ["Moving Average", "Linear Regression", "Random Forest"]
N_LAGS = 4


def weekly_series(sales: pd.DataFrame, product_id: str | None = None) -> pd.Series:
    s = sales if product_id is None else sales[sales["Product ID"] == product_id]
    if s.empty:
        return pd.Series(dtype=float)
    return s.set_index("Date")["Units Sold"].resample("W").sum().astype(float)


def _predict(y: np.ndarray, horizon: int, method: str) -> np.ndarray:
    hist = list(y)
    out = []
    if method == "Moving Average" or len(y) <= N_LAGS + 3:
        w = min(4, len(y))
        for _ in range(horizon):
            v = float(np.mean(hist[-w:]))
            out.append(v)
            hist.append(v)
        return np.array(out)
    X = np.array([y[i - N_LAGS:i] for i in range(N_LAGS, len(y))])
    t = y[N_LAGS:]
    model = LinearRegression() if method == "Linear Regression" else RandomForestRegressor(
        n_estimators=150, min_samples_leaf=2, random_state=42, n_jobs=-1)
    model.fit(X, t)
    for _ in range(horizon):
        v = max(0.0, float(model.predict(np.array(hist[-N_LAGS:]).reshape(1, -1))[0]))
        out.append(v)
        hist.append(v)
    return np.array(out)


def forecast(series: pd.Series, horizon: int = 8, method: str = "Linear Regression"):
    """Forecast `horizon` weeks ahead and back-test on the last weeks of history.

    Returns dict with forecast (Series), backtest (DataFrame) and metrics.
    """
    y = series.values.astype(float)
    future_idx = pd.date_range(series.index[-1] + pd.Timedelta(weeks=1), periods=horizon, freq="W")
    fc = pd.Series(_predict(y, horizon, method), index=future_idx, name="Forecast")

    hold = max(4, min(12, len(y) // 5))
    bt = None
    metrics = {"MAE": np.nan, "RMSE": np.nan, "WAPE %": np.nan}
    if len(y) > hold + N_LAGS + 3:
        pred = _predict(y[:-hold], hold, method)
        actual = y[-hold:]
        err = actual - pred
        metrics = {"MAE": float(np.mean(np.abs(err))), "RMSE": float(np.sqrt(np.mean(err ** 2))),
                   "WAPE %": float(np.abs(err).sum() / max(actual.sum(), 1e-9) * 100)}
        bt = pd.DataFrame({"Actual": actual, "Predicted": pred}, index=series.index[-hold:])
    return {"forecast": fc, "backtest": bt, "metrics": metrics}


def forecast_all(sales: pd.DataFrame, horizon: int = 8, method: str = "Linear Regression") -> pd.DataFrame:
    """Average forecast weekly demand and total forecast units for every product."""
    rows = []
    for pid, g in sales.groupby("Product ID"):
        s = weekly_series(g)
        if len(s) < 2:
            continue
        fc = forecast(s, horizon, method)["forecast"]
        rows.append({"Product ID": pid, "Forecast Weekly Demand": fc.mean(), f"Forecast Units ({horizon}w)": fc.sum()})
    return pd.DataFrame(rows)
