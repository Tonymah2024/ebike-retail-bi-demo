"""Prairie Pulse E-Bikes - Executive BI Dashboard (VisiVault Analytics).

Run:  streamlit run dashboard/app.py
All figures are SYNTHETIC DEMONSTRATION DATA unless labelled as verified public/external data.
"""
import json
import sqlite3
import sys
from pathlib import Path

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
from src.config import BRAND, DB_PATH, SERIES, TABLES  # noqa: E402
from src.models import scenarios as scn  # noqa: E402

st.set_page_config(page_title="Prairie Pulse E-Bikes | VisiVault Analytics", page_icon="⚡", layout="wide")

st.markdown(f"""
<style>
  .block-container {{padding-top: 1.2rem; max-width: 1400px;}}
  .vv-banner {{background: linear-gradient(90deg, {BRAND['navy']} 0%, {BRAND['brand_dark']} 100%); color: #fff; padding: 14px 20px;
              border-radius: 12px; display:flex; justify-content:space-between; align-items:center; margin-bottom: 10px;}}
  .vv-banner h1 {{font-size: 1.35rem; margin:0; color:#fff;}}
  .vv-banner span {{font-size: .82rem; opacity:.85}}
  .vv-synth {{background:#fff4e5; border:1px solid #f5c37a; color:#7a4a00; padding:6px 12px; border-radius:8px; font-size:.82rem; font-weight:600;}}
  .kpi {{background:#fff; border:1px solid rgba(11,15,25,.08); border-radius:12px; padding:12px 14px; box-shadow:0 1px 2px rgba(0,0,0,.04);}}
  .kpi .l {{font-size:.74rem; color:{BRAND['muted']}; text-transform:uppercase; letter-spacing:.04em;}}
  .kpi .v {{font-size:1.45rem; font-weight:700; color:{BRAND['navy']}; margin-top:2px;}}
  .kpi .d {{font-size:.78rem; margin-top:2px;}}
  .reco {{background:{BRAND['brand_light']}; border-left:4px solid {BRAND['brand']}; padding:10px 14px; border-radius:6px; margin:6px 0; font-size:.9rem;}}
</style>""", unsafe_allow_html=True)

px.defaults.color_discrete_sequence = SERIES
PLOT = dict(template="plotly_white", colorway=SERIES, font=dict(family="Inter, Helvetica, Arial", size=12),
            margin=dict(l=10, r=10, t=50, b=10), legend=dict(orientation="h", y=-0.18))


# ------------------------------------------------------------------------------------------- data
@st.cache_data
def sql(q, params=None):
    con = sqlite3.connect(DB_PATH)
    try:
        return pd.read_sql_query(q, con, params=params or [])
    finally:
        con.close()


@st.cache_data
def table(name, **kw):
    p = TABLES / f"{name}.csv"
    return pd.read_csv(p, **kw) if p.exists() else pd.DataFrame()


@st.cache_data
def findings():
    p = TABLES / "eda_findings.json"
    return json.load(open(p)) if p.exists() else {"metrics": {}, "findings": {}}


@st.cache_data
def model_results():
    p = TABLES / "model_results.json"
    return json.load(open(p)) if p.exists() else {}


@st.cache_data
def sales_df():
    s = sql("SELECT * FROM sales_transactions WHERE return_status='Completed'")
    s["transaction_date"] = pd.to_datetime(s.transaction_date)
    s["month"] = s.transaction_date.dt.to_period("M").dt.to_timestamp()
    return s


@st.cache_data
def service_df():
    v = sql("SELECT * FROM service_orders")
    v["date_received"] = pd.to_datetime(v.date_received)
    v["month"] = v.date_received.dt.to_period("M").dt.to_timestamp()
    v["revenue"] = v.labour_revenue_cad + v.parts_revenue_cad
    return v


@st.cache_data
def monthly_history(target):
    q = {"retail_revenue": "SELECT substr(transaction_date,1,7)||'-01' month, SUM(net_sales_cad) value FROM sales_transactions WHERE return_status='Completed' GROUP BY 1",
         "bike_units": "SELECT substr(transaction_date,1,7)||'-01' month, SUM(units_sold) value FROM sales_transactions WHERE return_status='Completed' AND product_class='E-Bike' GROUP BY 1",
         "service_revenue": "SELECT substr(date_received,1,7)||'-01' month, SUM(labour_revenue_cad+parts_revenue_cad) value FROM service_orders GROUP BY 1",
         "bike_demand_unconstrained": """SELECT month, SUM(v) value FROM (
             SELECT substr(transaction_date,1,7)||'-01' month, SUM(units_sold) v FROM sales_transactions WHERE product_class='E-Bike' AND return_status='Completed' GROUP BY 1
             UNION ALL SELECT substr(e.event_date,1,7)||'-01', SUM(e.lost_units) FROM stockout_events e JOIN products p USING(product_id)
             WHERE p.product_class='E-Bike' GROUP BY 1) GROUP BY month"""}[target]
    h = sql(q)
    h["month"] = pd.to_datetime(h.month)
    return h.sort_values("month")


def money(v, d=0):
    s = "-" if v < 0 else ""
    v = abs(v)
    return f"{s}${v / 1e6:,.2f}M" if v >= 1e6 else f"{s}${v:,.{d}f}"


def md_safe(text):
    """Escape $ so Streamlit markdown doesn't render dollar amounts as LaTeX math."""
    return str(text).replace("$", "\\$")


def kpis(items):
    cols = st.columns(len(items))
    for c, (label, value, delta, good) in zip(cols, items):
        color = BRAND["good"] if good is True else (BRAND["bad"] if good is False else BRAND["muted"])
        c.markdown(f"<div class='kpi'><div class='l'>{label}</div><div class='v'>{value}</div><div class='d' style='color:{color}'>{delta or '&nbsp;'}</div></div>",
                   unsafe_allow_html=True)


def show(fig, h=380):
    fig.update_layout(height=h, **PLOT)
    st.plotly_chart(fig, use_container_width=True)


def download(df, name, label="Download CSV"):
    st.download_button(label, df.to_csv(index=False).encode(), file_name=f"{name}.csv", mime="text/csv", key=f"dl_{name}")


def reco(lines):
    for l in lines:
        st.markdown(f"<div class='reco'>{l}</div>", unsafe_allow_html=True)


# ------------------------------------------------------------------------------------------- layout
st.markdown(f"""<div class='vv-banner'><div><h1>Prairie Pulse E-Bikes - Retail Analytics & Business Intelligence</h1>
<span>Prepared by VisiVault Analytics Ltd. | Proof of concept | Data through 30 Sep 2026</span></div>
<div class='vv-synth'>⚠ SYNTHETIC DEMONSTRATION DATA - not Prairie Pulse E-Bikes internal results</div></div>""", unsafe_allow_html=True)

PAGES = ["1. Executive Overview", "2. Sales Performance", "3. Product & Brand Performance", "4. Profitability",
         "5. Inventory Intelligence", "6. Customer Analytics", "7. Service & Repair Analytics", "8. Sales & Demand Forecasts",
         "9. Business Scenario Simulator"]
with st.sidebar:
    st.markdown(f"<div style='font-weight:800;font-size:1.1rem;color:{BRAND['brand_dark']}'>VisiVault Analytics</div>", unsafe_allow_html=True)
    page = st.radio("Navigate", PAGES, label_visibility="collapsed")
    st.divider()
    st.caption("FILTERS (pages 2-4)")
    s_all = sales_df()
    dmin, dmax = s_all.transaction_date.min().date(), s_all.transaction_date.max().date()
    dr = st.date_input("Date range", (dmin, dmax), min_value=dmin, max_value=dmax)
    classes = st.multiselect("Product class", sorted(s_all.product_class.unique()), default=sorted(s_all.product_class.unique()))
    cats = st.multiselect("Category", sorted(s_all.product_category.unique()), default=[])
    brands = st.multiselect("Brand", sorted(s_all.brand.unique()), default=[])
    st.divider()
    st.caption("Fictional retailer. E-bike brands, models and CAD list prices reflect public market listings (Oct 2026); Calgary weather (ECCC) and Bank of Canada data are real. Sales, costs, customers, service, inventory and expenses are synthetic (seed 20240101).")

if isinstance(dr, tuple) and len(dr) == 2:
    d0, d1 = pd.Timestamp(dr[0]), pd.Timestamp(dr[1])
else:
    d0, d1 = pd.Timestamp(dmin), pd.Timestamp(dmax)
S = s_all[(s_all.transaction_date >= d0) & (s_all.transaction_date <= d1) & s_all.product_class.isin(classes)]
if cats:
    S = S[S.product_category.isin(cats)]
if brands:
    S = S[S.brand.isin(brands)]
M = findings()["metrics"]
F = findings()["findings"]
MR = model_results()
TTM = "2025-10-01"

# ------------------------------------------------------------------------------------------- pages
if page == PAGES[0]:
    from src.engineering.sqlutil import query
    p = query("monthly_pnl")
    p["month"] = pd.to_datetime(p.month)
    t = p[p.month >= TTM]
    prev = p[(p.month >= "2024-10-01") & (p.month < TTM)]
    sv = service_df()
    kpis([
        ("Revenue (TTM)", money(t.total_revenue.sum()), f"{t.total_revenue.sum() / prev.total_revenue.sum() - 1:+.1%} vs prior 12m", t.total_revenue.sum() >= prev.total_revenue.sum()),
        ("Gross profit (TTM)", money(t.total_gross_profit.sum()), f"GM {t.total_gross_profit.sum() / t.total_revenue.sum():.1%}", None),
        ("Operating profit (TTM)", money(t.operating_profit.sum()), f"{t.operating_profit.sum() / t.total_revenue.sum():.1%} margin", t.operating_profit.sum() > 0),
        ("E-bikes sold (TTM)", f"{int(s_all[(s_all.transaction_date >= TTM) & (s_all.product_class == 'E-Bike')].units_sold.sum()):,}", f"{M.get('lost_bike_units_ttm', 0):,.0f} lost to stockouts", False),
        ("Service revenue (TTM)", money(t.service_revenue.sum()), f"{M.get('service_margin', 0):.0%} gross margin", True),
        ("Revenue lost to stockouts", money(M.get("lost_revenue_ttm", 0)), "estimated, TTM", False),
    ])
    st.write("")
    c1, c2 = st.columns([3, 2])
    with c1:
        fig = go.Figure()
        fig.add_bar(x=p.month, y=p.retail_revenue, name="Retail revenue", marker_color=BRAND["brand"])
        fig.add_bar(x=p.month, y=p.service_revenue, name="Service revenue", marker_color=BRAND["teal"])
        fig.add_scatter(x=p.month, y=p.operating_profit, name="Operating profit", line=dict(color=BRAND["navy"], width=3), yaxis="y2")
        fig.update_layout(barmode="stack", title="Monthly revenue and operating profit (CAD)", yaxis2=dict(overlaying="y", side="right", showgrid=False))
        show(fig, 420)
    with c2:
        st.subheader("Headline findings")
        for k in ["pnl", "stockouts", "service", "atv"]:
            if k in F:
                st.markdown(f"- {md_safe(F[k])}")
    st.subheader("Priority actions (ranked by value and effort)")
    rc = table("recommendations")
    if not rc.empty:
        reco([f"<b>{r.rank}. {r.title}</b>{' <i>(quick win)</i>' if r.quick_win else ''} - {r.impact}" for r in rc.head(5).itertuples()])
        with st.expander("All recommendations with evidence, KPIs and timeframes"):
            st.dataframe(rc[["rank", "title", "evidence_type", "value", "effort", "priority_score", "evidence", "action", "impact", "kpis", "timeframe"]],
                         use_container_width=True, hide_index=True)
            download(rc, "recommendations")
    st.caption("All values are synthetic and illustrative. See the report for the full recommendation set, evidence and caveats.")

elif page == PAGES[1]:
    st.subheader("Sales performance")
    tx = S.groupby("transaction_id").net_sales_cad.sum()
    kpis([("Net sales", money(S.net_sales_cad.sum()), f"{S.transaction_date.min():%b %Y} - {S.transaction_date.max():%b %Y}", None),
          ("Gross profit", money(S.gross_profit_cad.sum()), f"GM {S.gross_profit_cad.sum() / max(S.net_sales_cad.sum(), 1):.1%}", None),
          ("Units sold", f"{int(S.units_sold.sum()):,}", f"{int(S[S.product_class == 'E-Bike'].units_sold.sum()):,} e-bikes", None),
          ("Transactions", f"{S.transaction_id.nunique():,}", f"ATV {money(tx.mean() if len(tx) else 0)}", None)])
    m = S.groupby(["month", "product_class"]).net_sales_cad.sum().reset_index()
    show(px.bar(m, x="month", y="net_sales_cad", color="product_class", title="Monthly net sales by product class", labels={"net_sales_cad": "Net sales (CAD)"}))
    c1, c2 = st.columns(2)
    with c1:
        y = S.assign(year=S.transaction_date.dt.year.astype(str), mo=S.transaction_date.dt.month).groupby(["year", "mo"]).net_sales_cad.sum().reset_index()
        show(px.line(y, x="mo", y="net_sales_cad", color="year", markers=True, title="Year-over-year by month", labels={"mo": "Month", "net_sales_cad": "Net sales"}))
    with c2:
        ch = S.groupby("sales_channel").agg(net_sales=("net_sales_cad", "sum"), transactions=("transaction_id", "nunique")).reset_index()
        show(px.pie(ch, names="sales_channel", values="net_sales", hole=0.55, title="Net sales by channel"))
    q = S.assign(quarter=S.transaction_date.dt.to_period("Q").astype(str)).groupby("quarter").agg(net_sales=("net_sales_cad", "sum"), gross_profit=("gross_profit_cad", "sum"), units=("units_sold", "sum")).reset_index()
    q["QoQ %"] = (q.net_sales.pct_change() * 100).round(1); q["YoY %"] = (q.net_sales.pct_change(4) * 100).round(1)
    st.dataframe(q, use_container_width=True, hide_index=True)
    download(q, "quarterly_sales")
    reco([F.get("growth", ""), F.get("atv", "")])

elif page == PAGES[2]:
    st.subheader("Product & brand performance")
    b = S.groupby(["brand"]).agg(units=("units_sold", "sum"), net_sales=("net_sales_cad", "sum"), gross_profit=("gross_profit_cad", "sum")).reset_index()
    b["gross_margin_%"] = (b.gross_profit / b.net_sales * 100).round(1)
    c1, c2 = st.columns(2)
    with c1:
        show(px.bar(b.sort_values("net_sales"), x="net_sales", y="brand", orientation="h", color="gross_margin_%", color_continuous_scale="Blues",
                    title="Net sales by brand (colour = gross margin %)"), 460)
    with c2:
        tm = S.groupby(["product_category", "brand", "model"]).net_sales_cad.sum().reset_index()
        show(px.treemap(tm, path=["product_category", "brand", "model"], values="net_sales_cad", title="Revenue contribution: category > brand > model"), 460)
    md = S.groupby(["brand", "model", "product_category"]).agg(units=("units_sold", "sum"), net_sales=("net_sales_cad", "sum"), gross_profit=("gross_profit_cad", "sum"),
                                                                avg_discount=("discount_pct", "mean")).reset_index().sort_values("net_sales", ascending=False)
    md["gross_margin_%"] = (md.gross_profit / md.net_sales * 100).round(1); md["avg_discount"] = (md.avg_discount * 100).round(1)
    md["revenue_share_%"] = (md.net_sales / md.net_sales.sum() * 100).round(2)
    st.markdown("**Best-selling and under-performing products** (sort any column)")
    st.dataframe(md, use_container_width=True, hide_index=True, height=380)
    download(md, "product_performance")
    reco([F.get("brand", ""), F.get("models", ""), F.get("category", "")])

elif page == PAGES[3]:
    st.subheader("Profitability")
    from src.engineering.sqlutil import query
    p = query("monthly_pnl"); p["month"] = pd.to_datetime(p.month)
    kpis([("Break-even revenue / month", money(M.get("break_even_monthly_revenue", 0)), f"CM ratio {M.get('contribution_margin_ratio', 0):.1%}", None),
          ("Margin of safety (TTM)", f"{M.get('margin_of_safety', 0):.0%}", "revenue above break-even", M.get("margin_of_safety", 0) > 0.1),
          ("Loss-making months", f"{M.get('loss_months', 0)} of 33", "winter seasonality", False),
          ("Discretionary bike discounts", money(M.get("discretionary_bike_discount_cad", 0)), "not tied to promotions", False)])
    fig = go.Figure()
    fig.add_bar(x=p.month, y=p.operating_profit, marker_color=[BRAND["teal"] if v >= 0 else BRAND["bad"] for v in p.operating_profit], name="Operating profit")
    fig.add_scatter(x=p.month, y=[M.get("break_even_monthly_revenue", 0)] * len(p), name="Break-even revenue", line=dict(dash="dash", color=BRAND["bad"]), yaxis="y2")
    fig.add_scatter(x=p.month, y=p.total_revenue, name="Total revenue", line=dict(color=BRAND["brand"]), yaxis="y2")
    fig.update_layout(title="Operating profit (bars) vs revenue and break-even (lines)", yaxis2=dict(overlaying="y", side="right", showgrid=False))
    show(fig, 420)
    c1, c2 = st.columns(2)
    with c1:
        dbd = sql("""SELECT product_class, CASE WHEN discount_pct=0 THEN '0%' WHEN discount_pct<=0.05 THEN '0-5%' WHEN discount_pct<=0.10 THEN '5-10%'
                     WHEN discount_pct<=0.15 THEN '10-15%' ELSE '>15%' END band, SUM(units_sold) units, SUM(gross_profit_cad)*100.0/SUM(net_sales_cad) gm
                     FROM sales_transactions WHERE return_status='Completed' AND product_class='E-Bike' GROUP BY 1,2""")
        dbd["band"] = pd.Categorical(dbd.band, ["0%", "0-5%", "5-10%", "10-15%", ">15%"], ordered=True)
        dbd = dbd.sort_values("band")
        fig = go.Figure([go.Bar(x=dbd.band, y=dbd.units, name="E-bike units", marker_color=BRAND["brand"]),
                         go.Scatter(x=dbd.band, y=dbd.gm, name="Gross margin %", yaxis="y2", line=dict(color=BRAND["bad"], width=3))])
        fig.update_layout(title="Discount depth vs margin (e-bikes)", yaxis2=dict(overlaying="y", side="right", showgrid=False))
        show(fig)
    with c2:
        o = sql("SELECT * FROM operating_expenses WHERE month >= ?", [TTM])
        oc = o[[c for c in o.columns if c.endswith("_cad") and c not in ("total_opex_cad", "avg_inventory_value_cad")]].sum().reset_index()
        oc.columns = ["expense", "cad"]; oc["expense"] = oc.expense.str.replace("_cad", "").str.replace("_", " ").str.title()
        show(px.pie(oc, names="expense", values="cad", hole=0.5, title="Operating expenses - trailing 12 months"))
    st.dataframe(p, use_container_width=True, hide_index=True)
    download(p, "monthly_pnl")
    rp = table("sales_rep_performance")
    if not rp.empty:
        st.markdown("**Sales expert performance**"); st.dataframe(rp, use_container_width=True, hide_index=True)
    reco([F.get("pnl", ""), F.get("discount", ""), F.get("promotions", "")])

elif page == PAGES[4]:
    st.subheader("Inventory intelligence")
    inv = table("inventory_analysis_by_product")
    kpis([("Inventory at cost (now)", money(M.get("inventory_value_now", 0)), "30 Sep 2026", None),
          ("E-bike turnover (TTM)", f"{M.get('turnover_bikes', 0):.1f}x", f"~{M.get('doh_bikes', 0):.0f} days on hand", None),
          ("Lost revenue to stockouts (TTM)", money(M.get("lost_revenue_ttm", 0)), f"{M.get('lost_bike_units_ttm', 0):.0f} e-bikes", False),
          ("Slow-moving stock", money(M.get("slow_moving_value", 0)), f"{M.get('slow_moving_n', 0):.0f} SKUs > 6 months cover", False),
          ("Carrying cost (TTM)", money(M.get("holding_cost_ttm", 0)), "financing + storage + obsolescence", None)])
    v = table("inventory_value_month_end")
    if not v.empty:
        v = v.melt(id_vars=v.columns[0], var_name="class", value_name="value"); v.columns = ["month", "class", "value"]
        show(px.area(v, x="month", y="value", color="class", title="Month-end inventory value at cost"))
    c1, c2 = st.columns(2)
    with c1:
        fr = table("inventory_service_level_frontier")
        if not fr.empty:
            fig = px.scatter(fr, x="avg_inventory_value", y="lost_gross_profit", text="service_target", size="total_cost",
                             title="Policy frontier: capital vs lost gross profit (Jan-Sep 2026 replay)", color="service_target")
            fig.update_traces(textposition="top center", showlegend=False)
            show(fig, 420)
    with c2:
        so = sql("""SELECT substr(e.event_date,1,7) month, p.product_class, SUM(e.lost_revenue_est_cad) lost FROM stockout_events e
                    JOIN products p USING(product_id) GROUP BY 1,2""")
        show(px.bar(so, x="month", y="lost", color="product_class", title="Estimated revenue lost to stockouts"), 420)
    abc = st.multiselect("ABC class", ["A", "B", "C"], default=["A", "B", "C"])
    view = inv[inv.abc_class.isin(abc)][["product_id", "brand", "model", "product_class", "abc_class", "current_inventory", "inventory_value_cost",
                                         "units_last_12m", "months_of_cover", "turnover_ttm", "stockout_occurrences", "lost_units", "lost_revenue_est", "slow_moving"]]
    st.dataframe(view.round(2), use_container_width=True, hide_index=True, height=320)
    download(view, "inventory_status")
    st.markdown("**Recommended seasonal reorder points & safety stock**")
    rc = table("inventory_policy_recommendations")
    st.dataframe(rc[["product_id", "brand", "model", "abc_class", "service_level", "lead_time_mean_days", "safety_stock_peak", "reorder_point_peak",
                     "reorder_point_offpeak", "eoq", "current_rop", "current_order_up_to"]], use_container_width=True, hide_index=True, height=300)
    download(rc, "reorder_point_recommendations", "Download reorder-point recommendations")
    pp = table("purchase_plan_by_model")
    download(pp, "purchase_plan_by_model", "Download quarterly purchase plan (by model)")
    reco([F.get("inventory", ""), F.get("stockouts", "")])

elif page == PAGES[5]:
    st.subheader("Customer analytics")
    seg = table("segment_profiles")
    kpis([("Active customers", f"{M.get('n_customers', 0):,.0f}", f"{M.get('bike_buyers', 0):,.0f} e-bike buyers", None),
          ("Repeat customer rate", f"{M.get('repeat_rate', 0):.0%}", "2+ purchase/service interactions", None),
          ("Lead conversion", f"{M.get('lead_conversion', 0):.1%}", f"{M.get('total_leads', 0):,.0f} leads", None),
          ("Test-ride conversion", f"{M.get('test_ride_conv', 0):.0%}", f"vs {M.get('no_test_ride_conv', 0):.0%} without", True),
          ("E-bike customer CLV (GP, 5y)", money(M.get("clv_bike_customer", 0)), "estimated", None)])
    c1, c2 = st.columns(2)
    with c1:
        if not seg.empty:
            show(px.bar(seg.sort_values("spend_share"), x="spend_share", y="segment", orientation="h", text="customers",
                        title="Segments: share of spend (label = customers)"), 400)
    with c2:
        lf = table("lead_funnel_by_channel")
        if not lf.empty:
            fig = go.Figure([go.Bar(x=lf.lead_channel, y=lf.leads, name="Leads", marker_color=BRAND["brand_light"]),
                             go.Bar(x=lf.lead_channel, y=lf.conversions, name="Conversions", marker_color=BRAND["brand"])])
            fig.update_layout(barmode="overlay", title="Lead funnel by channel")
            show(fig, 400)
    if not seg.empty:
        st.markdown("**Segment strategies**")
        st.dataframe(seg[["segment", "customers", "recency_days", "frequency", "monetary", "spend_share", "strategy"]].round(2), use_container_width=True, hide_index=True)
    lf2 = table("lead_funnel_by_channel")
    if not lf2.empty:
        st.markdown("**Marketing channel effectiveness** (paid channels; spend-to-source mapping is an assumption)")
        st.dataframe(lf2.round(2), use_container_width=True, hide_index=True)
        download(lf2, "marketing_channel_effectiveness")
    cs = table("customer_segments")
    if not cs.empty:
        download(cs[["customer_id", "segment", "recency_days", "frequency", "monetary", "R_score", "F_score", "M_score", "RFM_score"]], "customer_rfm_segments",
                 "Download RFM segment list (fictional IDs)")
    reco([F.get("leads", ""), F.get("clv", "")])

elif page == PAGES[6]:
    st.subheader("Service & repair analytics")
    v = service_df()
    ttm = v[v.date_received >= TTM]
    kpis([("Service revenue (TTM)", money(ttm.revenue.sum()), f"{len(ttm):,} orders", None),
          ("Service gross margin", f"{ttm.gross_profit_cad.sum() / ttm.revenue.sum():.0%}", "labour + parts - tech cost", True),
          ("Avg turnaround", f"{ttm.turnaround_days.mean():.1f} days", f"peak Jun-Jul {M.get('tat_peak', 0):.1f} (all years)", None),
          ("Avg satisfaction", f"{ttm.satisfaction_score.mean():.2f} / 5", f"peak {M.get('sat_peak', 0):.2f}", None),
          ("Warranty orders (all)", f"{M.get('warranty_orders', 0):,.0f}", f"net {money(M.get('warranty_net', 0))}", None)])
    m = v.groupby(["month", "service_type"]).revenue.sum().reset_index()
    show(px.bar(m, x="month", y="revenue", color="service_type", title="Monthly service revenue by type"), 420)
    c1, c2 = st.columns(2)
    with c1:
        w = sql("SELECT substr(date,1,7) month, SUM(capacity_hours) cap, SUM(assembly_hours) asm, SUM(repair_hours_received) rep FROM workshop_daily GROUP BY 1")
        w["utilisation_%"] = (w.asm + w.rep) / w.cap * 100
        tat = v.groupby(v.month.dt.strftime("%Y-%m")).turnaround_days.mean().reset_index()
        fig = go.Figure([go.Bar(x=w.month, y=w["utilisation_%"], name="Utilisation %", marker_color=BRAND["brand"]),
                         go.Scatter(x=tat.month, y=tat.turnaround_days, name="Avg turnaround (days)", yaxis="y2", line=dict(color=BRAND["warn"], width=3))])
        fig.update_layout(title="Workshop utilisation vs turnaround", yaxis2=dict(overlaying="y", side="right", showgrid=False))
        show(fig)
    with c2:
        tp = table("technician_productivity")
        if not tp.empty:
            tp["GP per labour hour"] = tp.gross_profit / tp.labour_hours
            show(px.bar(tp, x="technician_id", y="GP per labour hour", text="orders", title="Technician productivity (label = orders)"))
    st.dataframe(table("service_by_type"), use_container_width=True, hide_index=True)
    download(table("service_by_type"), "service_by_type")
    reco([F.get("service", "")])

elif page == PAGES[7]:
    st.subheader("Sales & demand forecasts (Oct 2026 - Sep 2027)")
    comp = table("forecast_model_comparison")
    fc = table("forecast_next_12_months_all_models", parse_dates=["month"])
    target = st.selectbox("Target", ["retail_revenue", "bike_units", "service_revenue", "bike_demand_unconstrained"],
                          format_func=lambda x: {"retail_revenue": "Retail net sales (CAD)", "bike_units": "E-bike units sold",
                                                 "service_revenue": "Service revenue (CAD)", "bike_demand_unconstrained": "Unconstrained e-bike demand (units)"}[x])
    models = st.multiselect("Models", sorted(fc.model.unique()), default=["Prophet", "Seasonal naive"])
    hist = monthly_history(target)
    fig = go.Figure([go.Scatter(x=hist.month, y=hist.value, name="History", line=dict(color=BRAND["navy"], width=3))])
    for i, m_ in enumerate(models):
        g = fc[(fc.target == target) & (fc.model == m_)]
        fig.add_scatter(x=g.month, y=g.forecast, name=m_, line=dict(width=2.5, dash="solid" if m_ == "Prophet" else "dash", color=SERIES[(i + 1) % len(SERIES)]))
        if m_ == "Prophet":
            fig.add_scatter(x=list(g.month) + list(g.month[::-1]), y=list(g.hi80) + list(g.lo80[::-1]), fill="toself", fillcolor="rgba(42,120,214,0.15)",
                            line=dict(width=0), name="Prophet 80% PI")
    fig.update_layout(title="History and 12-month forecast")
    show(fig, 440)
    key = target if target != "bike_demand_unconstrained" else "bike_units"
    st.markdown("**Backtest accuracy (holdout Jan-Sep 2026 + rolling origins)** - lower WAPE is better")
    st.dataframe(comp[comp.target == key].round(3), use_container_width=True, hide_index=True)
    sel = fc[(fc.target == target) & fc.selected][["month", "model", "forecast", "lo80", "hi80"]]
    st.dataframe(sel.round(1), use_container_width=True, hide_index=True)
    download(sel, f"forecast_{target}")
    c1, c2 = st.columns(2)
    with c1:
        dc = table("demand_forecast_by_category")
        if not dc.empty:
            dc = dc.melt(id_vars=dc.columns[0]); dc.columns = ["month", "category", "units"]
            show(px.bar(dc, x="month", y="units", color="category", title="Demand forecast by category (units)"))
    with c2:
        bq = table("purchase_plan_by_brand_quarter")
        if not bq.empty:
            st.markdown("**Recommended e-bike purchases by brand and quarter (units)**")
            st.dataframe(bq, use_container_width=True, hide_index=True)
            download(bq, "purchase_plan_by_brand_quarter")
    st.caption("Forecasts are trained on synthetic data; accuracy demonstrates the method, not the predictability of Prairie Pulse E-Bikes' real sales.")

elif page == PAGES[8]:
    st.subheader("Business scenario simulator (illustrative)")
    st.caption("Adjust drivers to see the effect on the next-12-month P&L. Responses (elasticities) are assumptions, not causal estimates.")
    b = scn.baseline()
    preset = st.selectbox("Start from preset", ["Base", "Conservative", "Optimistic"])
    p0 = scn.SCENARIOS[preset]
    c1, c2, c3 = st.columns(3)
    with c1:
        price = st.slider("List price change %", -10.0, 10.0, p0.price_change * 100, 0.5) / 100
        elas = st.slider("Price elasticity of bike demand", -2.5, 0.0, p0.price_elasticity, 0.1)
        vol = st.slider("Bike volume change % (exogenous)", -20.0, 20.0, p0.volume_change * 100, 1.0) / 100
        disc = st.slider("Change in avg discount (pts)", -3.0, 5.0, p0.discount_change * 100, 0.5) / 100
    with c2:
        cost = st.slider("Supplier cost change %", -10.0, 10.0, p0.supplier_cost_change * 100, 0.5) / 100
        adv = st.slider("Advertising spend change %", -50.0, 100.0, p0.advertising_change * 100, 5.0) / 100
        adel = st.slider("Advertising elasticity", 0.0, 0.3, p0.advertising_elasticity, 0.01)
        mix = st.slider("Mix shift to higher-margin brands (% of units)", 0.0, 20.0, p0.mix_shift * 100, 1.0) / 100
    with c3:
        svc = st.slider("Service revenue change %", -20.0, 40.0, p0.service_change * 100, 1.0) / 100
        carry = st.slider("Inventory carrying cost change %", -30.0, 20.0, p0.carrying_cost_change * 100, 1.0) / 100
        conv = st.slider("Qualified lead conversion change %", -20.0, 40.0, p0.lead_conversion_change * 100, 1.0) / 100
    dr = scn.Drivers(price_change=price, price_elasticity=elas, volume_change=vol, supplier_cost_change=cost, discount_change=disc,
                     advertising_change=adv, advertising_elasticity=adel, mix_shift=mix, service_change=svc, carrying_cost_change=carry,
                     lead_conversion_change=conv)
    base = scn.simulate(scn.Drivers(), b)
    r = scn.simulate(dr, b)
    kpis([("Revenue", money(r["revenue"]), f"{r['revenue'] - base['revenue']:+,.0f} vs base", r["revenue"] >= base["revenue"]),
          ("Gross profit", money(r["gross_profit"]), f"GM {r['gross_margin_pct']:.1f}% ({r['gross_margin_pct'] - base['gross_margin_pct']:+.1f} pts)", r["gross_profit"] >= base["gross_profit"]),
          ("Operating profit", money(r["operating_profit"]), f"{r['operating_profit'] - base['operating_profit']:+,.0f} vs base", r["operating_profit"] >= base["operating_profit"]),
          ("Inventory investment", money(r["inventory_investment"]), f"{r['inventory_investment'] - base['inventory_investment']:+,.0f}", None),
          ("E-bike units", f"{r['bike_units']:,.0f}", f"{r['bike_units'] - base['bike_units']:+,.0f}", None)])
    comp = pd.DataFrame({"Base": base, "Scenario": r}).loc[["revenue", "gross_profit", "operating_expenses", "operating_profit"]]
    show(px.bar(comp.reset_index().melt(id_vars="index"), x="index", y="value", color="variable", barmode="group", title="Base vs scenario (next 12 months, CAD)",
                labels={"index": "", "value": "CAD", "variable": ""}))
    st.markdown("**Required sensitivities (each lever alone vs base)**")
    st.dataframe(table("sensitivity_analysis").round(0), use_container_width=True, hide_index=True)
    st.dataframe(table("scenarios", index_col=0).round(1), use_container_width=True)
    with st.expander("Formulas and assumptions"):
        st.code(scn.__doc__)
        st.json({k: (round(v, 4) if isinstance(v, float) else v) for k, v in b.items()})
    st.warning("Scenario results are illustrative estimates on synthetic data. They are not forecasts of Prairie Pulse E-Bikes results and are not guaranteed benefits.")

st.markdown(f"<div style='text-align:center;color:{BRAND['subtle']};font-size:.75rem;margin-top:30px'>VisiVault Analytics Ltd. | Prairie Pulse E-Bikes proof of concept | "
            "SYNTHETIC DEMONSTRATION DATA - fictional retailer; product prices from public market listings; weather from ECCC; rates from Bank of Canada</div>",
            unsafe_allow_html=True)
