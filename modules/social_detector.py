"""
modules/social_detector.py
───────────────────────────
Social Hype & Anomaly Detector

Real signal sources used (no API key needed):
  1. CoinGecko community data  → sentiment_votes_up/down, public_interest_score
  2. CoinGecko trending endpoint → top-24h trending coins (strong signal)
  3. Price momentum divergence  → price flat but social spiking = early accumulation

Stub extension points clearly labelled for X API / Reddit / LunarCrush.

Outputs per coin:
  {
    "hype_score":        float,   # 0–1, drives Social Momentum score
    "trending_rank":     int|None,# rank in CoinGecko trending (1 = hottest)
    "social_spike":      bool,    # True if 300%+ anomaly detected
    "spike_magnitude":   float,   # multiplier vs baseline
    "sentiment_ratio":   float,   # votes_up / (votes_up + votes_down)
    "public_interest":   float,   # CoinGecko public_interest_score
    "alert":             str,     # human-readable flag message
  }
"""

import time
from typing import Optional

from utils.config import GemConfig, COINGECKO_BASE, CALL_DELAY_SEC, SOCIAL_SPIKE_THRESHOLD
from utils.http_client import build_session, safe_get


class SocialHypeDetector:

    def __init__(self, config: GemConfig):
        self.config   = config
        self.session  = build_session()
        self._trending_ids: dict[str, int] = {}   # coin_id → rank
        self._fetch_trending()

    # ── Public ─────────────────────────────────────────────────────────────────

    def analyse(self, coin: dict) -> dict:
        """Run social analysis for a single coin dict (from scanner)."""
        detail = self._fetch_coin_detail(coin["id"])
        return self._build_social_signal(coin, detail)

    def analyse_batch(self, coins: list[dict]) -> list[dict]:
        """Enrich a list of coins with social data in-place. Returns same list."""
        total = len(coins)
        for i, coin in enumerate(coins, 1):
            print(f"  [social {i}/{total}] {coin['symbol']}")
            coin["social"] = self.analyse(coin)
            time.sleep(CALL_DELAY_SEC)
        return coins

    # ── Trending fetch ──────────────────────────────────────────────────────────

    def _fetch_trending(self):
        data = safe_get(
            self.session,
            f"{COINGECKO_BASE}/search/trending",
            headers=self.config.cg_headers,
        )
        if data:
            for rank, item in enumerate(data.get("coins", []), 1):
                cid = item.get("item", {}).get("id")
                if cid:
                    self._trending_ids[cid] = rank
        print(f"[social] {len(self._trending_ids)} trending coins loaded")

    # ── Coin detail ─────────────────────────────────────────────────────────────

    def _fetch_coin_detail(self, coin_id: str) -> Optional[dict]:
        return safe_get(
            self.session,
            f"{COINGECKO_BASE}/coins/{coin_id}",
            params={
                "localization":    False,
                "tickers":         False,
                "market_data":     True,
                "community_data":  True,
                "developer_data":  False,
                "sparkline":       False,
            },
            headers=self.config.cg_headers,
            delay=CALL_DELAY_SEC,
        )

    # ── Signal builder ──────────────────────────────────────────────────────────

    def _build_social_signal(self, coin: dict, detail: Optional[dict]) -> dict:
        result = {
            "hype_score":      0.0,
            "trending_rank":   self._trending_ids.get(coin["id"]),
            "social_spike":    False,
            "spike_magnitude": 1.0,
            "sentiment_ratio": 0.5,
            "public_interest": 0.0,
            "alert":           "",
        }

        if not detail:
            return result

        # ── Community data ─────────────────────────────────────────────────────
        community = detail.get("community_data") or {}
        votes_up   = detail.get("sentiment_votes_up_percentage")   or 50.0
        votes_down = detail.get("sentiment_votes_down_percentage") or 50.0
        result["sentiment_ratio"] = votes_up / max(votes_up + votes_down, 1)

        # ── Public interest score (CoinGecko's own composite signal) ──────────
        pub_interest = detail.get("public_interest_score") or 0.0
        result["public_interest"] = pub_interest

        # ── Social spike proxy ─────────────────────────────────────────────────
        # CoinGecko free tier doesn't expose raw tweet counts over time, so
        # we proxy a "spike" using:
        #   - Whether the coin is on the trending list (strong signal)
        #   - Price momentum divergence (price barely moved but huge vol = pre-pump)
        #   - public_interest_score magnitude
        trending_rank = result["trending_rank"]
        spike_mag = 1.0

        if trending_rank:
            # Top trending rank 1–3 = strong social explosion signal
            spike_mag = max(spike_mag, (8 - trending_rank) / 2)

        # Price/volume divergence: big vol swing but small price move = accumulation
        chg_24h = abs(coin.get("chg_24h") or 0)
        vol = coin.get("volume_24h") or 0
        mcap = coin.get("mcap") or 1
        vol_ratio = vol / mcap
        if vol_ratio > 0.3 and chg_24h < 5:
            spike_mag = max(spike_mag, 2.5)   # stealth accumulation

        if pub_interest > 50:
            spike_mag = max(spike_mag, pub_interest / 20)

        result["spike_magnitude"] = round(spike_mag, 2)
        result["social_spike"]    = spike_mag >= self.config.social_spike_thresh

        # ── Composite hype score 0–1 ───────────────────────────────────────────
        hype = 0.0
        # Trending bonus (0–0.5)
        if trending_rank:
            hype += max(0, (10 - trending_rank) / 20)
        # Sentiment ratio contribution (0–0.2)
        hype += (result["sentiment_ratio"] - 0.5) * 0.4
        # Spike magnitude (0–0.3)
        hype += min(spike_mag / 10, 0.3)
        result["hype_score"] = round(min(max(hype, 0.0), 1.0), 4)

        # ── Alert message ──────────────────────────────────────────────────────
        alerts = []
        if trending_rank and trending_rank <= 3:
            alerts.append(f"TOP-{trending_rank} TRENDING")
        if result["social_spike"]:
            alerts.append(f"HYPE SPIKE x{spike_mag:.1f}")
        if result["sentiment_ratio"] > 0.75:
            alerts.append("BULLISH COMMUNITY")
        result["alert"] = " | ".join(alerts)

        return result

    # ── Stub: real X / Reddit / LunarCrush integration ────────────────────────

    @staticmethod
    def fetch_twitter_volume_stub(coin_symbol: str) -> dict:
        """
        STUB — replace with real X API v2 call.

        Real implementation:
            GET https://api.twitter.com/2/tweets/search/recent
                ?query=$SYMBOL OR #SYMBOL -is:retweet
                &start_time=<24h ago>
                &granularity=hour
            Headers: Authorization: Bearer <X_BEARER_TOKEN>

        Returns hourly tweet counts. Compare last 6h vs prior 18h average
        to detect a genuine 300%+ spike.
        """
        raise NotImplementedError("Wire in your X Bearer Token to activate.")

    @staticmethod
    def fetch_reddit_volume_stub(subreddit: str, coin_symbol: str) -> dict:
        """
        STUB — replace with Reddit API (PRAW) or Pushshift.

        Real implementation:
            import praw
            reddit = praw.Reddit(client_id=..., client_secret=..., user_agent=...)
            posts = list(reddit.subreddit('CryptoMoonShots+SatoshiStreetBets')
                           .search(coin_symbol, time_filter='day', limit=100))
            Return count vs 7-day rolling average.
        """
        raise NotImplementedError("Wire in PRAW credentials to activate.")
