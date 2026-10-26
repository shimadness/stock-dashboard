#!/usr/bin/env python3
"""Rebuild data/reports/index.json (newest first) from the report files present."""
import json, os, re
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPORTS = os.path.join(ROOT, "data", "reports")
os.makedirs(REPORTS, exist_ok=True)
dates = sorted((f[:-5] for f in os.listdir(REPORTS) if re.fullmatch(r"\d{4}-\d{2}-\d{2}\.json", f)), reverse=True)
json.dump(dates, open(os.path.join(REPORTS, "index.json"), "w"), indent=0)
print(f"{len(dates)} reports indexed")
