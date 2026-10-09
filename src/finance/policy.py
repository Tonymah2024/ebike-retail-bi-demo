"""Chart of accounts and accounting policy assumptions for the ILLUSTRATIVE Calgary management accounts.

Scope: Prairie Pulse E-Bikes is modelled as a branch/division of a multi-store business. These are SIMULATED Calgary
management accounts, not consolidated corporate financial statements. Corporate equity, debt and shared services
are ALLOCATED to the branch under the assumptions below. Every figure is synthetic.
"""
from __future__ import annotations

FIN_LABEL = "SIMULATED FINANCIAL INFORMATION - illustrative Calgary management accounts, not Prairie Pulse E-Bikes' actual financials"

# ----------------------------------------------------------------------------------------------- chart of accounts
# (code, name, type, normal balance, statement line, cash-flow class)
#   type: asset | contra_asset | liability | equity | revenue | contra_revenue | cogs | opex | other_exp | tax
#   cf:   cash | op_wc (working capital) | ppe | accdep | fin_rev | fin_term | equity | re | pnl
COA = [
    ("1000", "Cash - operating bank account", "asset", "D", "Cash and cash equivalents", "cash"),
    ("1100", "Card & debit processor settlements receivable", "asset", "D", "Accounts receivable", "op_wc"),
    ("1110", "Consumer-financing partner receivable", "asset", "D", "Accounts receivable", "op_wc"),
    ("1120", "Trade receivables - business/fleet accounts", "asset", "D", "Accounts receivable", "op_wc"),
    ("1130", "Manufacturer warranty claims receivable", "asset", "D", "Accounts receivable", "op_wc"),
    ("1200", "Merchandise inventory (standard cost)", "asset", "D", "Inventory", "op_wc"),
    ("1250", "Service work in progress", "asset", "D", "Inventory", "op_wc"),
    ("1300", "Prepaid insurance", "asset", "D", "Prepaid expenses", "op_wc"),
    ("1310", "Supplier deposits on open purchase orders", "asset", "D", "Prepaid expenses", "op_wc"),
    ("1400", "GST input tax credits (ITCs)", "asset", "D", "Sales tax payable (recoverable)", "op_wc"),
    ("1500", "Leasehold improvements", "asset", "D", "Property, plant and equipment", "ppe"),
    ("1510", "Workshop equipment & racking", "asset", "D", "Property, plant and equipment", "ppe"),
    ("1520", "POS, IT & furniture", "asset", "D", "Property, plant and equipment", "ppe"),
    ("1590", "Accumulated depreciation", "contra_asset", "C", "Accumulated depreciation", "accdep"),
    ("2000", "Accounts payable - inventory & parts suppliers", "liability", "C", "Accounts payable", "op_wc"),
    ("2010", "Accounts payable - operating vendors", "liability", "C", "Accounts payable", "op_wc"),
    ("2100", "Accrued payroll, commissions & source deductions", "liability", "C", "Accrued expenses", "op_wc"),
    ("2300", "GST collected", "liability", "C", "Sales tax payable (recoverable)", "op_wc"),
    ("2400", "Income tax payable (allocated)", "liability", "C", "Accrued expenses", "op_wc"),
    ("2500", "Due to head office - shared services", "liability", "C", "Accrued expenses", "op_wc"),
    ("2600", "Revolving inventory line of credit", "liability", "C", "Short-term borrowings", "fin_rev"),
    ("2700", "Term loan (allocated corporate debt)", "liability", "C", "Long-term debt", "fin_term"),
    ("3000", "Allocated corporate equity (head-office investment)", "equity", "C", "Share capital / allocated corporate equity", "equity"),
    ("3200", "Retained earnings", "equity", "C", "Retained earnings", "re"),
    ("3300", "Distributions to head office", "equity", "D", "Retained earnings", "equity"),
    ("4000", "Bicycle sales", "revenue", "C", "Bicycle sales revenue", "pnl"),
    ("4100", "Accessories sales", "revenue", "C", "Accessories and parts revenue", "pnl"),
    ("4110", "Batteries & chargers sales", "revenue", "C", "Accessories and parts revenue", "pnl"),
    ("4120", "Parts sales (retail)", "revenue", "C", "Accessories and parts revenue", "pnl"),
    ("4200", "Service labour revenue", "revenue", "C", "Maintenance and repair revenue", "pnl"),
    ("4210", "Service parts revenue", "revenue", "C", "Maintenance and repair revenue", "pnl"),
    ("4220", "Warranty labour reimbursements", "revenue", "C", "Maintenance and repair revenue", "pnl"),
    ("4900", "Sales discounts & promotional allowances", "contra_revenue", "D", "Sales returns and allowances", "pnl"),
    ("4910", "Sales returns & refunds", "contra_revenue", "D", "Sales returns and allowances", "pnl"),
    ("5000", "Cost of goods sold - e-bikes", "cogs", "D", "Cost of goods sold", "pnl"),
    ("5010", "Cost of goods sold - accessories, batteries & parts", "cogs", "D", "Cost of goods sold", "pnl"),
    ("5100", "Inventory shrinkage & damaged write-offs", "cogs", "D", "Cost of goods sold", "pnl"),
    ("5200", "Service parts cost", "cogs", "D", "Cost of goods sold", "pnl"),
    ("5210", "Direct service labour", "cogs", "D", "Cost of goods sold", "pnl"),
    ("6000", "Wages - sales, management & admin (incl. commission)", "opex", "D", "Employee compensation", "pnl"),
    ("6010", "Technician unapplied & assembly time", "opex", "D", "Employee compensation", "pnl"),
    ("6100", "Rent", "opex", "D", "Rent and occupancy", "pnl"),
    ("6110", "Utilities", "opex", "D", "Utilities", "pnl"),
    ("6200", "Advertising & marketing", "opex", "D", "Marketing and advertising", "pnl"),
    ("6300", "Insurance", "opex", "D", "Administrative expenses", "pnl"),
    ("6310", "Administrative - local", "opex", "D", "Administrative expenses", "pnl"),
    ("6320", "Corporate shared-services allocation", "opex", "D", "Administrative expenses", "pnl"),
    ("6400", "Freight & logistics", "opex", "D", "Freight and logistics", "pnl"),
    ("6410", "Merchant, financing-partner & sundry fees", "opex", "D", "Merchant and financing fees", "pnl"),
    ("6420", "Inventory storage, handling & obsolescence", "opex", "D", "Inventory storage and handling", "pnl"),
    ("6900", "Depreciation", "opex", "D", "Depreciation and amortization", "pnl"),
    ("7000", "Interest - term loan", "other_exp", "D", "Interest expense", "pnl"),
    ("7010", "Interest - revolving line of credit", "other_exp", "D", "Interest expense", "pnl"),
    ("8000", "Income tax expense (allocated)", "tax", "D", "Income taxes", "pnl"),
]
ACCOUNTS = {c[0]: dict(zip(["code", "name", "type", "normal", "line", "cf"], c)) for c in COA}
PNL_TYPES = {"revenue", "contra_revenue", "cogs", "opex", "other_exp", "tax"}

# ----------------------------------------------------------------------------------------------- policies (ASSUMPTIONS)
GST_RATE = 0.05                 # Alberta: GST only (no PST/HST). List prices are GST-exclusive.
INCOME_TAX_RATE = 0.23          # 15% federal general + 8% Alberta general rate, allocated to the branch
TAX_PAYMENT = "Prior-year balance paid on the last business day of February (no instalments modelled)"

# Tender settlement (calendar days after the sale) -> receivable account
SETTLEMENT = {  # payment_method: (account, lag_days)
    "Cash": ("1000", 0), "E-Transfer": ("1000", 0), "Gift Card": ("1000", 0),
    "Debit": ("1100", 1), "Credit Card": ("1100", 2), "Unknown": ("1100", 2),
    "Financing": ("1110", 5),
}
FLEET_TERMS_DAYS = 30           # Business/Fleet customers are invoiced on account, Net 30
SERVICE_TENDER = ("1100", 2)    # service customers pay by card at pickup (completion)
WARRANTY_SETTLE_DAYS = 45       # manufacturer reimburses warranty labour 45 days after claim (completion)

# Supplier terms (from suppliers.payment_terms)
NET30_DAYS = 30
PREPAID_DEPOSIT = 0.50          # "Prepaid/Net 15": 50% deposit at order, balance Net 15 after receipt
PREPAID_BALANCE_DAYS = 15
SERVICE_PARTS_SUPPLIER = {"electrical": "SUP-17", "other": "SUP-15"}

# Operating vendors / payroll timing
OPEX_VENDOR_PAY_DAY = 20        # vendor invoices dated month-end, paid on the 20th of the next month
PAYROLL_FIRST_HALF = 0.50       # 50% of the month's payroll paid on the 15th, remainder on the 5th of next month
RENT_PAY_DAY = 1                # rent paid in advance on the 1st
INSURANCE_PAID = "Annual premium paid on 2 January, amortised monthly"
HEAD_OFFICE_SETTLE = "Due-to-head-office balance settled on the 15th of the month after each quarter end"
GST_REMIT = "Quarterly filer: net GST for the quarter remitted (or refunded) on the last day of the following month"
GST_TAXABLE_OPEX = {"6100", "6110", "6200", "6310", "6400", "6420"}   # ITCs claimed; insurance, fees, wages exempt/none
CORPORATE_ALLOCATION_MONTHLY = 650.0   # the $650/month inside the operational administrative line = shared services

# Operational inventory_holding_cost = avg inventory x (policy rate + 3% + 12%) / 12. In the GL only the PHYSICAL
# 12% component (storage, handling, obsolescence) is an expense; the financing component is an imputed cost of
# capital and is replaced by actual interest on the allocated debt (no double counting).
PHYSICAL_CARRY_RATE = 0.12

# Fixed assets (straight-line, depreciation starts the month after acquisition; no disposals)
FIXED_ASSETS = [  # asset_id, description, account, acquisition date, cost, useful life (months)
    ("FA-001", "Store fit-out & showroom (leasehold improvements)", "1500", "2023-10-25", 165000.0, 120),
    ("FA-002", "Workshop benches, stands & tools", "1510", "2023-10-25", 38000.0, 60),
    ("FA-003", "POS terminals, IT & showroom furniture", "1520", "2023-10-25", 22000.0, 36),
    ("FA-004", "Third service bench & tooling (seasonal technician)", "1510", "2024-04-02", 14500.0, 60),
    ("FA-005", "E-bike diagnostic tools (Bosch/Shimano/Bafang)", "1510", "2025-03-03", 9800.0, 60),
    ("FA-006", "Exterior signage refresh", "1500", "2025-05-05", 6500.0, 96),
    ("FA-007", "POS & inventory-system upgrade", "1520", "2026-02-02", 18000.0, 36),
    ("FA-008", "Back-room bike storage racking", "1510", "2026-04-06", 7200.0, 60),
]
CAPEX_CF_LINE = {"1500": "Capital expenditures (leasehold & systems)", "1520": "Capital expenditures (leasehold & systems)",
                 "1510": "Equipment purchases"}

# Allocated financing
TERM_LOAN = dict(principal=250000.0, drawn="2023-12-01", months=60, spread=0.0225, first_payment="2024-01-31")
PRIME_SPREAD_OVER_POLICY = 0.0220   # Canadian prime ~ BoC policy rate + 2.20%
REVOLVER = dict(limit=350000.0, spread=0.0100, min_cash=60000.0, target_cash=100000.0, repay_above=160000.0, step=1000.0,
                intramonth_floor=15000.0, intramonth_target=50000.0)   # daily sweep keeps the bank account from going overdrawn
DISTRIBUTION_POLICY = "At each year end, cash above $250,000 with the revolver fully repaid is distributed to head office down to $150,000"

# Opening position at 31 Dec 2023 (store opened Nov 2023) - summarised start-up transactions
OPENING = dict(
    date="2023-12-31",
    equity_contribution=600000.0,
    pre_opening_expenses=58400.0,        # wages, rent, launch marketing Nov-Dec 2023 (cash)
    opening_ap_share=0.40,               # 40% of opening inventory from Net-30 suppliers unpaid at 31 Dec 2023
    opening_ap_due="2024-01-25",
)
