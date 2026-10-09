"""Central configuration for the Prairie Pulse E-Bikes analytics proof of concept.

All synthetic generation is driven by SEED so every run reproduces identical data.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
RAW_EXTERNAL = DATA / "external" / "raw"
EXTERNAL = DATA / "external" / "processed"
SYNTH_RAW = DATA / "synthetic" / "raw"        # synthetic "system exports" incl. injected data-quality issues
SYNTH_CLEAN = DATA / "synthetic" / "clean"    # cleaned, validated tables
DB_PATH = DATA / "ebike_retail_demo_synthetic.db"
SQL_DIR = ROOT / "sql"
DOCS = ROOT / "docs"
OUT = ROOT / "outputs"
CHARTS = OUT / "charts"
TABLES = OUT / "tables"
REPORTS = OUT / "reports"
MODELS = OUT / "models"

SEED = 20240101
START = "2024-01-01"
END = "2026-09-30"
FORECAST_START = "2026-10-01"
FORECAST_MONTHS = 12
RETRIEVAL_DATE = "2026-10-08"

STORE_ID = "CGY01"
STORE_NAME = "Prairie Pulse E-Bikes ()"

SYNTHETIC_LABEL = "SYNTHETIC DEMONSTRATION DATA - not Prairie Pulse E-Bikes internal results"

# VisiVault brand palette (taken from the VisiVault website CSS variables)
BRAND = {
    "brand": "#2a78d6", "brand_dark": "#184f95", "brand_light": "#eaf2fc",
    "accent": "#4a3aa7", "accent_light": "#efeaf9", "teal": "#0d9488",
    "navy": "#0b1120", "navy2": "#10192e", "bg": "#f9f9f7", "muted": "#52514e",
    "subtle": "#898781", "good": "#0ca30c", "warn": "#d97706", "bad": "#c2410c",
}
SERIES = ["#2a78d6", "#0d9488", "#4a3aa7", "#d97706", "#c2410c", "#64748b",
          "#9085e9", "#0ca30c", "#184f95", "#b45309"]

