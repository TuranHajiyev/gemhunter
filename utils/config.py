"""
utils/config.py  —  GemHunter configuration
All thresholds, weights, and API constants in one place.
"""
from dataclasses import dataclass
from typing import Optional


# ── Scanner filters ────────────────────────────────────────────────────────────
MAX_PRICE_USD          = 1.00
MCAP_MIN_USD           = 5_000_000
MCAP_MAX_USD           = 50_000_000
SCAN_UNIVERSE          = 500
COINGECKO_PAGE_SIZE    = 250

# ── Whale / volume thresholds ──────────────────────────────────────────────────
WHALE_VOL_MCAP_RATIO   = 0.50
VOL_SPIKE_MULTIPLIER   = 3.0
VOL_HISTORY_DAYS       = 30

# ── Social hype thresholds ─────────────────────────────────────────────────────
SOCIAL_SPIKE_THRESHOLD = 3.0
SENTIMENT_BULLISH_CUTOFF = 0.60

# ── Scoring weights (sum = 10) ─────────────────────────────────────────────────
SCORE_LOWCAP_MAX       = 3.0
SCORE_SOCIAL_MAX       = 4.0
SCORE_WHALE_MAX        = 3.0

# ── API ────────────────────────────────────────────────────────────────────────
COINGECKO_BASE         = "https://api.coingecko.com/api/v3"
CALL_DELAY_SEC         = 1.3

# ── Dashboard output ───────────────────────────────────────────────────────────
DASHBOARD_OUTPUT_PATH  = "gem_dashboard.png"
DASHBOARD_DPI          = 150


@dataclass
class GemConfig:
    max_price:           float = MAX_PRICE_USD
    mcap_min:            float = MCAP_MIN_USD
    mcap_max:            float = MCAP_MAX_USD
    scan_universe:       int   = SCAN_UNIVERSE
    whale_vol_ratio:     float = WHALE_VOL_MCAP_RATIO
    social_spike_thresh: float = SOCIAL_SPIKE_THRESHOLD
    vol_history_days:    int   = VOL_HISTORY_DAYS
    coingecko_api_key:   Optional[str] = None
    verbose:             bool  = False

    @property
    def cg_headers(self) -> dict:
        h = {"Accept": "application/json"}
        if self.coingecko_api_key:
            h["x-cg-pro-api-key"] = self.coingecko_api_key
        return h
