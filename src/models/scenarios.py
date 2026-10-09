"""Model 5 + Phase 6 - driver-based profitability simulation, scenarios, sensitivity and Monte Carlo.

All outputs are ILLUSTRATIVE: they apply assumed driver changes to a SYNTHETIC baseline. They are not
predictions of Prairie Pulse E-Bikes results and do not imply causal effects.

Baseline = next-12-month forecast (Oct 2026 - Sep 2027) from Model 1 + trailing-12-month cost structure.

Formulas (b = baseline value, ' = scenario value)
  U'      = U_b * (1+v) * (1+p)^e * (1 + conv * lead_share) * (1+a)^ad_el * (1 + mix_vol)        bike units
  ASP'    = ASP_b * (1+p) * (1 - dd) / (1 - d_b)                                                   avg bike net price
  UC'     = UC_b * (1+c)                                                                           avg bike unit cost
  R_bike' = U' * ASP'        GP_bike' = U' * (ASP' - UC') + mix_gp
  R_acc'  = R_acc_b * (att_share * U'/U_b + (1-att_share)) * (1+p)   GP_acc' = R_acc' * gm_acc
  R_svc'  = R_svc_b * (1+s)  GP_svc' = R_svc' * gm_svc
  Opex'   = Fixed_b + adv_b*(1+a) + comm*R_bike' + fee_rate*(R_bike'+R_acc') + ship_rate*COGS'
            + InvValue' * carry_rate * (1+k)            InvValue' = InvValue_b * (U'/U_b)^0.5 * (1+c)
  OP'     = GP_bike' + GP_acc' + GP_svc' - Opex'
"""
from __future__ import annotations

from dataclasses import asdict, dataclass

import numpy as np
import pandas as pd

from src.config import FORECAST_START, SEED, TABLES
from src.engineering.sqlutil import connect

TTM_START = "2025-10-01"


@dataclass
class Drivers:
    price_change: float = 0.0           # p  (+0.05 = +5% list prices)
    price_elasticity: float = -1.2      # e  (bike unit response to own price; ASSUMPTION, not estimated causally)
    volume_change: float = 0.0          # v  (exogenous bike volume change)
    supplier_cost_change: float = 0.0   # c
    discount_change: float = 0.0        # dd (additional average discount, percentage points as fraction)
    advertising_change: float = 0.0     # a  (+0.2 = +20% spend)
    advertising_elasticity: float = 0.10  # ad_el (bike volume response to ad spend; ASSUMPTION)
    mix_shift: float = 0.0              # share of bike units moved from lowest- to highest-margin brand group
    service_change: float = 0.0         # s
    carrying_cost_change: float = 0.0   # k  (-0.10 = 10% lower carrying cost)
    lead_conversion_change: float = 0.0  # conv (+0.20 = 20% relative improvement in qualified lead conversion)
    lead_share: float = 0.80            # share of bike sales originating from tracked, non-walk-in leads


def baseline() -> dict:
    con = connect()
    fc = pd.read_csv(TABLES / "forecast_next_12_months.csv", parse_dates=["month"])
    sel = fc[fc.selected]
    s = pd.read_sql_query("SELECT product_class, brand, SUM(net_sales_cad) r, SUM(gross_sales_cad) g, SUM(cogs_cad) c, SUM(gross_profit_cad) gp, SUM(units_sold) u "
                          "FROM sales_transactions WHERE return_status='Completed' AND transaction_date >= ? GROUP BY 1,2", con, params=(TTM_START,))
    v = pd.read_sql_query("SELECT SUM(labour_revenue_cad+parts_revenue_cad) r, SUM(gross_profit_cad) gp FROM service_orders WHERE date_received >= ?", con, params=(TTM_START,))
    o = pd.read_sql_query("SELECT * FROM operating_expenses WHERE month >= ?", con, params=(TTM_START,))
    con.close()
    bikes = s[s.product_class == "E-Bike"]
    non = s[s.product_class != "E-Bike"]
    retail_fc = sel[sel.target == "retail_revenue"].forecast.sum()
    units_fc = sel[sel.target == "bike_units"].forecast.sum()
    svc_fc = sel[sel.target == "service_revenue"].forecast.sum()
    bike_share = bikes.r.sum() / s.r.sum()
    R_bike = retail_fc * bike_share
    ASP = R_bike / units_fc
    disc_b = 1 - bikes.r.sum() / bikes.g.sum()
    UC = bikes.c.sum() / bikes.u.sum() * (ASP / (bikes.r.sum() / bikes.u.sum()))     # keep TTM cost ratio at forecast ASP
    # brand margin groups for mix shift
    bm = bikes.assign(gm=bikes.gp / bikes.r).sort_values("gm")
    gm_low = bm.head(len(bm) // 3).gp.sum() / bm.head(len(bm) // 3).r.sum()
    gm_high = bm.tail(len(bm) // 3).gp.sum() / bm.tail(len(bm) // 3).r.sum()
    infl = 1.025
    fixed_cols = ["rent_cad", "utilities_cad", "insurance_cad", "administrative_cad", "technician_assembly_idle_time_cad"]
    comm = 0.015
    wages_ex_comm = o.staff_wages_cad.sum() - comm * bikes.r.sum()
    fee_rate = (o.other_expenses_cad.sum() - 800 * len(o)) / s.r.sum()
    ship_rate = o.shipping_logistics_cad.sum() / s.c.sum()
    carry = o.carrying_rate_annual.mean()
    inv_value = o.avg_inventory_value_cad.mean()
    return dict(
        units=units_fc, ASP=ASP, UC=UC, disc_b=disc_b, R_bike=R_bike, R_acc=retail_fc - R_bike,
        gm_acc=non.gp.sum() / non.r.sum(), att_share=0.55, R_svc=svc_fc, gm_svc=v.gp[0] / v.r[0],
        fixed=(o[fixed_cols].sum().sum() + wages_ex_comm + 800 * len(o)) * infl, adv=o.advertising_cad.sum() * infl,
        comm=comm, fee_rate=fee_rate, ship_rate=ship_rate, carry=carry, inv_value=inv_value,
        gm_gap=gm_high - gm_low, retail_fc=retail_fc, months=f"{FORECAST_START} to +12m")


def simulate(dr: Drivers, b: dict | None = None) -> dict:
    b = b or baseline()
    U = b["units"] * (1 + dr.volume_change) * (1 + dr.price_change) ** dr.price_elasticity \
        * (1 + dr.lead_conversion_change * dr.lead_share) * (1 + dr.advertising_change) ** dr.advertising_elasticity
    ASP = b["ASP"] * (1 + dr.price_change) * (1 - b["disc_b"] - dr.discount_change) / (1 - b["disc_b"])
    UC = b["UC"] * (1 + dr.supplier_cost_change)
    R_bike = U * ASP
    mix_gp = dr.mix_shift * R_bike * b["gm_gap"]
    GP_bike = U * (ASP - UC) + mix_gp
    R_acc = b["R_acc"] * (b["att_share"] * U / b["units"] + (1 - b["att_share"])) * (1 + dr.price_change)
    GP_acc = R_acc * b["gm_acc"]
    R_svc = b["R_svc"] * (1 + dr.service_change)
    GP_svc = R_svc * b["gm_svc"]
    cogs = U * UC + R_acc * (1 - b["gm_acc"])
    inv_value = b["inv_value"] * (U / b["units"]) ** 0.5 * (1 + dr.supplier_cost_change)
    holding = inv_value * b["carry"] * (1 + dr.carrying_cost_change)
    opex = b["fixed"] + b["adv"] * (1 + dr.advertising_change) + b["comm"] * R_bike + b["fee_rate"] * (R_bike + R_acc) + b["ship_rate"] * cogs + holding
    rev = R_bike + R_acc + R_svc
    gp = GP_bike + GP_acc + GP_svc
    return {"bike_units": U, "revenue": rev, "retail_revenue": R_bike + R_acc, "service_revenue": R_svc, "gross_profit": gp,
            "gross_margin_pct": gp / rev * 100, "operating_expenses": opex, "operating_profit": gp - opex,
            "operating_margin_pct": (gp - opex) / rev * 100, "inventory_investment": inv_value, "inventory_holding_cost": holding}


SCENARIOS = {
    "Conservative": Drivers(volume_change=-0.08, supplier_cost_change=0.03, discount_change=0.01, service_change=-0.03, price_change=0.0),
    "Base": Drivers(),
    "Optimistic": Drivers(volume_change=0.06, price_change=0.02, discount_change=-0.01, service_change=0.10,
                          carrying_cost_change=-0.10, lead_conversion_change=0.10, mix_shift=0.05),
}
SCENARIO_NOTES = {
    "Conservative": "Bike demand -8% (weak spring/consumer slowdown), supplier costs +3% (CAD/USD, tariffs), +1pt discounting, service -3%.",
    "Base": "Model 1 (Prophet) 12-month forecast, TTM cost structure, opex inflation +2.5%.",
    "Optimistic": "Demand +6%, +2% price realisation, -1pt discounting, service +10%, carrying cost -10%, lead conversion +10%, 5% mix shift to higher-margin brands.",
}
SENSITIVITIES = {
    "5% price increase (no volume response)": Drivers(price_change=0.05, price_elasticity=0.0),
    "5% price increase (elasticity -1.2)": Drivers(price_change=0.05),
    "10% increase in bike sales volume": Drivers(volume_change=0.10),
    "10% reduction in inventory carrying costs": Drivers(carrying_cost_change=-0.10),
    "15% increase in repair & maintenance revenue": Drivers(service_change=0.15),
    "20% improvement in qualified lead conversion": Drivers(lead_conversion_change=0.20),
}


def run():
    b = baseline()
    base = simulate(Drivers(), b)
    sc = pd.DataFrame({k: simulate(v, b) for k, v in SCENARIOS.items()}).T
    sc["assumptions"] = pd.Series(SCENARIO_NOTES)
    rows = []
    for k, v in SENSITIVITIES.items():
        r = simulate(v, b)
        rows.append({"sensitivity": k, "delta_revenue": r["revenue"] - base["revenue"], "delta_gross_profit": r["gross_profit"] - base["gross_profit"],
                     "delta_operating_profit": r["operating_profit"] - base["operating_profit"],
                     "delta_inventory_investment": r["inventory_investment"] - base["inventory_investment"],
                     "operating_profit": r["operating_profit"], "gross_margin_pct": r["gross_margin_pct"]})
    sens = pd.DataFrame(rows)
    # Monte Carlo around Base: forecast error (WAPE-scaled), elasticity, supplier cost, service growth
    rng = np.random.default_rng(SEED)
    mc = []
    for _ in range(5000):
        dr = Drivers(volume_change=rng.normal(0, 0.11), price_elasticity=rng.uniform(-1.8, -0.6), supplier_cost_change=rng.normal(0.01, 0.02),
                     service_change=rng.normal(0, 0.065), discount_change=rng.normal(0, 0.005))
        mc.append(simulate(dr, b))
    mc = pd.DataFrame(mc)
    mc_s = mc[["revenue", "gross_profit", "operating_profit"]].quantile([0.1, 0.5, 0.9]).T
    mc_s["prob_loss"] = [np.nan, np.nan, (mc.operating_profit < 0).mean()]
    return b, base, sc, sens, mc, mc_s


if __name__ == "__main__":
    b, base, sc, sens, mc, mcs = run()
    print({k: round(v, 3) if isinstance(v, float) else v for k, v in b.items()})
    print(sc.drop(columns="assumptions").round(0).to_string())
    print(sens.round(0).to_string())
    print(mcs.round(0))
