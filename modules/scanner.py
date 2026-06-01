"""
modules/scanner.py
───────────────────
Low-Cap Scanner: fetches the micro-cap universe from CoinGecko.

Filters:
  • price  < $1
  • market cap  $5M – $50M
  • excludes stablecoins and wrapped tokens by category tag

Returns a list of dicts with standardised fields used downstream.
"""

import time
from typing import Optional

from utils.config import GemConfig, COINGECKO_BASE, COINGECKO_PAGE_SIZE, CALL_DELAY_SEC
from utils.http_client import build_session, safe_get

# Categories that are definitionally not "gems"
EXCLUDED_CATEGORIES = {
    "stablecoins", "wrapped-tokens", "bridged-tokens",
    "liquid-staking-tokens", "staking", "fan-token",
}

STABLECOIN_SYMBOLS = {"usdt","usdc","busd","dai","tusd","frax","lusd","usdd","gusd","usdp"}


class LowCapScanner:
    """
    Scans CoinGecko's /coins/markets for micro-cap coins matching the
    price and market-cap filters defined in GemConfig.
    """

    def __init__(self, config: GemConfig):
        self.config  = config
        self.session = build_session()

    def scan(self) -> list[dict]:
        """
        Fetch the broad universe then filter down to low-cap gems.
        Returns a list of normalised coin dicts.
        """
        print(f"\n[scanner] Fetching universe (top {self.config.scan_universe} by volume)...")
        raw = self._fetch_market_pages(self.config.scan_universe)
        print(f"[scanner] {len(raw)} coins fetched — applying filters...")
        gems = [self._normalise(c) for c in raw if self._passes_filter(c)]
        print(f"[scanner] {len(gems)} coins pass low-cap filter  "
              f"(price < ${self.config.max_price:.2f}, "
              f"mcap ${self.config.mcap_min/1e6:.0f}M–${self.config.mcap_max/1e6:.0f}M)")
        return gems

    # ── Internal ───────────────────────────────────────────────────────────────

    def _fetch_market_pages(self, limit: int) -> list[dict]:
        coins = []
        pages = (limit // COINGECKO_PAGE_SIZE) + 1
        for page in range(1, pages + 1):
            per_page = min(COINGECKO_PAGE_SIZE, limit - len(coins))
            data = safe_get(
                self.session,
                f"{COINGECKO_BASE}/coins/markets",
                params={
                    "vs_currency":            "usd",
                    "order":                  "volume_desc",   # sort by volume to catch activity
                    "per_page":               per_page,
                    "page":                   page,
                    "sparkline":              False,
                    "price_change_percentage":"24h,7d",
                },
                headers=self.config.cg_headers,
                delay=CALL_DELAY_SEC,
            )
            if data:
                coins.extend(data)
            if len(coins) >= limit:
                break
        return coins[:limit]

    def _passes_filter(self, c: dict) -> bool:
        price  = c.get("current_price") or 0
        mcap   = c.get("market_cap")    or 0
        symbol = (c.get("symbol") or "").lower()

        # Hard price / mcap gates
        if not (0 < price < self.config.max_price):
            return False
        if not (self.config.mcap_min <= mcap <= self.config.mcap_max):
            return False
        # Exclude stablecoins by symbol
        if symbol in STABLECOIN_SYMBOLS:
            return False
        return True

    def _normalise(self, c: dict) -> dict:
        return {
            "id":         c.get("id", ""),
            "symbol":     (c.get("symbol") or "").upper(),
            "name":       c.get("name", ""),
            "price":      c.get("current_price"),
            "mcap":       c.get("market_cap"),
            "mcap_rank":  c.get("market_cap_rank"),
            "volume_24h": c.get("total_volume"),
            "chg_24h":    c.get("price_change_percentage_24h"),
            "chg_7d":     c.get("price_change_percentage_7d_in_currency"),
            "ath":        c.get("ath"),
            "ath_pct":    c.get("ath_change_percentage"),
            "image":      c.get("image"),
            # Populated by downstream modules:
            "social":     {},
            "whale":      {},
            "scores":     {},
        }
