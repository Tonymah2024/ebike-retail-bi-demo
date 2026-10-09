"""Phase 14 - financial ratio analysis of the ILLUSTRATIVE Calgary management accounts (SIMULATED).

Flow-based ratios use trailing-twelve-month (TTM) flows; balance-based ratios use month-end balances, or the
average of the 13 month-ends spanning the TTM window where a ratio mixes flows and balances.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from src.finance import policy as P

DEFINITIONS = [  # key, name, group, formula, what it tells management, unit, higher_is_better
    ("gross_margin", "Gross profit margin", "Profitability", "Gross profit / net revenue", "Pricing power, discount discipline and product/service mix after all cost of sales.", "%", True),
    ("operating_margin", "Operating profit margin", "Profitability", "EBIT / net revenue", "Profit left after running the store, before financing and tax.", "%", True),
    ("net_margin", "Net profit margin", "Profitability", "Net income / net revenue", "Bottom-line return on each dollar of revenue after interest and tax.", "%", True),
    ("ebitda_margin", "EBITDA margin", "Profitability", "EBITDA / net revenue", "Cash-like operating earnings before depreciation; comparable across financing structures.", "%", True),
    ("roa", "Return on assets", "Profitability", "TTM net income / average total assets", "How productively the branch uses the assets it holds (mostly inventory).", "%", True),
    ("roe", "Return on equity", "Profitability", "TTM net income / average total equity", "Return earned on the head-office capital allocated to Calgary.", "%", True),
    ("current_ratio", "Current ratio", "Liquidity", "Current assets / current liabilities", "Ability to meet obligations due within a year from short-term assets.", "x", True),
    ("quick_ratio", "Quick ratio", "Liquidity", "(Cash + receivables) / current liabilities", "Liquidity without relying on selling inventory.", "x", True),
    ("cash_ratio", "Cash ratio", "Liquidity", "Cash / current liabilities", "Most conservative liquidity test.", "x", True),
    ("working_capital", "Working capital", "Liquidity", "Current assets - current liabilities", "Net short-term resources funding day-to-day operations.", "$", True),
    ("inventory_turnover", "Inventory turnover", "Efficiency", "TTM merchandise COGS / average inventory", "How many times stock is sold and replaced per year.", "x", True),
    ("dio", "Days inventory outstanding", "Efficiency", "365 / inventory turnover", "Days of stock held; ties up cash and drives carrying cost.", "days", False),
    ("dso", "Days sales outstanding", "Efficiency", "Average receivables / (TTM net revenue x 1.05 GST) x 365", "Days to collect card, financing, fleet and warranty receivables.", "days", False),
    ("dpo", "Days payables outstanding", "Efficiency", "Average accounts payable / TTM total cost of sales x 365", "Days of supplier credit used to fund inventory.", "days", True),
    ("ccc", "Cash conversion cycle", "Efficiency", "DIO + DSO - DPO", "Days between paying for stock and collecting from customers; lower frees cash.", "days", False),
    ("asset_turnover", "Asset turnover", "Efficiency", "TTM net revenue / average total assets", "Revenue generated per dollar of assets.", "x", True),
    ("debt_to_equity", "Debt-to-equity", "Solvency", "(Revolver + term loan) / total equity", "Reliance on borrowed versus head-office capital.", "x", False),
    ("interest_coverage", "Interest coverage", "Solvency", "TTM EBIT / TTM interest expense", "Headroom to service interest from operating profit (lenders often want > 3x).", "x", True),
    ("dscr", "Debt service coverage", "Solvency", "TTM EBITDA / (TTM interest + TTM scheduled principal)", "Ability to meet all scheduled debt payments from operating cash earnings (> 1.25x typical covenant).", "x", True),
]
DEF = {d[0]: d for d in DEFINITIONS}


def compute(is_m: pd.DataFrame, bs_m: pd.DataFrame, bs_open: pd.Series) -> pd.DataFrame:
    """Monthly ratio series (columns = months from the 12th month onward so every TTM window is complete)."""
    bs = pd.concat([bs_open.rename("2023-12"), bs_m], axis=1)
    cols = list(is_m.columns)
    out = {}
    for i in range(11, len(cols)):
        w = cols[i - 11:i + 1]
        bw = ["2023-12" if i == 11 else cols[i - 12]] + w            # 13 month-ends spanning the window
        f = is_m[w].sum(axis=1)
        b = bs[cols[i]]
        avg = bs[bw].mean(axis=1)
        merch_cogs = -(f["cogs_bike"] + f["cogs_acc"] + f["shrink"])
        nr = f["net_rev"]
        debt = b["revolver"] + b["term_current"] + b["term_lt"]
        b0 = bs[bw[0]]
        principal = (b0["term_current"] + b0["term_lt"]) - (b["term_current"] + b["term_lt"])   # scheduled principal repaid in the window
        turnover = merch_cogs / avg["inventory"]
        dso = avg["ar"] / (nr * (1 + P.GST_RATE)) * 365
        dpo = avg["ap"] / -f["cogs"] * 365
        out[cols[i]] = {
            "gross_margin": f["gross_profit"] / nr * 100, "operating_margin": f["ebit"] / nr * 100, "net_margin": f["net_income"] / nr * 100,
            "ebitda_margin": f["ebitda"] / nr * 100, "roa": f["net_income"] / avg["total_assets"] * 100, "roe": f["net_income"] / avg["total_equity"] * 100,
            "current_ratio": b["current_assets"] / b["current_liabilities"], "quick_ratio": (b["cash"] + b["ar"]) / b["current_liabilities"],
            "cash_ratio": b["cash"] / b["current_liabilities"], "working_capital": b["current_assets"] - b["current_liabilities"],
            "inventory_turnover": turnover, "dio": 365 / turnover, "dso": dso, "dpo": dpo, "ccc": 365 / turnover + dso - dpo,
            "asset_turnover": nr / avg["total_assets"], "debt_to_equity": debt / b["total_equity"],
            "interest_coverage": f["ebit"] / -f["interest"] if f["interest"] else np.nan,
            "dscr": f["ebitda"] / (-f["interest"] + principal),
        }
    return pd.DataFrame(out).loc[[d[0] for d in DEFINITIONS]]


def annual_table(r: pd.DataFrame) -> pd.DataFrame:
    """FY2024 (TTM at Dec-24), FY2025 (TTM at Dec-25) and TTM Sep-26, with changes."""
    t = r[["2024-12", "2025-12", "2026-09"]].copy()
    t.columns = ["FY2024", "FY2025", "TTM Sep-2026"]
    t["change_vs_FY2025"] = t["TTM Sep-2026"] - t["FY2025"]
    t["change_vs_FY2024"] = t["TTM Sep-2026"] - t["FY2024"]
    meta = pd.DataFrame([d[1:] for d in DEFINITIONS], index=[d[0] for d in DEFINITIONS],
                        columns=["ratio", "group", "formula", "meaning", "unit", "higher_is_better"])
    t = meta.join(t)
    t["direction"] = np.where(np.sign(t.change_vs_FY2025) == 0, "flat",
                              np.where((t.change_vs_FY2025 > 0) == t.higher_is_better, "improved", "deteriorated"))
    return t


ACTIONS = {
    "gross_margin": "Tighten discretionary e-bike discounting, shift mix to higher-margin brands/accessories, negotiate volume rebates.",
    "operating_margin": "Flex seasonal staffing to demand, convert unapplied technician time to billable service, review freight and storage spend.",
    "net_margin": "Combine margin and opex actions; reduce revolver usage to cut interest.",
    "ebitda_margin": "Same levers as operating margin; EBITDA excludes the fixed depreciation of the fit-out.",
    "roa": "Release inventory (the largest asset) through seasonal reorder points and clearance of slow movers.",
    "roe": "Improve profit and return surplus summer cash to head office instead of holding idle balances.",
    "current_ratio": "Healthy; avoid letting seasonal revolver draws push it below 1.5x.",
    "quick_ratio": "Hold a minimum cash buffer; quick ratio dips during the pre-season build when cash funds stock.",
    "cash_ratio": "Summer cash peaks exceed needs - sweep surplus to head office or prepay the term loan.",
    "working_capital": "Size the revolver to the Feb-Apr working-capital peak; avoid tying cash in slow-moving SKUs.",
    "inventory_turnover": "Order to seasonal demand (Model 4 reorder points), cut winter cover, clear aged stock before spring.",
    "dio": "Target fewer days on hand for C-class SKUs and international brands with long lead times.",
    "dso": "Already short (card settlements); keep fleet/warranty claims on 30/45-day follow-up.",
    "dpo": "Move 'Prepaid/Net 15' brands to Net 30 and remove deposits where volume justifies it.",
    "ccc": "Lower DIO and raise DPO - every 10 days of CCC is roughly $50K of cash at the current cost base.",
    "asset_turnover": "Grow sales per square foot (service, accessories attach) without adding inventory.",
    "debt_to_equity": "Low; keep revolver usage seasonal and fully repaid by June.",
    "interest_coverage": "Thin because EBIT is thin; profit improvement matters more than refinancing.",
    "dscr": "Below 1.25x would breach a typical covenant - prioritise EBITDA improvement and avoid new term debt.",
}
