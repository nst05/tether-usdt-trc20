#!/usr/bin/env python3
"""
Multi-Timeframe (MTF) Confluence Indicator
===========================================
Timeframes : 1H · 4H · 1D · 1W · 1M
Indicators : EMA(9/21/50/200), RSI, MACD, Bollinger Bands, ATR,
             Stochastic RSI, Supertrend, ADX, VWAP
Signal     : Strong Buy → Buy → Neutral → Sell → Strong Sell
Data       : Binance public API (no key required)

Usage
-----
  python multi_timeframe_indicator.py [SYMBOL] [CHART_TF]

  python multi_timeframe_indicator.py BTCUSDT 1d
  python multi_timeframe_indicator.py ETHUSDT 4h
  python multi_timeframe_indicator.py TRXUSDT 1h
"""

import sys
import time
import warnings
from datetime import datetime
from typing import Dict, Tuple

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec
import requests

warnings.filterwarnings("ignore")

# ─── Colour palette (GitHub-dark inspired) ───────────────────────────────────
C = {
    "bg":       "#0d1117",
    "panel":    "#161b22",
    "text":     "#e6edf3",
    "grid":     "#21262d",
    "green":    "#26a641",
    "red":      "#f85149",
    "yellow":   "#d29922",
    "blue":     "#58a6ff",
    "purple":   "#bc8cff",
    "ema9":     "#ffd60a",
    "ema21":    "#ff9f0a",
    "ema50":    "#30d158",
    "ema200":   "#0a84ff",
    "bb":       "#636e72",
    "bb_mid":   "#fdcb6e",
    "macd":     "#74b9ff",
    "sig_line": "#fd79a8",
    "rsi":      "#a29bfe",
    "stoch_k":  "#55efc4",
    "stoch_d":  "#fd79a8",
    "vwap":     "#dfe6e9",
}

plt.rcParams.update({
    "figure.facecolor":  C["bg"],
    "axes.facecolor":    C["panel"],
    "axes.edgecolor":    C["grid"],
    "axes.labelcolor":   C["text"],
    "xtick.color":       C["text"],
    "ytick.color":       C["text"],
    "text.color":        C["text"],
    "grid.color":        C["grid"],
    "grid.linewidth":    0.4,
    "font.family":       "monospace",
})


# ─── MTFIndicator class ───────────────────────────────────────────────────────

class MTFIndicator:
    """Multi-timeframe confluence trading indicator."""

    TIMEFRAMES: Dict[str, dict] = {
        "1h": {"interval": "1h",  "limit": 300, "weight": 1.0, "label": "1 Hour"},
        "4h": {"interval": "4h",  "limit": 200, "weight": 1.5, "label": "4 Hours"},
        "1d": {"interval": "1d",  "limit": 200, "weight": 2.0, "label": "1 Day"},
        "1w": {"interval": "1w",  "limit": 104, "weight": 2.5, "label": "1 Week"},
        "1M": {"interval": "1M",  "limit":  60, "weight": 3.0, "label": "1 Month"},
    }
    _KLINE_URL = "https://api.binance.com/api/v3/klines"

    def __init__(self, symbol: str = "BTCUSDT") -> None:
        self.symbol = symbol.upper()
        self.data:    Dict[str, pd.DataFrame] = {}
        self.signals: Dict[str, dict]         = {}

    # ── Fetching ──────────────────────────────────────────────────────────────

    def _fetch_one(self, tf: str) -> pd.DataFrame:
        cfg = self.TIMEFRAMES[tf]
        params = {"symbol": self.symbol, "interval": cfg["interval"], "limit": cfg["limit"]}
        for attempt in range(4):
            try:
                r = requests.get(self._KLINE_URL, params=params, timeout=15)
                r.raise_for_status()
                raw = r.json()
                break
            except Exception as exc:
                if attempt == 3:
                    raise RuntimeError(f"Fetch failed [{tf}]: {exc}") from exc
                time.sleep(2 ** attempt)

        df = pd.DataFrame(raw, columns=[
            "time", "open", "high", "low", "close", "volume",
            "close_time", "quote_vol", "trades",
            "taker_buy_base", "taker_buy_quote", "ignore",
        ])
        df["time"] = pd.to_datetime(df["time"], unit="ms")
        for col in ("open", "high", "low", "close", "volume"):
            df[col] = df[col].astype(float)
        return df.set_index("time")

    def fetch_all(self) -> None:
        print(f"\n  Fetching {self.symbol} …")
        for tf in self.TIMEFRAMES:
            df = self._fetch_one(tf)
            self.data[tf] = df
            print(f"    [{tf:>2}]  {len(df):>4} candles  "
                  f"up to {df.index[-1].strftime('%Y-%m-%d %H:%M')}")
        print()

    # ── Maths ─────────────────────────────────────────────────────────────────

    @staticmethod
    def _ema(s: pd.Series, n: int) -> pd.Series:
        return s.ewm(span=n, adjust=False).mean()

    @staticmethod
    def _rsi(s: pd.Series, n: int = 14) -> pd.Series:
        d = s.diff()
        gain = d.clip(lower=0).ewm(com=n - 1, adjust=False).mean()
        loss = (-d.clip(upper=0)).ewm(com=n - 1, adjust=False).mean()
        return 100 - 100 / (1 + gain / loss.replace(0, np.nan))

    @staticmethod
    def _macd(s: pd.Series, fast=12, slow=26, sig=9) -> Tuple[pd.Series, pd.Series, pd.Series]:
        line   = s.ewm(span=fast, adjust=False).mean() - s.ewm(span=slow, adjust=False).mean()
        signal = line.ewm(span=sig, adjust=False).mean()
        return line, signal, line - signal

    @staticmethod
    def _bbands(s: pd.Series, n=20, k=2.0) -> Tuple[pd.Series, pd.Series, pd.Series]:
        mid = s.rolling(n).mean()
        std = s.rolling(n).std()
        return mid + k * std, mid, mid - k * std

    @staticmethod
    def _atr(df: pd.DataFrame, n: int = 14) -> pd.Series:
        hl = df["high"] - df["low"]
        hc = (df["high"] - df["close"].shift()).abs()
        lc = (df["low"]  - df["close"].shift()).abs()
        tr = pd.concat([hl, hc, lc], axis=1).max(axis=1)
        return tr.ewm(com=n - 1, adjust=False).mean()

    @staticmethod
    def _stoch_rsi(s: pd.Series, rn=14, sn=14, k=3, d=3) -> Tuple[pd.Series, pd.Series]:
        r  = MTFIndicator._rsi(s, rn)
        lo = r.rolling(sn).min()
        hi = r.rolling(sn).max()
        st = 100 * (r - lo) / (hi - lo + 1e-9)
        K  = st.rolling(k).mean()
        D  = K.rolling(d).mean()
        return K, D

    @staticmethod
    def _adx(df: pd.DataFrame, n: int = 14) -> Tuple[pd.Series, pd.Series, pd.Series]:
        up  = df["high"].diff()
        dn  = -df["low"].diff()
        pdm = up.where((up > dn) & (up > 0), 0.0)
        ndm = dn.where((dn > up) & (dn > 0), 0.0)
        atr = MTFIndicator._atr(df, n)
        pdi = 100 * pdm.ewm(com=n - 1, adjust=False).mean() / atr
        ndi = 100 * ndm.ewm(com=n - 1, adjust=False).mean() / atr
        dx  = 100 * (pdi - ndi).abs() / (pdi + ndi + 1e-9)
        return dx.ewm(com=n - 1, adjust=False).mean(), pdi, ndi

    @staticmethod
    def _supertrend(df: pd.DataFrame, n: int = 10, mult: float = 3.0) -> Tuple[pd.Series, pd.Series]:
        hl2      = (df["high"] + df["low"]) / 2
        atr      = MTFIndicator._atr(df, n)
        ub_raw   = hl2 + mult * atr
        lb_raw   = hl2 - mult * atr

        ub   = ub_raw.copy()
        lb   = lb_raw.copy()
        st   = pd.Series(np.nan, index=df.index)
        dire = pd.Series(1,      index=df.index)

        close = df["close"].values
        ub_v  = ub.values.copy()
        lb_v  = lb.values.copy()
        st_v  = st.values.copy()
        dr_v  = dire.values.copy()

        for i in range(1, len(df)):
            lb_v[i] = max(lb_v[i], lb_v[i - 1]) if close[i] > lb_v[i - 1] else lb_v[i]
            ub_v[i] = min(ub_v[i], ub_v[i - 1]) if close[i] < ub_v[i - 1] else ub_v[i]

            if dr_v[i - 1] == 1:
                dr_v[i] = 1 if close[i] >= lb_v[i] else -1
            else:
                dr_v[i] = -1 if close[i] <= ub_v[i] else 1

            st_v[i] = lb_v[i] if dr_v[i] == 1 else ub_v[i]

        return pd.Series(st_v, index=df.index), pd.Series(dr_v, index=df.index)

    # ── Enrichment ────────────────────────────────────────────────────────────

    def _enrich(self, df: pd.DataFrame) -> pd.DataFrame:
        c = df["close"]
        df["ema9"]    = self._ema(c, 9)
        df["ema21"]   = self._ema(c, 21)
        df["ema50"]   = self._ema(c, 50)
        df["ema200"]  = self._ema(c, 200)
        df["rsi"]     = self._rsi(c)
        df["macd"], df["macd_sig"], df["macd_hist"] = self._macd(c)
        df["bb_up"], df["bb_mid"], df["bb_lo"]      = self._bbands(c)
        df["atr"]     = self._atr(df)
        df["stoch_k"], df["stoch_d"] = self._stoch_rsi(c)
        df["adx"], df["pdi"], df["ndi"] = self._adx(df)
        df["st"], df["st_dir"] = self._supertrend(df)
        tp = (df["high"] + df["low"] + df["close"]) / 3
        df["vwap"] = (tp * df["volume"]).rolling(20).sum() / df["volume"].rolling(20).sum()
        return df

    # ── Scoring ───────────────────────────────────────────────────────────────

    def _score(self, df: pd.DataFrame) -> dict:
        """
        Score the latest bar across all sub-indicators.
        Each sub-score ∈ {-2, -1, 0, +1, +2}; max possible = 16.
        """
        last = df.iloc[-1]
        prev = df.iloc[-2]
        s: Dict[str, int] = {}

        # EMA trend stack
        bull_stack = last["ema9"] > last["ema21"] > last["ema50"] > last["ema200"]
        bear_stack = last["ema9"] < last["ema21"] < last["ema50"] < last["ema200"]
        s["EMA Stack"]  = 2 if bull_stack else (-2 if bear_stack else 0)

        # Price vs EMA200
        s["vs EMA200"]  = 1 if last["close"] > last["ema200"] else -1

        # RSI
        r = last["rsi"]
        if   r < 30:  s["RSI"] =  2
        elif r < 45:  s["RSI"] =  1
        elif r > 70:  s["RSI"] = -2
        elif r > 55:  s["RSI"] = -1
        else:         s["RSI"] =  0

        # MACD
        cross_up   = (last["macd"] > last["macd_sig"]) and (prev["macd"] <= prev["macd_sig"])
        cross_down = (last["macd"] < last["macd_sig"]) and (prev["macd"] >= prev["macd_sig"])
        if   cross_up:                          s["MACD"] =  2
        elif cross_down:                        s["MACD"] = -2
        elif last["macd"] > last["macd_sig"]:  s["MACD"] =  1
        else:                                   s["MACD"] = -1

        # Bollinger Bands
        if   last["close"] < last["bb_lo"]:   s["BB"] =  2
        elif last["close"] > last["bb_up"]:   s["BB"] = -2
        elif last["close"] > last["bb_mid"]:  s["BB"] =  1
        else:                                  s["BB"] = -1

        # Supertrend
        s["Supertrend"] = 2 if last["st_dir"] == 1 else -2

        # Stochastic RSI
        k, d = last["stoch_k"], last["stoch_d"]
        if   k < 20 and d < 20:  s["StochRSI"] =  2
        elif k > 80 and d > 80:  s["StochRSI"] = -2
        elif k > d:              s["StochRSI"] =  1
        else:                    s["StochRSI"] = -1

        # ADX (trend strength)
        if last["adx"] > 25:
            s["ADX"] = 1 if last["pdi"] > last["ndi"] else -1
        else:
            s["ADX"] = 0

        # VWAP
        s["VWAP"] = 1 if last["close"] > last["vwap"] else -1

        total = sum(s.values())
        return {
            "scores":  s,
            "total":   total,
            "max":     16,
            "pct":     total / 16 * 100,
            "close":   float(last["close"]),
            "atr":     float(last["atr"]),
            "rsi":     float(last["rsi"]),
            "adx":     float(last["adx"]),
        }

    @staticmethod
    def _label(pct: float) -> Tuple[str, str]:
        if   pct >=  62:  return "STRONG BUY",  C["green"]
        elif pct >=  25:  return "BUY",          "#52be80"
        elif pct >= -25:  return "NEUTRAL",      C["yellow"]
        elif pct >= -62:  return "SELL",         "#e74c3c"
        else:             return "STRONG SELL",  C["red"]

    # ── Analysis ──────────────────────────────────────────────────────────────

    def analyse(self) -> None:
        for tf in self.TIMEFRAMES:
            self.data[tf]    = self._enrich(self.data[tf])
            self.signals[tf] = self._score(self.data[tf])

    def confluence(self) -> dict:
        tw  = sum(v["weight"] for v in self.TIMEFRAMES.values())
        pct = sum(self.signals[tf]["pct"] * self.TIMEFRAMES[tf]["weight"]
                  for tf in self.TIMEFRAMES) / tw
        lbl, clr = self._label(pct)
        return {"pct": pct, "label": lbl, "color": clr}

    # ── Pretty print ──────────────────────────────────────────────────────────

    def print_summary(self) -> None:
        conf = self.confluence()
        bar  = "─" * 44
        print(f"  {bar}")
        print(f"  {'Timeframe':<12} {'Signal':<14} {'Score':>7}")
        print(f"  {bar}")
        for tf in self.TIMEFRAMES:
            sig       = self.signals[tf]
            lbl, _    = self._label(sig["pct"])
            print(f"  {self.TIMEFRAMES[tf]['label']:<12} {lbl:<14} {sig['pct']:>+6.1f}%")
        print(f"  {bar}")
        print(f"  CONFLUENCE SIGNAL : {conf['label']}  ({conf['pct']:>+.1f}%)")
        print(f"  {bar}\n")

    # ── Visualisation ─────────────────────────────────────────────────────────

    def plot(self, tf: str = "1d", save: bool = True) -> plt.Figure:
        df  = self.data[tf]
        n   = min(130, len(df))
        d   = df.iloc[-n:].copy()
        idx = np.arange(len(d))

        fig = plt.figure(figsize=(24, 16), facecolor=C["bg"])
        gs  = gridspec.GridSpec(
            5, 2,
            figure=fig,
            height_ratios=[4, 1.1, 1.1, 1.1, 1.7],
            width_ratios=[3, 1],
            hspace=0.03, wspace=0.12,
            left=0.04, right=0.98, top=0.94, bottom=0.04,
        )

        ax_price  = fig.add_subplot(gs[0, 0])
        ax_vol    = fig.add_subplot(gs[1, 0], sharex=ax_price)
        ax_rsi    = fig.add_subplot(gs[2, 0], sharex=ax_price)
        ax_macd   = fig.add_subplot(gs[3, 0], sharex=ax_price)
        ax_mtf    = fig.add_subplot(gs[4, 0], sharex=ax_price)
        ax_info   = fig.add_subplot(gs[:, 1])

        for ax in (ax_price, ax_vol, ax_rsi, ax_macd, ax_mtf):
            ax.yaxis.tick_right()
            ax.yaxis.set_label_position("right")
            ax.grid(True)

        plt.setp(ax_price.get_xticklabels(), visible=False)
        plt.setp(ax_vol.get_xticklabels(),   visible=False)
        plt.setp(ax_rsi.get_xticklabels(),   visible=False)
        plt.setp(ax_macd.get_xticklabels(),  visible=False)

        # ── Candles ───────────────────────────────────────────────────────────
        for i, (_, row) in enumerate(d.iterrows()):
            clr = C["green"] if row["close"] >= row["open"] else C["red"]
            ax_price.plot([i, i], [row["low"], row["high"]], color=clr, lw=0.8)
            ax_price.add_patch(plt.Rectangle(
                (i - 0.35, min(row["open"], row["close"])),
                0.7, abs(row["close"] - row["open"]),
                color=clr, alpha=0.88,
            ))

        # EMAs
        ax_price.plot(idx, d["ema9"],   color=C["ema9"],   lw=1.2, label="EMA 9")
        ax_price.plot(idx, d["ema21"],  color=C["ema21"],  lw=1.2, label="EMA 21")
        ax_price.plot(idx, d["ema50"],  color=C["ema50"],  lw=1.5, label="EMA 50")
        ax_price.plot(idx, d["ema200"], color=C["ema200"], lw=2.0, label="EMA 200")

        # Bollinger Bands
        ax_price.fill_between(idx, d["bb_up"], d["bb_lo"], alpha=0.07, color=C["blue"])
        ax_price.plot(idx, d["bb_up"], color=C["bb"],     lw=0.7, ls="--")
        ax_price.plot(idx, d["bb_lo"], color=C["bb"],     lw=0.7, ls="--")
        ax_price.plot(idx, d["bb_mid"], color=C["bb_mid"], lw=0.8, ls=":")

        # Supertrend dots
        for dir_val, clr in ((1, C["green"]), (-1, C["red"])):
            mask = d["st_dir"] == dir_val
            ii   = idx[mask.values]
            ax_price.scatter(ii, d["st"][mask], color=clr, s=5, zorder=6)

        # VWAP
        ax_price.plot(idx, d["vwap"], color=C["vwap"], lw=1.0, ls=":", alpha=0.65, label="VWAP")

        ax_price.legend(loc="upper left", fontsize=7, facecolor=C["panel"],
                        labelcolor=C["text"], edgecolor=C["grid"], framealpha=0.9)
        ax_price.set_ylabel("Price (USDT)", fontsize=9)
        ax_price.set_title(
            f"  {self.symbol}  ·  {self.TIMEFRAMES[tf]['label']}  "
            f"·  {d.index[-1].strftime('%Y-%m-%d %H:%M')}",
            loc="left", fontsize=11, fontweight="bold",
        )

        # ── Volume ────────────────────────────────────────────────────────────
        vol_clr = [C["green"] if d["close"].iloc[i] >= d["open"].iloc[i]
                   else C["red"] for i in range(len(d))]
        ax_vol.bar(idx, d["volume"], color=vol_clr, alpha=0.7, width=0.8)
        ax_vol.set_ylabel("Volume", fontsize=8)

        # ── RSI + StochRSI ────────────────────────────────────────────────────
        ax_rsi.plot(idx, d["rsi"], color=C["rsi"], lw=1.2, label="RSI")
        ax_rsi.axhline(70, color=C["red"],   lw=0.8, ls="--", alpha=0.6)
        ax_rsi.axhline(50, color=C["text"],  lw=0.5, ls=":",  alpha=0.35)
        ax_rsi.axhline(30, color=C["green"], lw=0.8, ls="--", alpha=0.6)
        ax_rsi.fill_between(idx, d["rsi"], 30, where=d["rsi"] < 30,
                            color=C["green"], alpha=0.18)
        ax_rsi.fill_between(idx, d["rsi"], 70, where=d["rsi"] > 70,
                            color=C["red"],   alpha=0.18)
        ax_rsi.set_ylim(0, 100)

        ax_rsi2 = ax_rsi.twinx()
        ax_rsi2.plot(idx, d["stoch_k"], color=C["stoch_k"], lw=0.9, alpha=0.8)
        ax_rsi2.plot(idx, d["stoch_d"], color=C["stoch_d"], lw=0.9, alpha=0.8, ls="--")
        ax_rsi2.axhline(80, color=C["grid"], lw=0.5)
        ax_rsi2.axhline(20, color=C["grid"], lw=0.5)
        ax_rsi2.set_ylim(0, 100)
        ax_rsi2.tick_params(colors=C["text"], labelsize=7)
        ax_rsi2.spines[:].set_color(C["grid"])

        ax_rsi.set_ylabel("RSI / StochRSI", fontsize=8)
        ax_rsi.legend(loc="upper left", fontsize=7, facecolor=C["panel"],
                      labelcolor=C["text"], edgecolor=C["grid"])

        # ── MACD ──────────────────────────────────────────────────────────────
        ax_macd.plot(idx, d["macd"],     color=C["macd"],     lw=1.2, label="MACD")
        ax_macd.plot(idx, d["macd_sig"], color=C["sig_line"], lw=1.2, label="Signal")
        ax_macd.bar(idx, d["macd_hist"].clip(lower=0), color=C["green"], alpha=0.55, width=0.8)
        ax_macd.bar(idx, d["macd_hist"].clip(upper=0), color=C["red"],   alpha=0.55, width=0.8)
        ax_macd.axhline(0, color=C["grid"], lw=0.8)
        ax_macd.set_ylabel("MACD", fontsize=8)
        ax_macd.legend(loc="upper left", fontsize=7, facecolor=C["panel"],
                       labelcolor=C["text"], edgecolor=C["grid"])

        # ── MTF Signal Strength bars ──────────────────────────────────────────
        for i, tfk in enumerate(self.TIMEFRAMES):
            pct = self.signals[tfk]["pct"] / 100
            clr = C["green"] if pct > 0.25 else (C["red"] if pct < -0.25 else C["yellow"])
            ax_mtf.barh(i, pct, color=clr, height=0.55, alpha=0.85)
            lbl_text, _ = self._label(self.signals[tfk]["pct"])
            ax_mtf.text(pct + (0.03 if pct >= 0 else -0.03), i, lbl_text,
                        va="center", ha="left" if pct >= 0 else "right",
                        color=clr, fontsize=7)

        ax_mtf.set_yticks(range(len(self.TIMEFRAMES)))
        ax_mtf.set_yticklabels([self.TIMEFRAMES[t]["label"] for t in self.TIMEFRAMES], fontsize=8)
        ax_mtf.axvline(0, color=C["text"], lw=0.8)
        ax_mtf.set_xlim(-1.15, 1.15)
        ax_mtf.set_xlabel("Signal Strength  (–1 = Strong Sell · +1 = Strong Buy)", fontsize=8)
        ax_mtf.set_ylabel("Timeframe Signal", fontsize=8)

        # ── Right panel: confluence dashboard ────────────────────────────────
        ax_info.set_facecolor(C["panel"])
        ax_info.set_xlim(0, 10)
        ax_info.set_ylim(0, 10)
        ax_info.axis("off")

        conf = self.confluence()

        # Header
        ax_info.text(5, 9.75, "MTF CONFLUENCE", ha="center",
                     fontsize=12, fontweight="bold")

        # Big signal
        ax_info.text(5, 8.8, conf["label"],  ha="center",
                     color=conf["color"], fontsize=24, fontweight="bold")
        ax_info.text(5, 8.05, f"{conf['pct']:+.1f}%", ha="center",
                     color=conf["color"], fontsize=14)

        # Divider
        ax_info.plot([0.3, 9.7], [7.65, 7.65], color=C["grid"], lw=0.8)

        # Per-TF table
        ax_info.text(0.5, 7.45, "Timeframe",  fontsize=8, fontweight="bold")
        ax_info.text(5.0, 7.45, "Signal",     fontsize=8, fontweight="bold", ha="center")
        ax_info.text(9.0, 7.45, "Score",      fontsize=8, fontweight="bold", ha="right")

        for i, tfk in enumerate(self.TIMEFRAMES):
            y   = 6.95 - i * 0.88
            sig = self.signals[tfk]
            lbl, clr = self._label(sig["pct"])
            ax_info.text(0.5, y, self.TIMEFRAMES[tfk]["label"], fontsize=8)
            ax_info.text(5.0, y, lbl,                fontsize=8,  color=clr,
                         fontweight="bold", ha="center")
            ax_info.text(9.0, y, f"{sig['pct']:+.0f}%", fontsize=8, color=clr, ha="right")

        ax_info.plot([0.3, 9.7], [2.55, 2.55], color=C["grid"], lw=0.8)

        # Current stats (for the chosen chart TF)
        last_sig = self.signals[tf]
        stats = [
            ("Price",  f"${last_sig['close']:>12,.2f}"),
            ("RSI",    f"{last_sig['rsi']:>12.1f}"),
            ("ATR",    f"{last_sig['atr']:>12.4f}"),
            ("ADX",    f"{last_sig['adx']:>12.1f}"),
        ]
        ax_info.text(5, 2.4, "Current Stats", ha="center", fontsize=9, fontweight="bold")
        for i, (key, val) in enumerate(stats):
            y = 1.95 - i * 0.44
            ax_info.text(0.5, y, key, fontsize=8)
            ax_info.text(9.5, y, val, fontsize=8, color=C["blue"], ha="right")

        # Sub-scores
        ax_info.plot([0.3, 9.7], [0.0, 0.0], color=C["grid"], lw=0.8)
        sub = last_sig["scores"]
        for i, (name, val) in enumerate(sub.items()):
            y   = -0.35 - i * 0.38
            clr = C["green"] if val > 0 else (C["red"] if val < 0 else C["yellow"])
            ax_info.text(0.3, y, f"{name}: {val:+d}", color=clr, fontsize=7)

        # Footer
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        fig.text(0.5, 0.005,
                 f"Generated: {ts}  ·  Data: Binance public API  ·  NOT financial advice",
                 ha="center", color="#636e72", fontsize=7)

        if save:
            fname = f"mtf_{self.symbol}_{tf}.png"
            fig.savefig(fname, dpi=150, bbox_inches="tight", facecolor=C["bg"])
            print(f"  Chart saved → {fname}")

        plt.show()
        return fig


# ─── Entry point ─────────────────────────────────────────────────────────────

def run(symbol: str = "BTCUSDT", chart_tf: str = "1d") -> MTFIndicator:
    if chart_tf not in MTFIndicator.TIMEFRAMES:
        raise ValueError(f"chart_tf must be one of: {list(MTFIndicator.TIMEFRAMES)}")

    ind = MTFIndicator(symbol)
    ind.fetch_all()
    ind.analyse()
    ind.print_summary()
    ind.plot(chart_tf)
    return ind


if __name__ == "__main__":
    _sym = sys.argv[1] if len(sys.argv) > 1 else "BTCUSDT"
    _tf  = sys.argv[2] if len(sys.argv) > 2 else "1d"
    run(_sym, _tf)
