"""
modules/whale_tracker.py
─────────────────────────
Smart Money & Whale Accumulation Tracker

Signals detected:
  1. Vol/MCap ratio spike  → daily volume > 50% of market cap
  2. Volume trend          → is volume accelerating over last 7 days?
  3. Price-volume divergence → price flat/down but volume rising = accumulation
  4. ATH distance + volume → deep discount + vol spike = high asymmetry
  5. Micro-cap liquidity ratio → volume / mcap normalised (higher = more interest)

All signals derived from CoinGecko OHLCV history (no on-chain node needed).
For true on-chain data, stub endpoints point to Etherscan/BSCScan/Dune.

Output per coin:
  {
    "whale_score":      float,   # 0–1
    "vol_mcap_ratio":   float,   # current daily vol / mcap
    "vol_spike":        bool,
    "vol_trend":        str,     # "accelerating" | "stable" | "declining"
    "pv_divergence":    bool,    # price flat + vol rising
    "asymmetry_score":  float,   # ath_discount * vol_ratio (upside leverage)
    "alert":            str,
  }
"""

import time
import numpy as np
import pandas as pd
from typing import Optional

from utils.config import (
    GemConfig, COINGECKO_BASE, CALL_DELAY_SEC,
    WHALE_VOL_MCAP_RATIO, VOL_SPIKE_MULTIPLIER, VOL_HISTORY_DAYS,
)
from utils.http_client import build_session, safe_get


class WhaleAccumulationTracker:

    def __init__(self, config: GemConfig):
        self.config  = config
        self.session = build_session()

    # ── Public ─────────────────────────────────────────────────────────────────

    def analyse(self, coin: dict) -> dict:
        """Run whale analysis for a single coin. Returns signal dict."""
        history = self._fetch_ohlcv(coin["id"])
        return self._build_whale_signal(coin, history)

    def analyse_batch(self, coins: list[dict]) -> list[dict]:
        total = len(coins)
        for i, coin in enumerate(coins, 1):
            print(f"  [whale {i}/{total}] {coin['symbol']}")
            coin["whale"] = self.analyse(coin)
            time.sleep(CALL_DELAY_SEC)
        return coins

    # ── OHLCV fetch ─────────────────────────────────────────────────────────────

    def _fetch_ohlcv(self, coin_id: str) -> Optional[pd.DataFrame]:
        data = safe_get(
            self.session,
            f"{COINGECKO_BASE}/coins/{coin_id}/market_chart",
            params={
                "vs_currency": "usd",
                "days":        self.config.vol_history_days,
                "interval":    "daily",
            },
            headers=self.config.cg_headers,
            delay=CALL_DELAY_SEC,
        )
        if not data:
            return None

        prices  = data.get("prices",        [])
        volumes = data.get("total_volumes", [])
        if not prices or not volumes:
            return None

        df = pd.DataFrame(prices,  columns=["ts", "price"])
        df["volume"] = [v[1] for v in volumes]
        df["date"]   = pd.to_datetime(df["ts"], unit="ms", utc=True)
        return df.sort_values("date").reset_index(drop=True)

    # ── Signal builder ──────────────────────────────────────────────────────────

    def _build_whale_signal(self, coin: dict, df: Optional[pd.DataFrame]) -> dict:
        result = {
            "whale_score":    0.0,
            "vol_mcap_ratio": 0.0,
            "vol_spike":      False,
            "vol_trend":      "unknown",
            "pv_divergence":  False,
            "asymmetry_score":0.0,
            "alert":          "",
        }

        mcap = coin.get("mcap") or 0
        vol  = coin.get("volume_24h") or 0

        # ── Signal 1: Vol/MCap ratio ───────────────────────────────────────────
        vmr = vol / mcap if mcap > 0 else 0
        result["vol_mcap_ratio"] = round(vmr, 4)
        result["vol_spike"]      = vmr >= self.config.whale_vol_ratio

        score = 0.0

        # Vol/MCap contributes up to 0.4 of whale_score
        score += min(vmr / (self.config.whale_vol_ratio * 2), 0.4)

        if df is not None and len(df) >= 7:
            prices  = df["price"].values
            volumes = df["volume"].values

            # ── Signal 2: Volume trend ─────────────────────────────────────────
            recent_vol = volumes[-3:].mean()
            prior_vol  = volumes[-10:-3].mean() if len(volumes) >= 10 else volumes[:-3].mean()
            vol_trend_ratio = recent_vol / max(prior_vol, 1)

            if vol_trend_ratio >= VOL_SPIKE_MULTIPLIER:
                result["vol_trend"] = "accelerating"
                score += 0.25
            elif vol_trend_ratio >= 1.5:
                result["vol_trend"] = "rising"
                score += 0.10
            elif vol_trend_ratio < 0.7:
                result["vol_trend"] = "declining"
            else:
                result["vol_trend"] = "stable"

            # ── Signal 3: Price-volume divergence ──────────────────────────────
            price_change_pct  = (prices[-1] - prices[-7]) / max(prices[-7], 1e-12) * 100
            volume_change_pct = (volumes[-1] - volumes[-7]) / max(volumes[-7], 1) * 100
            # Price barely moved but volume surging = hidden accumulation
            if abs(price_change_pct) < 10 and volume_change_pct > 50:
                result["pv_divergence"] = True
                score += 0.20

            # ── Signal 4: Volume consistency (not a single-day spike) ──────────
            vol_std = np.std(volumes[-7:])
            vol_mean = np.mean(volumes[-7:])
            vol_cv = vol_std / max(vol_mean, 1)   # coefficient of variation
            if vol_cv < 0.5:    # low variance = sustained accumulation, not a flash
                score += 0.10

        # ── Signal 5: ATH asymmetry (deep discount + vol activity = high upside) ─
        ath_pct = coin.get("ath_pct") or 0
        discount = abs(ath_pct) / 100   # 0 to ~1
        asymmetry = discount * min(vmr * 4, 1.0)
        result["asymmetry_score"] = round(asymmetry, 4)
        score += min(asymmetry * 0.2, 0.1)

        result["whale_score"] = round(min(score, 1.0), 4)

        # ── Alerts ─────────────────────────────────────────────────────────────
        alerts = []
        if result["vol_spike"]:
            alerts.append(f"VOL/MCAP {vmr:.0%}")
        if result["vol_trend"] == "accelerating":
            alerts.append("VOL ACCELERATING")
        if result["pv_divergence"]:
            alerts.append("STEALTH ACCUMULATION")
        result["alert"] = " | ".join(alerts)

        return result

    # ── On-chain stubs ──────────────────────────────────────────────────────────

    @staticmethod
    def fetch_onchain_whale_txns_stub(contract_address: str, chain: str = "ethereum") -> dict:
        """
        STUB — replace with Etherscan/BSCScan/Dune API.

        Real implementation (Etherscan):
            GET https://api.etherscan.io/api
                ?module=account&action=tokentx
                &contractaddress=<contract>
                &startblock=0&endblock=99999999
                &sort=desc&apikey=<ETHERSCAN_KEY>

        Then filter for transfers > $50k USD equivalent in last 48h.
        A cluster of large inbound transfers to new wallets = whale accumulation.
        """
        raise NotImplementedError("Wire in Etherscan API key.")

    @staticmethod
    def fetch_dex_liquidity_stub(pair_address: str) -> dict:
        """
        STUB — replace with DEX Screener / The Graph / Uniswap subgraph.

        GET https://api.dexscreener.com/latest/dex/pairs/<chain>/<pair_address>

        Key signals:
          - liquidity_usd trending up with price flat = whale LP addition
          - txns.buys >> txns.sells over 24h = accumulation
          - priceImpact of a $10k buy < 1% = sufficient liquidity to exit safely
        """
        raise NotImplementedError("Wire in DexScreener API (free, no key needed).")
