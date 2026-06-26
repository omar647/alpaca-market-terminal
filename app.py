"""Mini Market Data Terminal — Streamlit UI.

Run with:
    streamlit run app.py

A trading-desk style market terminal on Alpaca's data API:
  * Type-ahead ticker search (stocks + crypto) via streamlit-searchbox.
  * Live tab: bid/ask/last/spread read-out with price-tick flashes, a session-range
    bar, tick-latency, and a real-time streaming price chart (seeded intraday,
    extended tick-by-tick).
  * Historical tab: OHLCV candlestick + volume (Plotly).
  * Dark / Light themes; dark control rail in both.
"""

from __future__ import annotations

from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

from src import symbols as sym
from src.config import load_settings
from src.data_connector import AlpacaConnector, LiveQuoteStore, is_crypto

try:
    from streamlit_searchbox import st_searchbox
    HAS_SEARCHBOX = True
except Exception:  # noqa: BLE001
    HAS_SEARCHBOX = False

st.set_page_config(
    page_title="Market Terminal", page_icon="◧", layout="wide",
    initial_sidebar_state="auto",
)

# --------------------------------------------------------------------------- #
# Theme system  (the control rail stays dark in both; only the canvas flips)
# --------------------------------------------------------------------------- #
THEMES = {
    "Dark": dict(
        app_bg="#0a0d12", panel="#0e1219", panel2="#11161f", raised="#161c27",
        line="rgba(255,255,255,.07)", line2="rgba(255,255,255,.13)",
        ink="#eef1f6", ink2="#a2adbf", ink3="#717c92",
        mint="#00e5a0", mint_text="#00e5a0", mint_soft="rgba(0,229,160,.12)", on_mint="#04130d",
        up="#2bd07c", down="#ff5d6c", amber="#ffb454",
        up_soft="rgba(43,208,124,.22)", down_soft="rgba(255,93,108,.20)",
        c_grid="rgba(255,255,255,.05)", c_axis="rgba(255,255,255,.09)", c_font="#a2adbf",
        c_hbg="#11161f", c_hbd="rgba(255,255,255,.14)", c_htx="#eef1f6",
        c_edge="#0a0d12", c_band="rgba(0,229,160,.12)", c_line="#00e5a0",
        c_hline="rgba(0,229,160,.5)", c_up="#2bd07c", c_down="#ff5d6c",
        c_volup="rgba(43,208,124,.5)", c_voldn="rgba(255,93,108,.45)", c_spike="rgba(255,255,255,.22)",
        sb_ctrl="#11161f", sb_border="#262d3a", sb_menu="#11161f", sb_hi="#1b2230",
    ),
    "Light": dict(
        app_bg="#eceef2", panel="#ffffff", panel2="#f6f7f9", raised="#ffffff",
        line="rgba(16,22,38,.10)", line2="rgba(16,22,38,.17)",
        ink="#0f1620", ink2="#46505f", ink3="#5e6878",
        mint="#06b083", mint_text="#067a5a", mint_soft="rgba(6,176,131,.12)", on_mint="#ffffff",
        up="#0c9a55", down="#d3243c", amber="#b67400",
        up_soft="rgba(12,154,85,.16)", down_soft="rgba(211,36,60,.14)",
        c_grid="rgba(16,22,38,.07)", c_axis="rgba(16,22,38,.16)", c_font="#46505f",
        c_hbg="#ffffff", c_hbd="rgba(16,22,38,.16)", c_htx="#0f1620",
        c_edge="#ffffff", c_band="rgba(6,176,131,.14)", c_line="#06b083",
        c_hline="rgba(6,176,131,.55)", c_up="#0c9a55", c_down="#d3243c",
        c_volup="rgba(12,154,85,.45)", c_voldn="rgba(211,36,60,.4)", c_spike="rgba(16,22,38,.28)",
        sb_ctrl="#ffffff", sb_border="#d6dae2", sb_menu="#ffffff", sb_hi="#eef1f5",
    ),
}

if "theme" not in st.session_state:
    st.session_state["theme"] = "Dark"
theme_name = st.session_state.get("theme") or "Dark"
T = THEMES.get(theme_name, THEMES["Dark"])


def render_css(t: dict) -> str:
    root = f""":root{{
      --app-bg:{t['app_bg']}; --panel:{t['panel']}; --panel-2:{t['panel2']}; --raised:{t['raised']};
      --line:{t['line']}; --line-2:{t['line2']};
      --ink:{t['ink']}; --ink-2:{t['ink2']}; --ink-3:{t['ink3']};
      --mint:{t['mint']}; --mint-text:{t['mint_text']}; --mint-soft:{t['mint_soft']}; --on-mint:{t['on_mint']};
      --up:{t['up']}; --down:{t['down']}; --amber:{t['amber']};
      --up-soft:{t['up_soft']}; --down-soft:{t['down_soft']};
      --r:10px; --r-sm:7px;
    }}"""
    return "<style>\n" + IMPORTS + "\n" + root + "\n" + SIDEBAR_CSS + "\n" + BASE_CSS + "\n</style>"


IMPORTS = ("@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800"
           "&family=JetBrains+Mono:wght@400;500;600;700&display=swap');")

# Sidebar follows the active theme. Native baseweb widgets (slider, select,
# segmented control) are dark-based by default, so they're re-coloured here via
# the themed CSS variables to read correctly in both themes.
SIDEBAR_CSS = """
section[data-testid="stSidebar"]{ background:var(--panel); border-right:1px solid var(--line); color:var(--ink); }
section[data-testid="stSidebar"] .block-container{ padding-top:1.4rem; }
section[data-testid="stSidebar"] hr{ border-color:var(--line); }

/* segmented control (theme toggle) */
[data-testid="stSidebar"] [data-testid="stBaseButton-segmented_control"]{ background:var(--panel-2) !important;
  color:var(--ink-2) !important; border:1px solid var(--line-2) !important; }
[data-testid="stSidebar"] [data-testid="stBaseButton-segmented_controlActive"]{ background:var(--mint) !important;
  color:var(--on-mint) !important; border:1px solid transparent !important; }

/* slider */
[data-testid="stSidebar"] [data-baseweb="slider"] [role="slider"]{ background:var(--mint) !important; }
[data-testid="stSidebar"] [data-testid="stTickBar"]{ color:var(--ink-3); }
[data-testid="stSidebar"] [data-testid="stTickBarMin"],
[data-testid="stSidebar"] [data-testid="stTickBarMax"]{ color:var(--ink-3) !important; }

/* select (bar size) */
[data-testid="stSidebar"] [data-baseweb="select"] > div{ background:var(--panel-2) !important;
  border-color:var(--line-2) !important; }
[data-testid="stSidebar"] [data-baseweb="select"] *{ color:var(--ink) !important; }
[data-testid="stSidebar"] label p{ color:var(--ink-2) !important; }

/* select dropdown menu (rendered in a body-level popover → uses the active root theme) */
[data-baseweb="popover"] [role="listbox"], [data-baseweb="menu"] ul{ background:var(--panel-2) !important;
  border:1px solid var(--line-2) !important; }
[data-baseweb="popover"] [role="option"]{ color:var(--ink) !important; }
[data-baseweb="popover"] [role="option"]:hover, [data-baseweb="popover"] [role="option"][aria-selected="true"]{
  background:var(--raised) !important; }
"""

BASE_CSS = """
html,body,[class*="css"]{ font-family:'Inter',sans-serif; }
.stApp,[data-testid="stAppViewContainer"]{ background:var(--app-bg); color:var(--ink); }
/* hide the toolbar's noise (menu / deploy / status) but NOT the toolbar itself —
   it hosts the collapsed-sidebar reopen control */
#MainMenu, footer, [data-testid="stDecoration"], [data-testid="stToolbarActions"],
[data-testid="stStatusWidget"], [data-testid="stAppDeployButton"]{ display:none; }
/* keep the header transparent + click-through so it never overlaps the chrome,
   re-enabling pointer events only on the sidebar reopen control */
header[data-testid="stHeader"]{ background:transparent !important; box-shadow:none !important; pointer-events:none; }
[data-testid="stExpandSidebarButton"], [data-testid="stExpandSidebarButton"] *,
[data-testid="stSidebarCollapsedControl"], [data-testid="stSidebarCollapsedControl"] *{ pointer-events:auto; }
[data-testid="stExpandSidebarButton"] button, [data-testid="stSidebarCollapsedControl"] button{ color:var(--ink) !important; }
.block-container{ padding-top:1.2rem; padding-bottom:2.4rem; max-width:1340px; }
::selection{ background:rgba(0,229,160,.28); }
[data-testid="stCaptionContainer"]{ color:var(--ink-3) !important; }
.mono{ font-family:'JetBrains Mono',monospace; font-variant-numeric:tabular-nums; }

/* ---------- top bar ---------- */
.topbar{ display:flex; align-items:center; justify-content:space-between;
  padding:12px 16px; margin-bottom:18px; background:var(--panel);
  border:1px solid var(--line); border-radius:var(--r); }
.brand{ display:flex; align-items:center; gap:10px; }
.brand svg{ display:block; }
.brand .wm{ font:700 14.5px/1 'JetBrains Mono',monospace; letter-spacing:.22em; color:var(--ink); }
.brand .wm b{ color:var(--mint-text); font-weight:700; }
.topbar-meta{ display:flex; align-items:center; gap:8px; }
.tag{ font:600 11px/1 'JetBrains Mono',monospace; letter-spacing:.06em; color:var(--ink-2);
  padding:6px 10px; border:1px solid var(--line); border-radius:6px; }
.conn{ display:inline-flex; align-items:center; gap:7px; font:600 12px/1 'Inter';
  padding:6px 11px; border-radius:6px; border:1px solid var(--line); }
.conn.ok{ color:var(--up); background:var(--up-soft); border-color:transparent; }
.conn.err{ color:var(--down); background:var(--down-soft); border-color:transparent; }
.conn i{ width:7px; height:7px; border-radius:50%; background:currentColor; }

/* ---------- instrument panel (price header + quotes + range, one unit) ---------- */
.inst{ background:var(--panel); border:1px solid var(--line); border-radius:var(--r);
  overflow:hidden; margin-bottom:16px; }
.inst-top{ display:flex; align-items:flex-end; justify-content:space-between; gap:16px;
  flex-wrap:wrap; padding:16px 18px 15px; }
.px-id{ display:flex; align-items:center; gap:10px; flex-wrap:wrap; }
.px-sym{ font:800 26px/1 'Inter'; letter-spacing:-.02em; color:var(--ink); }
.px-chip{ font:600 10px/1 'JetBrains Mono',monospace; letter-spacing:.08em;
  padding:5px 8px; border-radius:5px; color:var(--ink-2); border:1px solid var(--line); }
.px-chip.crypto{ color:var(--amber); border-color:color-mix(in srgb,var(--amber) 35%, transparent); }
.mkt{ display:inline-flex; align-items:center; gap:6px; font:600 10px/1 'JetBrains Mono',monospace;
  letter-spacing:.05em; padding:5px 8px; border-radius:5px; border:1px solid var(--line); }
.mkt i{ width:6px; height:6px; border-radius:50%; background:currentColor; }
.mkt.open{ color:var(--up); background:var(--up-soft); border-color:transparent; }
.mkt.closed{ color:var(--ink-2); }
.px-main{ display:flex; align-items:baseline; gap:14px; }
.px-now{ font:700 40px/1 'JetBrains Mono',monospace; font-variant-numeric:tabular-nums;
  color:var(--ink); letter-spacing:-.015em; }
.px-chg{ font:600 15px/1 'JetBrains Mono',monospace; font-variant-numeric:tabular-nums; }
.px-chg.up{ color:var(--up); }  .px-chg.down{ color:var(--down); }  .px-chg.flat{ color:var(--ink-3); }

/* ---------- quote read-out strip (nested in .inst) ---------- */
.quotes{ display:grid; grid-template-columns:repeat(4,1fr);
  border-top:1px solid var(--line); }
.q{ padding:14px 16px; }
.q + .q{ border-left:1px solid var(--line); }
.q-l{ font:600 10px/1 'Inter'; letter-spacing:.16em; text-transform:uppercase; color:var(--ink-3); }
.q-v{ font:700 24px/1 'JetBrains Mono',monospace; font-variant-numeric:tabular-nums;
  color:var(--ink); margin-top:9px; }
.q-v.up{ color:var(--up); }  .q-v.down{ color:var(--down); }  .q-v.mint{ color:var(--mint-text); }  .q-v.amber{ color:var(--amber); }
.q-s{ font:500 11px/1 'JetBrains Mono',monospace; color:var(--ink-3); margin-top:8px; }

/* price-tick flash — a real tape highlight, not decoration */
@keyframes flU{ 0%{background:var(--up-soft)} 100%{background:transparent} }
@keyframes flD{ 0%{background:var(--down-soft)} 100%{background:transparent} }
.q.up-fl{ animation:flU .85s ease-out; }
.q.dn-fl{ animation:flD .85s ease-out; }
@keyframes txU{ 0%{color:var(--up)} 100%{color:var(--ink)} }
@keyframes txD{ 0%{color:var(--down)} 100%{color:var(--ink)} }
.px-now.up-fl{ animation:txU .85s ease-out; }
.px-now.dn-fl{ animation:txD .85s ease-out; }

/* ---------- session range bar (nested in .inst) ---------- */
.range{ display:flex; align-items:center; gap:11px; padding:13px 18px; margin:0;
  border-top:1px solid var(--line); font:600 11px/1 'JetBrains Mono',monospace; color:var(--ink-2); }
.range .cap{ font:600 9.5px/1 'Inter'; letter-spacing:.16em; text-transform:uppercase; color:var(--ink-3); }
.r-track{ position:relative; flex:1; height:4px; border-radius:999px; background:var(--line-2); }
.r-fill{ position:absolute; inset:0 auto 0 0; border-radius:999px; background:var(--mint-soft); }
.r-dot{ position:absolute; top:50%; width:11px; height:11px; border-radius:50%;
  background:var(--mint); border:2px solid var(--app-bg); transform:translate(-50%,-50%); }

/* ---------- chart panel ---------- */
[data-testid="stVerticalBlockBorderWrapper"]{ border:1px solid var(--line) !important;
  border-radius:var(--r) !important; background:var(--panel); }
[data-testid="stVerticalBlockBorderWrapper"] .empty{ border:0; min-height:320px; }
.chart-bar{ display:flex; align-items:center; justify-content:space-between; padding:2px 4px 10px; }
.pill{ display:inline-flex; align-items:center; gap:8px; font:600 12px/1 'Inter';
  padding:6px 11px; border-radius:6px; border:1px solid var(--line); }
.pill.live{ color:var(--up); background:var(--up-soft); border-color:transparent; }
.pill.idle{ color:var(--ink-3); }
.dot{ width:8px; height:8px; border-radius:50%; background:var(--up);
  box-shadow:0 0 0 0 var(--up-soft); animation:pulse 1.6s infinite; }
.pill.idle .dot{ background:var(--ink-3); animation:none; box-shadow:none; }
@keyframes pulse{ 0%{box-shadow:0 0 0 0 var(--up-soft)} 70%{box-shadow:0 0 0 8px transparent} 100%{box-shadow:0 0 0 0 transparent} }
.meta-r{ display:flex; align-items:center; gap:14px; }
.clock{ font:600 12px/1 'JetBrains Mono',monospace; color:var(--ink-3); letter-spacing:.04em; }
.lat{ font:600 11px/1 'JetBrains Mono',monospace; color:var(--ink-3); letter-spacing:.03em; }
.lat b{ color:var(--up); font-weight:700; }  .lat.stale b{ color:var(--amber); }

/* ---------- empty / gate states ---------- */
.empty{ display:flex; flex-direction:column; align-items:center; justify-content:center;
  text-align:center; gap:10px; min-height:300px; border:1px dashed var(--line-2);
  border-radius:var(--r); }
.empty .i{ color:var(--ink-3); opacity:.75; }
.empty .big{ font:700 16px/1.3 'Inter'; color:var(--ink); }
.empty .small{ font:500 13px/1.55 'Inter'; color:var(--ink-3); max-width:44ch; }

/* ---------- streamlit widget refinements ---------- */
.side-h{ font:700 11px/1 'Inter'; letter-spacing:.16em; text-transform:uppercase;
  color:var(--ink-3); margin:2px 0 10px; }
.stButton>button{ border-radius:var(--r-sm); font-weight:600; font-size:13.5px;
  border:1px solid var(--line-2); background:var(--panel-2); color:var(--ink);
  transition:border-color .15s ease, background .15s ease, transform .08s ease; }
.stButton>button:hover{ border-color:color-mix(in srgb,var(--mint) 45%, transparent); background:var(--raised); }
.stButton>button:active{ transform:translateY(1px); }
.stButton>button[kind="primary"]{ background:var(--mint); color:var(--on-mint); border-color:transparent; }
.stButton>button[kind="primary"]:hover{ filter:brightness(1.07); border-color:transparent; }

div[data-testid="stMetric"]{ background:var(--panel); border:1px solid var(--line);
  border-radius:var(--r-sm); padding:13px 15px; }
div[data-testid="stMetricLabel"] p{ font-size:11px !important; letter-spacing:.12em;
  text-transform:uppercase; color:var(--ink-3) !important; }
div[data-testid="stMetricValue"]{ font-family:'JetBrains Mono',monospace !important;
  font-variant-numeric:tabular-nums; font-size:22px !important; color:var(--ink) !important; }

.stTabs [data-baseweb="tab-list"]{ gap:2px; border-bottom:1px solid var(--line); }
.stTabs [data-baseweb="tab"]{ background:transparent; color:var(--ink-3); font-weight:600;
  font-size:13.5px; padding:9px 16px; }
.stTabs [data-baseweb="tab"][aria-selected="true"]{ color:var(--ink); }
.stTabs [data-baseweb="tab-highlight"]{ background:var(--mint); height:2px; }
[data-testid="stExpander"] details{ border:1px solid var(--line); border-radius:var(--r-sm); background:var(--panel); }

@media (prefers-reduced-motion: reduce){
  .dot{ animation:none !important; box-shadow:none; }
  .q.up-fl,.q.dn-fl,.px-now.up-fl,.px-now.dn-fl{ animation:none !important; }
  .stButton>button:active{ transform:none; }
}
@media (max-width:760px){
  .quotes{ grid-template-columns:repeat(2,1fr); }
  .q:nth-child(3){ border-left:0; }
  .q:nth-child(3),.q:nth-child(4){ border-top:1px solid var(--line); }
  .px-main{ margin-left:0; }
  .px-now{ font-size:30px; }
  .topbar-meta .tag{ display:none; }
}
"""

st.markdown(render_css(T), unsafe_allow_html=True)


def logo_svg(t: dict) -> str:
    return (
        '<svg width="22" height="22" viewBox="0 0 24 24" fill="none">'
        f'<rect x="3.5" y="9" width="4" height="8" rx="1" fill="{t["mint"]}"/>'
        f'<rect x="5" y="4.5" width="1" height="4.5" fill="{t["mint"]}"/>'
        f'<rect x="5" y="17" width="1" height="3" fill="{t["mint"]}"/>'
        f'<rect x="10" y="7" width="4" height="6" rx="1" fill="{t["up"]}"/>'
        f'<rect x="11.5" y="3" width="1" height="4" fill="{t["up"]}"/>'
        f'<rect x="11.5" y="13" width="1" height="3.5" fill="{t["up"]}"/>'
        f'<rect x="16.5" y="11" width="4" height="7" rx="1" fill="{t["down"]}"/>'
        f'<rect x="18" y="7" width="1" height="4" fill="{t["down"]}"/>'
        f'<rect x="18" y="18" width="1" height="2.5" fill="{t["down"]}"/>'
        '</svg>'
    )


def icon(paths: str, size: int = 32) -> str:
    return (f'<svg class="i" width="{size}" height="{size}" viewBox="0 0 24 24" fill="none" '
            f'stroke="currentColor" stroke-width="1.5" stroke-linecap="round" '
            f'stroke-linejoin="round">{paths}</svg>')


I_CHART = icon('<path d="M3 17l5-5 3 3 7-7"/><path d="M14 8h4v4"/>')
I_BARS = icon('<path d="M4 20V10"/><path d="M10 20V4"/><path d="M16 20v-7"/><path d="M21 20H3"/>')
I_NONE = icon('<circle cx="12" cy="12" r="8"/><path d="M7.5 16.5L16.5 7.5"/>')
I_KEY = icon('<circle cx="9" cy="9" r="3.6"/><path d="M11.6 11.6L20 20"/><path d="M16.5 16.5l2-2"/>')


def searchbox_style(t: dict) -> dict:
    """Theme the (iframe) searchbox so it flips with Dark / Light."""
    return {
        "wrapper": {"borderRadius": "7px"},
        "searchbox": {
            "control": {"backgroundColor": t["sb_ctrl"], "border": f"1px solid {t['sb_border']}",
                        "borderRadius": "7px"},
            "input": {"color": t["ink"]},
            "singleValue": {"color": t["ink"], "fontWeight": "600"},
            "placeholder": {"color": t["ink2"], "fontWeight": "600"},
            "menuList": {"backgroundColor": t["sb_menu"], "border": f"1px solid {t['sb_border']}",
                         "borderRadius": "8px"},
            "option": {"color": t["ink"], "backgroundColor": t["sb_menu"], "highlightColor": t["sb_hi"]},
        },
        "dropdown": {"fill": t["ink3"]},
        "clear": {"fill": t["ink3"], "stroke": t["ink3"]},
    }


# --------------------------------------------------------------------------- #
# Formatting helpers
# --------------------------------------------------------------------------- #
def _dp(v) -> int:
    """Decimal places: 2 for normal prices, 6 for sub-$1 (small-cap crypto)."""
    if v is None:
        return 2
    return 2 if abs(v) >= 1 else 6


def fmt_price(v) -> str:
    return "—" if v is None else f"${v:,.{_dp(v)}f}"


def fmt_size(v) -> str:
    return "" if v is None else f"×{v:,.4g}"


# --------------------------------------------------------------------------- #
# Plotly theming
# --------------------------------------------------------------------------- #
def style_fig(fig: go.Figure, height: int, t: dict) -> go.Figure:
    fig.update_layout(
        height=height, margin=dict(l=8, r=60, t=10, b=8),
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        font=dict(family="Inter, sans-serif", size=12, color=t["c_font"]),
        hoverlabel=dict(bgcolor=t["c_hbg"], bordercolor=t["c_hbd"],
                        font=dict(family="JetBrains Mono, monospace", size=12, color=t["c_htx"])),
        showlegend=False, hovermode="x unified", dragmode="pan",
    )
    fig.update_xaxes(showgrid=True, gridcolor=t["c_grid"], zeroline=False, linecolor=t["c_axis"],
                     showspikes=True, spikemode="across", spikethickness=1,
                     spikecolor=t["c_spike"], spikedash="dot")
    fig.update_yaxes(side="right", showgrid=True, gridcolor=t["c_grid"], zeroline=False,
                     linecolor=t["c_axis"])
    return fig


def build_live_chart(history: list, snap: dict, t: dict) -> go.Figure:
    df = pd.DataFrame(history)
    fig = go.Figure()

    # bid/ask band — only where live quotes exist (seeded bars have None)
    if not df.empty and {"bid", "ask"}.issubset(df.columns):
        band = df.dropna(subset=["bid", "ask"])
        if len(band) >= 2:
            fig.add_trace(go.Scatter(x=band["ts"], y=band["ask"], mode="lines",
                                     line=dict(width=0), hoverinfo="skip"))
            fig.add_trace(go.Scatter(x=band["ts"], y=band["bid"], mode="lines", line=dict(width=0),
                                     fill="tonexty", fillcolor=t["c_band"], hoverinfo="skip"))

    if not df.empty:
        ref = df["mid"].iloc[-1]
        fig.add_trace(go.Scatter(
            x=df["ts"], y=df["mid"], mode="lines", name="Price",
            line=dict(color=t["c_line"], width=2, shape="spline", smoothing=0.4),
            hovertemplate=f"%{{y:$,.{_dp(ref)}f}}<extra></extra>"))

    last, tt = snap.get("last_price"), snap.get("trade_time")
    if last is not None and tt is not None:
        fig.add_trace(go.Scatter(
            x=[tt], y=[last], mode="markers",
            marker=dict(size=10, color=t["c_line"], line=dict(width=2.5, color=t["c_edge"])),
            hovertemplate=f"last %{{y:$,.{_dp(last)}f}}<extra></extra>"))
    cur = last if last is not None else (df["mid"].iloc[-1] if not df.empty else None)
    if cur is not None:
        fig.add_hline(y=cur, line_dash="dot", line_width=1, line_color=t["c_hline"])
        fig.update_yaxes(tickprefix="$", tickformat=f",.{_dp(cur)}f")

    style_fig(fig, 360, t)
    return fig


# --------------------------------------------------------------------------- #
# Session state
# --------------------------------------------------------------------------- #
if "store" not in st.session_state:
    st.session_state.store = LiveQuoteStore()
if "connector" not in st.session_state:
    try:
        st.session_state.connector = AlpacaConnector(load_settings())
        st.session_state.conn_error = None
    except Exception as exc:  # noqa: BLE001
        st.session_state.connector = None
        st.session_state.conn_error = str(exc)
if "streaming_symbol" not in st.session_state:
    st.session_state.streaming_symbol = None
if "symbol" not in st.session_state:
    # Deep-linkable: /?sym=BTC%2FUSD loads straight into that instrument.
    st.session_state.symbol = (st.query_params.get("sym") or "AAPL").upper().strip()

connector: AlpacaConnector | None = st.session_state.connector
store: LiveQuoteStore = st.session_state.store


@st.cache_data(ttl=3600, show_spinner=False)
def get_index(have_keys: bool, api_key: str, secret_key: str):
    full = sym.load_full_universe(api_key, secret_key) if have_keys else []
    return sym.build_index(full)


INDEX = get_index(
    connector is not None,
    connector.settings.api_key if connector else "",
    connector.settings.secret_key if connector else "",
)


def search_symbols(query: str):
    return [(f"{s}   ·   {n}" if n else s, s) for s, n in sym.search(INDEX, query)]


ET = ZoneInfo("America/New_York")


@st.cache_data(ttl=60, show_spinner=False)
def get_market_status(api_key: str, secret_key: str):
    """US-equity market clock (is_open + next_open). Cached ~1 min; crypto is 24/7."""
    try:
        from alpaca.trading.client import TradingClient
        clk = TradingClient(api_key, secret_key, paper=True).get_clock()
        return {"is_open": bool(clk.is_open), "next_open": clk.next_open}
    except Exception:  # noqa: BLE001 — clock is a nice-to-have, never fatal
        return None


def market_badge(symbol: str) -> str:
    """HTML badge: crypto → 24/7, equity → OPEN / CLOSED · opens <time ET>."""
    if is_crypto(symbol):
        return '<span class="mkt open"><i></i>OPEN 24/7</span>'
    status = get_market_status(connector.settings.api_key, connector.settings.secret_key)
    if status is None:
        return ""
    if status["is_open"]:
        return '<span class="mkt open"><i></i>MARKET OPEN</span>'
    nxt = status.get("next_open")
    opens = f" · opens {nxt.astimezone(ET).strftime('%a %H:%M ET')}" if nxt else ""
    return f'<span class="mkt closed"><i></i>MARKET CLOSED{opens}</span>'


# --------------------------------------------------------------------------- #
# Top bar
# --------------------------------------------------------------------------- #
feed_txt = connector.settings.data_feed.upper() if connector else "—"
conn_html = ('<span class="conn ok"><i></i>connected</span>' if connector
             else '<span class="conn err"><i></i>offline</span>')
st.markdown(
    f"""
    <div class="topbar">
      <div class="brand">{logo_svg(T)}<span class="wm">MARKET&nbsp;<b>TERMINAL</b></span></div>
      <div class="topbar-meta">
        <span class="tag">ALPACA</span>
        <span class="tag">FEED&nbsp;{feed_txt}</span>
        {conn_html}
      </div>
    </div>
    """,
    unsafe_allow_html=True,
)

# --------------------------------------------------------------------------- #
# Sidebar — theme, ticker search, settings
# --------------------------------------------------------------------------- #
st.sidebar.markdown('<div class="side-h">Appearance</div>', unsafe_allow_html=True)
st.sidebar.segmented_control(
    "Theme", ["Dark", "Light"], key="theme",
    selection_mode="single", label_visibility="collapsed",
)

st.sidebar.divider()
st.sidebar.markdown('<div class="side-h">Instrument</div>', unsafe_allow_html=True)
if HAS_SEARCHBOX:
    _cur_sym = st.session_state.symbol
    # st_searchbox can't render a pre-selected chip, so surface the active symbol
    # as the (value-styled) placeholder; it updates whenever the symbol changes.
    picked = st_searchbox(
        search_symbols, placeholder=f"{_cur_sym}    ·    type to search",
        key="ticker_search", default=_cur_sym,
        style_overrides=searchbox_style(T), rerun_on_update=True,
    )
    if picked:
        st.session_state.symbol = picked.upper().strip()
else:
    st.session_state.symbol = st.sidebar.text_input(
        "Ticker", value=st.session_state.symbol, label_visibility="collapsed"
    ).upper().strip()

symbol = st.session_state.symbol
if symbol:
    st.query_params["sym"] = symbol  # keep the URL shareable / in sync
asset_line = ("Crypto · trades live 24/7" if is_crypto(symbol)
              else "Equity · live in market hours")
st.sidebar.markdown(
    f'<div style="font:600 13px/1.4 Inter;color:var(--ink);margin-top:6px">'
    f'<span class="mono" style="color:var(--mint)">{symbol}</span>'
    f'<div style="font:500 12px/1.4 Inter;color:var(--ink-3);margin-top:3px">{asset_line}</div></div>',
    unsafe_allow_html=True,
)

st.sidebar.divider()
st.sidebar.markdown('<div class="side-h">History range</div>', unsafe_allow_html=True)
days = st.sidebar.slider("Look-back (days)", 5, 60, 30)
minutes = st.sidebar.selectbox("Bar size (minutes)", [1, 5], index=1)

st.sidebar.divider()
if connector is None:
    st.sidebar.markdown('<span class="conn err"><i></i>not connected</span>', unsafe_allow_html=True)
else:
    st.sidebar.markdown(
        f'<span class="conn ok"><i></i>connected · {connector.settings.data_feed}</span>',
        unsafe_allow_html=True)

# Setup gate
if connector is None:
    st.markdown(
        f"""
        <div class="empty">
          {I_KEY}
          <div class="big">Alpaca API keys not configured</div>
          <div class="small">Copy <code>.env.example</code> to <code>.env</code>, paste your
          <b>paper-trading</b> keys, then restart. Free accounts use the <code>iex</code> feed.</div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.caption(f"Details: {st.session_state.conn_error}")
    st.stop()


# --------------------------------------------------------------------------- #
# Tabs
# --------------------------------------------------------------------------- #
tab_live, tab_hist = st.tabs(["  Live  ", "  Historical  "])

# ------------------------------ Live --------------------------------------- #
with tab_live:
    c1, c2, _ = st.columns([1.1, 1, 3])
    if c1.button("▶  Start streaming", type="primary", use_container_width=True):
        try:
            connector.start_stream(symbol, store)
            st.session_state.streaming_symbol = symbol
            st.session_state.pop("prev_q", None)
            try:  # seed the chart with recent intraday bars so it's never empty
                store.seed_history(connector.get_intraday_bars(symbol))
            except Exception:  # noqa: BLE001 — chart still works from live ticks
                pass
            snap = connector.get_latest_snapshot(symbol)
            if snap.get("bid_price") is not None:
                store.update_quote(snap.get("bid_price"), snap.get("ask_price"),
                                   snap.get("bid_size"), snap.get("ask_size"), snap.get("quote_time"))
            if snap.get("last_price") is not None:
                store.update_trade(snap.get("last_price"), snap.get("last_size"), snap.get("trade_time"))
        except Exception as exc:  # noqa: BLE001
            st.error(f"Could not start stream: {exc}")
    if c2.button("◼  Stop", use_container_width=True):
        connector.stop_stream()
        st.session_state.streaming_symbol = None

    @st.fragment(run_every="1s")
    def live_panel():
        snap = store.snapshot()
        history = store.price_history()
        streaming = st.session_state.streaming_symbol

        bid, ask = snap.get("bid_price"), snap.get("ask_price")
        last, spread = snap.get("last_price"), snap.get("spread")
        qt, tt = snap.get("quote_time"), snap.get("trade_time")
        mid_now = (bid + ask) / 2 if bid is not None and ask is not None else None

        mids = [h["mid"] for h in history if h.get("mid") is not None]
        if mid_now is not None and (tt is None or (qt is not None and qt >= tt)):
            cur = mid_now           # live quote at least as fresh as last trade
        elif last is not None:
            cur = last
        else:
            cur = mids[-1] if mids else None
        open_p = mids[0] if mids else None

        # price-tick flash: compare to previous tick
        prev = st.session_state.get("prev_q", {})

        def flash(key, val):
            p = prev.get(key)
            if val is None or p is None or val == p:
                return ""
            return "up-fl" if val > p else "dn-fl"

        bid_fl, ask_fl, last_fl, cur_fl = (flash("bid", bid), flash("ask", ask),
                                           flash("last", last), flash("cur", cur))
        st.session_state["prev_q"] = {"bid": bid, "ask": ask, "last": last, "cur": cur}

        # ---- header values ----
        chip = "crypto" if is_crypto(symbol) else ""
        chip_txt = "CRYPTO · 24/7" if is_crypto(symbol) else f"EQUITY · {feed_txt}"
        if cur is not None and open_p:
            chg = cur - open_p
            pct = (chg / open_p * 100) if open_p else 0
            cls = "up" if chg > 0 else "down" if chg < 0 else "flat"
            arr = "▲" if chg > 0 else "▼" if chg < 0 else "■"
            chg_html = (f'<span class="px-chg {cls}">{arr} {abs(chg):,.{_dp(cur)}f}'
                        f'&nbsp;&nbsp;({pct:+.2f}%)</span>')
            now_html = f'<span class="px-now {cur_fl}">{fmt_price(cur)}</span>'
        else:
            chg_html = '<span class="px-chg flat">awaiting ticks</span>'
            now_html = '<span class="px-now">—</span>'

        bps = f"{spread / mid_now * 1e4:,.1f} bps" if spread and mid_now else "bid/ask gap"

        # ---- session range bar (built into the instrument panel) ----
        span = mids + ([cur] if cur is not None else [])
        range_html = ""
        if len(span) >= 2 and cur is not None:
            lo, hi = min(span), max(span)
            pos = (cur - lo) / (hi - lo) * 100 if hi > lo else 50
            range_html = (
                f'<div class="range"><span class="cap">Range</span>'
                f'<span>{fmt_price(lo)}</span>'
                f'<div class="r-track"><div class="r-fill" style="width:{pos:.1f}%"></div>'
                f'<div class="r-dot" style="left:{pos:.1f}%"></div></div>'
                f'<span>{fmt_price(hi)}</span></div>')

        # ---- one cohesive instrument panel ----
        st.markdown(
            f"""
            <div class="inst">
              <div class="inst-top">
                <div class="px-id">
                  <span class="px-sym">{symbol}</span>
                  <span class="px-chip {chip}">{chip_txt}</span>
                  {market_badge(symbol)}
                </div>
                <div class="px-main">{now_html}{chg_html}</div>
              </div>
              <div class="quotes">
                <div class="q {bid_fl}"><div class="q-l">Bid</div>
                  <div class="q-v up">{fmt_price(bid)}</div><div class="q-s">{fmt_size(snap.get('bid_size'))}</div></div>
                <div class="q {ask_fl}"><div class="q-l">Ask</div>
                  <div class="q-v down">{fmt_price(ask)}</div><div class="q-s">{fmt_size(snap.get('ask_size'))}</div></div>
                <div class="q {last_fl}"><div class="q-l">Last trade</div>
                  <div class="q-v mint">{fmt_price(last)}</div><div class="q-s">{fmt_size(snap.get('last_size'))}</div></div>
                <div class="q"><div class="q-l">Spread</div>
                  <div class="q-v amber">{fmt_price(spread)}</div><div class="q-s">{bps}</div></div>
              </div>
              {range_html}
            </div>
            """, unsafe_allow_html=True)

        # ---- chart panel: toolbar (status · tick latency · clock) + chart ----
        now = datetime.now(timezone.utc)
        pill = (f'<span class="pill live"><span class="dot"></span>LIVE · {streaming}</span>'
                if streaming else '<span class="pill idle"><span class="dot"></span>IDLE</span>')
        stamps = [s for s in (qt, tt) if s is not None]
        if stamps:
            age = (now - max(stamps)).total_seconds()
            lat = (f'<span class="lat"><b>{age:.1f}s</b> since tick</span>' if age < 90
                   else '<span class="lat stale"><b>stale</b> · no recent ticks</span>')
        else:
            lat = '<span class="lat">awaiting first tick</span>'

        with st.container(border=True):
            st.markdown(
                f'<div class="chart-bar">{pill}'
                f'<span class="meta-r">{lat}<span class="clock">{now.strftime("%H:%M:%S")} UTC</span></span></div>',
                unsafe_allow_html=True)
            if history:
                st.plotly_chart(build_live_chart(history, snap, T), use_container_width=True,
                                key="live_chart", config={"displayModeBar": False})
            else:
                st.markdown(
                    f"""
                    <div class="empty">
                      {I_CHART}
                      <div class="big">No live data yet</div>
                      <div class="small">Press <b>Start streaming</b> to seed the intraday chart and
                      watch quotes update live. Off-hours? Try a crypto pair like <b>BTC/USD</b> for 24/7 ticks.</div>
                    </div>
                    """, unsafe_allow_html=True)

        if snap.get("error"):
            st.error(f"Stream error: {snap['error']}")

    live_panel()

# ---------------------------- Historical ----------------------------------- #
with tab_hist:
    top_l, top_r = st.columns([3, 1])
    top_l.markdown(
        f'<div style="font:700 17px/1.3 Inter;color:var(--ink);padding-top:4px">'
        f'{symbol} <span style="color:var(--ink-3);font-weight:600;font-size:14px">· '
        f'{minutes}-min OHLCV · {days}d</span></div>', unsafe_allow_html=True)
    load_clicked = top_r.button("⤓  Load data", type="primary", use_container_width=True)
    if load_clicked:
        with st.spinner(f"Downloading {days}d of {minutes}-min bars for {symbol}…"):
            try:
                st.session_state.hist_df = connector.get_historical_bars(
                    symbol, days=days, timeframe_minutes=minutes)
                st.session_state.hist_symbol = symbol
            except Exception as exc:  # noqa: BLE001
                st.session_state.hist_df = None
                st.error(f"Download failed: {exc}")

    df = st.session_state.get("hist_df")
    if df is not None and not df.empty:
        m1, m2, m3, m4 = st.columns(4)
        first, last_c = df["open"].iloc[0], df["close"].iloc[-1]
        chg = last_c - first
        m1.metric("Last", fmt_price(last_c), f"{chg:+,.{_dp(last_c)}f} ({chg / first * 100:+.2f}%)")
        m2.metric("High", fmt_price(df["high"].max()))
        m3.metric("Low", fmt_price(df["low"].min()))
        m4.metric("Volume", f"{df['volume'].sum():,.0f}")

        vol_colors = [T["c_volup"] if c >= o else T["c_voldn"]
                      for o, c in zip(df["open"], df["close"])]
        fig = make_subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.03,
                            row_heights=[0.76, 0.24])
        fig.add_trace(go.Candlestick(
            x=df["timestamp"], open=df["open"], high=df["high"], low=df["low"],
            close=df["close"], name="OHLC",
            increasing=dict(line=dict(color=T["c_up"], width=1), fillcolor=T["c_up"]),
            decreasing=dict(line=dict(color=T["c_down"], width=1), fillcolor=T["c_down"]),
        ), row=1, col=1)
        fig.add_trace(go.Bar(x=df["timestamp"], y=df["volume"], name="Volume",
                             marker_color=vol_colors, marker_line_width=0), row=2, col=1)
        style_fig(fig, 600, T)
        fig.update_layout(
            xaxis_rangeslider_visible=False, bargap=0.15, hovermode="x unified",
            dragmode="zoom",  # click-drag to box-zoom a region
            modebar=dict(bgcolor="rgba(0,0,0,0)", color=T["ink3"], activecolor=T["mint"]),
        )
        fig.update_yaxes(tickprefix="$", tickformat=f",.{_dp(last_c)}f", row=1, col=1)
        st.plotly_chart(
            fig, use_container_width=True,
            config={"displayModeBar": True, "displaylogo": False, "scrollZoom": True,
                    "modeBarButtonsToRemove": ["lasso2d", "select2d"]})

        with st.expander("OHLCV table  ·  last 200 bars"):
            st.dataframe(
                df[["timestamp", "open", "high", "low", "close", "volume"]].tail(200),
                use_container_width=True, hide_index=True)
    elif df is not None:
        st.markdown(
            f'<div class="empty">{I_NONE}<div class="big">No bars returned</div>'
            '<div class="small">The market may be closed for this symbol, or the ticker is invalid. '
            'Try a different range or a crypto pair.</div></div>', unsafe_allow_html=True)
    else:
        st.markdown(
            f'<div class="empty">{I_BARS}<div class="big">Load historical bars</div>'
            '<div class="small">Pick a range in the sidebar and press <b>Load data</b> '
            'to chart OHLCV candles and volume.</div></div>', unsafe_allow_html=True)
