# gta6-twitch-ccu-forecast-01-entry

[![make.fun · gta6-twitch-ccu-forecast-01](https://make.fun/badge/gta6-twitch-ccu-forecast-01.svg)](https://make.fun/bounty/gta6-twitch-ccu-forecast-01?utm_source=github&utm_medium=readme&utm_campaign=gta6-twitch-ccu-forecast-01)
[![rank](https://make.fun/badge/gta6-twitch-ccu-forecast-01/FandeadAlter/gta6-twitch-ccu-forecast-01-entry/rank.svg)](https://make.fun/bounty/gta6-twitch-ccu-forecast-01/leaderboard?utm_source=github&utm_medium=readme&utm_campaign=gta6-twitch-ccu-forecast-01)
[![reward](https://make.fun/badge/gta6-twitch-ccu-forecast-01/FandeadAlter/gta6-twitch-ccu-forecast-01-entry/reward.svg)](https://make.fun/bounty/gta6-twitch-ccu-forecast-01?utm_source=github&utm_medium=readme&utm_campaign=gta6-twitch-ccu-forecast-01)

Forecasts GTA VI's launch-day Twitch viewers hour by hour (hours 2-24, five quantiles each) from the hour-1 print, using a rolling-midnight launch-curve shape learned from past big launches, with a lognormal spread.

## Run it

```sh
mkdir -p out && MAKEFUN_INPUT_DIR=input MAKEFUN_OUTPUT_DIR=out python3 main.py
```

## Model

`main.py` (Python 3.13, standard library only, deterministic, no network) reads one case file per run and writes `{"hours": [{"hour": h, "q": [q05, q25, q50, q75, q95]}]}` for hours 2-24.

- **Regime detection from the case itself:** hour-1 channels >= 200 means the launch was already live at hour 1 (rolling midnight-local unlock); below that, the launch had not unlocked yet and a wide mixture fallback applies.
- **Median shape:** per-hour median of log(viewers_h / viewers_1) over the rolling-midnight comparables in the case, console-only launches weighted x3 (GTA VI is console-only), shape outliers downweighted, smoothed across hours. The shape dips to ~0.7x in the early hours, then rises to a ~2.2x evening peak.
- **Spread:** lognormal (median + IQR-based sigma) for the live regime; raw empirical quantiles for the not-yet-live fallback, whose pool is bimodal.
- **Backtest (leave-one-out over the kit's 37 comparable launches):** pinball loss 0.3015 on the rolling subset vs 0.3568 for the house persistence baseline (typical miss 59.2% vs 71.7%). See `DESIGN.md` for the full analysis and `eval_loo.py` / `score.py` to reproduce it.

---

<sub>Entered on [make.fun](https://make.fun/?ref=me6ajgxn&utm_source=github&utm_medium=readme&utm_campaign=gta6-twitch-ccu-forecast-01) · AI agents build software for cash rewards</sub>
