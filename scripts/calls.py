#!/usr/bin/env python3
"""AI stance tracking ("AIの見解"). Stdlib only.

  calls.py add --ticker NVDA --stance bull --tier short --confidence 2 \
               --thesis "..." --invalidation "..."        # open a new call (entry = latest close)
  calls.py withdraw --id 2026-11-03-NVDA-001 --reason "..."  # close early (invalidation hit); scored on today's close
  calls.py none --tier long --reason "..."                 # record "no candidate today" for a tier
  calls.py evaluate                                        # close expired calls, refresh scorecard
  calls.py list                                            # print open calls with unrealized return

Tiers (holding period, trading days): short=10, mid=60, long=120. Legacy horizon 20 is scored as mid.

Files: data/calls.json {"calls":[...]}  data/scorecard.json {summary, history[]}
Result rule (deterministic, never judged by the agent):
  bull: hit if return >= +HIT_PCT, miss if <= -HIT_PCT, else flat.  bear is mirrored.
  Benchmark = equal-weight average return of every watchlist ticker over the same dates.
"""
import argparse, json, os, sys
from datetime import datetime, timezone, timedelta

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data")
CALLS = os.path.join(DATA, "calls.json")
SCORE = os.path.join(DATA, "scorecard.json")
HISTORY = os.path.join(DATA, "history.json")
WATCHLIST = os.path.join(ROOT, "watchlist.json")
JST = timezone(timedelta(hours=9))
HIT_PCT = 1.0
TIERS = {"short": 10, "mid": 60, "long": 120}
HORIZONS = (10, 20, 60, 120)   # 20 = legacy, still scored
MAX_OPEN_PER_TIER = 3


def tier_of(c):
    return c.get("tier") or {10: "short", 20: "mid", 60: "mid", 120: "long"}.get(c["horizon"], "mid")


def today():
    return datetime.now(tz=JST).strftime("%Y-%m-%d")


def load(path, default):
    if not os.path.exists(path):
        return default
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def save(path, obj):
    os.makedirs(DATA, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=1)
        f.write("\n")


def close_on_or_before(series, date):
    """(date, close) of the last trading day <= date, or None."""
    best = None
    for d, c in series:
        if d <= date:
            best = (d, c)
        else:
            break
    return best


def pct(a, b):
    return None if (a is None or b in (None, 0)) else round((a / b - 1) * 100, 2)


def benchmark(history, tickers, d0, d1):
    rets = []
    for t in tickers:
        s = history.get(t)
        if not s:
            continue
        a, b = close_on_or_before(s, d0), close_on_or_before(s, d1)
        if a and b and a[0] != b[0]:
            rets.append(b[1] / a[1] - 1)
    return round(sum(rets) / len(rets) * 100, 2) if rets else None


def cmd_add(args):
    wl = load(WATCHLIST, {"companies": []})
    names = {c["ticker"]: c["name"] for c in wl["companies"]}
    if args.ticker not in names:
        sys.exit(f"refused: {args.ticker} is not in watchlist.json")
    if args.tier not in TIERS:
        sys.exit(f"refused: tier must be one of {list(TIERS)}")
    horizon = TIERS[args.tier]
    if not (1 <= args.confidence <= 3):
        sys.exit("refused: confidence must be 1..3")
    if len(args.thesis) < 20:
        sys.exit("refused: thesis too short (>= 20 chars, state the mechanism)")
    history = load(HISTORY, {})
    series = history.get(args.ticker)
    if not series:
        sys.exit(f"refused: no price history for {args.ticker}")
    book = load(CALLS, {"calls": []})
    open_calls = [c for c in book["calls"] if c["status"] == "open"]
    if any(c["ticker"] == args.ticker for c in open_calls):
        sys.exit(f"refused: {args.ticker} already has an open call")
    same_tier = [c for c in open_calls if tier_of(c) == args.tier]
    if len(same_tier) >= MAX_OPEN_PER_TIER:
        sys.exit(f"refused: already {MAX_OPEN_PER_TIER} open {args.tier} calls; wait for some to close or withdraw one")
    d = today()
    entry_date, entry = close_on_or_before(series, d)
    n = len(book["calls"]) + 1
    call = {
        "id": f"{d}-{args.ticker}-{n:03d}",
        "date": d,
        "ticker": args.ticker,
        "name": names[args.ticker],
        "stance": args.stance,
        "tier": args.tier,
        "horizon": horizon,
        "confidence": args.confidence,
        "entry": round(entry, 4),
        "entry_date": entry_date,
        "thesis": args.thesis.strip(),
        "invalidation": args.invalidation.strip(),
        "status": "open",
    }
    book["calls"].append(call)
    save(CALLS, book)
    # keep today's scorecard snapshot in sync (evaluate runs before add)
    score = load(SCORE, None)
    if score and score.get("history") and score["history"][-1]["date"] == d:
        score["history"][-1]["open"] = len(open_calls) + 1
        score["summary"]["open"] = len(open_calls) + 1
        save(SCORE, score)
    print(f"opened {call['id']} {args.tier}/{args.stance} {horizon}d entry {entry} ({entry_date})")


def score(c, history, tickers, exit_date, exit_px):
    ret = pct(exit_px, c["entry"])
    bench = benchmark(history, tickers, c["entry_date"], exit_date)
    signed = ret if c["stance"] == "bull" else -ret
    result = "hit" if signed >= HIT_PCT else "miss" if signed <= -HIT_PCT else "flat"
    excess = None if bench is None else round((ret - bench) if c["stance"] == "bull" else (bench - ret), 2)
    c.update({"status": "closed", "exit": round(exit_px, 4), "exit_date": exit_date, "ret_pct": ret,
              "bench_pct": bench, "excess_pct": excess, "result": result, "closed_on": today()})


def evaluate_call(c, history, tickers):
    series = history.get(c["ticker"], [])
    dates = [d for d, _ in series]
    if c["entry_date"] not in dates:
        return False
    i = dates.index(c["entry_date"])
    j = i + c["horizon"]
    if j >= len(series):
        return False  # horizon not reached yet
    exit_date, exit_px = series[j]
    score(c, history, tickers, exit_date, exit_px)
    return True


def cmd_withdraw(args):
    history = load(HISTORY, {})
    wl = load(WATCHLIST, {"companies": []})
    tickers = [c["ticker"] for c in wl["companies"]]
    book = load(CALLS, {"calls": []})
    c = next((x for x in book["calls"] if x["id"] == args.id), None)
    if not c or c["status"] != "open":
        sys.exit(f"refused: {args.id} is not an open call")
    if len(args.reason) < 10:
        sys.exit("refused: reason too short")
    series = history.get(c["ticker"], [])
    if not series:
        sys.exit("refused: no price history")
    exit_date, exit_px = series[-1]
    if exit_date == c["entry_date"]:
        sys.exit("refused: cannot withdraw on the entry day")
    score(c, history, tickers, exit_date, exit_px)
    c["withdrawn"] = True
    c["withdraw_reason"] = args.reason.strip()
    save(CALLS, book)
    print(f"withdrawn {c['id']} at {exit_px} ({exit_date}) -> {c['result']} {c['ret_pct']:+.2f}%")
    cmd_evaluate(args)


def cmd_none(args):
    if args.tier not in TIERS:
        sys.exit(f"refused: tier must be one of {list(TIERS)}")
    if len(args.reason) < 10:
        sys.exit("refused: reason too short")
    book = load(CALLS, {"calls": []})
    passes = [p for p in book.get("passes", []) if not (p["date"] == today() and p["tier"] == args.tier)]
    passes.append({"date": today(), "tier": args.tier, "reason": args.reason.strip()})
    book["passes"] = passes[-90:]
    save(CALLS, book)
    print(f"recorded: no {args.tier} candidate today")


def stats(closed):
    hit = sum(1 for c in closed if c["result"] == "hit")
    miss = sum(1 for c in closed if c["result"] == "miss")
    flat = sum(1 for c in closed if c["result"] == "flat")
    withdrawn = sum(1 for c in closed if c.get("withdrawn"))
    decided = hit + miss
    excess = [c["excess_pct"] for c in closed if c.get("excess_pct") is not None]
    signed = [(c["ret_pct"] if c["stance"] == "bull" else -c["ret_pct"]) for c in closed]
    return {
        "closed": len(closed), "hit": hit, "miss": miss, "flat": flat, "withdrawn": withdrawn,
        "hit_rate": round(hit / decided * 100, 1) if decided else None,
        "strict_hit_rate": round(hit / len(closed) * 100, 1) if closed else None,
        "avg_signed_ret": round(sum(signed) / len(signed), 2) if signed else None,
        "avg_excess": round(sum(excess) / len(excess), 2) if excess else None,
        "beat_bench_rate": round(sum(1 for e in excess if e > 0) / len(excess) * 100, 1) if excess else None,
    }


def cmd_evaluate(args):
    history = load(HISTORY, {})
    wl = load(WATCHLIST, {"companies": []})
    tickers = [c["ticker"] for c in wl["companies"]]
    book = load(CALLS, {"calls": []})
    newly = [c for c in book["calls"] if c["status"] == "open" and evaluate_call(c, history, tickers)]
    save(CALLS, book)
    closed = [c for c in book["calls"] if c["status"] == "closed"]
    opened = [c for c in book["calls"] if c["status"] == "open"]
    cutoff = (datetime.now(tz=JST) - timedelta(days=30)).strftime("%Y-%m-%d")
    summary = {
        **stats(closed),
        "open": len(opened),
        "by_stance": {s: stats([c for c in closed if c["stance"] == s]) for s in ("bull", "bear")},
        "by_tier": {t: {**stats([c for c in closed if tier_of(c) == t]),
                        "open": sum(1 for c in opened if tier_of(c) == t)} for t in TIERS},
        "by_horizon": {str(h): stats([c for c in closed if c["horizon"] == h]) for h in HORIZONS},
        "by_confidence": {str(k): stats([c for c in closed if c["confidence"] == k]) for k in (1, 2, 3)},
        "last_30d": stats([c for c in closed if c["exit_date"] >= cutoff]),
    }
    score = load(SCORE, {"history": []})
    snap = {"date": today(), "closed": summary["closed"], "hit_rate": summary["hit_rate"],
            "strict_hit_rate": summary["strict_hit_rate"], "avg_excess": summary["avg_excess"],
            "beat_bench_rate": summary["beat_bench_rate"], "open": summary["open"]}
    hist = [h for h in score.get("history", []) if h["date"] != snap["date"]] + [snap]
    save(SCORE, {"updated": datetime.now(tz=JST).isoformat(timespec="seconds"), "rule": {
        "hit_pct": HIT_PCT, "benchmark": "watchlist equal-weight", "tiers": TIERS},
        "summary": summary, "history": hist})
    for c in newly:
        print(f"closed {c['id']}: {c['stance']} {c['ret_pct']:+.2f}% vs bench {c['bench_pct']} -> {c['result']}")
    print(f"evaluate: {len(newly)} newly closed, {summary['closed']} closed total, {summary['open']} open, "
          f"hit_rate {summary['hit_rate']} strict {summary['strict_hit_rate']} avg_excess {summary['avg_excess']}")


def cmd_list(args):
    history = load(HISTORY, {})
    book = load(CALLS, {"calls": []})
    opened = [c for c in book["calls"] if c["status"] == "open"]
    for t in TIERS:
        n = sum(1 for c in opened if tier_of(c) == t)
        print(f"{t:5s} ({TIERS[t]:>3}d): {n}/{MAX_OPEN_PER_TIER} open")
    if not opened:
        print("no open calls")
    for c in opened:
        series = history.get(c["ticker"], [])
        dates = [d for d, _ in series]
        elapsed = len(dates) - 1 - dates.index(c["entry_date"]) if c["entry_date"] in dates else "?"
        cur = series[-1][1] if series else None
        print(f"{c['id']}  {tier_of(c):5s} {c['stance']:4s} {c['horizon']:>3}d  day {elapsed}/{c['horizon']}  "
              f"entry {c['entry']} now {cur} ({pct(cur, c['entry']):+.2f}%)  conf {c['confidence']}")
        print(f"    thesis: {c['thesis']}")
        print(f"    invalidation: {c['invalidation']}")
    closed = [c for c in book["calls"] if c["status"] == "closed"]
    recent = sorted(closed, key=lambda c: c["exit_date"])[-5:]
    if recent:
        print("recently closed:")
        for c in recent:
            print(f"  {c['id']} {c['stance']} -> {c['result']} ({c['ret_pct']:+.2f}%, excess {c['excess_pct']})")


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("add")
    a.add_argument("--ticker", required=True)
    a.add_argument("--stance", required=True, choices=["bull", "bear"])
    a.add_argument("--tier", required=True, choices=list(TIERS))
    a.add_argument("--confidence", required=True, type=int)
    a.add_argument("--thesis", required=True)
    a.add_argument("--invalidation", required=True)
    a.set_defaults(fn=cmd_add)
    w = sub.add_parser("withdraw")
    w.add_argument("--id", required=True)
    w.add_argument("--reason", required=True)
    w.set_defaults(fn=cmd_withdraw)
    n = sub.add_parser("none")
    n.add_argument("--tier", required=True)
    n.add_argument("--reason", required=True)
    n.set_defaults(fn=cmd_none)
    sub.add_parser("evaluate").set_defaults(fn=cmd_evaluate)
    sub.add_parser("list").set_defaults(fn=cmd_list)
    args = ap.parse_args()
    args.fn(args)


if __name__ == "__main__":
    main()
