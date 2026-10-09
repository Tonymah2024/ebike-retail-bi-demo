# Prairie Pulse E-Bikes — Retail Analytics & BI Demo (VisiVault Analytics)

Interactive Streamlit dashboard demonstrating retail business intelligence and predictive analytics for a **fictional**
Calgary electric-bicycle retailer, *Prairie Pulse E-Bikes*.

> **SYNTHETIC DEMONSTRATION DATA.** The retailer is fictional. E-bike brands, models and CAD list prices reflect public
> market listings (Oct 2026); Calgary daily weather (Environment and Climate Change Canada) and Bank of Canada indicators
> are real. All sales, cost, inventory, customer, service and expense records are synthetic (seed 20240101).

**Pages:** Executive Overview · Sales Performance · Product & Brand Performance · Profitability · Inventory Intelligence ·
Customer Analytics · Service & Repair Analytics · Sales & Demand Forecasts · Business Scenario Simulator

**Behind the dashboard** (pre-computed): validated SQLite model (30 integrity checks), Prophet / SARIMA / XGBoost forecasts with
leakage-safe backtesting, top-down demand forecasts, RFM + K-means segmentation, seasonal reorder-point optimisation with
out-of-sample replay, and a driver-based profit simulator.

```bash
pip install -r requirements.txt
streamlit run streamlit_app.py
```

Built by [VisiVault Analytics Ltd.](https://visivaultanalytics.com)
