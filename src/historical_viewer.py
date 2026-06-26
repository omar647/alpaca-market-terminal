"""Standalone Historical Data Viewer (matplotlib).

Downloads >=30 days of intraday OHLCV bars for a symbol and renders a
candlestick + volume chart. Run it directly:

    python -m src.historical_viewer AAPL --days 30 --minutes 5
    python -m src.historical_viewer TSLA --save chart.png
"""

from __future__ import annotations

import argparse

import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import pandas as pd

from .config import load_settings
from .data_connector import AlpacaConnector


def plot_ohlcv(df: pd.DataFrame, symbol: str, minutes: int):
    """Render a candlestick price panel above a volume panel."""
    fig, (ax_price, ax_vol) = plt.subplots(
        2, 1, figsize=(14, 8), sharex=True,
        gridspec_kw={"height_ratios": [3, 1]},
    )

    times = mdates.date2num(pd.to_datetime(df["timestamp"]))
    # candle width = ~70% of one bar interval, in days
    width = (minutes / (24 * 60)) * 0.7

    for t, o, h, l, c in zip(times, df["open"], df["high"], df["low"], df["close"]):
        up = c >= o
        color = "#26a69a" if up else "#ef5350"
        ax_price.add_line(plt.Line2D((t, t), (l, h), color=color, linewidth=1))
        ax_price.add_patch(
            plt.Rectangle(
                (t - width / 2, min(o, c)),
                width,
                max(abs(c - o), 1e-9),
                facecolor=color,
                edgecolor=color,
            )
        )

    ax_price.set_title(f"{symbol} — {minutes}-minute OHLC")
    ax_price.set_ylabel("Price ($)")
    ax_price.grid(True, alpha=0.3)

    ax_vol.bar(times, df["volume"], width=width, color="#90a4ae")
    ax_vol.set_ylabel("Volume")
    ax_vol.set_xlabel("Time")
    ax_vol.grid(True, alpha=0.3)
    ax_vol.xaxis_date()
    fig.autofmt_xdate()
    fig.tight_layout()
    return fig


def main():
    parser = argparse.ArgumentParser(description="Alpaca historical OHLCV viewer")
    parser.add_argument("symbol", help="Ticker symbol, e.g. AAPL")
    parser.add_argument("--days", type=int, default=30, help="Look-back window (default 30)")
    parser.add_argument("--minutes", type=int, default=5, help="Bar size in minutes (1 or 5)")
    parser.add_argument("--save", default=None, help="Optional path to save a PNG")
    args = parser.parse_args()

    connector = AlpacaConnector(load_settings())
    df = connector.get_historical_bars(args.symbol, days=args.days, timeframe_minutes=args.minutes)
    if df.empty:
        print(f"No bars returned for {args.symbol}. Markets may be closed or symbol invalid.")
        return

    print(f"Downloaded {len(df)} bars for {args.symbol.upper()}.")
    print(df[["timestamp", "open", "high", "low", "close", "volume"]].tail())

    fig = plot_ohlcv(df, args.symbol.upper(), args.minutes)
    if args.save:
        fig.savefig(args.save, dpi=120, bbox_inches="tight")
        print(f"Saved chart to {args.save}")
    else:
        plt.show()


if __name__ == "__main__":
    main()
