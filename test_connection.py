"""Quick smoke test for your Alpaca setup.

Run:
    python test_connection.py            # default checks (AAPL + BTC/USD)
    python test_connection.py --symbol TSLA --live 10

Verifies: keys load, historical bars download, latest snapshot, and (optionally)
that live ticks arrive over the WebSocket stream.
"""

from __future__ import annotations

import argparse
import time

from src.config import load_settings
from src.data_connector import AlpacaConnector, LiveQuoteStore, is_crypto


def check(symbol: str, connector: AlpacaConnector) -> None:
    print(f"\n=== {symbol} ({'crypto' if is_crypto(symbol) else 'stock'}) ===")

    df = connector.get_historical_bars(symbol, days=5, timeframe_minutes=5)
    if df.empty:
        print("  historical: ⚠️  no bars (market closed or symbol invalid)")
    else:
        last = df.iloc[-1]
        print(f"  historical: ✅  {len(df)} bars · last close ${last['close']:,.2f} @ {last['timestamp']}")

    snap = connector.get_latest_snapshot(symbol)
    if snap.get("error"):
        print(f"  snapshot:   ⚠️  {snap['error'][:80]}")
    else:
        print(f"  snapshot:   ✅  bid ${snap.get('bid_price')} / ask ${snap.get('ask_price')} / last ${snap.get('last_price')}")


def live_test(symbol: str, connector: AlpacaConnector, seconds: int) -> None:
    print(f"\n=== live stream {symbol} for {seconds}s ===")
    store = LiveQuoteStore()
    connector.start_stream(symbol, store)
    ticks = 0
    try:
        for _ in range(seconds):
            time.sleep(1)
            s = store.snapshot()
            if s.get("bid_price") is not None or s.get("last_price") is not None:
                ticks += 1
                print(f"  tick: bid {s.get('bid_price')} ask {s.get('ask_price')} last {s.get('last_price')}")
            if s.get("error"):
                print(f"  stream error: {s['error'][:80]}")
                break
    finally:
        connector.stop_stream()
    print(f"  live: {'✅ ' + str(ticks) + ' updates' if ticks else '⚠️  no ticks (market may be closed — try BTC/USD)'}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbol", default=None, help="Extra symbol to test")
    ap.add_argument("--live", type=int, default=0, help="Seconds to stream live (0 = skip)")
    args = ap.parse_args()

    try:
        settings = load_settings()
    except Exception as exc:  # noqa: BLE001
        print(f"❌ {exc}")
        return
    print(f"✅ Keys loaded · feed = {settings.data_feed} · key ends …{settings.api_key[-4:]}")

    connector = AlpacaConnector(settings)
    symbols = [args.symbol] if args.symbol else ["AAPL", "BTC/USD"]
    for sym in symbols:
        check(sym, connector)

    if args.live:
        live_test(symbols[-1], connector, args.live)

    print("\nDone. If the checks above are ✅, run:  streamlit run app.py")


if __name__ == "__main__":
    main()
