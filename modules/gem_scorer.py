"""
modules/gem_scorer.py
──────────────────────
10-Point Hype & Gem Scoring Engine

Dimension          Max   Weight   Core signals
─────────────────────────────────────────────────────────────────────
Low-Cap Discount    3     30%     MCap size, price discount, ATH depth
Social Momentum     4     40%     Trending rank, hype score, spike, sentiment
Whale Accumulation  3     30%     Vol/MCap, vol trend, PV divergence, asymmetry
─────────────────────────────────────────────────────────────────────
TOTAL              10    100%

Each sub-score maps its 0-1 signal onto its max-point range.
The final gem_score is the sum rounded to 2dp.
"""

import numpy as np
from utils.config import (
    GemConfig,
    SCORE_LOWCAP_MAX, SCORE_SOCIAL_MAX, SCORE_WHALE_MAX,
    MCAP_MIN_USD, MCAP_MAX_USD,
)


class GemScorer:

    def __init__(self, config: GemConfig):
        self.config = config

    def score(self, coin: dict) -> dict:
        """
        Takes an enriched coin dict (with .social and .whale populated)
        and returns a scores dict.
        """
        lowcap = self._lowcap_score(coin)
        social = self._social_score(coin)
        whale  = self._whale_score(coin)
        total  = round(lowcap + social + whale, 2)

        return {
            "lowcap_score": round(lowcap, 2),
            "social_score": round(social, 2),
            "whale_score":  round(whale,  2),
            "gem_score":    total,
            "tier":         self._tier(total),
            "alerts":       self._collect_alerts(coin),
        }

    def score_all(self, coins: list[dict]) -> list[dict]:
        for coin in coins:
            coin["scores"] = self.score(coin)
        return sorted(coins, key=lambda c: c["scores"]["gem_score"], reverse=True)

    # ── Dimension scorers ───────────────────────────────────────────────────────

    def _lowcap_score(self, coin: dict) -> float:
        """
        3 points split across:
          1.2 pt  — MCap size (smaller = higher score within $5M–$50M range)
          0.9 pt  — ATH discount (deeper = higher upside potential)
          0.9 pt  — Price level (lower absolute price = more retail accessibility)
        """
        mcap = coin.get("mcap") or 0
        price = coin.get("price") or 0
        ath_pct = coin.get("ath_pct") or 0   # negative number

        # MCap score: $5M mcap → 1.2, $50M mcap → 0.0
        mcap_norm  = 1 - (mcap - MCAP_MIN_USD) / max(MCAP_MAX_USD - MCAP_MIN_USD, 1)
        mcap_score = np.clip(mcap_norm, 0, 1) * 1.2

        # ATH discount score: 90% below ATH → 0.9, at ATH → 0.0
        ath_score  = np.clip(abs(ath_pct) / 90, 0, 1) * 0.9

        # Price accessibility: $0.001 → 0.9, $0.99 → 0.0
        price_score = np.clip(1 - price / self.config.max_price, 0, 1) * 0.9

        return float(mcap_score + ath_score + price_score)

    def _social_score(self, coin: dict) -> float:
        """
        4 points split across:
          1.6 pt  — Hype score (composite CoinGecko proxy)
          1.2 pt  — Trending rank bonus
          0.8 pt  — Sentiment ratio
          0.4 pt  — Social spike flag
        """
        s = coin.get("social", {})

        hype      = s.get("hype_score",      0.0)
        trending  = s.get("trending_rank",   None)
        sentiment = s.get("sentiment_ratio", 0.5)
        spike     = s.get("social_spike",    False)

        hype_score     = np.clip(hype, 0, 1) * 1.6

        # Trending rank: rank 1 → full 1.2, rank 7 → 0.0
        if trending:
            trending_score = np.clip((7 - trending) / 6, 0, 1) * 1.2
        else:
            trending_score = 0.0

        sentiment_score = np.clip((sentiment - 0.5) * 2, 0, 1) * 0.8
        spike_score     = 0.4 if spike else 0.0

        return float(hype_score + trending_score + sentiment_score + spike_score)

    def _whale_score(self, coin: dict) -> float:
        """
        3 points split across:
          1.5 pt  — Composite whale_score (from WhaleTracker)
          0.9 pt  — Vol/MCap ratio
          0.6 pt  — Vol trend direction
        """
        w = coin.get("whale", {})

        whale_raw  = w.get("whale_score",    0.0)
        vmr        = w.get("vol_mcap_ratio", 0.0)
        vol_trend  = w.get("vol_trend",      "stable")

        whale_score = np.clip(whale_raw, 0, 1) * 1.5

        # Vol/MCap: 50% threshold → 0.9 full score
        vmr_score   = np.clip(vmr / self.config.whale_vol_ratio, 0, 1) * 0.9

        trend_map   = {"accelerating": 0.6, "rising": 0.35, "stable": 0.1, "declining": 0.0}
        trend_score = trend_map.get(vol_trend, 0.0)

        return float(whale_score + vmr_score + trend_score)

    # ── Helpers ─────────────────────────────────────────────────────────────────

    @staticmethod
    def _tier(score: float) -> str:
        if score >= 8.0:  return "MOONSHOT"
        if score >= 6.5:  return "HIGH CONVICTION"
        if score >= 5.0:  return "WATCHLIST"
        if score >= 3.5:  return "SPECULATIVE"
        return "AVOID"

    @staticmethod
    def _collect_alerts(coin: dict) -> list[str]:
        alerts = []
        for key in ("social", "whale"):
            a = coin.get(key, {}).get("alert", "")
            if a:
                alerts.extend(a.split(" | "))
        return [a for a in alerts if a]
