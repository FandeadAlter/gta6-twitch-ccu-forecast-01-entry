"""gta6-twitch-ccu-forecast-01 entry in Python 3.13 (standard library only).

Forecasts GTA VI's launch-day Twitch viewers hour by hour (hours 2..24)
from the first hour's print, as five quantiles an hour.

Model (see DESIGN.md for the evidence):
  The comparables in the case mix two unlock regimes. Launches already
  live at hour 1 (rolling midnight-local unlock, or early access) rise
  from ~0.7x of hour 1 in the early hours to a ~2x peak in the evening;
  launches not yet unlocked at hour 1 (one simultaneous global unlock
  later in the day) explode 50x-1000x. The regime is detected from the
  case itself: hour-1 channels >= 200 means already live (in the kit's
  data the two groups are separated by a clean gap, 126 vs 210 channels).
  * live: median log-shape + spread from the rolling-midnight subset
    (unlock text says "rolling" or "midnight local", or the launch is
    console-only and already live at hour 1), console-only launches
    weighted x3 (GTA VI is console-only, as are the four practice
    launches), with a generic shape-distance trim that downweights any
    launch whose curve sits far from the subset median (this catches the
    one PC-unlock outlier without naming any game).
  * not live: the same machinery over ALL comparables, unweighted and
    untrimmed, as a catastrophe hedge (wide upper quantiles).
  The median log-shape is smoothed across hours (3-hour moving average),
  preserving the early-hours dip, the hour-6 US-unlock step and the
  evening peak. Spread is one of three candidates (SPREAD below):
  "raw" empirical quantiles, "lognormal" (median + IQR-based sigma),
  "winsorized" (clip log-ratios at the 10th/90th percentile, then
  empirical quantiles) -- but only for the live regime, whose log-ratio
  distribution is roughly unimodal. The not-live fallback pool (ALL
  comparables) is bimodal -- a rolling cluster near 1x and a simultaneous
  cluster at 50x-1000x -- and a lognormal fit understates its upper tail
  catastrophically (smoke test: Silksong's hour-19 truth is 307,362 from
  a 164 hour-1 print; lognormal gives q95 = 2,423, raw empirical gives
  the honest mixture quantile). So the not-live fallback ALWAYS uses
  "raw" empirical quantiles, whatever SPREAD says. All three are computed
  at runtime from the comparables inside the case file itself; no fitted
  number is hardcoded except the regime threshold and the weighting rules.

How the grader runs it: `python3 -P -s /bot/main.py` in python:3.13-slim.
Reads every <id>.in in the input directory, writes <id>.out per case:
{"hours": [{"hour": 2, "q": [q05, q25, q50, q75, q95]}, ...]}, 23 rows.
Deterministic: no randomness, no network, no clock.
"""

import json
import math
import os
import sys
from datetime import datetime
from pathlib import Path

# The grader's -P leaves /bot off sys.path: put it back first.
sys.path.insert(0, str(Path(__file__).resolve().parent))

INPUT_DIR = Path(os.environ.get("MAKEFUN_INPUT_DIR", "/input"))
OUTPUT_DIR = Path(os.environ.get("MAKEFUN_OUTPUT_DIR", "/output"))

LEVELS = [0.05, 0.25, 0.5, 0.75, 0.95]
Z = [-1.645, -0.674, 0, 0.674, 1.645]
HOURS = list(range(2, 25))

# Spread candidate used for the shipped forecast. One of
# "raw" | "lognormal" | "winsorized" (see DESIGN.md Step 2 for the LOO
# comparison that chose it).
SPREAD = "lognormal"

# Hour-1 channels at or above this mean the launch was already live at
# hour 1 (rolling midnight unlock / early access). Kit data: not-yet-live
# launches have at most 126 channels at hour 1, live ones at least 210.
LIVE_CHANNELS = 200
# Fallback live test when hour-1 channels are missing: hour-1 viewers.
LIVE_VIEWERS = 10000
# Console-only launches are the closest analogs to GTA VI (console-only).
CONSOLE_WEIGHT = 3.0
# A launch whose mean |log-ratio - subset median| over hours 2..24 exceeds
# this is downweighted as a shape outlier (kit data: exactly one rolling
# launch sits above 1.0, at 1.33; the next is 0.65).
OUTLIER_DISTANCE = 1.0
OUTLIER_WEIGHT = 0.25


def round2(x):
    """x rounded to 2 decimals, half up (as the starter does)."""
    scaled = x * 100
    whole = math.floor(scaled)
    if scaled - whole >= 0.5:
        whole += 1
    value = whole / 100
    return int(value) if value.is_integer() else value


def parse_ts(s):
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


def weighted_quantile(pairs, p):
    """Quantile of weighted samples; pairs = [(value, weight)], p in [0, 1].

    Linear interpolation on cumulative weight (type-7 style).
    """
    pts = sorted((v, w) for v, w in pairs if w > 0)
    if not pts:
        raise ValueError("weighted_quantile of empty sample")
    total = sum(w for _, w in pts)
    if len(pts) == 1:
        return pts[0][0]
    target = p * total
    acc = 0.0
    for i, (v, w) in enumerate(pts):
        prev_acc = acc
        acc += w
        if acc >= target:
            if i == 0 or acc == target:
                return v
            prev_v = pts[i - 1][0]
            frac = (target - prev_acc) / w
            return prev_v * (1 - frac) + v * frac
    return pts[-1][0]


def moving_average_3(xs):
    """Centered 3-point moving average; edges average the points available."""
    out = []
    for i in range(len(xs)):
        lo = max(0, i - 1)
        hi = min(len(xs), i + 2)
        out.append(sum(xs[lo:hi]) / (hi - lo))
    return out


def extract_curve(comp):
    """Release-day curve of one comparable: {hour: viewers}, hour-1 channels.

    Returns (curve, ch1) or (None, None) when the comparable has no
    usable release day (e.g. the GTA VI pre-release pseudo-comparable,
    which has no points on its release day yet).
    """
    try:
        ds = parse_ts(comp["day_start"])
    except (KeyError, TypeError, ValueError):
        return None, None
    curve = {}
    ch1 = None
    for pt in comp.get("hourly") or []:
        try:
            t = parse_ts(pt["from"])
            viewers = pt["viewers"]
        except (KeyError, TypeError, ValueError):
            continue
        h = int((t - ds).total_seconds() // 3600) + 1
        if 1 <= h <= 24 and viewers is not None and viewers > 0:
            curve[h] = viewers
            if h == 1:
                ch1 = pt.get("channels")
    if 1 not in curve or len(curve) < 20:
        return None, None
    return curve, ch1


def is_rolling(comp):
    unlock = (comp.get("unlock") or "").lower()
    return ("rolling" in unlock) or ("midnight local" in unlock)


def is_console_only(comp):
    platforms = comp.get("platforms") or ""
    return ("PC" not in platforms) and ("Stadia" not in platforms)


def is_live(ch1, p1):
    """Was the launch already live at hour 1? Channels decide; viewers
    are the fallback when channels are missing."""
    if ch1 is not None:
        return ch1 >= LIVE_CHANNELS
    return p1 >= LIVE_VIEWERS


def log_ratios(curve):
    """{hour: log(viewers_h / viewers_1)} for hours 2..24 present."""
    p1 = curve[1]
    return {h: math.log(curve[h] / p1) for h in HOURS if h in curve}


def weighted_median_shape(items):
    """Per-hour weighted median log-ratio over items.

    items: [{curve, weight}]. Returns {hour: median log-ratio}.
    """
    shape = {}
    for h in HOURS:
        pairs = [(log_ratios(it["curve"])[h], it["weight"])
                 for it in items if h in it["curve"]]
        if pairs:
            shape[h] = weighted_quantile(pairs, 0.5)
    return shape


def shape_distance(curve, median_shape):
    """Mean |log-ratio - median| over hours 2..24 (shape-outlier score)."""
    lr = log_ratios(curve)
    diffs = [abs(lr[h] - median_shape[h]) for h in HOURS
             if h in lr and h in median_shape]
    return sum(diffs) / len(diffs) if diffs else 0.0


def build_pool(comps, live):
    """The comparables the forecast shape is learned from, with weights.

    live: rolling subset (keyword, or console-only + live at hour 1),
    console-only weighted x3, shape outliers downweighted.
    not live: every comparable, weight 1, no trimming (the mixture IS
    the hedge).
    """
    items = []
    for comp in comps:
        curve, ch1 = extract_curve(comp)
        if curve is None:
            continue
        if live:
            if not (is_rolling(comp) or
                    (is_console_only(comp) and ch1 is not None
                     and ch1 >= LIVE_CHANNELS)):
                continue
            weight = CONSOLE_WEIGHT if is_console_only(comp) else 1.0
        else:
            weight = 1.0
        items.append({"curve": curve, "weight": weight})
    if live and len(items) >= 3:
        median_shape = weighted_median_shape(items)
        for it in items:
            if shape_distance(it["curve"], median_shape) > OUTLIER_DISTANCE:
                it["weight"] *= OUTLIER_WEIGHT
    return items


def spread_log_quantiles(items, spread):
    """Per-hour log-quantiles {hour: [log q05..q95]} for the pool.

    spread: "raw" | "lognormal" | "winsorized". Every series is smoothed
    across hours with a 3-point moving average (the median shape with it
    too, inside the lognormal branch via the same smoothed median).
    """
    med = weighted_median_shape(items)
    med_s = {h: v for h, v in zip(HOURS, moving_average_3(
        [med[h] for h in HOURS]))}
    out = {}
    if spread == "lognormal":
        sigmas = []
        for h in HOURS:
            pairs = [(log_ratios(it["curve"])[h], it["weight"])
                     for it in items if h in it["curve"]]
            q25 = weighted_quantile(pairs, 0.25)
            q75 = weighted_quantile(pairs, 0.75)
            sigma = (q75 - q25) / 1.349
            sigmas.append(min(1.5, max(0.05, sigma)))
        sig_s = moving_average_3(sigmas)
        for h, sigma in zip(HOURS, sig_s):
            out[h] = [med_s[h] + z * sigma for z in Z]
    else:
        for h in HOURS:
            pairs = [(log_ratios(it["curve"])[h], it["weight"])
                     for it in items if h in it["curve"]]
            if spread == "winsorized":
                lo = weighted_quantile(pairs, 0.10)
                hi = weighted_quantile(pairs, 0.90)
                pairs = [(min(hi, max(lo, v)), w) for v, w in pairs]
            out[h] = [weighted_quantile(pairs, tau) for tau in LEVELS]
        # Smooth each quantile series across hours.
        for j in range(len(LEVELS)):
            series = moving_average_3([out[h][j] for h in HOURS])
            for h, v in zip(HOURS, series):
                out[h][j] = v
    # Enforce non-decreasing quantiles within each hour (log space).
    for h in HOURS:
        run = out[h][0]
        fixed = []
        for v in out[h]:
            run = max(run, v)
            fixed.append(run)
        out[h] = fixed
    return out


def baseline_forecast(p1):
    """House persistence baseline (starter): flat median, widening spread."""
    p1 = max(1.0, float(p1))
    return {h: [p1 * math.exp(z * 0.15 * math.sqrt(h - 1)) for z in Z]
            for h in HOURS}


def forecast_case(case, spread=SPREAD):
    first = next((k for k in case["known"] if k["hour"] == 1), None)
    if first is None:
        raise ValueError("case has no hour-1 print")
    p1 = max(1.0, float(first["viewers"]))
    ch1 = first.get("channels")
    live = is_live(ch1, p1)
    items = build_pool(case.get("comparables") or [], live)
    if len(items) < 3:
        log_q = {h: [math.log(v) - math.log(p1) for v in baseline_forecast(p1)[h]]
                 for h in HOURS}
    else:
        # Live regime: the chosen spread candidate. Not-live regime: the
        # all-comparables pool is bimodal, so always raw empirical
        # quantiles (a lognormal fit would crush the upper tail).
        effective_spread = spread if live else "raw"
        log_q = spread_log_quantiles(items, effective_spread)
    hours = []
    for row in case["forecast"]:
        h = row["hour"]
        qs = []
        for v in log_q[h]:
            q = round2(p1 * math.exp(v))
            q = max(1, min(1_000_000_000, q))
            qs.append(q)
        # Final monotonicity guard (rounding/clipping cannot break it,
        # but never ship a decreasing row).
        fixed = []
        run = qs[0]
        for q in qs:
            run = max(run, q)
            fixed.append(run)
        hours.append({"hour": h, "q": fixed})
    return {"hours": hours}


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    for path in sorted(INPUT_DIR.glob("*.in")):
        case = json.loads(path.read_text(encoding="utf-8"))
        forecast = forecast_case(case)
        (OUTPUT_DIR / f"{path.stem}.out").write_text(
            json.dumps(forecast, separators=(",", ":")) + "\n",
            encoding="utf-8")


if __name__ == "__main__":
    main()
