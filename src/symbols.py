"""Symbol universe + type-ahead search for the ticker box.

Provides a curated list of popular stocks/crypto (always available, even before
keys are set) and, when an Alpaca account is connected, merges in the full list
of tradable assets so the autocomplete covers everything.
"""

from __future__ import annotations

from typing import List, Tuple

Pair = Tuple[str, str]  # (symbol, name)

POPULAR_STOCKS: List[Pair] = [
    ("AAPL", "Apple Inc."), ("MSFT", "Microsoft"), ("NVDA", "NVIDIA"),
    ("TSLA", "Tesla"), ("AMZN", "Amazon"), ("GOOGL", "Alphabet"),
    ("META", "Meta Platforms"), ("NFLX", "Netflix"), ("AMD", "Adv. Micro Devices"),
    ("INTC", "Intel"), ("SPY", "S&P 500 ETF"), ("QQQ", "Nasdaq 100 ETF"),
    ("JPM", "JPMorgan Chase"), ("DIS", "Walt Disney"), ("BA", "Boeing"),
    ("KO", "Coca-Cola"), ("WMT", "Walmart"), ("XOM", "Exxon Mobil"),
    ("UBER", "Uber"), ("COIN", "Coinbase"), ("PLTR", "Palantir"),
]

POPULAR_CRYPTO: List[Pair] = [
    ("BTC/USD", "Bitcoin"), ("ETH/USD", "Ethereum"), ("SOL/USD", "Solana"),
    ("DOGE/USD", "Dogecoin"), ("AVAX/USD", "Avalanche"), ("LTC/USD", "Litecoin"),
    ("LINK/USD", "Chainlink"), ("UNI/USD", "Uniswap"), ("AAVE/USD", "Aave"),
    ("BCH/USD", "Bitcoin Cash"),
]


def load_full_universe(api_key: str, secret_key: str) -> List[Pair]:
    """Fetch all tradable equities + crypto pairs from Alpaca (best-effort)."""
    try:
        from alpaca.trading.client import TradingClient
        from alpaca.trading.enums import AssetClass, AssetStatus
        from alpaca.trading.requests import GetAssetsRequest
    except Exception:  # noqa: BLE001
        return []

    universe: List[Pair] = []
    try:
        client = TradingClient(api_key, secret_key, paper=True)
        for asset_class in (AssetClass.US_EQUITY, AssetClass.CRYPTO):
            assets = client.get_all_assets(
                GetAssetsRequest(status=AssetStatus.ACTIVE, asset_class=asset_class)
            )
            for a in assets:
                if getattr(a, "tradable", True):
                    universe.append((a.symbol, (a.name or "")[:40]))
    except Exception:  # noqa: BLE001 — no keys / offline → just use the curated list
        return []
    return universe


def build_index(full_universe: List[Pair] | None = None) -> List[Pair]:
    """Merge popular symbols (first, for ranking) with the full universe, de-duped."""
    seen = set()
    merged: List[Pair] = []
    for symbol, name in (*POPULAR_CRYPTO, *POPULAR_STOCKS, *(full_universe or [])):
        if symbol not in seen:
            seen.add(symbol)
            merged.append((symbol, name))
    return merged


def search(index: List[Pair], query: str, limit: int = 20) -> List[Pair]:
    """Rank matches: symbol-prefix first, then symbol-substring, then name match."""
    q = (query or "").upper().strip()
    if not q:
        return POPULAR_STOCKS[:6] + POPULAR_CRYPTO[:4]

    prefix, contains, by_name = [], [], []
    for symbol, name in index:
        su = symbol.upper()
        if su.startswith(q):
            prefix.append((symbol, name))
        elif q in su:
            contains.append((symbol, name))
        elif name and q in name.upper():
            by_name.append((symbol, name))
    return (prefix + contains + by_name)[:limit]
