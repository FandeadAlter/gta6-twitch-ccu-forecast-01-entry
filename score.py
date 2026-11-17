#!/usr/bin/env python3
"""Step 1 scorer + backtest harness for gta6-twitch-ccu-forecast-01.

Backtest design (truth for the 4 practice launches is server-side, so it is
NOT in the .in files): treat every comparable launch as one pseudo-case.
Its hour-1 print is the known, its hours 2..24 are the truth, and the loss
is the contest's pinball loss on the log scale, averaged over every
(case, hour, level) item.

Models compared here:
  baseline : house persistence, q_tau(h) = p1 * exp(z_tau * 0.15 * sqrt(h-1))
  v0-all   : per-hour empirical quantiles of log(viewers_h / viewers_1)
             over ALL usable comparables (n=37)
  v0-roll  : same, over rolling-midnight launches only (unlock text contains
             "rolling" or "midnight local", n=12)
  v0-live  : same, over launches already live at hour 1 (hour-1 channels
             >= 200, n=? -- printed at run time)

Every model is evaluated on every subset, so the loss matrix shows what a
model tuned on one population costs on another. The scored population
(the 4 practice launches + GTA VI itself) is entirely rolling-midnight
console launches, so the rolling-subset column is the decision-relevant one;
the all-launch column is reported for honesty, not for model selection.

Stdlib only. Usage:  python3 score.py  (run from this directory)
"""
import json
import math
import os
import statistics
from datetime import datetime

KIT = os.path.expanduser("~/workspace/makefun/gta6-kit/input")
LEVELS = [0.05, 0.25, 0.5, 0.75, 0.95]
Z = [-1.645, -0.674, 0, 0.674, 1.645]
HOURS = list(range(2, 25))


def parse_ts(s):
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


def pinball(y, q, tau):
    """Contest pinball loss on the log scale (RULES.txt, Scoring)."""
    y = max(1.0, float(y))
    q = max(1e-9, float(q))
    d = math.log(y) - math.log(q)
    return 2.0 * max(tau * d, (tau - 1.0) * d)


def quantile(sorted_xs, p):
    """Linear-interpolation quantile (type 7), p in [0, 1]."""
    n = len(sorted_xs)
    if n == 0:
        raise ValueError("quantile of empty sample")
    if n == 1:
        return sorted_xs[0]
    pos = p * (n - 1)
    lo = int(math.floor(pos))
    hi = min(lo + 1, n - 1)
    frac = pos - lo
    return sorted_xs[lo] * (1 - frac) + sorted_xs[hi] * frac


def baseline_forecast(p1):
    p1 = max(1.0, float(p1))
    out = {}
    for h in HOURS:
        out[h] = [p1 * math.exp(z * 0.15 * math.sqrt(h - 1)) for z in Z]
    return out


def empirical_forecast(p1, log_ratios_by_hour):
    """log_ratios_by_hour: {h: [log(v_h / v_1), ...]} -> {h: [q05..q95]}.

    The pinball-optimal forecast for the empirical distribution is its
    quantiles, so each hour's five quantiles are the empirical quantiles
    of that hour's log-ratios, exponentiated and scaled by p1.
    """
    p1 = max(1.0, float(p1))
    out = {}
    for h in HOURS:
        xs = sorted(log_ratios_by_hour[h])
        qs = [quantile(xs, tau) for tau in LEVELS]
        out[h] = [max(1.0, min(1e9, p1 * math.exp(v))) for v in qs]
    return out


def load_comparables():
    """Dedup comparables across p00-p03 by (name, day_start).

    Returns list of dicts: name, unlock, platforms, day_curve {h: viewers},
    h1_channels, with a complete-ish release day (hours 1..24 present).
    The GTA VI pre-release pseudo-comparable has no release day and is
    dropped (it is not a launch curve).
    """
    seen = {}
    for pid in ("p00", "p01", "p02", "p03"):
        with open(os.path.join(KIT, pid + ".in"), encoding="utf-8") as f:
            case = json.load(f)
        for comp in case["comparables"]:
            key = (comp["name"], comp["day_start"])
            if key in seen:
                continue
            ds = parse_ts(comp["day_start"])
            curve = {}
            ch1 = None
            for pt in comp["hourly"]:
                t = parse_ts(pt["from"])
                h = int((t - ds).total_seconds() // 3600) + 1
                if 1 <= h <= 24:
                    curve[h] = pt["viewers"]
                    if h == 1:
                        ch1 = pt.get("channels")
            if 1 in curve and len(curve) >= 20:
                seen[key] = {
                    "name": comp["name"],
                    "unlock": comp.get("unlock") or "",
                    "platforms": comp.get("platforms") or "",
                    "curve": curve,
                    "h1_channels": ch1,
                }
    return list(seen.values())


def is_rolling(comp):
    u = comp["unlock"].lower()
    return ("rolling" in u) or ("midnight local" in u)


def is_simultaneous(comp):
    u = comp["unlock"].lower()
    return ("simultaneous" in u) or ("single global" in u) or ("single time" in u)


def log_ratios(comps):
    """{h: [log(v_h/v_1)]} over the given comparables (hours present only)."""
    by_hour = {h: [] for h in HOURS}
    for comp in comps:
        c = comp["curve"]
        if c.get(1, 0) <= 0:
            continue
        for h in HOURS:
            if h in c and c[h] > 0:
                by_hour[h].append(math.log(c[h] / c[1]))
    return by_hour


def score_model(forecast_fn, comps):
    """Mean pinball loss + coverage + typical miss over pseudo-cases."""
    losses, per_hour, covered, total_hours, med_err = [], {}, 0, 0, []
    for comp in comps:
        c = comp["curve"]
        p1 = c[1]
        fc = forecast_fn(p1)
        for h in HOURS:
            if h not in c:
                continue
            y = c[h]
            for tau, q in zip(LEVELS, fc[h]):
                l = pinball(y, q, tau)
                losses.append(l)
                per_hour.setdefault(h, []).append(l)
            if fc[h][0] <= y <= fc[h][-1]:
                covered += 1
            total_hours += 1
            med_err.append(abs(math.log(max(1, y)) - math.log(fc[h][2])))
    mean_loss = sum(losses) / len(losses)
    typ_miss = 100 * (math.exp(sum(med_err) / len(med_err)) - 1)
    return {
        "loss": mean_loss,
        "coverage90": covered / total_hours if total_hours else float("nan"),
        "typical_miss_pct": typ_miss,
        "n_items": len(losses),
        "n_hours": total_hours,
        "per_hour": {h: sum(v) / len(v) for h, v in sorted(per_hour.items())},
    }


def main():
    comps = load_comparables()
    rolling = [c for c in comps if is_rolling(c)]
    simul = [c for c in comps if is_simultaneous(c)]
    live = [c for c in comps
            if c["h1_channels"] is not None and c["h1_channels"] >= 200]
    subsets = {"all (n=%d)" % len(comps): comps,
               "rolling (n=%d)" % len(rolling): rolling,
               "simultaneous (n=%d)" % len(simul): simul,
               "live-at-h1 ch>=200 (n=%d)" % len(live): live}
    print("comparables usable as pseudo-cases: %d" % len(comps))
    print("rolling: %d   simultaneous: %d   live-at-h1: %d"
          % (len(rolling), len(simul), len(live)))
    print("live-at-h1 names: %s" % ", ".join(c["name"] for c in live))
    print()

    models = {
        "baseline": lambda p1: baseline_forecast(p1),
        "v0-all": lambda p1: empirical_forecast(p1, log_ratios(comps)),
        "v0-roll": lambda p1: empirical_forecast(p1, log_ratios(rolling)),
        "v0-live": lambda p1: empirical_forecast(p1, log_ratios(live)),
    }

    results = {}
    for mname, fn in models.items():
        results[mname] = {}
        for sname, sub in subsets.items():
            results[mname][sname] = score_model(fn, sub)

    print("MEAN PINBALL LOSS (log scale; lower is better)")
    print("model      | " + " | ".join("%-26s" % s for s in subsets))
    for mname in models:
        row = " | ".join("%.4f (cov %.2f)" % (results[mname][s]["loss"],
                                              results[mname][s]["coverage90"])
                        for s in subsets)
        print("%-10s | %s" % (mname, row))
    print()
    print("TYPICAL MISS (median |log error|, %%) on rolling subset:")
    for mname in models:
        key = [s for s in subsets if s.startswith("rolling")][0]
        print("  %-10s %.1f%%   coverage90 %.2f   n_items %d"
              % (mname, results[mname][key]["typical_miss_pct"],
                 results[mname][key]["coverage90"],
                 results[mname][key]["n_items"]))
    print()
    print("PER-HOUR MEAN PINBALL LOSS on rolling subset (n=%d):" % len(rolling))
    key = [s for s in subsets if s.startswith("rolling")][0]
    print("hour | " + " | ".join("%-10s" % m for m in models))
    for h in HOURS:
        print("%4d | %s" % (h, " | ".join("%.4f    " % results[m][key]["per_hour"][h]
                                          for m in models)))
    print()
    print("PER-HOUR MEAN PINBALL LOSS on ALL comparables (n=%d):" % len(comps))
    key = [s for s in subsets if s.startswith("all")][0]
    print("hour | " + " | ".join("%-10s" % m for m in models))
    for h in HOURS:
        print("%4d | %s" % (h, " | ".join("%.4f    " % results[m][key]["per_hour"][h]
                                          for m in models)))
    print()
    print("SHAPE: median log-ratio -> ratio to hour 1, per hour")
    for label, sub in (("all", comps), ("rolling", rolling), ("live", live)):
        lr = log_ratios(sub)
        med = [math.exp(quantile(sorted(lr[h]), 0.5)) for h in HOURS]
        print("  %-8s median ratio h2..h24: %s"
              % (label, " ".join("%.2f" % v for v in med)))
        sd = [statistics.pstdev(lr[h]) for h in HOURS]
        print("  %-8s sd of log-ratio    : %s"
              % ("", " ".join("%.2f" % v for v in sd)))
        q05 = [math.exp(quantile(sorted(lr[h]), 0.05)) for h in HOURS]
        q95 = [math.exp(quantile(sorted(lr[h]), 0.95)) for h in HOURS]
        print("  %-8s q05 ratio h19/h20 : %.2f / %.2f ; q95: %.2f / %.2f"
              % ("", q05[17], q05[18], q95[17], q95[18]))
    print()
    print("NOTE: house baseline scores ~0.387 on the 4 practice launches (RULES.txt);")
    print("that number is NOT reproducible locally -- practice truth is server-side.")
    print("The rolling-subset column above is the proxy for the scored population:")
    print("all 4 practice launches and GTA VI are rolling-midnight console launches.")


if __name__ == "__main__":
    main()
