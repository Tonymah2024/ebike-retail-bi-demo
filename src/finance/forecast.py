"""Phase 15 - integrated, driver-based 12-month forecast (Oct 2026 - Sep 2027) of the ILLUSTRATIVE Calgary accounts.

Single source of truth: every forecast line is ONE formula template (ROWS below). The same template is
  * evaluated in Python (run()), and
  * written into the Excel model as a live formula (src.finance.excel), so the workbook recalculates when
    assumptions change and cannot drift from the Python results.
Template tokens:  {key} same month | {key[-1]} prior month (t=0 = actual 30-Sep-2026 opening) | {key[+1]} next month
(wraps to month 1 as a seasonal proxy past the horizon) | {key@1} month 1 | {$name} active scenario assumption.

Drivers are explicit (units x price, discount %, unit cost, attach revenue, service revenue, staffing plan, lease
schedule, inventory months-of-cover policy, DSO/DPO/deposit ratios, GST timing, debt terms, treasury rules) rather
than arbitrary growth rates. Base volumes come from Model 1 (Prophet) forecasts. All values are SIMULATED.
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass, field, replace

import numpy as np
import pandas as pd

from src.config import END, TABLES
from src.finance import policy as P
from src.finance.ledger import fixed_asset_schedule, prime_rate
from src.finance.statements import MONTHS

H = 12
FC_MONTHS = pd.period_range("2026-10", periods=H, freq="M")
TTM = pd.period_range("2025-10", END, freq="M")


# ----------------------------------------------------------------------------------------------- assumptions
@dataclass
class Scenario:
    demand_mult: float = 1.0        # e-bike units and accessory volume vs Model 1 base forecast
    price_change: float = 0.0       # list-price change
    elasticity: float = -1.2        # bike unit response to price (ASSUMPTION, not causally estimated)
    discount_delta: float = 0.0     # change in average bike discount rate (fraction, +0.01 = +1 pt)
    margin_pts: float = 0.0         # merchandise gross-margin improvement from buying/mix (fraction of net merch revenue)
    supplier_cost: float = 0.0      # supplier / inventory cost change
    service_mult: float = 1.0       # service revenue vs Model 1 base forecast
    dpo_delta: float = 0.0          # change in supplier payment days
    rate_delta: float = 0.0         # change in prime rate (fraction, +0.01 = +100 bps)
    cover_mult: float = 1.0         # inventory months-of-cover policy multiplier


SCENARIOS = {
    "Conservative": Scenario(demand_mult=0.92, supplier_cost=0.03, discount_delta=0.01, service_mult=0.97, dpo_delta=-5, rate_delta=0.005, cover_mult=1.05),
    "Base": Scenario(),
    "Optimistic": Scenario(demand_mult=1.06, price_change=0.02, discount_delta=-0.01, margin_pts=0.01, service_mult=1.10, dpo_delta=5, rate_delta=-0.0025, cover_mult=0.90),
}
SCENARIO_NOTES = {
    "Conservative": "Demand -8%, supplier costs +3% (CAD/USD, tariffs), +1 pt discounting, service -3%, suppliers tighten terms by 5 days, prime +50 bps, slower sell-through (+5% cover).",
    "Base": "Model 1 (Prophet) volumes, TTM prices/discounts/costs, current staffing and lease schedule, current working-capital ratios, prime flat at 4.45%.",
    "Optimistic": "Demand +6%, +2% list price, -1 pt discounting, +1 pt merchandise margin, service +10%, +5 supplier days, prime -25 bps, leaner inventory (-10% cover).",
}
SCENARIO_FIELDS = [  # name, label, unit
    ("demand_mult", "Demand multiplier (bikes & accessories)", "x"), ("price_change", "List-price change", "%"),
    ("elasticity", "Price elasticity of bike units", "x"), ("discount_delta", "Change in bike discount rate", "pts"),
    ("margin_pts", "Merchandise gross-margin improvement", "pts"), ("supplier_cost", "Supplier / inventory cost change", "%"),
    ("service_mult", "Service revenue multiplier", "x"), ("dpo_delta", "Change in supplier payment days", "days"),
    ("rate_delta", "Change in prime rate", "%"), ("cover_mult", "Inventory cover policy multiplier", "x"),
]
FIXED_LABELS = {
    "asp_list": "Average e-bike list price (TTM)", "d_b": "Bike discount rate (TTM)", "r_b": "Bike return rate (TTM, % of net)",
    "d_a": "Accessory discount rate (TTM)", "r_a": "Accessory return rate (TTM)", "uc_bike": "Average e-bike unit cost (TTM)",
    "c_a": "Accessory COGS ratio (TTM)", "shrink_rate": "Shrinkage & write-offs, % of merchandise COGS", "parts_ratio": "Service parts cost, % of service revenue",
    "labour_ratio": "Direct service labour, % of service revenue", "comm_rate": "Sales commission on net bike revenue", "freight_rate": "Freight, % of inventory purchases",
    "fee_rate": "Merchant & financing fees, % of net revenue", "storage_rate": "Physical carrying cost, % of avg inventory p.a.", "ar_ratio": "Receivables, months of gross (incl. GST) revenue",
    "wip_ratio": "Service WIP, months of service cost", "dep_ratio": "Supplier deposits, months of purchases", "dpo_base": "Supplier payment days (TTM, inventory & parts)",
    "ap_opex_ratio": "Operating-vendor payables, months of vendor spend", "accrued_ratio": "Accrued payroll, months of payroll", "gst": "GST rate",
    "tax_rate": "Income-tax rate (allocated)", "prime": "Prime rate (BoC policy 2.25% + 2.20%)", "term_spread": "Term-loan spread over prime",
    "rev_spread": "Revolver spread over prime", "rev_limit": "Revolver limit", "min_cash": "Minimum month-end cash", "target_cash": "Target cash after a draw",
    "repay_above": "Repay revolver when cash above", "step": "Revolver draw/repay increment", "dist_trigger": "Year-end distribution trigger (cash above)",
    "dist_floor": "Cash retained after distribution", "term_pmt": "Term-loan principal instalment", "new_capex_life": "Useful life of new capex (months)",
    "corp_alloc": "Corporate shared-services allocation / month",
}


# ----------------------------------------------------------------------------------------------- formula rows
# (key, label, section, template, phase)   phase: s = static (driver-only, evaluated row-by-row), d = dynamic (month-by-month)
D = "Drivers"
ROWS = [
    # ---- volume & revenue
    ("units", "E-bike units sold (net of returns)", "Revenue build", "{units_base}*{$demand_mult}*(1+{$price_change})**{$elasticity}", "s"),
    ("asp", "Average e-bike list price", "Revenue build", "{$asp_list}*(1+{$price_change})", "s"),
    ("disc_rate", "Bike discount rate", "Revenue build", "{$d_b}+{$discount_delta}", "s"),
    ("bike_net", "Net e-bike revenue (after discounts & returns)", "Revenue build", "{units}*{asp}*(1-{disc_rate})", "s"),
    ("acc_net", "Net accessories & parts revenue", "Revenue build", "{acc_net_base}*{$demand_mult}*(1+{$price_change})", "s"),
    ("bike_rev", "Bicycle sales revenue", "Income statement", "{units}*{asp}/(1-{$r_b})", "s"),
    ("acc_rev", "Accessories and parts revenue", "Income statement", "{acc_net}/((1-{$d_a})*(1-{$r_a}))", "s"),
    ("svc_rev", "Maintenance and repair revenue", "Income statement", "{svc_base}*{$service_mult}", "s"),
    ("gross_rev", "Gross revenue", "Income statement", "{bike_rev}+{acc_rev}+{svc_rev}", "s"),
    ("discounts", "Sales discounts & promotional allowances", "Income statement", "-({bike_rev}*{disc_rate}+{acc_rev}*{$d_a})", "s"),
    ("returns", "Sales returns & refunds", "Income statement", "-({$r_b}*{bike_rev}*(1-{disc_rate})+{$r_a}*{acc_rev}*(1-{$d_a}))", "s"),
    ("returns_allow", "Sales returns and allowances", "Income statement", "{discounts}+{returns}", "s"),
    ("net_rev", "Net revenue", "Income statement", "{gross_rev}+{returns_allow}", "s"),
    # ---- cost of sales
    ("cogs_bike", "Cost of goods sold - e-bikes", "Income statement", "-({units}*{$uc_bike}*(1+{$supplier_cost})-{$margin_pts}*{bike_net})", "s"),
    ("cogs_acc", "Cost of goods sold - accessories, batteries & parts", "Income statement", "-({acc_net_base}*{$demand_mult}*{$c_a}*(1+{$supplier_cost})-{$margin_pts}*{acc_net})", "s"),
    ("merch_cogs", "Merchandise COGS (memo)", "Income statement", "{cogs_bike}+{cogs_acc}", "s"),
    ("shrink", "Inventory shrinkage & write-offs", "Income statement", "{merch_cogs}*{$shrink_rate}", "s"),
    ("svc_parts", "Service parts cost", "Income statement", "-{svc_rev}*{$parts_ratio}", "s"),
    ("svc_labour", "Direct service labour", "Income statement", "-MIN({tech_payroll},{svc_rev}*{$labour_ratio})", "s"),
    ("cogs", "Cost of goods sold (total cost of sales)", "Income statement", "{merch_cogs}+{shrink}+{svc_parts}+{svc_labour}", "s"),
    ("gross_profit", "Gross profit", "Income statement", "{net_rev}+{cogs}", "s"),
    # ---- operating expenses
    ("commission", "Sales commission (memo)", "Opex build", "{$comm_rate}*{bike_net}", "s"),
    ("emp_comp", "Employee compensation", "Income statement", "-({staff_payroll}+{commission}+{tech_payroll}+{svc_labour})", "s"),
    ("rent", "Rent and occupancy", "Income statement", "-{rent_d}", "s"),
    ("utilities", "Utilities", "Income statement", "-{utilities_d}", "s"),
    ("marketing", "Marketing and advertising", "Income statement", "-{marketing_d}", "s"),
    ("admin", "Administrative expenses (incl. insurance & corporate allocation)", "Income statement", "-({insurance_exp}+{admin_local}+{$corp_alloc})", "s"),
    ("fees", "Merchant and financing fees", "Income statement", "-{$fee_rate}*{net_rev}", "s"),
    ("inv_target", "Inventory target (cover x avg next-2-month merchandise COGS)", "Inventory", "-{cover_k}*{$cover_mult}*({merch_cogs[+1]}+{merch_cogs[+2]})/2", "s"),
    ("capex_cum", "Cumulative new capex (memo)", "Fixed assets", "{capex_cum[-1]}+{capex_d}", "s"),
    ("da", "Depreciation and amortization", "Income statement", "-({da_existing}+{capex_cum[-1]}/{$new_capex_life})", "s"),
    # ---- inventory (dynamic)
    ("purchases", "Inventory purchases at cost", "Inventory", "MAX(0,{inv_target}-{inventory[-1]}-{merch_cogs}-{shrink})", "d"),
    ("inventory", "Inventory (merchandise at cost)", "Balance sheet", "{inventory[-1]}+{purchases}+{merch_cogs}+{shrink}", "d"),
    ("freight", "Freight and logistics", "Income statement", "-{$freight_rate}*{purchases}", "d"),
    ("storage", "Inventory storage, handling & obsolescence", "Income statement", "-{$storage_rate}/12*({inventory[-1]}+{inventory})/2", "d"),
    ("opex", "Total operating expenses (before D&A)", "Income statement", "{emp_comp}+{rent}+{utilities}+{marketing}+{admin}+{freight}+{fees}+{storage}", "d"),
    ("ebitda", "EBITDA", "Income statement", "{gross_profit}+{opex}", "d"),
    ("ebit", "EBIT (operating profit)", "Income statement", "{ebitda}+{da}", "d"),
    ("interest", "Interest expense", "Income statement", "-({term_loan[-1]}*({$prime}+{$rate_delta}+{$term_spread})+{revolver[-1]}*({$prime}+{$rate_delta}+{$rev_spread}))/12", "d"),
    ("pbt", "Profit before tax", "Income statement", "{ebit}+{interest}", "d"),
    ("ytd_pbt", "Fiscal YTD profit before tax (memo)", "Tax", "IF({is_jan},0,{ytd_pbt[-1]})+{pbt}", "d"),
    ("lcf", "Loss carry-forward available at 1 January (memo)", "Tax", "IF({is_jan},MAX(0,{lcf[-1]}-{ytd_pbt[-1]}),{lcf[-1]})", "d"),
    ("tax_ytd", "Fiscal YTD income tax (memo)", "Tax", "{$tax_rate}*MAX(0,{ytd_pbt}-{lcf})", "d"),
    ("tax", "Income taxes", "Income statement", "-({tax_ytd}-IF({is_jan},0,{tax_ytd[-1]}))", "d"),
    ("net_income", "Net income", "Income statement", "{pbt}+{tax}", "d"),
    # ---- working capital balances
    ("ar", "Accounts receivable", "Balance sheet", "{$ar_ratio}*{net_rev}*(1+{$gst})", "d"),
    ("wip", "Service work in progress", "Balance sheet", "-{$wip_ratio}*({svc_parts}+{svc_labour})", "d"),
    ("prepaid_ins", "Prepaid insurance (memo)", "Working capital", "{prepaid_ins[-1]}+{insurance_premium}-{insurance_exp}", "d"),
    ("deposits", "Supplier deposits (memo)", "Working capital", "{$dep_ratio}*{purchases}", "d"),
    ("gst_remit", "GST remitted for prior quarter (memo)", "Working capital", "IF({q_start},{gst_net[-1]},0)", "d"),
    ("gst_net", "Net GST payable / (recoverable) (memo)", "Working capital",
     "{gst_net[-1]}+{$gst}*({net_rev}-({purchases}-{svc_parts}+{rent_d}+{utilities_d}+{marketing_d}+{admin_local}-{freight}-{storage}+{capex_d}))-{gst_remit}", "d"),
    ("ap_trade", "Trade payables - inventory & parts (memo)", "Working capital", "({$dpo_base}+{$dpo_delta})/30.4*({purchases}-{svc_parts})*(1+{$gst})", "d"),
    ("ap_opex", "Operating-vendor payables (memo)", "Working capital",
     "{$ap_opex_ratio}*(({utilities_d}+{marketing_d}+{admin_local}-{freight}-{storage})*(1+{$gst})-{fees})", "d"),
    ("accrued_pay", "Accrued payroll (memo)", "Working capital", "{$accrued_ratio}*({staff_payroll}+{commission}+{tech_payroll})", "d"),
    ("due_ho", "Due to head office (memo)", "Working capital", "{due_ho[-1]}+{$corp_alloc}-IF({q_start},{due_ho[-1]},0)", "d"),
    ("prior_tax", "Prior-year tax awaiting payment (memo)", "Tax", "IF({is_jan},{tax_ytd[-1]},IF({is_feb},0,{prior_tax[-1]}))", "d"),
    ("tax_paid", "Income tax paid (memo)", "Tax", "IF({is_feb},{prior_tax[-1]},0)", "d"),
    ("tax_payable", "Income taxes payable", "Balance sheet", "{tax_payable[-1]}-{tax}-{tax_paid}", "d"),
    ("ppe_gross", "Property, plant and equipment (cost)", "Balance sheet", "{ppe_gross[-1]}+{capex_d}", "d"),
    ("acc_dep", "Accumulated depreciation", "Balance sheet", "{acc_dep[-1]}+{da}", "d"),
    # ---- cash flow (indirect) and financing
    ("cf_ni", "Net income", "Cash flow", "{net_income}", "d"),
    ("cf_da", "Depreciation and amortization", "Cash flow", "-{da}", "d"),
    ("d_ar", "(Increase) decrease in accounts receivable", "Cash flow", "{ar[-1]}-{ar}", "d"),
    ("d_inv", "(Increase) decrease in inventory", "Cash flow", "{inventory[-1]}-{inventory}", "d"),
    ("d_ap", "Increase (decrease) in accounts payable", "Cash flow", "{ap_trade}+{ap_opex}-{ap_trade[-1]}-{ap_opex[-1]}", "d"),
    ("other_wc", "Other working capital adjustments", "Cash flow",
     "{wip[-1]}-{wip}+{prepaid_ins[-1]}+{deposits[-1]}-{prepaid_ins}-{deposits}+{accrued_pay}+{due_ho}-{accrued_pay[-1]}-{due_ho[-1]}+{gst_net}-{gst_net[-1]}+{tax_payable}-{tax_payable[-1]}", "d"),
    ("cfo", "Net cash from operating activities", "Cash flow", "{cf_ni}+{cf_da}+{d_ar}+{d_inv}+{d_ap}+{other_wc}", "d"),
    ("cfi", "Net cash used in investing activities (capex)", "Cash flow", "-{capex_d}", "d"),
    ("term_repay", "Term loan repayments", "Cash flow", "-MIN({$term_pmt},{term_loan[-1]})", "d"),
    ("pre_cash", "Cash before revolver (memo)", "Cash flow", "{cash[-1]}+{cfo}+{cfi}+{term_repay}", "d"),
    ("rev_draw", "New borrowings - revolving line of credit", "Cash flow",
     "IF({pre_cash}<{$min_cash},MIN({$rev_limit}-{revolver[-1]},CEIL(MAX(0,{$target_cash}-{pre_cash}),{$step})),0)", "d"),
    ("rev_repay", "Repayments - revolving line of credit", "Cash flow",
     "IF(({pre_cash}>{$repay_above})*({revolver[-1]}>0),-MIN({revolver[-1]},FLOOR(MAX(0,{pre_cash}-{$target_cash}),{$step})),0)", "d"),
    ("contrib", "Capital contributions from head office (financing requirement)", "Cash flow",
     "IF({pre_cash}+{rev_draw}<{$min_cash},CEIL(MAX(0,{$target_cash}-{pre_cash}-{rev_draw}),{$step}),0)", "d"),
    ("revolver", "Short-term borrowings - revolving line of credit", "Balance sheet", "{revolver[-1]}+{rev_draw}+{rev_repay}", "d"),
    ("dist", "Distributions to head office", "Cash flow",
     "IF({is_dec}*({revolver}<0.005)*({pre_cash}+{rev_draw}+{rev_repay}+{contrib}>{$dist_trigger}),-FLOOR(MAX(0,{pre_cash}+{rev_draw}+{rev_repay}+{contrib}-{$dist_floor}),1000),0)", "d"),
    ("cff", "Net cash from (used in) financing activities", "Cash flow", "{term_repay}+{rev_draw}+{rev_repay}+{contrib}+{dist}", "d"),
    ("net_change", "Net change in cash", "Cash flow", "{cfo}+{cfi}+{cff}", "d"),
    ("cash", "Cash and cash equivalents", "Balance sheet", "{cash[-1]}+{net_change}", "d"),
    ("term_loan", "Term loan balance (memo)", "Balance sheet", "{term_loan[-1]}+{term_repay}", "d"),
    ("equity_cap", "Share capital / allocated corporate equity", "Balance sheet", "{equity_cap[-1]}+{contrib}", "d"),
    ("cpe", "Current period earnings", "Balance sheet", "IF({is_dec},0,{cpe[-1]}+{net_income})", "d"),
    ("retained", "Retained earnings", "Balance sheet", "{retained[-1]}+IF({is_dec},{cpe[-1]}+{net_income},0)+{dist}", "d"),
    # ---- balance-sheet presentation
    ("prepaid", "Prepaid expenses & supplier deposits", "Balance sheet", "{prepaid_ins}+{deposits}", "d"),
    ("gst_rec", "Sales tax recoverable", "Balance sheet", "MAX(0,-{gst_net})", "d"),
    ("current_assets", "Total current assets", "Balance sheet", "{cash}+{ar}+{inventory}+{wip}+{prepaid}+{gst_rec}", "d"),
    ("ppe_net", "Net property, plant and equipment", "Balance sheet", "{ppe_gross}+{acc_dep}", "d"),
    ("total_assets", "TOTAL ASSETS", "Balance sheet", "{current_assets}+{ppe_net}", "d"),
    ("ap", "Accounts payable", "Balance sheet", "{ap_trade}+{ap_opex}", "d"),
    ("accrued", "Accrued expenses (payroll & head office)", "Balance sheet", "{accrued_pay}+{due_ho}", "d"),
    ("gst_pay", "Sales tax payable", "Balance sheet", "MAX(0,{gst_net})", "d"),
    ("term_current", "Current portion of long-term debt", "Balance sheet", "MIN({term_loan},12*{$term_pmt})", "d"),
    ("current_liabilities", "Total current liabilities", "Balance sheet", "{ap}+{accrued}+{tax_payable}+{gst_pay}+{revolver}+{term_current}", "d"),
    ("term_lt", "Long-term debt (non-current portion)", "Balance sheet", "{term_loan}-{term_current}", "d"),
    ("total_liabilities", "TOTAL LIABILITIES", "Balance sheet", "{current_liabilities}+{term_lt}", "d"),
    ("total_equity", "TOTAL EQUITY", "Balance sheet", "{equity_cap}+{retained}+{cpe}", "d"),
    ("total_le", "TOTAL LIABILITIES AND EQUITY", "Balance sheet", "{total_liabilities}+{total_equity}", "d"),
    ("check_bs", "Check: assets - liabilities - equity (must be 0)", "Checks", "{total_assets}-{total_le}", "d"),
    ("check_cash", "Check: CF closing cash - BS cash (must be 0)", "Checks", "{cash[-1]}+{net_change}-{cash}", "d"),
]
ROW = {r[0]: r for r in ROWS}
DRIVER_ROWS = [  # key, label (monthly inputs on the Drivers sheet)
    ("units_base", "E-bike units - Model 1 Prophet base forecast"), ("acc_net_base", "Net accessories & parts revenue - Model 1 base (retail less bikes)"),
    ("svc_base", "Service revenue - Model 1 Prophet base forecast"), ("staff_payroll", "Sales, management & admin payroll (excl. commission) - staffing plan"),
    ("tech_payroll", "Technician payroll capacity - staffing plan"), ("rent_d", "Rent - lease schedule (3% escalation each January)"),
    ("utilities_d", "Utilities - seasonal TTM +2.5%"), ("marketing_d", "Marketing plan - seasonal TTM +6%"),
    ("insurance_exp", "Insurance expense - policy schedule"), ("insurance_premium", "Insurance premium paid (January)"),
    ("admin_local", "Local administrative costs"), ("capex_d", "Capital expenditure plan"), ("da_existing", "Depreciation - existing asset register"),
    ("cover_k", "Inventory policy: months of forward cover (seasonal, from history)"),
    ("is_jan", "Flag: January"), ("is_feb", "Flag: February"), ("is_dec", "Flag: December"), ("q_start", "Flag: first month of quarter"),
]
OPENING = {  # rows that carry an actual 30-Sep-2026 opening balance (t=0); value = GL-derived (see opening_values)
    "inventory", "ar", "wip", "prepaid_ins", "deposits", "gst_net", "ap_trade", "ap_opex", "accrued_pay", "due_ho", "tax_payable",
    "ppe_gross", "acc_dep", "cash", "term_loan", "revolver", "equity_cap", "retained", "cpe", "ytd_pbt", "lcf", "tax_ytd", "prior_tax", "capex_cum",
}
TOK = re.compile(r"\{(\$?)([a-z_0-9]+)(\[[+-]\d\]|@\d+)?\}")


# ----------------------------------------------------------------------------------------------- calibration (history -> drivers)
def calibrate(L: dict, S: dict) -> dict:
    gl, T = L["gl"], L["T"]
    is_m, bal = S["is_m"], S["bal"]
    ttm = [str(m) for m in TTM]
    s = T["sales"].assign(month=lambda x: x.transaction_date.dt.to_period("M"))
    ret = T["returns"].merge(T["sales"][["line_id", "product_class"]], on="line_id")
    ret["month"] = ret.return_date.dt.to_period("M")
    st = s[s.month.isin(TTM)]
    rt = ret[ret.month.isin(TTM)]
    bk, ac = st[st.product_class == "E-Bike"], st[st.product_class != "E-Bike"]
    A = {}
    A["asp_list"] = bk.gross_sales_cad.sum() / bk.units_sold.sum()
    A["d_b"] = 1 - bk.net_sales_cad.sum() / bk.gross_sales_cad.sum()
    A["r_b"] = rt[rt.product_class == "E-Bike"].refund_amount_cad.sum() / bk.net_sales_cad.sum()
    A["d_a"] = 1 - ac.net_sales_cad.sum() / ac.gross_sales_cad.sum()
    A["r_a"] = rt[rt.product_class != "E-Bike"].refund_amount_cad.sum() / ac.net_sales_cad.sum()
    A["uc_bike"] = (bk.units_sold * bk.unit_cost_cad).sum() / bk.units_sold.sum()
    acc_net_after = ac.net_sales_cad.sum() - rt[rt.product_class != "E-Bike"].refund_amount_cad.sum()
    A["c_a"] = -is_m.loc["cogs_acc", ttm].sum() / acc_net_after
    merch = -(is_m.loc["cogs_bike", ttm] + is_m.loc["cogs_acc", ttm])
    A["shrink_rate"] = -is_m.loc["shrink", ttm].sum() / merch.sum()
    svc = is_m.loc["svc_rev", ttm].sum()
    A["parts_ratio"] = -is_m.loc["svc_parts", ttm].sum() / svc
    A["labour_ratio"] = -is_m.loc["svc_labour", ttm].sum() / svc
    A["comm_rate"] = 0.015
    rc = gl[(gl.source == "Purchasing") & (gl.account == "1200")].groupby("month").debit.sum().reindex(MONTHS, fill_value=0.0)
    rc.index = rc.index.astype(str)
    A["freight_rate"] = -is_m.loc["freight", ttm].sum() / rc[ttm].sum()
    A["fee_rate"] = -is_m.loc["fees", ttm].sum() / is_m.loc["net_rev", ttm].sum()
    A["storage_rate"] = P.PHYSICAL_CARRY_RATE
    b = bal.loc[TTM]
    nr = is_m.loc["net_rev", ttm].values
    A["ar_ratio"] = float(np.mean(b[["1100", "1110", "1120", "1130"]].sum(axis=1).values / (nr * (1 + P.GST_RATE))))
    svc_cost = -(is_m.loc["svc_parts", ttm] + is_m.loc["svc_labour", ttm]).values
    A["wip_ratio"] = float(np.mean(b["1250"].values / svc_cost))
    rcv = rc[ttm].values
    A["dep_ratio"] = float(np.mean(b["1310"].values[rcv > 0] / rcv[rcv > 0]))
    parts = -is_m.loc["svc_parts", ttm].values
    A["dpo_base"] = float(np.mean(-b["2000"].values / ((rcv + parts) * (1 + P.GST_RATE)))) * 30.4
    vend = ((-(is_m.loc["utilities", ttm] + is_m.loc["marketing", ttm] + is_m.loc["freight", ttm] + is_m.loc["storage", ttm])).values
            + gl[(gl.account == "6310")].groupby("month").debit.sum().reindex(TTM).values) * (1 + P.GST_RATE) - is_m.loc["fees", ttm].values
    A["ap_opex_ratio"] = float(np.mean(-b["2010"].values / vend))
    A["accrued_ratio"] = 1 - P.PAYROLL_FIRST_HALF
    A["gst"] = P.GST_RATE
    A["tax_rate"] = P.INCOME_TAX_RATE
    A["prime"] = float(prime_rate(T["econ"]).iloc[-1])
    A["term_spread"] = P.TERM_LOAN["spread"]
    A["rev_spread"] = P.REVOLVER["spread"]
    for k in ["limit", "min_cash", "target_cash", "repay_above", "step"]:
        A[{"limit": "rev_limit"}.get(k, k)] = P.REVOLVER[k]
    A["dist_trigger"], A["dist_floor"] = 250000.0, 150000.0
    A["term_pmt"] = round(P.TERM_LOAN["principal"] / P.TERM_LOAN["months"], 2)
    A["new_capex_life"] = 60.0
    A["corp_alloc"] = P.CORPORATE_ALLOCATION_MONTHLY
    return {k: float(v) for k, v in A.items()}


def drivers(L: dict, S: dict, A: dict) -> pd.DataFrame:
    """Monthly driver rows (index = driver key, columns = 1..12)."""
    gl, T = L["gl"], L["T"]
    is_m = S["is_m"]
    fc = pd.read_csv(TABLES / "forecast_next_12_months.csv", parse_dates=["month"])
    fc = fc[fc.selected]
    g = lambda t: fc[fc.target == t].sort_values("month").forecast.values[:H]
    units = g("bike_units")
    retail = g("retail_revenue")
    svc = g("service_revenue")
    bike_net_base = units * A["asp_list"] * (1 - A["d_b"])
    acc = np.maximum(retail - bike_net_base, 0.0)
    same = [str(m - 12) for m in FC_MONTHS]                     # same calendar month, prior year (inside TTM)
    o = T["opex"].assign(m=T["opex"].month.dt.to_period("M").astype(str)).set_index("m")
    sv = T["services"]
    direct = sv.groupby(sv.date_received.dt.to_period("M").astype(str)).service_cost_cad.sum()
    s = T["sales"]
    bike_net_hist = s[s.product_class == "E-Bike"].groupby(s.transaction_date.dt.to_period("M").astype(str)).net_sales_cad.sum()
    wage_infl, infl = 1.03, 1.025
    staff = np.array([(o.at[m, "staff_wages_cad"] - A["comm_rate"] * bike_net_hist.get(m, 0.0)) * wage_infl for m in same])
    tech = np.array([(o.at[m, "technician_assembly_idle_time_cad"] + direct.get(m, 0.0)) * wage_infl for m in same])
    rent_sep = o.at[END[:7], "rent_cad"]
    rent = np.array([rent_sep * (1.03 if m.year == 2027 else 1.0) for m in FC_MONTHS])
    util = np.array([o.at[m, "utilities_cad"] * infl for m in same])
    mkt = np.array([o.at[m, "advertising_cad"] * 1.06 for m in same])
    ins26 = o.at[END[:7], "insurance_cad"]
    ins = np.array([ins26 * (1.04 if m.year == 2027 else 1.0) for m in FC_MONTHS])
    prem = np.array([ins26 * 1.04 * 12 if m.month == 1 else 0.0 for m in FC_MONTHS])
    admin_local = (o.loc[[str(m) for m in TTM], "administrative_cad"].mean() - P.CORPORATE_ALLOCATION_MONTHLY) * infl
    capex = np.array([6000.0 if str(m) == "2027-01" else 12000.0 if str(m) == "2027-03" else 0.0 for m in FC_MONTHS])
    dep = fixed_asset_schedule(until="2027-09")
    da = dep.groupby("month").depreciation.sum().reindex(FC_MONTHS, fill_value=0.0).values
    # inventory policy: historical month-end inventory / average merchandise COGS of the next two months, by calendar month
    inv = S["bal"]["1200"].loc[MONTHS]
    merch = -(is_m.loc["cogs_bike"] + is_m.loc["cogs_acc"]).values
    ratios = {}
    for i, m in enumerate(MONTHS[:-2]):
        ratios.setdefault(m.month, []).append(inv.iloc[i] / ((merch[i + 1] + merch[i + 2]) / 2))
    cover = np.array([np.mean(ratios[m.month]) for m in FC_MONTHS])
    Dv = pd.DataFrame({
        "units_base": units, "acc_net_base": acc, "svc_base": svc, "staff_payroll": staff, "tech_payroll": tech, "rent_d": rent,
        "utilities_d": util, "marketing_d": mkt, "insurance_exp": ins, "insurance_premium": prem, "admin_local": np.full(H, admin_local),
        "capex_d": capex, "da_existing": da, "cover_k": cover,
        "is_jan": [int(m.month == 1) for m in FC_MONTHS], "is_feb": [int(m.month == 2) for m in FC_MONTHS],
        "is_dec": [int(m.month == 12) for m in FC_MONTHS], "q_start": [int(m.month in (1, 4, 7, 10)) for m in FC_MONTHS],
    }, index=range(1, H + 1)).T
    return Dv


def opening_values(L: dict, S: dict) -> dict:
    """Actual 30-Sep-2026 balances (t=0), all taken from the general ledger."""
    b = S["bal"].loc[pd.Period(END, "M")]
    tr = L["treasury"].set_index("month")
    is26 = S["is_m"][[c for c in S["is_m"].columns if c.startswith("2026")]]
    return {
        "inventory": b["1200"], "ar": b[["1100", "1110", "1120", "1130"]].sum(), "wip": b["1250"], "prepaid_ins": b["1300"], "deposits": b["1310"],
        "gst_net": -(b["1400"] + b["2300"]), "ap_trade": -b["2000"], "ap_opex": -b["2010"], "accrued_pay": -b["2100"], "due_ho": -b["2500"],
        "tax_payable": -b["2400"], "ppe_gross": b[["1500", "1510", "1520"]].sum(), "acc_dep": b["1590"], "cash": b["1000"],
        "term_loan": -b["2700"], "revolver": -b["2600"], "equity_cap": -b["3000"], "retained": -(b["3200"] + b["3300"]),
        "cpe": S["bs_m"].at["cpe", END[:7]], "ytd_pbt": is26.loc["pbt"].sum(), "lcf": tr.at[END[:7], "loss_carryforward_start_of_year"],
        "tax_ytd": -is26.loc["tax"].sum(), "prior_tax": 0.0, "capex_cum": 0.0,
    }


# ----------------------------------------------------------------------------------------------- evaluation
def _py(template: str) -> str:
    def sub(m):
        dollar, key, suf = m.groups()
        if dollar:
            return f"A['{key}']"
        if not suf:
            return f"V['{key}'][t]"
        if suf.startswith("@"):
            return f"V['{key}'][{int(suf[1:])}]"
        k = int(suf[1:-1])
        return f"V['{key}'][W(t{k:+d})]"
    return TOK.sub(sub, template).replace("CEIL(", "CEIL(").replace("FLOOR(", "FLOOR(")


FUN = dict(IF=lambda c, a, b: a if c else b, MAX=max, MIN=min, CEIL=lambda x, s: math.ceil(round(x / s, 9)) * s,
           FLOOR=lambda x, s: math.floor(round(x / s, 9)) * s, W=lambda i: i if i <= H else i - H)
COMPILED = {k: compile(_py(tpl), k, "eval") for k, _, _, tpl, _ in ROWS}


def run(sc: Scenario, base: dict) -> pd.DataFrame:
    """Evaluate the forecast for one scenario. Returns rows x months (0 = opening, 1..12)."""
    A = dict(base["A"])
    A.update({k: float(getattr(sc, k)) for k in sc.__dataclass_fields__})
    V = {k: [0.0] * (H + 1) for k, *_ in ROWS}
    for k in base["drivers"].index:
        V[k] = [0.0] + list(map(float, base["drivers"].loc[k].values))
    for k, v in base["opening"].items():
        V[k][0] = float(v)
    ns = dict(FUN, A=A, V=V)
    for k, _, _, _, ph in ROWS:          # static rows: row by row
        if ph == "s":
            for t in range(1, H + 1):
                ns["t"] = t
                V[k][t] = eval(COMPILED[k], ns)
    for t in range(1, H + 1):            # dynamic rows: month by month, in row order
        ns["t"] = t
        for k, _, _, _, ph in ROWS:
            if ph == "d":
                V[k][t] = eval(COMPILED[k], ns)
    out = pd.DataFrame({k: V[k] for k, *_ in ROWS}).T
    out.columns = ["2026-09 (actual)"] + [str(m) for m in FC_MONTHS]
    return out


def summary(f: pd.DataFrame) -> dict:
    x = f.iloc[:, 1:]
    return {"net_revenue": x.loc["net_rev"].sum(), "gross_profit": x.loc["gross_profit"].sum(), "gross_margin_pct": x.loc["gross_profit"].sum() / x.loc["net_rev"].sum() * 100,
            "ebitda": x.loc["ebitda"].sum(), "ebit": x.loc["ebit"].sum(), "pbt": x.loc["pbt"].sum(), "net_income": x.loc["net_income"].sum(),
            "net_margin_pct": x.loc["net_income"].sum() / x.loc["net_rev"].sum() * 100, "cfo": x.loc["cfo"].sum(),
            "closing_cash": x.loc["cash"].iloc[-1], "min_cash": x.loc["cash"].min(), "peak_revolver": max(0.0, x.loc["revolver"].max()),
            "contributions_required": x.loc["contrib"].sum(), "financing_requirement": max(0.0, x.loc["revolver"].max()) + x.loc["contrib"].sum(),
            "peak_inventory": x.loc["inventory"].max(), "avg_inventory": x.loc["inventory"].mean(), "inventory_purchases": x.loc["purchases"].sum(),
            "bike_units": x.loc["units"].sum(), "max_abs_bs_check": x.loc["check_bs"].abs().max(), "max_abs_cash_check": x.loc["check_cash"].abs().max()}


SENSITIVITIES = [  # label, field, low value, high value
    ("Product demand (-/+10%)", "demand_mult", 0.90, 1.10),
    ("Merchandise gross margin (-/+2 pts)", "margin_pts", -0.02, 0.02),
    ("Inventory / supplier costs (+/-5%)", "supplier_cost", 0.05, -0.05),
    ("Supplier payment terms (-/+10 days)", "dpo_delta", -10, 10),
    ("Interest rates (+/-100 bps)", "rate_delta", 0.01, -0.01),
    ("Service revenue (-/+15%)", "service_mult", 0.85, 1.15),
]


def sensitivity(base: dict) -> pd.DataFrame:
    b = summary(run(SCENARIOS["Base"], base))
    rows = []
    for lab, fld, lo, hi in SENSITIVITIES:
        for case, v in (("downside", lo), ("upside", hi)):
            r = summary(run(replace(SCENARIOS["Base"], **{fld: v}), base))
            rows.append({"driver": lab, "case": case, "value": v, "net_income": r["net_income"], "delta_net_income": r["net_income"] - b["net_income"],
                         "closing_cash": r["closing_cash"], "delta_closing_cash": r["closing_cash"] - b["closing_cash"], "min_cash": r["min_cash"],
                         "peak_revolver": r["peak_revolver"], "financing_requirement": r["financing_requirement"],
                         "delta_financing_requirement": r["financing_requirement"] - b["financing_requirement"]})
    return pd.DataFrame(rows)


def build(L: dict, S: dict) -> dict:
    A = calibrate(L, S)
    base = {"A": A, "drivers": None, "opening": opening_values(L, S)}
    base["drivers"] = drivers(L, S, A)
    res = {name: run(sc, base) for name, sc in SCENARIOS.items()}
    summ = pd.DataFrame({k: summary(v) for k, v in res.items()}).T
    summ["assumptions"] = pd.Series(SCENARIO_NOTES)
    return dict(base=base, results=res, summary=summ, sensitivity=sensitivity(base))
