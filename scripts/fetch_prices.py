#!/usr/bin/env python3
"""Fetch daily closes for every ticker in watchlist.json (Yahoo Finance chart API, stdlib only)
and write data/latest.json + data/history.json. Safe to re-run; falls back to the previous
value (flagged stale) when a ticker fails."""
import json, os, sys, time, urllib.request, urllib.error
from datetime import datetime, timezone, timedelta

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WATCHLIST = os.path.join(ROOT, "watchlist.json")
DATA = os.path.join(ROOT, "data")
LATEST = os.path.join(DATA, "latest.json")
HISTORY = os.path.join(DATA, "history.json")
JST = timezone(timedelta(hours=9))
UA = {"User-Agent": "Mozilla/5.0 (stock-dashboard; +https://github.com/shimadness/stock-dashboard)"}


def fetch_chart(ticker, rng="1y"):
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}?range={rng}&interval=1d"
    last_err = None
    for attempt in range(3):
        try:
            req = urllib.request.Request(url, headers=UA)
            with urllib.request.urlopen(req, timeout=20) as r:
                d = json.load(r)
            res = d["chart"]["result"][0]
            ts = res["timestamp"]
            closes = res["indicators"]["quote"][0]["close"]
            meta = res["meta"]
            points = [(datetime.fromtimestamp(t, tz=timezone.utc).strftime("%Y-%m-%d"), c)
                      for t, c in zip(ts, closes) if c is not None]
            return meta, points
        except Exception as e:  # network, rate limit, schema
            last_err = e
            time.sleep(1.5 * (attempt + 1))
    raise RuntimeError(f"{ticker}: {last_err}")


def pct(a, b):
    return None if (a is None or b in (None, 0)) else round((a / b - 1) * 100, 2)


def summarize(points):
    closes = [c for _, c in points]
    dates = [d for d, _ in points]
    last = closes[-1]
    def back(n):
        return closes[-1 - n] if len(closes) > n else None
    year = dates[-1][:4]
    ytd_base = next((c for d, c in points if d.startswith(year)), None)
    return {
        "last": round(last, 4),
        "last_date": dates[-1],
        "prev": round(back(1), 4) if back(1) else None,
        "chg_1d": pct(last, back(1)),
        "chg_5d": pct(last, back(5)),
        "chg_1m": pct(last, back(21)),
        "chg_3m": pct(last, back(63)),
        "chg_ytd": pct(last, ytd_base),
        "high_52w": round(max(closes), 4),
        "low_52w": round(min(closes), 4),
        "from_high": pct(last, max(closes)),
        "spark": [round(c, 4) for c in closes[-30:]],
    }


def main():
    wl = json.load(open(WATCHLIST, encoding="utf-8"))
    prev_latest = {}
    if os.path.exists(LATEST):
        try:
            prev_latest = {i["ticker"]: i for i in json.load(open(LATEST, encoding="utf-8"))["items"]}
        except Exception:
            pass
    items, history, errors = [], {}, []
    for i, c in enumerate(wl["companies"]):
        t = c["ticker"]
        try:
            meta, points = fetch_chart(t)
            if len(points) < 2:
                raise RuntimeError("too few points")
            item = {"ticker": t, "name": c["name"], "sector": c["sector"], "market": c["market"],
                    "currency": meta.get("currency"), "stale": False, **summarize(points)}
            history[t] = points
        except Exception as e:
            errors.append(str(e))
            old = prev_latest.get(t)
            item = {**old, "stale": True} if old else {"ticker": t, "name": c["name"], "sector": c["sector"],
                                                       "market": c["market"], "stale": True, "last": None}
        items.append(item)
        print(f"[{i+1:2d}/{len(wl['companies'])}] {t:10s} {item.get('last')} {item.get('chg_1d')}%", file=sys.stderr)
        time.sleep(0.4)
    os.makedirs(DATA, exist_ok=True)
    now = datetime.now(tz=JST)
    json.dump({"generated_at": now.isoformat(timespec="seconds"), "generated_date": now.strftime("%Y-%m-%d"),
               "errors": errors, "items": items}, open(LATEST, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    # merge history so points older than 1y survive across runs
    old_hist = {}
    if os.path.exists(HISTORY):
        try:
            old_hist = json.load(open(HISTORY, encoding="utf-8"))
        except Exception:
            pass
    for t, pts in history.items():
        merged = dict(old_hist.get(t, []))
        merged.update(dict(pts))
        old_hist[t] = sorted(merged.items())
    json.dump(old_hist, open(HISTORY, "w", encoding="utf-8"), separators=(",", ":"))
    print(f"done: {len(items)} items, {len(errors)} errors", file=sys.stderr)
    for e in errors:
        print("  ERR", e, file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
