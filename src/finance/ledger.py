"""Phase 12 - double-entry general ledger generated from the operational (synthetic) datasets.

Every operational event becomes a balanced journal entry; nothing in the financial statements is generated
independently of these entries. Sources -> journals:
    opening position (31 Dec 2023)        OB-*   summarised start-up transactions (equity, loan, fit-out, stock)
    sales_transactions                    SAL-*  revenue at list price, discounts, GST, tender receivable, COGS
    tender settlements                    SET-*  card/financing/fleet/warranty receivables collected
    returns + inventory_movements         RET-*/ADJ-*  refunds, restocks, damaged and cycle-count write-offs
    purchase_orders                       DEP-*/RCV-*/PAY-*  supplier deposits, receipts (with GST ITCs), payments
    service_orders                        SVI-*/SVC-*  intake costs to WIP (parts + direct labour), revenue at completion
    operating_expenses                    OPX-*/PRL-*/INS-*/HOS-*  expenses, payroll, prepaid insurance, head office
    fixed-asset register                  CAP-*/DEP-*  capex, monthly straight-line depreciation
    treasury & tax (month-end loop)       INT-*/TLP-*/REV-*/TAX-*/GST-*/DIS-*/CON-*  financing, tax, GST remittance
    year-end close                        CLS-*  P&L and distributions closed to retained earnings
All amounts are SIMULATED (see policy.FIN_LABEL).
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from src.config import END, START
from src.engineering.sqlutil import connect
from src.finance import policy as P

END_TS = pd.Timestamp(END)
MONTHS = pd.period_range(START, END, freq="M")
REV_ACCT = {"E-Bike": "4000", "Accessories": "4100", "Batteries & Chargers": "4110", "Parts": "4120"}
COGS_ACCT = {"E-Bike": "5000"}


def r2(x):
    return float(np.round(x + 1e-12, 2))


@dataclass
class Book:
    rows: list = field(default_factory=list)            # (je_id, date, account, debit, credit, source, reference, counterparty, description, is_closing)
    ar_items: list = field(default_factory=list)        # subsidiary ledger: receivables
    ap_items: list = field(default_factory=list)        # subsidiary ledger: payables
    n: int = 0

    def je(self, prefix, date, source, ref, desc, lines, closing=False):
        """lines: (account, amount, counterparty) with +debit / -credit. Must balance to the cent."""
        cents = [int(round(a * 100)) for _, a, _ in lines]
        if sum(cents) != 0:
            raise ValueError(f"Unbalanced JE {prefix} {ref}: {sum(cents) / 100}")
        self.n += 1
        jid = f"{prefix}-{self.n:07d}"
        d = pd.Timestamp(date)
        for (acct, _, cp), c in zip(lines, cents):
            if c == 0:
                continue
            if acct not in P.ACCOUNTS:
                raise KeyError(acct)
            self.rows.append((jid, d, acct, c / 100 if c > 0 else 0.0, -c / 100 if c < 0 else 0.0, source, ref, cp, desc, closing))
        return jid


# ----------------------------------------------------------------------------------------------- inputs
def load_operational():
    con = connect()
    q = lambda s: pd.read_sql_query(s, con)
    T = dict(
        sales=q("SELECT * FROM sales_transactions"), returns=q("SELECT * FROM returns"), products=q("SELECT * FROM products"),
        moves=q("SELECT * FROM inventory_movements"), pos=q("SELECT * FROM purchase_orders"), suppliers=q("SELECT * FROM suppliers"),
        services=q("SELECT * FROM service_orders"), opex=q("SELECT * FROM operating_expenses"), customers=q("SELECT customer_id, customer_type FROM customers"),
        econ=q("SELECT * FROM external_economic_monthly"),
    )
    con.close()
    for k, cols in dict(sales=["transaction_date"], returns=["return_date"], moves=["movement_date"], pos=["order_date", "received_date"],
                        services=["date_received", "date_completed"], opex=["month"], econ=["month"]).items():
        for c in cols:
            T[k][c] = pd.to_datetime(T[k][c])
    return T


def prime_rate(econ: pd.DataFrame) -> pd.Series:
    r = econ.set_index(econ.month.dt.to_period("M")).policy_rate_pct.reindex(pd.period_range("2023-12", END, freq="M")).ffill().bfill()
    return r / 100 + P.PRIME_SPREAD_OVER_POLICY


def fixed_asset_schedule(assets=P.FIXED_ASSETS, until=END) -> pd.DataFrame:
    """Monthly straight-line depreciation per asset (starts the month after acquisition)."""
    rows = []
    months = pd.period_range("2023-11", until, freq="M")
    for aid, desc, acct, acq, cost, life in assets:
        start = pd.Period(acq, "M") + 1
        monthly = r2(cost / life)
        acc = 0.0
        for k in range(life):
            m = start + k
            if m > months[-1]:
                break
            amt = monthly if k < life - 1 else r2(cost - acc)
            acc = r2(acc + amt)
            rows.append({"asset_id": aid, "month": m, "account": acct, "depreciation": amt})
    return pd.DataFrame(rows)


# ----------------------------------------------------------------------------------------------- builders
def post_opening(B: Book, T):
    o = P.OPENING
    d = o["date"]
    B.je("OB", d, "Opening balance", "OB-EQUITY", "Head-office equity contribution (start-up)", [("1000", o["equity_contribution"], "Head office"), ("3000", -o["equity_contribution"], "Head office")])
    tl = P.TERM_LOAN["principal"]
    B.je("OB", d, "Opening balance", "OB-LOAN", "Allocated term loan drawn 1 Dec 2023", [("1000", tl, "Lender"), ("2700", -tl, "Lender")])
    for aid, desc, acct, acq, cost, life in P.FIXED_ASSETS:
        if pd.Timestamp(acq) <= pd.Timestamp(d):
            B.je("OB", d, "Opening balance", aid, f"Start-up capex: {desc}", [(acct, cost, None), ("1000", -cost, None)])
    p = T["products"]
    sup = T["suppliers"].set_index("supplier_id").payment_terms
    for sid, g in p.groupby("supplier_id"):
        v = r2((g.initial_inventory * g.est_purchase_cost_cad).sum())
        if v == 0:
            continue
        ap = r2(v * o["opening_ap_share"]) if sup[sid] == "Net 30" else 0.0
        B.je("OB", d, "Opening balance", f"OB-INV-{sid}", "Opening inventory (received Nov-Dec 2023)", [("1200", v, sid), ("2000", -ap, sid), ("1000", -(v - ap), sid)])
        if ap:
            B.ap_items.append(dict(item_id=f"OB-AP-{sid}", account="2000", counterparty=sid, doc_date=pd.Timestamp(d), due_date=pd.Timestamp(o["opening_ap_due"]), amount=ap))
    pre = o["pre_opening_expenses"]
    B.je("OB", d, "Opening balance", "OB-PREOPEN", "Pre-opening losses Nov-Dec 2023 (wages, rent, launch marketing) - prior-period result", [("3200", pre, None), ("1000", -pre, None)])
    dep = fixed_asset_schedule()
    pre_dep = r2(dep[dep.month <= pd.Period("2023-12", "M")].depreciation.sum())
    B.je("OB", d, "Opening balance", "OB-PREDEP", "Depreciation Nov-Dec 2023 - prior-period result", [("3200", pre_dep, None), ("1590", -pre_dep, None)])
    return pre + pre_dep          # opening tax loss carry-forward


def post_sales(B: Book, T):
    s = T["sales"].merge(T["customers"], on="customer_id", how="left")
    s["fleet"] = s.customer_type.eq("Business/Fleet")
    s = s.sort_values(["transaction_id", "line_id"], kind="stable")
    recs = s[["transaction_id", "transaction_date", "payment_method", "fleet", "customer_id", "product_class",
              "gross_sales_cad", "net_sales_cad", "units_sold", "unit_cost_cad"]].to_dict("records")
    names = {"1000": None, "1100": "Card & debit processor", "1110": "Consumer-financing partner"}
    i = 0
    while i < len(recs):
        j = i
        while j < len(recs) and recs[j]["transaction_id"] == recs[i]["transaction_id"]:
            j += 1
        g = recs[i:j]
        h = g[0]
        txn, d = h["transaction_id"], h["transaction_date"]
        net = r2(sum(x["net_sales_cad"] for x in g))
        gst = r2(net * P.GST_RATE)
        if h["fleet"]:
            acct, lag, cp = "1120", P.FLEET_TERMS_DAYS, h["customer_id"]
        else:
            pm = h["payment_method"]
            acct, lag = P.SETTLEMENT.get("Unknown" if pd.isna(pm) else pm, P.SETTLEMENT["Unknown"])
            cp = names[acct]
        lines = [(acct, r2(net + gst), cp), ("2300", -gst, None)]
        for x in g:
            lines.append((REV_ACCT[x["product_class"]], -r2(x["gross_sales_cad"]), None))
            disc = r2(x["gross_sales_cad"] - x["net_sales_cad"])
            if disc:
                lines.append(("4900", disc, None))
            cost = r2(x["units_sold"] * x["unit_cost_cad"])
            lines += [(COGS_ACCT.get(x["product_class"], "5010"), cost, None), ("1200", -cost, None)]
        B.je("SAL", d, "Sales", txn, f"POS sale {txn}", lines)
        if acct != "1000":
            B.ar_items.append(dict(item_id=txn, account=acct, counterparty=cp, doc_date=d, due_date=d + pd.Timedelta(days=lag), amount=r2(net + gst)))
        i = j


def post_returns_and_adjustments(B: Book, T):
    p = T["products"].set_index("product_id")
    cost = p.est_purchase_cost_cad
    klass = p.product_class
    ret = T["returns"].set_index("return_id")
    for r in ret.itertuples():
        gst = r2(r.refund_amount_cad * P.GST_RATE)
        B.je("RET", r.return_date, "Returns", r.Index, f"Customer refund for {r.line_id}",
             [("4910", r2(r.refund_amount_cad), None), ("2300", gst, None), ("1000", -r2(r.refund_amount_cad + gst), None)])
    mv = T["moves"]
    for m in mv[mv.movement_type.isin(["CUSTOMER_RETURN", "ADJ_DAMAGED_WRITE_OFF", "ADJ_CYCLE_COUNT"])].itertuples():
        v = r2(m.quantity * cost[m.product_id])
        if m.movement_type == "CUSTOMER_RETURN":
            B.je("RET", m.movement_date, "Returns", m.reference_id, f"Returned stock {m.product_id} back to inventory",
                 [("1200", v, None), (COGS_ACCT.get(klass[m.product_id], "5010"), -v, None)])
        else:
            B.je("ADJ", m.movement_date, "Inventory adjustment", m.reference_id, f"{m.movement_type} {m.product_id}", [("5100", -v, None), ("1200", v, None)])


def post_purchases(B: Book, T):
    terms = T["suppliers"].set_index("supplier_id").payment_terms
    for po in T["pos"].itertuples():
        prepaid = terms[po.supplier_id].startswith("Prepaid")
        dep = r2(po.qty_ordered * po.unit_cost_cad * P.PREPAID_DEPOSIT) if prepaid else 0.0
        if dep and po.order_date <= END_TS:
            B.je("DEP", po.order_date, "Purchasing", po.po_id, "Supplier deposit on order", [("1310", dep, po.supplier_id), ("1000", -dep, po.supplier_id)])
        if pd.isna(po.received_date) or po.received_date > END_TS:
            continue
        v = r2(po.qty_received * po.unit_cost_cad)
        gst = r2(v * P.GST_RATE)
        bal = r2(v + gst - dep)
        B.je("RCV", po.received_date, "Purchasing", po.po_id, "Goods received (supplier invoice)",
             [("1200", v, po.supplier_id), ("1400", gst, po.supplier_id), ("1310", -dep, po.supplier_id), ("2000", -bal, po.supplier_id)])
        due = po.received_date + pd.Timedelta(days=P.PREPAID_BALANCE_DAYS if prepaid else P.NET30_DAYS)
        B.ap_items.append(dict(item_id=po.po_id, account="2000", counterparty=po.supplier_id, doc_date=po.received_date, due_date=due, amount=bal))


def post_services(B: Book, T):
    """Intake: parts + direct labour cost to WIP. Completion: revenue, receivable, cost of service."""
    sv = T["services"].copy()
    sv["warranty"] = sv.warranty.astype(bool)
    sv["supplier"] = np.where(sv.electrical.astype(bool), P.SERVICE_PARTS_SUPPLIER["electrical"], P.SERVICE_PARTS_SUPPLIER["other"])
    # intake (aggregated per day: one WIP journal per day, one parts invoice per supplier per day)
    for d, g in sv.groupby("date_received"):
        lines = []
        for sup, gg in g.groupby("supplier"):
            pc = r2(gg.parts_cost_cad.sum())
            if pc:
                gst = r2(pc * P.GST_RATE)
                lines += [("1250", pc, sup), ("1400", gst, sup), ("2000", -r2(pc + gst), sup)]
                B.ap_items.append(dict(item_id=f"SP-{d:%Y%m%d}-{sup}", account="2000", counterparty=sup, doc_date=d, due_date=d + pd.Timedelta(days=P.NET30_DAYS), amount=r2(pc + gst)))
        lab = r2(g.service_cost_cad.sum())
        lines += [("1250", lab, None), ("2100", -lab, None)]
        B.je("SVI", d, "Service", f"SVI-{d:%Y%m%d}", f"Service intake {len(g)} orders: parts and direct labour to WIP", lines)
    done = sv[sv.status.eq("Completed") & sv.date_completed.le(END_TS)]
    for r in done.itertuples():
        rev = r2(r.labour_revenue_cad + r.parts_revenue_cad)
        gst = r2(rev * P.GST_RATE)
        if r.warranty:
            acct, cp, lag = "1130", f"{r.bike_brand} (manufacturer)", P.WARRANTY_SETTLE_DAYS
            lines = [("4220", -r2(r.labour_revenue_cad), None)]
        else:
            acct, lag = P.SERVICE_TENDER
            cp = "Card & debit processor"
            lines = [("4200", -r2(r.labour_revenue_cad), None), ("4210", -r2(r.parts_revenue_cad), None)]
        lines += [(acct, r2(rev + gst), cp), ("2300", -gst, None),
                  ("5200", r2(r.parts_cost_cad), None), ("5210", r2(r.service_cost_cad), None), ("1250", -r2(r.parts_cost_cad + r.service_cost_cad), None)]
        B.je("SVC", r.date_completed, "Service", r.service_order_id, f"Service completed {r.service_type}", lines)
        B.ar_items.append(dict(item_id=r.service_order_id, account=acct, counterparty=cp, doc_date=r.date_completed,
                               due_date=r.date_completed + pd.Timedelta(days=lag), amount=r2(rev + gst)))


OPEX_MAP = [  # operational column, GL account, vendor counterparty, GST-taxable
    ("utilities_cad", "6110", "VEN-UTIL Utility provider", True),
    ("advertising_cad", "6200", "VEN-MKTG Digital advertising & media vendors", True),
    ("shipping_logistics_cad", "6400", "VEN-FRT Freight carriers", True),
    ("admin_local_cad", "6310", "VEN-ADM Office & administrative vendors", True),
    ("storage_physical_cad", "6420", "VEN-STOR Storage, handling & disposal services", True),
    ("other_expenses_cad", "6410", "VEN-PAY Payment processors & financing partner", False),
]


def post_opex(B: Book, T):
    o = T["opex"].copy()
    o["admin_local_cad"] = o.administrative_cad - P.CORPORATE_ALLOCATION_MONTHLY
    o["storage_physical_cad"] = o.inventory_holding_cost_cad * P.PHYSICAL_CARRY_RATE / o.carrying_rate_annual
    sv = T["services"]
    direct = sv.groupby(sv.date_received.dt.to_period("M")).service_cost_cad.sum()
    for r in o.itertuples():
        m = r.month.to_period("M")
        me = m.end_time.normalize()
        # rent paid in advance on the 1st
        rent = r2(r.rent_cad)
        gst = r2(rent * P.GST_RATE)
        B.je("OPX", m.start_time, "Operating expenses", f"RENT-{m}", "Monthly rent (paid in advance)", [("6100", rent, "Landlord"), ("1400", gst, "Landlord"), ("1000", -r2(rent + gst), "Landlord")])
        # vendor invoices dated month-end, paid on the 20th of next month
        for col, acct, ven, taxable in OPEX_MAP:
            v = r2(getattr(r, col))
            g = r2(v * P.GST_RATE) if taxable else 0.0
            B.je("OPX", me, "Operating expenses", f"{acct}-{m}", f"{P.ACCOUNTS[acct]['name']} - {m}", [(acct, v, ven), ("1400", g, ven), ("2010", -r2(v + g), ven)])
            B.ap_items.append(dict(item_id=f"{acct}-{m}", account="2010", counterparty=ven, doc_date=me,
                                   due_date=(m + 1).start_time + pd.Timedelta(days=P.OPEX_VENDOR_PAY_DAY - 1), amount=r2(v + g)))
        # corporate shared services -> due to head office
        B.je("OPX", me, "Operating expenses", f"HOA-{m}", "Corporate shared-services allocation", [("6320", P.CORPORATE_ALLOCATION_MONTHLY, "Head office"), ("2500", -P.CORPORATE_ALLOCATION_MONTHLY, "Head office")])
        # payroll accruals (direct technician labour was accrued at service intake)
        B.je("PRL", me, "Payroll", f"PRL-{m}", "Payroll accrual - sales, management, admin & unapplied technician time",
             [("6000", r2(r.staff_wages_cad), None), ("6010", r2(r.technician_assembly_idle_time_cad), None),
              ("2100", -r2(r.staff_wages_cad + r.technician_assembly_idle_time_cad), None)])
        total = r2(r.staff_wages_cad + r.technician_assembly_idle_time_cad + direct.get(m, 0.0))
        first = r2(total * P.PAYROLL_FIRST_HALF)
        B.je("PRL", m.start_time + pd.Timedelta(days=14), "Payroll", f"PAY1-{m}", "Payroll run 1 (1st-15th)", [("2100", first, None), ("1000", -first, None)])
        nxt = (m + 1).start_time + pd.Timedelta(days=4)
        if nxt <= END_TS:
            B.je("PRL", nxt, "Payroll", f"PAY2-{m}", "Payroll run 2 (16th-month end)", [("2100", r2(total - first), None), ("1000", -r2(total - first), None)])
        # insurance: annual premium on 2 January, amortised monthly
        ins = r2(r.insurance_cad)
        if m.month == 1:
            prem = r2(ins * 12)
            B.je("INS", m.start_time + pd.Timedelta(days=1), "Prepaid insurance", f"INSP-{m.year}", "Annual insurance premium", [("1300", prem, "Insurer"), ("1000", -prem, "Insurer")])
        B.je("INS", me, "Prepaid insurance", f"INSA-{m}", "Insurance amortisation", [("6300", ins, "Insurer"), ("1300", -ins, "Insurer")])
        # head-office settlement after each quarter end
        if m.month in (1, 4, 7, 10) and m > MONTHS[0]:
            amt = 3 * P.CORPORATE_ALLOCATION_MONTHLY
            B.je("HOS", m.start_time + pd.Timedelta(days=14), "Head office", f"HOS-{m}", "Settle due-to-head-office (prior quarter)", [("2500", amt, "Head office"), ("1000", -amt, "Head office")])


def post_capex_and_depreciation(B: Book):
    for aid, desc, acct, acq, cost, life in P.FIXED_ASSETS:
        if pd.Timestamp(acq) > pd.Timestamp(P.OPENING["date"]):
            B.je("CAP", acq, "Capital expenditure", aid, desc, [(acct, cost, None), ("1400", r2(cost * P.GST_RATE), None), ("1000", -r2(cost * (1 + P.GST_RATE)), None)])
    dep = fixed_asset_schedule()
    for m, g in dep[dep.month >= MONTHS[0]].groupby("month"):
        amt = r2(g.depreciation.sum())
        B.je("DPR", m.end_time.normalize(), "Depreciation", f"DPR-{m}", "Monthly straight-line depreciation", [("6900", amt, None), ("1590", -amt, None)])


def post_settlements(B: Book):
    """Collect receivables and pay payables from the subsidiary ledgers (only events on or before END)."""
    ar = pd.DataFrame(B.ar_items)
    for (acct, d, cp), g in ar[ar.due_date <= END_TS].groupby(["account", "due_date", "counterparty"]):
        amt = r2(g.amount.sum())
        B.je("SET", d, "Collections", f"SET-{acct}-{d:%Y%m%d}", f"Settlement received ({len(g)} items)", [("1000", amt, cp), (acct, -amt, cp)])
    ap = pd.DataFrame(B.ap_items)
    for (acct, d, cp), g in ap[ap.due_date <= END_TS].groupby(["account", "due_date", "counterparty"]):
        amt = r2(g.amount.sum())
        B.je("PAY", d, "Supplier payments", f"PAY-{cp}-{d:%Y%m%d}", f"Payment to {cp} ({len(g)} invoices)", [(acct, amt, cp), ("1000", -amt, cp)])


def _frame(B: Book) -> pd.DataFrame:
    gl = pd.DataFrame(B.rows, columns=["je_id", "date", "account", "debit", "credit", "source", "reference", "counterparty", "description", "is_closing"])
    gl["amount"] = gl.debit - gl.credit
    gl["month"] = gl.date.dt.to_period("M")
    return gl


def post_treasury_tax_and_close(B: Book, T, lcf_open: float):
    """Treasury, tax and close, processed day by day (cash) and month by month (accruals):
       * daily: if cash falls below the intra-month floor the revolver is drawn back to the intra-month target;
       * month end: GST remittance, interest (term loan on opening balance; revolver on average daily balance),
         term principal, tax provision/payment, cash-band revolver draw/repayment, head-office contribution;
       * December: distribution policy, then closing entries to retained earnings."""
    prime = prime_rate(T["econ"])
    pmt = r2(P.TERM_LOAN["principal"] / P.TERM_LOAN["months"])
    pnl_accts = sorted(k for k, v in P.ACCOUNTS.items() if v["type"] in P.PNL_TYPES)
    base = _frame(B)                                   # all operational entries (no treasury/tax/close yet)
    by_m = base.groupby(["month", "account"]).amount.sum().unstack(fill_value=0.0).reindex(columns=list(P.ACCOUNTS), fill_value=0.0)
    by_m = by_m.reindex(pd.period_range("2023-12", END, freq="M"), fill_value=0.0)
    cash_day = base[base.account == "1000"].groupby("date").amount.sum()
    n0 = len(B.rows)
    R = P.REVOLVER

    def tre(month_filter):
        out = defaultdict(float)
        for r in B.rows[n0:]:
            if not r[9] and month_filter(r[1].to_period("M")):
                out[r[2]] += r[3] - r[4]
        return out

    def ceil_step(x):
        return float(np.ceil(round(x / R["step"], 9)) * R["step"])

    cash = r2(cash_day[cash_day.index <= pd.Timestamp(P.OPENING["date"])].sum())
    term_bal, rev_bal = P.TERM_LOAN["principal"], 0.0
    lcf = lcf_open
    ytd_tax = tax_payable_prior = 0.0
    log = []
    for m in MONTHS:
        me = m.end_time.normalize()
        rate_t, rate_r = prime[m] + P.TERM_LOAN["spread"], prime[m] + P.REVOLVER["spread"]
        # ---- daily cash path with intra-month revolver sweep
        rev_days, min_day, intra_draw = 0.0, np.inf, 0.0
        for d in pd.date_range(m.start_time, me, freq="D"):
            cash = r2(cash + cash_day.get(d, 0.0))
            if d < me and cash < R["intramonth_floor"] and rev_bal < R["limit"]:
                draw = min(r2(R["limit"] - rev_bal), ceil_step(R["intramonth_target"] - cash))
                B.je("REV", d, "Financing", f"REVD-{d:%Y%m%d}", "Revolver draw (intra-month cash sweep)", [("1000", draw, "Lender"), ("2600", -draw, "Lender")])
                cash, rev_bal, intra_draw = r2(cash + draw), r2(rev_bal + draw), intra_draw + draw
            min_day = min(min_day, cash)
            if d < me:
                rev_days += rev_bal
        # ---- month end
        if m.month in (1, 4, 7, 10):
            q = (m - 1).asfreq("Q")
            qm = by_m[[pm.asfreq("Q") == q for pm in by_m.index]]
            col, itc = -r2(qm["2300"].sum()), r2(qm["1400"].sum())
            if col or itc:
                B.je("GST", me, "GST remittance", f"GST-{q}", f"GST return {q}: collected {col:,.2f} less ITCs {itc:,.2f}",
                     [("2300", col, "Canada Revenue Agency"), ("1400", -itc, "Canada Revenue Agency"), ("1000", -r2(col - itc), "Canada Revenue Agency")])
                cash = r2(cash - (col - itc))
        i_t = r2(term_bal * rate_t / 12)
        B.je("INT", me, "Financing", f"INT-TL-{m}", f"Term loan interest @ {rate_t:.2%}", [("7000", i_t, "Lender"), ("1000", -i_t, "Lender")])
        p_amt = min(pmt, r2(term_bal))
        if p_amt > 0:
            B.je("TLP", me, "Financing", f"TLP-{m}", "Term loan principal instalment", [("2700", p_amt, "Lender"), ("1000", -p_amt, "Lender")])
            term_bal = r2(term_bal - p_amt)
        if m.month == 2 and tax_payable_prior > 0:
            B.je("TAX", me, "Income tax", f"TAXPAY-{m.year - 1}", f"Income tax paid for {m.year - 1}",
                 [("2400", tax_payable_prior, "Canada Revenue Agency"), ("1000", -tax_payable_prior, "Canada Revenue Agency")])
            cash = r2(cash - tax_payable_prior)
            tax_payable_prior = 0.0
        # revolver interest on the average daily balance of the month (month-end balance counted for the last day)
        i_r = r2((rev_days + rev_bal) / m.days_in_month * rate_r / 12)
        if i_r:
            B.je("INT", me, "Financing", f"INT-RV-{m}", f"Revolver interest @ {rate_r:.2%} on average daily balance", [("7010", i_r, "Lender"), ("1000", -i_r, "Lender")])
        cash = r2(cash - i_t - p_amt - i_r)
        # income tax provision: YTD liability = rate x max(0, YTD PBT - loss carry-forward available at 1 Jan)
        in_ytd = lambda pm: pm.year == m.year and pm <= m
        t = tre(in_ytd)
        ytd_base = by_m.loc[[pm for pm in by_m.index if in_ytd(pm)]]
        pbt_ytd = -r2(sum(ytd_base[a].sum() + t.get(a, 0.0) for a in pnl_accts if a != "8000"))
        need = r2(P.INCOME_TAX_RATE * max(0.0, pbt_ytd - lcf))
        dtax = r2(need - ytd_tax)
        if dtax:
            B.je("TAX", me, "Income tax", f"TAXPROV-{m}", "Income tax provision (YTD true-up)", [("8000", dtax, None), ("2400", -dtax, None)])
            ytd_tax = need
        # month-end cash band
        draw = repay = contrib = dist = 0.0
        if cash < R["min_cash"]:
            draw = min(r2(R["limit"] - rev_bal), ceil_step(R["target_cash"] - cash))
            if cash + draw < R["min_cash"]:
                contrib = ceil_step(R["target_cash"] - cash - draw)
        elif cash > R["repay_above"] and rev_bal > 0:
            repay = min(rev_bal, float(np.floor(round((cash - R["target_cash"]) / R["step"], 9)) * R["step"]))
        if draw:
            B.je("REV", me, "Financing", f"REVD-{m}", "Revolver draw (month-end cash below minimum)", [("1000", draw, "Lender"), ("2600", -draw, "Lender")])
        if repay:
            B.je("REV", me, "Financing", f"REVR-{m}", "Revolver repayment (cash above policy)", [("2600", repay, "Lender"), ("1000", -repay, "Lender")])
        if contrib:
            B.je("CON", me, "Equity", f"CON-{m}", "Head-office capital contribution (revolver fully drawn)", [("1000", contrib, "Head office"), ("3000", -contrib, "Head office")])
        rev_bal = r2(rev_bal + draw - repay)
        cash = r2(cash + draw - repay + contrib)
        lcf_start = lcf
        if m.month == 12:
            if rev_bal == 0 and cash > 250000:
                dist = float(np.floor((cash - 150000) / 1000) * 1000)
                B.je("DIS", me, "Equity", f"DIS-{m.year}", "Distribution to head office", [("3300", dist, "Head office"), ("1000", -dist, "Head office")])
                cash = r2(cash - dist)
            t = tre(lambda pm: pm.year == m.year)
            yb = by_m.loc[[pm for pm in by_m.index if pm.year == m.year]]
            bal = {a: r2(yb[a].sum() + t.get(a, 0.0)) for a in pnl_accts + ["3300"]}
            bal = {a: v for a, v in bal.items() if v}
            lines = [(a, -v, None) for a, v in bal.items()] + [("3200", r2(sum(bal.values())), None)]
            B.je("CLS", me, "Year-end close", f"CLOSE-{m.year}", f"Close FY{m.year} P&L and distributions to retained earnings", lines, closing=True)
            lcf = max(0.0, lcf - pbt_ytd) if pbt_ytd > 0 else lcf - pbt_ytd
            tax_payable_prior, ytd_tax = ytd_tax, 0.0
        log.append(dict(month=str(m), prime_rate=prime[m], term_rate=rate_t, revolver_rate=rate_r, term_interest=i_t, revolver_interest=i_r,
                        term_principal=p_amt, term_balance=term_bal, revolver_intramonth_draws=intra_draw, revolver_draw=draw, revolver_repay=repay,
                        revolver_balance=rev_bal, contribution=contrib, distribution=dist, month_end_cash=cash, min_daily_cash=min_day,
                        pbt_ytd=pbt_ytd, tax_ytd=need, loss_carryforward_start_of_year=lcf_start, data_status="SIMULATED"))
    return pd.DataFrame(log), lcf


def build():
    T = load_operational()
    B = Book()
    lcf = post_opening(B, T)
    post_sales(B, T)
    post_returns_and_adjustments(B, T)
    post_purchases(B, T)
    post_services(B, T)
    post_opex(B, T)
    post_capex_and_depreciation(B)
    post_settlements(B)
    treasury, lcf_end = post_treasury_tax_and_close(B, T, lcf)
    gl = _frame(B).sort_values(["date", "je_id"], kind="stable").reset_index(drop=True)
    gl.insert(0, "line_no", np.arange(1, len(gl) + 1))
    gl["account_name"] = gl.account.map(lambda a: P.ACCOUNTS[a]["name"])
    gl["data_status"] = "SIMULATED"
    ar = pd.DataFrame(B.ar_items)
    ap = pd.DataFrame(B.ap_items)
    return dict(gl=gl, ar_items=ar, ap_items=ap, treasury=treasury, lcf_end=lcf_end, T=T)
