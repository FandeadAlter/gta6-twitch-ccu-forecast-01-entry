#!/usr/bin/env python3
"""Step 2 leave-one-out (LOO) evaluation of main.py's spread candidates.

Protocol (mirrors real grading): every usable comparable is held out in
turn as a pseudo-case -- its hour-1 print (viewers + channels) is the
known, its hours 2..24 are the truth -- and the forecast is built by
main.forecast_case() from the REMAINING comparables only (the target
launch is never in its own pool, exactly as in a real case: the target
is never among the comparables). Regime detection uses the held-out
launch's own hour-1 channels, as it would at runtime.

Models: baseline (house persistence), v0-roll-LOO (Step 1 method:
unweighted, untrimmed, unsmoothed empirical quantiles over the
keyword-rolling subset), and main.py with each spread candidate
("raw" | "lognormal" | "winsorized") over the shipped pool (keyword
rolling OR console-only+live, console weight x3, shape-distance trim).
A "R1" variant (keyword-rolling pool only, comparables list restricted
before the call) is shown for the subset-definition comparison.

Reports mean pinball loss on the rolling subset (n=12, the scored
population) and on all launches (n=37), plus coverage and typical miss.
"""
import importlib.util
import json
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
KIT = os.path.expanduser("~/workspace/makefun/gta6-kit/input")

spec = importlib.util.spec_from_file_location("gta6_main", os.path.join(HERE, "main.py"))
main = importlib.util.module_from_spec(spec)
spec.loader.exec_module(main)

LEVELS = [0.05, 0.25, 0.5, 0.75, 0.95]
HOURS = list(range(2, 25))


def pinball(y, q, tau):
    y = max(1.0, float(y))
    d = math.log(y) - math.log(max(1e-9, float(q)))
    return 2.0 * max(tau * d, (tau - 1.0) * d)


def quantile(sorted_xs, p):
    n = len(sorted_xs)
    if n == 1:
        return sorted_xs[0]
    pos = p * (n - 1)
    lo = int(math.floor(pos))
    hi = min(lo + 1, n - 1)
    return sorted_xs[lo] * (1 - (pos - lo)) + sorted_xs[hi] * (pos - lo)


def load_raw_comparables():
    """Raw comparable dicts from p00.in; assert the other files agree."""
    with open(os.path.join(KIT, "p00.in"), encoding="utf-8") as f:
        base = json.load(f)["comparables"]
    names = sorted((c["name"], c["day_start"]) for c in base)
    for pid in ("p01", "p02", "p03"):
        with open(os.path.join(KIT, pid + ".in"), encoding="utf-8") as f:
            other = json.load(f)["comparables"]
        assert sorted((c["name"], c["day_start"]) for c in other) == names, pid
    return base


def usable(comps):
    """(raw comp, curve, ch1) for comparables with a usable release day."""
    out = []
    for comp in comps:
        curve, ch1 = main.extract_curve(comp)
        if curve is not None:
            out.append((comp, curve, ch1))
    return out


def is_rolling_raw(comp):
    u = (comp.get("unlock") or "").lower()
    return ("rolling" in u) or ("midnight local" in u)


def v0_roll_loo_forecast(p1, pool_curves):
    """Step 1 v0-roll, leave-one-out: unweighted empirical quantiles over
    the keyword-rolling subset (pool_curves already excludes the target)."""
    out = {}
    for h in HOURS:
        xs = sorted(math.log(c[h] / c[1]) for c in pool_curves if h in c)
        out[h] = [max(1.0, p1 * math.exp(quantile(xs, tau))) for tau in LEVELS]
    return out


def score(forecast_by_hour, curve):
    losses, covered, total, med_err = [], 0, 0, []
    for h in HOURS:
        if h not in curve:
            continue
        y = curve[h]
        for tau, q in zip(LEVELS, forecast_by_hour[h]):
            losses.append(pinball(y, q, tau))
        if forecast_by_hour[h][0] <= y <= forecast_by_hour[h][-1]:
            covered += 1
        total += 1
        med_err.append(abs(math.log(max(1, y)) - math.log(forecast_by_hour[h][2])))
    return {
        "loss": sum(losses) / len(losses),
        "coverage": covered / total if total else float("nan"),
        "typ_miss": 100 * (math.exp(sum(med_err) / len(med_err)) - 1),
        "med_err": med_err,
        "per_hour": {},
    }


def main_eval():
    raw = load_raw_comparables()
    print("raw comparables: %d (identical across p00-p03: asserted)" % len(raw))
    print("missing 'unlock': %d, missing 'platforms': %d"
          % (sum(1 for c in raw if not c.get("unlock")),
             sum(1 for c in raw if not c.get("platforms"))))
    pool = usable(raw)
    print("usable as pseudo-cases: %d" % len(pool))
    rolling = [(c, cu, ch) for (c, cu, ch) in pool if is_rolling_raw(c)]
    print("keyword-rolling usable: %d" % len(rolling))

    models = ["baseline", "v0-roll-LOO", "raw", "lognormal", "winsorized",
              "lognormal-R1"]
    # results[model][subset] = list of per-launch scores
    results = {m: {"rolling": [], "all": []} for m in models}

    for target_comp, target_curve, target_ch1 in pool:
        others = [c for (c, _, _) in pool if c is not target_comp]
        p1 = target_curve[1]
        case_all = {"known": [{"hour": 1, "viewers": p1, "channels": target_ch1}],
                    "forecast": [{"hour": h} for h in HOURS],
                    "comparables": others}
        case_r1 = dict(case_all)
        case_r1["comparables"] = [c for c in others if is_rolling_raw(c)]
        roll_pool = [cu for (c, cu, _) in pool
                     if c is not target_comp and is_rolling_raw(c)]

        fc = {}
        fc["baseline"] = {h: qs for h, qs in main.baseline_forecast(p1).items()}
        fc["v0-roll-LOO"] = v0_roll_loo_forecast(p1, roll_pool)
        for spread in ("raw", "lognormal", "winsorized"):
            fc[spread] = {row["hour"]: row["q"]
                          for row in main.forecast_case(case_all, spread=spread)["hours"]}
        fc["lognormal-R1"] = {row["hour"]: row["q"]
                              for row in main.forecast_case(case_r1, spread="lognormal")["hours"]}

        subset = "rolling" if is_rolling_raw(target_comp) else "all"
        for m in models:
            s = score(fc[m], target_curve)
            results[m]["all"].append(s)
            if subset == "rolling":
                results[m]["rolling"].append(s)

    print()
    print("LEAVE-ONE-OUT MEAN PINBALL LOSS (lower is better)")
    print("Note: main.py forces the not-live fallback to raw empirical")
    print("quantiles (bimodal pool); the spread label below is the LIVE")
    print("regime's spread. Typical miss is pooled over all scored hours.")
    print("%-16s | %-22s | %-22s" % ("model", "rolling (n=12)", "all (n=37)"))
    for m in models:
        r = results[m]["rolling"]
        a = results[m]["all"]
        rl = sum(s["loss"] for s in r) / len(r)
        al = sum(s["loss"] for s in a) / len(a)
        rc = sum(s["coverage"] for s in r) / len(r)
        ac = sum(s["coverage"] for s in a) / len(a)
        r_err = [e for s in r for e in s["med_err"]]
        rt = 100 * (math.exp(sum(r_err) / len(r_err)) - 1)
        print("%-16s | %.4f (cov %.2f, miss %.1f%%) | %.4f (cov %.2f)"
              % (m, rl, rc, rt, al, ac))
    print()
    print("Per-launch LOO loss on rolling subset, lognormal (shipped) vs baseline:")
    for (comp, curve, _), rb, lb in zip(
            rolling,
            [s for s in results["baseline"]["rolling"]],
            [s for s in results["lognormal"]["rolling"]]):
        print("  %-42s baseline %.4f  lognormal %.4f" % (comp["name"][:42], rb["loss"], lb["loss"]))
    print()
    print("Per-hour LOO loss on rolling subset (lognormal vs baseline):")
    per_hour = {m: {h: [] for h in HOURS} for m in ("baseline", "lognormal")}
    for target_comp, target_curve, target_ch1 in pool:
        if not is_rolling_raw(target_comp):
            continue
        others = [c for (c, _, _) in pool if c is not target_comp]
        p1 = target_curve[1]
        case_all = {"known": [{"hour": 1, "viewers": p1, "channels": target_ch1}],
                    "forecast": [{"hour": h} for h in HOURS],
                    "comparables": others}
        fc_b = main.baseline_forecast(p1)
        fc_l = {row["hour"]: row["q"]
                for row in main.forecast_case(case_all, spread="lognormal")["hours"]}
        for h in HOURS:
            for m, fc in (("baseline", fc_b), ("lognormal", fc_l)):
                per_hour[m][h].append(
                    sum(pinball(target_curve[h], q, tau)
                        for tau, q in zip(LEVELS, fc[h])) / len(LEVELS))
    print("hour | baseline | lognormal")
    for h in HOURS:
        print("%4d | %.4f   | %.4f" % (h,
              sum(per_hour["baseline"][h]) / len(per_hour["baseline"][h]),
              sum(per_hour["lognormal"][h]) / len(per_hour["lognormal"][h])))
    print()
    print("Not-live fallback smoke test (Silksong as target, ch1=14):")
    sil = next((c, cu, ch) for (c, cu, ch) in pool if c["name"].startswith("Hollow Knight"))
    others = [c for (c, _, _) in pool if c is not sil[0]]
    case_s = {"known": [{"hour": 1, "viewers": sil[1][1], "channels": sil[2]}],
              "forecast": [{"hour": h} for h in HOURS], "comparables": others}
    out = main.forecast_case(case_s, spread="lognormal")["hours"]
    by_h = {r["hour"]: r["q"] for r in out}
    print("  forecast h19 q: %s (truth 307362, p1 164)" % by_h[19])
    print("  forecast h6  q: %s (truth 137)" % by_h[6])
    s = score(by_h, sil[1])
    print("  Silksong LOO loss lognormal %.4f vs baseline %.4f"
          % (s["loss"], score(main.baseline_forecast(sil[1][1]), sil[1])["loss"]))


if __name__ == "__main__":
    main_eval()
