"""Phase 13 - trial balances and the integrated three statements, derived ONLY from general-ledger balances.

Sign convention for presentation tables: income-statement and cash-flow lines are signed (+ inflow/income,
- outflow/expense); balance-sheet lines are positive balances with accumulated depreciation shown negative.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from src.config import END
from src.finance import policy as P
from src.finance.ledger import MONTHS, fixed_asset_schedule

ALL_M = pd.period_range("2023-12", END, freq="M")     # Dec 2023 = opening position


# ----------------------------------------------------------------------------------------------- balances
def activity(gl: pd.DataFrame, include_closing=True) -> pd.DataFrame:
    g = gl if include_closing else gl[~gl.is_closing]
    a = g.groupby(["month", "account"]).amount.sum().unstack(fill_value=0.0)
    return a.reindex(index=ALL_M, columns=list(P.ACCOUNTS), fill_value=0.0)


def balances(gl: pd.DataFrame) -> pd.DataFrame:
    """Month-end balances (debit positive), post-closing at year ends."""
    return activity(gl).cumsum().round(2)


def trial_balances(gl: pd.DataFrame) -> pd.DataFrame:
    """Long-format monthly trial balance (pre-closing at December so P&L accounts are visible) with Dr/Cr columns."""
    pre = activity(gl, include_closing=False).cumsum()
    # P&L accounts accumulate from the start of each fiscal year in a pre-closing TB
    pnl = [a for a, v in P.ACCOUNTS.items() if v["type"] in P.PNL_TYPES]
    act = activity(gl, include_closing=False)
    for a in pnl:
        pre[a] = act[a].groupby([m.year for m in act.index]).cumsum()
    re_pre = activity(gl)["3200"].cumsum() - activity(gl[gl.is_closing])["3200"].groupby([m.year for m in ALL_M]).cumsum()
    pre["3200"] = re_pre
    pre["3300"] = act["3300"].groupby([m.year for m in act.index]).cumsum()
    pre = pre.round(2)
    rows = []
    for m in pre.index:
        for a in P.ACCOUNTS:
            v = pre.at[m, a]
            if abs(v) < 0.005:
                continue
            rows.append({"month": str(m), "account": a, "account_name": P.ACCOUNTS[a]["name"], "type": P.ACCOUNTS[a]["type"],
                         "debit": round(v, 2) if v > 0 else 0.0, "credit": round(-v, 2) if v < 0 else 0.0})
    tb = pd.DataFrame(rows)
    tb["data_status"] = "SIMULATED"
    return tb


# ----------------------------------------------------------------------------------------------- income statement
IS_LINES = [  # key, label, accounts (credit-positive revenue / debit-positive cost), kind
    ("bike_rev", "Bicycle sales revenue", ["4000"], "rev"),
    ("acc_rev", "Accessories and parts revenue", ["4100", "4110", "4120"], "rev"),
    ("svc_rev", "Maintenance and repair revenue", ["4200", "4210", "4220"], "rev"),
    ("gross_rev", "Gross revenue", None, "sub"),
    ("discounts", "Sales discounts & promotional allowances", ["4900"], "cost"),
    ("returns", "Sales returns & refunds", ["4910"], "cost"),
    ("returns_allow", "Sales returns and allowances", None, "sub"),
    ("net_rev", "Net revenue", None, "sub"),
    ("cogs_bike", "Cost of goods sold - e-bikes", ["5000"], "cost"),
    ("cogs_acc", "Cost of goods sold - accessories, batteries & parts", ["5010"], "cost"),
    ("shrink", "Inventory shrinkage & write-offs", ["5100"], "cost"),
    ("svc_parts", "Service parts cost", ["5200"], "cost"),
    ("svc_labour", "Direct service labour", ["5210"], "cost"),
    ("cogs", "Cost of goods sold (total cost of sales)", None, "sub"),
    ("gross_profit", "Gross profit", None, "sub"),
    ("emp_comp", "Employee compensation", ["6000", "6010"], "cost"),
    ("rent", "Rent and occupancy", ["6100"], "cost"),
    ("utilities", "Utilities", ["6110"], "cost"),
    ("marketing", "Marketing and advertising", ["6200"], "cost"),
    ("admin", "Administrative expenses (incl. insurance & corporate allocation)", ["6300", "6310", "6320"], "cost"),
    ("freight", "Freight and logistics", ["6400"], "cost"),
    ("fees", "Merchant and financing fees", ["6410"], "cost"),
    ("storage", "Inventory storage, handling & obsolescence", ["6420"], "cost"),
    ("opex", "Total operating expenses (before D&A)", None, "sub"),
    ("ebitda", "EBITDA", None, "sub"),
    ("da", "Depreciation and amortization", ["6900"], "cost"),
    ("ebit", "EBIT (operating profit)", None, "sub"),
    ("interest", "Interest expense", ["7000", "7010"], "cost"),
    ("pbt", "Profit before tax", None, "sub"),
    ("tax", "Income taxes", ["8000"], "cost"),
    ("net_income", "Net income", None, "sub"),
]
IS_LABEL = {k: l for k, l, _, _ in IS_LINES}


def income_statement(gl: pd.DataFrame) -> pd.DataFrame:
    """Monthly income statement (signed: revenue +, costs -). Index = line key, columns = months."""
    a = activity(gl, include_closing=False).loc[MONTHS[0]:]
    out = {}
    for k, _, accts, kind in IS_LINES:
        if accts:
            out[k] = -a[accts].sum(axis=1)          # credit-positive -> revenue +, cost -
    out["gross_rev"] = out["bike_rev"] + out["acc_rev"] + out["svc_rev"]
    out["returns_allow"] = out["discounts"] + out["returns"]
    out["net_rev"] = out["gross_rev"] + out["returns_allow"]
    out["cogs"] = out["cogs_bike"] + out["cogs_acc"] + out["shrink"] + out["svc_parts"] + out["svc_labour"]
    out["gross_profit"] = out["net_rev"] + out["cogs"]
    out["opex"] = sum(out[k] for k in ["emp_comp", "rent", "utilities", "marketing", "admin", "freight", "fees", "storage"])
    out["ebitda"] = out["gross_profit"] + out["opex"]
    out["ebit"] = out["ebitda"] + out["da"]
    out["pbt"] = out["ebit"] + out["interest"]
    out["net_income"] = out["pbt"] + out["tax"]
    df = pd.DataFrame(out).T.loc[[k for k, *_ in IS_LINES]].round(2)
    df.columns = [str(c) for c in df.columns]
    return df


def is_with_margins(is_df: pd.DataFrame) -> pd.DataFrame:
    m = is_df.copy()
    nr = is_df.loc["net_rev"].replace(0, np.nan)
    for k, lab in [("gross_profit", "gross_margin_pct"), ("ebitda", "ebitda_margin_pct"), ("ebit", "operating_margin_pct"), ("net_income", "net_margin_pct")]:
        m.loc[lab] = (is_df.loc[k] / nr * 100).round(2)
    return m


# ----------------------------------------------------------------------------------------------- balance sheet
BS_LINES = [  # key, label, section
    ("cash", "Cash and cash equivalents", "Current assets"),
    ("ar", "Accounts receivable", "Current assets"),
    ("inventory", "Inventory (merchandise at cost)", "Current assets"),
    ("wip", "Service work in progress", "Current assets"),
    ("prepaid", "Prepaid expenses & supplier deposits", "Current assets"),
    ("gst_rec", "Sales tax recoverable", "Current assets"),
    ("current_assets", "Total current assets", "sub"),
    ("ppe_gross", "Property, plant and equipment (cost)", "Non-current assets"),
    ("acc_dep", "Accumulated depreciation", "Non-current assets"),
    ("ppe_net", "Net property, plant and equipment", "sub"),
    ("total_assets", "TOTAL ASSETS", "sub"),
    ("ap", "Accounts payable", "Current liabilities"),
    ("accrued", "Accrued expenses (payroll & head office)", "Current liabilities"),
    ("tax_payable", "Income taxes payable", "Current liabilities"),
    ("gst_pay", "Sales tax payable", "Current liabilities"),
    ("revolver", "Short-term borrowings - revolving line of credit", "Current liabilities"),
    ("term_current", "Current portion of long-term debt", "Current liabilities"),
    ("current_liabilities", "Total current liabilities", "sub"),
    ("term_lt", "Long-term debt (non-current portion)", "Non-current liabilities"),
    ("total_liabilities", "TOTAL LIABILITIES", "sub"),
    ("equity_cap", "Share capital / allocated corporate equity", "Equity"),
    ("retained", "Retained earnings", "Equity"),
    ("cpe", "Current period earnings", "Equity"),
    ("total_equity", "TOTAL EQUITY", "sub"),
    ("total_le", "TOTAL LIABILITIES AND EQUITY", "sub"),
    ("check", "Check: assets - liabilities - equity", "check"),
]
BS_LABEL = {k: l for k, l, _ in BS_LINES}


def term_current_portion(term_balance: float) -> float:
    pmt = round(P.TERM_LOAN["principal"] / P.TERM_LOAN["months"], 2)
    return round(min(term_balance, 12 * pmt), 2)


def balance_sheet(gl: pd.DataFrame) -> pd.DataFrame:
    b = balances(gl)
    pnl = [a for a, v in P.ACCOUNTS.items() if v["type"] in P.PNL_TYPES]
    o = {}
    o["cash"] = b["1000"]
    o["ar"] = b[["1100", "1110", "1120", "1130"]].sum(axis=1)
    o["inventory"] = b["1200"]
    o["wip"] = b["1250"]
    o["prepaid"] = b[["1300", "1310"]].sum(axis=1)
    gst_net = b["1400"] + b["2300"]                 # debit positive = recoverable
    o["gst_rec"] = gst_net.clip(lower=0)
    o["current_assets"] = o["cash"] + o["ar"] + o["inventory"] + o["wip"] + o["prepaid"] + o["gst_rec"]
    o["ppe_gross"] = b[["1500", "1510", "1520"]].sum(axis=1)
    o["acc_dep"] = b["1590"]
    o["ppe_net"] = o["ppe_gross"] + o["acc_dep"]
    o["total_assets"] = o["current_assets"] + o["ppe_net"]
    o["ap"] = -b[["2000", "2010"]].sum(axis=1)
    o["accrued"] = -b[["2100", "2500"]].sum(axis=1)
    o["tax_payable"] = -b["2400"]
    o["gst_pay"] = (-gst_net).clip(lower=0)
    o["revolver"] = -b["2600"]
    term = -b["2700"]
    o["term_current"] = term.map(term_current_portion)
    o["current_liabilities"] = o["ap"] + o["accrued"] + o["tax_payable"] + o["gst_pay"] + o["revolver"] + o["term_current"]
    o["term_lt"] = term - o["term_current"]
    o["total_liabilities"] = o["current_liabilities"] + o["term_lt"]
    o["equity_cap"] = -b["3000"]
    o["retained"] = -(b["3200"] + b["3300"])
    o["cpe"] = -b[pnl].sum(axis=1)
    o["total_equity"] = o["equity_cap"] + o["retained"] + o["cpe"]
    o["total_le"] = o["total_liabilities"] + o["total_equity"]
    o["check"] = o["total_assets"] - o["total_le"]
    df = pd.DataFrame(o).T.loc[[k for k, *_ in BS_LINES]].round(2)
    df.columns = [str(c) for c in df.columns]
    return df


# ----------------------------------------------------------------------------------------------- cash flow (indirect)
CF_LINES = [
    ("net_income", "Net income", "Operating"),
    ("da", "Depreciation and amortization", "Operating"),
    ("d_ar", "(Increase) decrease in accounts receivable", "Operating"),
    ("d_inv", "(Increase) decrease in inventory", "Operating"),
    ("d_ap", "Increase (decrease) in accounts payable", "Operating"),
    ("d_wip", "  Service work in progress", "Operating - other working capital"),
    ("d_prepaid", "  Prepaid expenses & supplier deposits", "Operating - other working capital"),
    ("d_accrued", "  Accrued payroll & due to head office", "Operating - other working capital"),
    ("d_gst", "  Sales tax payable / recoverable", "Operating - other working capital"),
    ("d_tax", "  Income taxes payable", "Operating - other working capital"),
    ("other_wc", "Other working capital adjustments", "sub"),
    ("cfo", "Net cash from operating activities", "sub"),
    ("capex", "Capital expenditures (leasehold & systems)", "Investing"),
    ("equipment", "Equipment purchases", "Investing"),
    ("cfi", "Net cash used in investing activities", "sub"),
    ("rev_draw", "New borrowings - revolving line of credit", "Financing"),
    ("rev_repay", "Repayments - revolving line of credit", "Financing"),
    ("term_repay", "Term loan repayments", "Financing"),
    ("contrib", "Capital contributions from head office", "Financing"),
    ("dist", "Distributions to head office", "Financing"),
    ("cff", "Net cash from (used in) financing activities", "sub"),
    ("net_change", "Net change in cash", "sub"),
    ("open_cash", "Opening cash", "sub"),
    ("close_cash", "Closing cash (cash flow statement)", "sub"),
    ("bs_cash", "Cash per balance sheet", "check"),
    ("check", "Check: closing cash - balance-sheet cash", "check"),
]
CF_LABEL = {k: l for k, l, _ in CF_LINES}


def cash_flow(gl: pd.DataFrame, is_df: pd.DataFrame) -> pd.DataFrame:
    """Indirect method. Every non-cash balance-sheet account is mapped to exactly one line (policy.COA 'cf' class)."""
    act = activity(gl).loc[MONTHS[0]:]                 # includes closing entries (they net to zero within equity/P&L)
    nc = gl[~gl.is_closing]
    def flow(acct, side, src=None):
        g = nc[(nc.account == acct) & ((nc.source == src) if src else True)]
        s = g.groupby("month")[side].sum()
        return s.reindex(MONTHS, fill_value=0.0)
    o = {}
    o["net_income"] = is_df.loc["net_income"].values
    o["da"] = -is_df.loc["da"].values
    o["d_ar"] = -act[["1100", "1110", "1120", "1130"]].sum(axis=1).values
    o["d_inv"] = -act["1200"].values
    o["d_ap"] = -act[["2000", "2010"]].sum(axis=1).values
    o["d_wip"] = -act["1250"].values
    o["d_prepaid"] = -act[["1300", "1310"]].sum(axis=1).values
    o["d_accrued"] = -act[["2100", "2500"]].sum(axis=1).values
    o["d_gst"] = -act[["1400", "2300"]].sum(axis=1).values
    o["d_tax"] = -act["2400"].values
    o["other_wc"] = o["d_wip"] + o["d_prepaid"] + o["d_accrued"] + o["d_gst"] + o["d_tax"]
    o["cfo"] = o["net_income"] + o["da"] + o["d_ar"] + o["d_inv"] + o["d_ap"] + o["other_wc"]
    o["capex"] = -(act["1500"] + act["1520"]).values
    o["equipment"] = -act["1510"].values
    o["cfi"] = o["capex"] + o["equipment"]
    o["rev_draw"] = flow("2600", "credit").values
    o["rev_repay"] = -flow("2600", "debit").values
    o["term_repay"] = -(flow("2700", "debit").values - flow("2700", "credit").values)
    o["contrib"] = flow("3000", "credit").values
    o["dist"] = -flow("3300", "debit").values
    o["cff"] = o["rev_draw"] + o["rev_repay"] + o["term_repay"] + o["contrib"] + o["dist"]
    o["net_change"] = o["cfo"] + o["cfi"] + o["cff"]
    bs_cash = balances(gl)["1000"]
    o["open_cash"] = bs_cash.shift(1).loc[MONTHS[0]:].values
    o["close_cash"] = o["open_cash"] + o["net_change"]
    o["bs_cash"] = bs_cash.loc[MONTHS[0]:].values
    o["check"] = o["close_cash"] - o["bs_cash"]
    df = pd.DataFrame(o, index=[str(m) for m in MONTHS]).T.loc[[k for k, *_ in CF_LINES]].round(2)
    return df


def direct_cash_flow(gl: pd.DataFrame) -> pd.DataFrame:
    """Direct-method cross-check: cash-account lines grouped by journal source."""
    c = gl[(gl.account == "1000") & (gl.date >= pd.Timestamp(str(MONTHS[0])))]
    m = {"Sales": "Receipts from customers (cash tenders)", "Collections": "Receipts from customers (settlements)",
         "Returns": "Customer refunds", "Purchasing": "Supplier deposits", "Supplier payments": "Payments to suppliers & vendors",
         "Operating expenses": "Rent paid", "Payroll": "Payroll paid", "Prepaid insurance": "Insurance premiums paid",
         "Head office": "Head-office shared-services settlements", "GST remittance": "GST remitted / refunded",
         "Income tax": "Income tax paid", "Financing": "Financing (interest, loan principal, revolver)",
         "Capital expenditure": "Capital expenditures", "Equity": "Head-office contributions / distributions"}
    d = c.assign(category=c.source.map(m)).pivot_table(index="category", columns="month", values="amount", aggfunc="sum", fill_value=0.0)
    d.columns = [str(x) for x in d.columns]
    return d.round(2)


# ----------------------------------------------------------------------------------------------- aggregation
def aggregate(is_df, bs_df, cf_df, freq: str):
    """Quarterly ('Q') or annual ('Y') statements. Flows are summed; balances taken at period end."""
    per = pd.PeriodIndex(is_df.columns, freq="M")
    key = per.asfreq("Q").astype(str) if freq == "Q" else per.year.astype(str)
    agg_is = is_df.T.groupby(key.values).sum().T
    agg_cf = cf_df.T.groupby(key.values).sum().T
    last = pd.Series(is_df.columns, index=key.values).groupby(level=0).last()
    first = pd.Series(is_df.columns, index=key.values).groupby(level=0).first()
    agg_cf.loc["open_cash"] = [cf_df.at["open_cash", first[k]] for k in agg_cf.columns]
    for r in ["close_cash", "bs_cash", "check"]:
        agg_cf.loc[r] = [cf_df.at[r, last[k]] for k in agg_cf.columns]
    agg_bs = bs_df[[last[k] for k in agg_is.columns]]
    agg_bs.columns = agg_is.columns
    return agg_is.round(2), agg_bs.round(2), agg_cf.round(2)


# ----------------------------------------------------------------------------------------------- subsidiary ledgers & schedules
def open_items(items: pd.DataFrame, at: pd.Timestamp) -> pd.DataFrame:
    return items[(items.doc_date <= at) & (items.due_date > at)]


def subledger_reconciliation(gl, ar_items, ap_items) -> pd.DataFrame:
    b = balances(gl)
    rows = []
    for m in MONTHS:
        at = m.end_time.normalize()
        for acct in ["1100", "1110", "1120", "1130"]:
            sub = open_items(ar_items[ar_items.account == acct], at).amount.sum()
            rows.append({"month": str(m), "control_account": acct, "ledger": "AR", "gl_balance": round(b.at[m, acct], 2), "subledger_open_items": round(sub, 2)})
        for acct in ["2000", "2010"]:
            sub = open_items(ap_items[ap_items.account == acct], at).amount.sum()
            rows.append({"month": str(m), "control_account": acct, "ledger": "AP", "gl_balance": round(-b.at[m, acct], 2), "subledger_open_items": round(sub, 2)})
    r = pd.DataFrame(rows)
    r["difference"] = (r.gl_balance - r.subledger_open_items).round(2)
    return r


def aging(items: pd.DataFrame, at=pd.Timestamp(END), basis="doc_date") -> pd.DataFrame:
    o = open_items(items, at).copy()
    o["days_outstanding"] = (at - o[basis]).dt.days
    o["bucket"] = pd.cut(o.days_outstanding, [-1, 30, 60, 90, 10_000], labels=["0-30", "31-60", "61-90", "90+"])
    return o


def inventory_valuation(T) -> pd.DataFrame:
    """Independent month-end inventory value from the operational movement records (qty x standard cost)."""
    cost = T["products"].set_index("product_id").est_purchase_cost_cad
    mv = T["moves"].assign(value=lambda x: x.quantity * x.product_id.map(cost), month=lambda x: x.movement_date.dt.to_period("M"))
    v = mv.groupby("month").value.sum().reindex(MONTHS, fill_value=0.0).cumsum()
    q = mv.groupby("month").quantity.sum().reindex(MONTHS, fill_value=0.0).cumsum()
    by_class = mv.assign(k=mv.product_id.map(T["products"].set_index("product_id").product_class)).pivot_table(
        index="month", columns="k", values="value", aggfunc="sum", fill_value=0.0).reindex(MONTHS, fill_value=0.0).cumsum()
    out = pd.DataFrame({"units_on_hand": q, "value_from_movements": v.round(2)}).join(by_class.round(2))
    out.index = out.index.astype(str)
    return out


def fixed_asset_register() -> pd.DataFrame:
    dep = fixed_asset_schedule()
    acc = dep[dep.month <= pd.Period(END, "M")].groupby("asset_id").depreciation.sum()
    rows = []
    for aid, desc, acct, acq, cost, life in P.FIXED_ASSETS:
        a = round(acc.get(aid, 0.0), 2)
        rows.append({"asset_id": aid, "description": desc, "account": acct, "acquired": acq, "cost": cost, "useful_life_months": life,
                     "monthly_depreciation": round(cost / life, 2), "accumulated_depreciation_30sep2026": a, "net_book_value_30sep2026": round(cost - a, 2),
                     "data_status": "SIMULATED"})
    return pd.DataFrame(rows)


def build(L: dict) -> dict:
    gl = L["gl"]
    is_m = income_statement(gl)
    bs_m = balance_sheet(gl)
    cf_m = cash_flow(gl, is_m)
    bs_open = bs_m["2023-12"]
    bs_m = bs_m.drop(columns="2023-12")
    is_q, bs_q, cf_q = aggregate(is_m, bs_m, cf_m, "Q")
    is_y, bs_y, cf_y = aggregate(is_m, bs_m, cf_m, "Y")
    return dict(is_m=is_m, bs_m=bs_m, cf_m=cf_m, bs_open=bs_open, is_q=is_q, bs_q=bs_q, cf_q=cf_q, is_y=is_y, bs_y=bs_y, cf_y=cf_y,
                tb=trial_balances(gl), direct=direct_cash_flow(gl), subledger=subledger_reconciliation(gl, L["ar_items"], L["ap_items"]),
                inv_val=inventory_valuation(L["T"]), far=fixed_asset_register(), bal=balances(gl))
