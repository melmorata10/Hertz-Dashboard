from datetime import datetime, timezone, timedelta
import io

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
import streamlit.components.v1 as components

from src.data_processor import prepare

# ── Page config ──────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Hertz Performance Dashboard",
    page_icon="🚗",
    layout="wide",
)

# ── Global theme ─────────────────────────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');

/* ── Base ───────────────────────────────────────── */
html, body, .stApp { font-family: 'Inter', sans-serif !important; }
.stApp { background: #eef2f7; }

/* ── Sidebar ────────────────────────────────────── */
section[data-testid="stSidebar"] {
    background: linear-gradient(175deg, #0a1628 0%, #112244 50%, #0f2d4a 100%) !important;
    border-right: 2px solid rgba(255,215,0,0.4);
    box-shadow: 4px 0 24px rgba(0,0,0,0.35);
}
section[data-testid="stSidebar"] label,
section[data-testid="stSidebar"] p,
section[data-testid="stSidebar"] span,
section[data-testid="stSidebar"] div,
section[data-testid="stSidebar"] caption,
section[data-testid="stSidebar"] small { color: #e2eeff !important; }
section[data-testid="stSidebar"] .stRadio label,
section[data-testid="stSidebar"] .stFileUploader label { color: #f0f6ff !important; font-weight: 500 !important; }
section[data-testid="stSidebar"] .stMarkdown h3 {
    color: #FFD700 !important;
    font-size: 12px !important;
    font-weight: 700 !important;
    letter-spacing: 1.5px !important;
    text-transform: uppercase !important;
    border-bottom: 1px solid rgba(255,215,0,0.2);
    padding-bottom: 6px;
    margin-bottom: 10px;
}
section[data-testid="stSidebar"] hr { border-color: rgba(255,255,255,0.08) !important; }
section[data-testid="stSidebar"] .stDownloadButton button,
section[data-testid="stSidebar"] .stButton button {
    background: linear-gradient(135deg, #FFD700 0%, #f5b800 100%) !important;
    color: #0a1628 !important;
    font-weight: 700 !important;
    border: none !important;
    border-radius: 8px !important;
    width: 100% !important;
    transition: all 0.2s ease !important;
    box-shadow: 0 2px 8px rgba(255,215,0,0.3) !important;
}
section[data-testid="stSidebar"] .stDownloadButton button:hover,
section[data-testid="stSidebar"] .stButton button:hover {
    transform: translateY(-1px) !important;
    box-shadow: 0 4px 14px rgba(255,215,0,0.45) !important;
}

/* ── Tabs ───────────────────────────────────────── */
.stTabs [data-baseweb="tab-list"] {
    background: transparent;
    border-bottom: 2px solid #d0dae8;
    gap: 2px;
    padding: 0;
}
.stTabs [data-baseweb="tab"] {
    color: #6b7e99 !important;
    font-weight: 600 !important;
    font-size: 14px !important;
    padding: 10px 24px !important;
    border-radius: 8px 8px 0 0 !important;
    border: 1px solid transparent !important;
    border-bottom: none !important;
    background: transparent !important;
    transition: all 0.18s ease !important;
}
.stTabs [data-baseweb="tab"]:hover { color: #1a3a5c !important; background: rgba(26,58,92,0.06) !important; }
.stTabs [aria-selected="true"] {
    background: white !important;
    color: #1a3a5c !important;
    border-color: #d0dae8 !important;
    border-bottom-color: white !important;
    margin-bottom: -2px !important;
}
.stTabs [data-baseweb="tab-panel"] {
    background: white;
    border: 1px solid #d0dae8;
    border-top: none;
    border-radius: 0 8px 8px 8px;
    padding: 24px;
    box-shadow: 0 4px 20px rgba(0,0,0,0.06);
}

/* ── Headings ───────────────────────────────────── */
h3 { color: #0f2d4a !important; font-weight: 700 !important; }
h4 { color: #1a3a5c !important; font-weight: 600 !important;
     border-left: 3px solid #FFD700; padding-left: 10px; }

/* ── KPI metric cards ───────────────────────────── */
div[data-testid="metric-container"] {
    background: white;
    border-radius: 12px;
    padding: 16px 20px 14px;
    border: 1px solid #e2eaf4;
    border-top: 3px solid #FFD700;
    box-shadow: 0 2px 12px rgba(0,0,0,0.06);
    transition: box-shadow 0.2s ease;
}
div[data-testid="metric-container"]:hover { box-shadow: 0 6px 20px rgba(0,0,0,0.1); }
div[data-testid="metric-container"] [data-testid="stMetricLabel"] {
    font-size: 12px !important; font-weight: 600 !important;
    color: #6b7e99 !important; text-transform: uppercase; letter-spacing: 0.8px;
}
div[data-testid="metric-container"] [data-testid="stMetricValue"] {
    font-size: 26px !important; font-weight: 800 !important; color: #0f2d4a !important;
}
div[data-testid="metric-container"] [data-testid="stMetricDelta"] { font-size: 12px !important; }

/* ── Dataframe / data-editor ────────────────────── */
.stDataFrame, .stDataEditor { border-radius: 10px !important; box-shadow: 0 2px 12px rgba(0,0,0,0.06) !important; }

/* ── Expander ───────────────────────────────────── */
details { border: 1px solid #d0dae8 !important; border-radius: 10px !important; overflow: hidden; }
details[open] summary { border-bottom: 1px solid #d0dae8; }
summary {
    background: linear-gradient(90deg,#eef3f9 0%,#f5f8fc 100%) !important;
    font-weight: 600 !important; color: #1a3a5c !important;
    padding: 12px 16px !important; border-radius: 10px !important;
}
summary:hover { background: linear-gradient(90deg,#e4ecf6 0%,#eef3f9 100%) !important; }

/* ── Dividers ───────────────────────────────────── */
hr { border: none !important; border-top: 1px solid #d8e3ef !important; margin: 18px 0 !important; }

/* ── Caption text ───────────────────────────────── */
.stCaption { color: #7b90a8 !important; font-size: 12px !important; }
</style>
""", unsafe_allow_html=True)


# ── Helpers ───────────────────────────────────────────────────────────────────
def _ct_now() -> str:
    ct = datetime.now(timezone(timedelta(hours=-5)))
    hour = ct.strftime("%I%p").lstrip("0")  # cross-platform: strip leading zero
    return f"Hertz Performance as of {hour} CT"


def _fmt_seconds(val) -> str:
    """1-decimal seconds — used for ASA."""
    if pd.isna(val):
        return "—"
    return f"{val:.1f}s"


def _fmt_seconds_int(val) -> str:
    """Whole-number seconds — used for AHT / Target AHT."""
    if pd.isna(val):
        return "—"
    return f"{int(round(val))}s"


def _fmt_pct(val) -> str:
    if pd.isna(val):
        return "—"
    return f"{val:.1f}%"


def _fmt_int(val) -> str:
    if pd.isna(val):
        return "—"
    return f"{int(val):,}"


def _colour_aht_var(val):
    if pd.isna(val):
        return ""
    if val <= 0:
        return "background-color: #C8F0C8; color: #1a5e1a"
    if val <= 5:
        return "background-color: #FFF4CC; color: #7a5c00"
    return "background-color: #FFD0D0; color: #8b0000"


def _colour_row(row):
    styles = [""] * len(row)
    cols = list(row.index)
    for metric, target_col in (("ABN%", "Target ABN%"), ("ASA", "Target ASA")):
        if metric in cols and target_col in cols:
            val, tgt = row[metric], row[target_col]
            if pd.notna(val) and pd.notna(tgt):
                idx = cols.index(metric)
                if val <= tgt:
                    styles[idx] = "background-color: #C8F0C8; color: #1a5e1a"
                elif val <= tgt * 1.1:
                    styles[idx] = "background-color: #FFF4CC; color: #7a5c00"
                else:
                    styles[idx] = "background-color: #FFD0D0; color: #8b0000"
    return styles


def _style_summary(df: pd.DataFrame):
    styler = df.style
    if "AHT Var%" in df.columns:
        styler = styler.map(_colour_aht_var, subset=["AHT Var%"])
    if "ABN%" in df.columns:
        styler = styler.apply(_colour_row, axis=1)
    if len(df) > 0:
        last = df.index[-1]
        styler = styler.apply(
            lambda col: ["font-weight: bold" if i == last else "" for i in col.index],
            axis=0,
        )
    return styler


def _abn_drivers(row: pd.Series) -> list[str]:
    """Return bullet-point reasons why a LOB missed its abandon rate target."""
    reasons = []

    abn_pct   = row.get("ABN%",        float("nan"))
    tgt_abn   = row.get("Target ABN%", float("nan"))
    aht       = row.get("AHT",         float("nan"))
    tgt_aht   = row.get("Target AHT",  float("nan"))
    asa       = row.get("ASA",         float("nan"))
    tgt_asa   = row.get("Target ASA",  float("nan"))
    nco       = row.get("NCO",         float("nan"))
    nch       = row.get("NCH",         float("nan"))

    # AHT over target → agents tied up longer → longer queue → more abandons
    if not (pd.isna(aht) or pd.isna(tgt_aht)) and tgt_aht > 0:
        aht_var = (aht - tgt_aht) / tgt_aht * 100
        if aht_var > 5:
            reasons.append(
                f"🕐 **AHT {int(round(aht))}s vs target {int(round(tgt_aht))}s "
                f"(+{aht_var:.1f}%)** — longer calls reduce agent availability, "
                f"extending wait times and driving abandons."
            )

    # ASA above target → callers waiting too long before answer
    if not (pd.isna(asa) or pd.isna(tgt_asa)) and tgt_asa > 0:
        asa_var = (asa - tgt_asa) / tgt_asa * 100
        if asa_var > 10:
            reasons.append(
                f"⏳ **ASA {asa:.1f}s vs target {tgt_asa:.1f}s "
                f"(+{asa_var:.1f}%)** — callers are waiting significantly longer "
                f"than target before being answered."
            )

    # High abandon gap
    if not (pd.isna(abn_pct) or pd.isna(tgt_abn)) and tgt_abn > 0:
        gap = abn_pct - tgt_abn
        if gap > 10:
            reasons.append(
                f"📉 **Abandon gap {gap:.1f}pp above target** — severely over threshold; "
                f"may indicate staffing shortfall or surge in contact volume."
            )

    # Volume pressure: high % of calls not handled
    if not (pd.isna(nco) or pd.isna(nch)) and nco > 0:
        handled_rate = nch / nco * 100
        if handled_rate < 85:
            missed = int(nco - nch)
            reasons.append(
                f"📞 **Only {handled_rate:.1f}% of calls handled** — "
                f"{missed:,} contacts offered but not answered, suggesting "
                f"insufficient staffing or high shrinkage."
            )

    if not reasons:
        reasons.append("ℹ️ No single dominant driver identified — review staffing levels and call volume patterns.")

    return reasons


def _interval_trends(lob: str, interval_df: pd.DataFrame, vendor: str = None) -> list[str]:
    """Check the two most-recent 30-min intervals for AHT spikes or volume surges."""
    reasons = []
    if interval_df is None or interval_df.empty:
        return reasons

    lob_iv = interval_df[interval_df["LOB"] == lob].copy()
    if vendor:
        lob_iv = lob_iv[lob_iv["Vendor"] == vendor]
    if lob_iv.empty:
        return reasons

    # Re-aggregate across vendors per interval slot using weighted AHT
    lob_iv["_AHT_w"] = lob_iv["NCH"].fillna(0) * lob_iv["AHT"].fillna(0)
    grp = lob_iv.groupby("Interval", sort=True).agg(
        NCO  =("NCO",    "sum"),
        NCH  =("NCH",    "sum"),
        AHT_w=("_AHT_w", "sum"),
    ).reset_index()
    safe_nch = grp["NCH"].replace(0, float("nan"))
    grp["AHT"] = (grp["AHT_w"] / safe_nch).round(1)

    if len(grp) < 2:
        return reasons

    last = grp.iloc[-1]
    prev = grp.iloc[-2]

    # Volume spike: NCO up ≥ 20% vs previous interval
    if prev["NCO"] > 0:
        nco_chg = (last["NCO"] - prev["NCO"]) / prev["NCO"] * 100
        if nco_chg >= 20:
            reasons.append(
                f"📈 **Volume spike at {last['Interval']}: NCO {int(last['NCO']):,} "
                f"vs {int(prev['NCO']):,} prior interval (+{nco_chg:.0f}%)** — sudden surge "
                f"in contacts likely overwhelmed available agents."
            )

    # AHT spike: AHT up ≥ 10% vs previous interval
    if pd.notna(prev["AHT"]) and prev["AHT"] > 0 and pd.notna(last["AHT"]):
        aht_chg = (last["AHT"] - prev["AHT"]) / prev["AHT"] * 100
        if aht_chg >= 10:
            reasons.append(
                f"🕐 **AHT spike at {last['Interval']}: {int(round(last['AHT']))}s "
                f"vs {int(round(prev['AHT']))}s prior interval (+{aht_chg:.0f}%)** — "
                f"handle time jumped between intervals, tying up agents longer."
            )

    return reasons


def _display_abn_analysis(
    df: pd.DataFrame,
    interval_df: pd.DataFrame = None,
    vendor: str = None,
):
    """Expandable section showing per-LOB abandon rate analysis."""
    # Only show LOBs (not Grand Total) that missed their target
    lob_df = df[df["LOB"] != "Grand Total"].copy()
    missed = lob_df[
        lob_df["ABN%"].notna() &
        lob_df["Target ABN%"].notna() &
        (lob_df["ABN%"] > lob_df["Target ABN%"])
    ].copy()

    if missed.empty:
        return

    missed = missed.sort_values("ABN%", ascending=False)

    with st.expander(f"🔍 Abandon Rate Analysis — {len(missed)} LOB(s) above target", expanded=False):
        for _, row in missed.iterrows():
            gap = row["ABN%"] - row["Target ABN%"]
            color = "#FFD0D0" if gap > 5 else "#FFF4CC"
            st.markdown(
                f"<div style='background:{color}; padding:10px 14px; border-radius:6px; margin-bottom:10px'>"
                f"<strong>{row['LOB']}</strong> &nbsp;·&nbsp; "
                f"ABN% <strong>{row['ABN%']:.1f}%</strong> vs target <strong>{row['Target ABN%']:.1f}%</strong> "
                f"&nbsp;<span style='color:#8b0000'>(+{gap:.1f}pp)</span>"
                f"</div>",
                unsafe_allow_html=True,
            )
            bullets = _abn_drivers(row)
            if interval_df is not None and not interval_df.empty:
                bullets += _interval_trends(row["LOB"], interval_df, vendor)
            for bullet in bullets:
                st.markdown(f"&nbsp;&nbsp;&nbsp;{bullet}")
            st.markdown("")


def _abn_driver_brief(row: pd.Series) -> str:
    """One-line driver summary for the inline Analysis column in the table."""
    if str(row.get("LOB", "")) == "Grand Total":
        return ""
    abn_pct = row.get("ABN%",        float("nan"))
    tgt_abn = row.get("Target ABN%", float("nan"))
    if pd.isna(abn_pct) or pd.isna(tgt_abn) or abn_pct <= tgt_abn:
        return ""          # on target — leave blank
    parts = []
    aht, tgt_aht = row.get("AHT", float("nan")), row.get("Target AHT", float("nan"))
    if pd.notna(aht) and pd.notna(tgt_aht) and tgt_aht > 0:
        v = (aht - tgt_aht) / tgt_aht * 100
        if v > 5:
            parts.append(f"AHT +{v:.0f}% above target")
    asa, tgt_asa = row.get("ASA", float("nan")), row.get("Target ASA", float("nan"))
    if pd.notna(asa) and pd.notna(tgt_asa) and tgt_asa > 0:
        v = (asa - tgt_asa) / tgt_asa * 100
        if v > 10:
            parts.append(f"ASA +{v:.0f}% above target")
    nco, nch = row.get("NCO", float("nan")), row.get("NCH", float("nan"))
    if pd.notna(nco) and pd.notna(nch) and nco > 0:
        hr = nch / nco * 100
        if hr < 85:
            parts.append(f"Only {hr:.0f}% calls handled")
    gap = abn_pct - tgt_abn
    if gap > 10 and not parts:
        parts.append(f"ABN {gap:.1f}pp above target — review staffing")
    return "; ".join(parts) if parts else "Review staffing & volume"


def _summary_to_tsv(df: pd.DataFrame) -> str:
    """Tab-separated + formatted — plain-text fallback for clipboard."""
    display_cols = [
        "LOB", "NCO", "NCH",
        "Target AHT", "AHT", "AHT Var%",
        "ABN", "Target ABN%", "ABN%",
        "Target ASA", "ASA", "Comment / Action",
    ]
    present = [c for c in display_cols if c in df.columns or c == "Comment / Action"]
    view = df[[c for c in present if c in df.columns]].copy()
    if "Comment / Action" not in view.columns:
        view["Comment / Action"] = ""
    for col in ("Target AHT", "AHT"):
        if col in view.columns:
            view[col] = view[col].apply(_fmt_seconds_int)
    for col in ("Target ASA", "ASA"):
        if col in view.columns:
            view[col] = view[col].apply(_fmt_seconds)
    for col in ("AHT Var%", "ABN%", "Target ABN%"):
        if col in view.columns:
            view[col] = view[col].apply(_fmt_pct)
    for col in ("NCO", "NCH", "ABN"):
        if col in view.columns:
            view[col] = view[col].apply(_fmt_int)
    return view.to_csv(sep="\t", index=False, na_rep="—")


def _summary_to_html_table(df: pd.DataFrame) -> str:
    """HTML table with inline conditional colours — pastes into Outlook/Word/Excel
    with green/yellow/red cells preserved, matching the dashboard display."""
    display_cols = [
        "LOB", "NCO", "NCH",
        "Target AHT", "AHT", "AHT Var%",
        "ABN", "Target ABN%", "ABN%",
        "Target ASA", "ASA", "Comment / Action",
    ]
    data_cols = [c for c in display_cols if c in df.columns or c == "Comment / Action"]

    HDR_BG    = "#1a3a5c"
    TOTAL_BG  = "#cce8e8"
    GREEN_BG  = "#C8F0C8"; GREEN_FG  = "#1a5e1a"
    YELLOW_BG = "#FFF4CC"; YELLOW_FG = "#7a5c00"
    RED_BG    = "#FFD0D0"; RED_FG    = "#8b0000"

    def _cell_colors(col, val, row):
        if pd.isna(val):
            return None, None
        if col == "AHT Var%":
            if val <= 0:  return GREEN_BG,  GREEN_FG
            if val <= 5:  return YELLOW_BG, YELLOW_FG
            return RED_BG, RED_FG
        if col == "ABN%":
            tgt = row.get("Target ABN%", float("nan"))
            if pd.notna(tgt):
                if val <= tgt:        return GREEN_BG,  GREEN_FG
                if val <= tgt * 1.1:  return YELLOW_BG, YELLOW_FG
                return RED_BG, RED_FG
        if col == "ASA":
            tgt = row.get("Target ASA", float("nan"))
            if pd.notna(tgt):
                if val <= tgt:        return GREEN_BG,  GREEN_FG
                if val <= tgt * 1.1:  return YELLOW_BG, YELLOW_FG
                return RED_BG, RED_FG
        return None, None

    def _fmt(col, val):
        if col in ("Target AHT", "AHT"):               return _fmt_seconds_int(val)
        if col in ("Target ASA", "ASA"):               return _fmt_seconds(val)
        if col in ("AHT Var%", "ABN%", "Target ABN%"): return _fmt_pct(val)
        if col in ("NCO", "NCH", "ABN"):               return _fmt_int(val)
        if col == "Comment / Action":                  return ""
        return str(val) if pd.notna(val) else "—"

    rows_html = []

    # Header row
    ths = "".join(
        f'<th style="background:{HDR_BG};color:white;padding:7px 10px;'
        f'border:1px solid #888;white-space:nowrap;font-weight:bold">{c}</th>'
        for c in data_cols
    )
    rows_html.append(f"<tr>{ths}</tr>")

    for _, row in df.iterrows():
        is_total = str(row.get("LOB", "")) == "Grand Total"
        base_bg  = TOTAL_BG if is_total else "white"
        fw       = "bold"   if is_total else "normal"
        tds = []
        for col in data_cols:
            val = row.get(col, float("nan")) if col != "Comment / Action" else ""
            bg, fg = _cell_colors(col, val, row) if not is_total else (None, None)
            cell_bg = bg or base_bg
            cell_fg = fg or "inherit"
            align   = "left" if col in ("LOB", "Comment / Action") else "center"
            fmt_val = _fmt(col, val)
            tds.append(
                f'<td style="background:{cell_bg};color:{cell_fg};padding:5px 9px;'
                f'border:1px solid #ccc;text-align:{align};'
                f'font-weight:{fw};white-space:nowrap">{fmt_val}</td>'
            )
        rows_html.append(f"<tr>{''.join(tds)}</tr>")

    table = (
        '<table style="border-collapse:collapse;font-family:Arial,sans-serif;font-size:13px">'
        + "".join(rows_html)
        + "</table>"
    )
    return (
        "<p><strong>Hi Team,</strong></p>"
        "<p>See performance below:</p>"
        + table
    )


_COL_WIDTHS = {
    "LOB":         180,
    "NCO":          70,
    "NCH":          70,
    "Target AHT":   82,
    "AHT":          70,
    "AHT Var%":     76,
    "ABN":          65,
    "Target ABN%":  90,
    "ABN%":         65,
    "Target ASA":   82,
    "ASA":          65,
    "Analysis":    320,
}


def _kpi_cards(df: pd.DataFrame):
    """Four headline KPI metric tiles from the Grand Total row."""
    gt = df[df["LOB"] == "Grand Total"]
    if gt.empty:
        return
    row = gt.iloc[0]
    nco  = int(row.get("NCO", 0) or 0)
    nch  = int(row.get("NCH", 0) or 0)
    abn  = row.get("ABN%", float("nan"))
    aht  = row.get("AHT",  float("nan"))
    asa  = row.get("ASA",  float("nan"))
    abandoned = nco - nch

    c1, c2, c3, c4, c5 = st.columns(5)
    with c1:
        st.metric("Contacts Offered", f"{nco:,}")
    with c2:
        st.metric("Contacts Handled", f"{nch:,}",
                  delta=f"-{abandoned:,} abandoned", delta_color="inverse")
    with c3:
        st.metric("Abandon Rate",
                  f"{abn:.1f}%" if pd.notna(abn) else "—")
    with c4:
        st.metric("Avg Handle Time",
                  f"{int(round(aht))}s" if pd.notna(aht) else "—")
    with c5:
        st.metric("Avg Speed to Answer",
                  f"{asa:.1f}s" if pd.notna(asa) else "—")


def _display_summary(df: pd.DataFrame, table_key: str = "main"):
    """Render the summary table. Analysis column is editable inline."""
    display_cols = [
        "LOB", "NCO", "NCH",
        "Target AHT", "AHT", "AHT Var%",
        "ABN", "Target ABN%", "ABN%",
        "Target ASA", "ASA", "Analysis",
    ]
    # Sort LOBs by NCO descending; Grand Total always last
    gt   = df[df["LOB"] == "Grand Total"]
    lobs = df[df["LOB"] != "Grand Total"].sort_values("NCO", ascending=False)
    df   = pd.concat([lobs, gt], ignore_index=True)

    # Session-state key for per-LOB user edits on this table
    skey = f"analysis_{table_key}"
    if skey not in st.session_state:
        st.session_state[skey] = {}

    # Build Analysis column: use saved user text if present, else auto-generate
    df = df.copy()
    df["Analysis"] = df.apply(
        lambda row: st.session_state[skey].get(
            str(row.get("LOB", "")), _abn_driver_brief(row)
        ),
        axis=1,
    )

    present = [c for c in display_cols if c in df.columns]
    view    = df[present].copy()

    # Apply colours first (needs numeric values), then format display strings
    styled = _style_summary(view)
    fmt = {}
    for col in ("Target AHT", "AHT"):
        if col in view.columns:
            fmt[col] = _fmt_seconds_int
    for col in ("Target ASA", "ASA"):
        if col in view.columns:
            fmt[col] = _fmt_seconds
    for col in ("AHT Var%", "ABN%", "Target ABN%"):
        if col in view.columns:
            fmt[col] = _fmt_pct
    for col in ("NCO", "NCH", "ABN"):
        if col in view.columns:
            fmt[col] = _fmt_int
    styled = styled.format(fmt, na_rep="—")

    # Column config — Analysis is editable, everything else locked
    col_cfg = {}
    for c, w in _COL_WIDTHS.items():
        if c not in present:
            continue
        if c == "Analysis":
            col_cfg[c] = st.column_config.TextColumn(
                "Analysis / Notes",
                width=w,
                help="Auto-generated from metrics. Click any cell to edit or add your own notes.",
            )
        else:
            col_cfg[c] = st.column_config.TextColumn(c, width=w)

    disabled_cols = [c for c in present if c != "Analysis"]
    result = st.data_editor(
        styled,
        column_config=col_cfg,
        disabled=disabled_cols,
        hide_index=True,
        use_container_width=True,
        key=f"editor_{table_key}",
        num_rows="fixed",
    )

    # Persist any edits the user made in the Analysis column
    if result is not None and "LOB" in result.columns and "Analysis" in result.columns:
        for _, row in result.iterrows():
            lob = str(row.get("LOB", ""))
            if lob:
                st.session_state[skey][lob] = str(row.get("Analysis", ""))


def _style_interval(df: pd.DataFrame):
    """Same colour rules as the summary table — no bold Grand Total row."""
    styler = df.style
    if "AHT Var%" in df.columns:
        styler = styler.map(_colour_aht_var, subset=["AHT Var%"])
    if "ABN%" in df.columns:
        styler = styler.apply(_colour_row, axis=1)
    return styler


def _chart_data(filtered: pd.DataFrame) -> pd.DataFrame:
    """Aggregate filtered interval rows into one row per time slot for charting."""
    if filtered.empty or "Interval" not in filtered.columns:
        return pd.DataFrame()
    tmp = filtered.copy()
    tmp["_AHT_w"] = tmp["NCH"].fillna(0) * tmp["AHT"].fillna(0)
    tmp["_ASA_w"] = tmp["NCH"].fillna(0) * tmp["ASA"].fillna(0)
    agg = tmp.groupby("Interval", sort=True).agg(
        NCO  =("NCO",    "sum"),
        NCH  =("NCH",    "sum"),
        ABN  =("ABN",    "sum"),
        AHT_w=("_AHT_w", "sum"),
        ASA_w=("_ASA_w", "sum"),
    ).reset_index()
    for tgt_col in ("Target AHT", "Target ASA"):
        if tgt_col in tmp.columns:
            agg = agg.merge(
                tmp.groupby("Interval")[tgt_col].mean().reset_index(),
                on="Interval", how="left",
            )
    safe_nch = agg["NCH"].replace(0, float("nan"))
    agg["AHT"] = (agg["AHT_w"] / safe_nch).round(1)
    agg["ASA"] = (agg["ASA_w"] / safe_nch).round(1)
    return agg


def _display_interval(df: pd.DataFrame, lob_filter: list, vendor_filter: list):
    filtered = df.copy()
    if lob_filter:
        filtered = filtered[filtered["LOB"].isin(lob_filter)]
    if vendor_filter:
        filtered = filtered[filtered["Vendor"].isin(vendor_filter)]

    # ── Charts ────────────────────────────────────────────────────────────────
    cd = _chart_data(filtered)
    if not cd.empty:
        GRAY   = "#9e9e9e"
        BLUE   = "#1f77b4"
        ORANGE = "#ff7f0e"
        GREEN  = "#2ca02c"
        LBLUE  = "#aec7e8"

        col_a, col_b, col_c = st.columns(3)

        # Chart 1 — Target AHT vs AHT
        with col_a:
            fig1 = go.Figure()
            if "Target AHT" in cd.columns:
                fig1.add_trace(go.Scatter(
                    x=cd["Interval"], y=cd["Target AHT"],
                    name="Target AHT", mode="lines",
                    line=dict(color=GRAY, dash="dash", width=2),
                ))
            fig1.add_trace(go.Scatter(
                x=cd["Interval"], y=cd["AHT"],
                name="AHT", mode="lines+markers",
                line=dict(color=BLUE, width=2),
                marker=dict(size=5),
            ))
            fig1.update_layout(
                title="AHT vs Target AHT",
                yaxis_title="Seconds",
                xaxis_title="Interval",
                height=320,
                legend=dict(orientation="h", y=-0.35),
                margin=dict(l=10, r=10, t=40, b=10),
            )
            st.plotly_chart(fig1, use_container_width=True)

        # Chart 2 — NCO vs NCH (grouped bars)
        with col_b:
            fig2 = go.Figure()
            fig2.add_trace(go.Bar(
                x=cd["Interval"], y=cd["NCO"],
                name="NCO (Offered)", marker_color=LBLUE,
            ))
            fig2.add_trace(go.Bar(
                x=cd["Interval"], y=cd["NCH"],
                name="NCH (Handled)", marker_color=BLUE,
            ))
            fig2.update_layout(
                title="Volume: Offered vs Handled",
                barmode="group",
                yaxis_title="Calls",
                xaxis_title="Interval",
                height=320,
                legend=dict(orientation="h", y=-0.35),
                margin=dict(l=10, r=10, t=40, b=10),
            )
            st.plotly_chart(fig2, use_container_width=True)

        # Chart 3 — ASA and AHT over time (dual lines)
        with col_c:
            fig3 = go.Figure()
            fig3.add_trace(go.Scatter(
                x=cd["Interval"], y=cd["AHT"],
                name="AHT", mode="lines+markers",
                line=dict(color=BLUE, width=2),
                marker=dict(size=5),
            ))
            fig3.add_trace(go.Scatter(
                x=cd["Interval"], y=cd["ASA"],
                name="ASA", mode="lines+markers",
                line=dict(color=ORANGE, width=2),
                marker=dict(size=5),
            ))
            if "Target ASA" in cd.columns:
                fig3.add_trace(go.Scatter(
                    x=cd["Interval"], y=cd["Target ASA"],
                    name="Target ASA", mode="lines",
                    line=dict(color=ORANGE, dash="dash", width=1.5),
                ))
            fig3.update_layout(
                title="AHT & ASA over Time",
                yaxis_title="Seconds",
                xaxis_title="Interval",
                height=320,
                legend=dict(orientation="h", y=-0.35),
                margin=dict(l=10, r=10, t=40, b=10),
            )
            st.plotly_chart(fig3, use_container_width=True)

        st.markdown("---")

    # ── Table with conditional formatting ─────────────────────────────────────
    display_cols = [
        "Interval", "LOB", "Vendor",
        "NCO", "NCH",
        "Target AHT", "AHT", "AHT Var%",
        "ABN", "Target ABN%", "ABN%",
        "Target ASA", "ASA",
    ]
    present = [c for c in display_cols if c in filtered.columns]
    view = filtered[present].copy()

    styled = _style_interval(view)
    fmt = {}
    for col in ("Target AHT", "AHT"):          # whole numbers
        if col in view.columns:
            fmt[col] = _fmt_seconds_int
    for col in ("Target ASA", "ASA"):           # 1 decimal
        if col in view.columns:
            fmt[col] = _fmt_seconds
    for col in ("AHT Var%", "ABN%", "Target ABN%"):
        if col in view.columns:
            fmt[col] = _fmt_pct
    for col in ("NCO", "NCH", "ABN"):
        if col in view.columns:
            fmt[col] = _fmt_int
    styled = styled.format(fmt, na_rep="—")

    st.dataframe(styled, use_container_width=True, hide_index=True)

    if not filtered.empty:
        num_cols = ["NCO", "NCH", "ABN"]
        totals = {c: int(filtered[c].sum()) for c in num_cols if c in filtered.columns}
        st.caption(
            f"**Totals** — NCO: {totals.get('NCO', 0):,} | "
            f"NCH: {totals.get('NCH', 0):,} | "
            f"ABN: {totals.get('ABN', 0):,}"
        )


# ── Data loading ─────────────────────────────────────────────────────────────
def _load_from_uploads(files) -> pd.DataFrame:
    frames = []
    for f in files:
        try:
            frames.append(pd.read_csv(io.BytesIO(f.read())))
        except Exception as e:
            st.sidebar.warning(f"Could not read {f.name}: {e}")
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()



# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    # Branding — CSS-rendered Hertz logo (no external dependency)
    st.markdown(
        """
        <div style='text-align:center; padding:18px 0 10px'>
          <div style='display:inline-block; background:#FFD700;
                      padding:7px 22px; border-radius:5px;
                      box-shadow:0 3px 12px rgba(255,215,0,0.4)'>
            <span style='font-family:Arial Black,Impact,sans-serif;
                         font-size:26px; font-weight:900; color:#1a1a1a;
                         letter-spacing:2px; line-height:1'>HERTZ</span>
          </div>
          <div style='font-size:9px; color:rgba(255,215,0,0.7);
                      letter-spacing:3px; margin-top:8px;
                      text-transform:uppercase; font-weight:600'>
            Powered by Callinsite
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.markdown("---")

    st.markdown("### 📂 Upload Data")
    uploaded = st.file_uploader(
        "Upload one or more CSV files",
        type="csv",
        accept_multiple_files=True,
        label_visibility="collapsed",
    )
    st.caption("Columns: SkillName, SupplierName, Interval, NCO, NCH, AHT, ABN, ASA")

# ── Load & process ────────────────────────────────────────────────────────────
summary_df = pd.DataFrame()
vendor_summaries: dict = {}
interval_df = pd.DataFrame()
data_ok = False

if uploaded:
    raw = _load_from_uploads(uploaded)
    if not raw.empty:
        summary_df, vendor_summaries, interval_df = prepare(raw)
        data_ok = True
    else:
        st.warning("No data could be read from the uploaded files.")
else:
    st.info("⬆️ Upload your CSV files from the sidebar to load the dashboard.")

# ── Sidebar — export buttons & notes (only when data is ready) ───────────────
if data_ok and not summary_df.empty:
    import json as _json
    with st.sidebar:
        st.markdown("---")
        st.markdown("### 📤 Export")
        csv_bytes = summary_df.to_csv(index=False).encode("utf-8")
        st.download_button(
            "⬇️ Download CSV",
            data=csv_bytes,
            file_name="hertz_performance_summary.csv",
            mime="text/csv",
            use_container_width=True,
        )

# ── Header ────────────────────────────────────────────────────────────────────
st.markdown(
    f"""
    <div style='background:linear-gradient(120deg,#0a1628 0%,#1a3a5c 60%,#1d4675 100%);
                padding:20px 32px; border-radius:14px; margin-bottom:16px;
                border-bottom:3px solid #FFD700;
                box-shadow:0 6px 28px rgba(10,22,40,0.28);
                display:flex; align-items:center; justify-content:space-between'>
      <div>
        <div style='font-size:10px;color:#FFD700;font-weight:800;
                    letter-spacing:2.5px;text-transform:uppercase;margin-bottom:4px;
                    opacity:0.9'>
          Hertz &nbsp;·&nbsp; Powered by Callinsite
        </div>
        <div style='font-size:26px;font-weight:800;color:white;line-height:1.1;
                    letter-spacing:-0.5px'>
          {_ct_now()}
        </div>
      </div>
      <div style='display:flex;gap:6px;align-items:center'>
        <div style='background:rgba(255,215,0,0.15);border:1px solid rgba(255,215,0,0.35);
                    border-radius:8px;padding:6px 14px;font-size:12px;
                    color:#FFD700;font-weight:600;letter-spacing:0.5px'>
          LIVE
        </div>
      </div>
    </div>
    """,
    unsafe_allow_html=True,
)

tab1, tab2 = st.tabs(["📊 Voice Performance Summary", "⏱️ Per Interval"])

# ── Tab 1: Voice Performance Summary ─────────────────────────────────────────
with tab1:
    if data_ok and not summary_df.empty:
        # ── KPI headline tiles ─────────────────────────────────────────────────
        _kpi_cards(summary_df)
        st.markdown("<div style='margin-top:20px'></div>", unsafe_allow_html=True)

        st.subheader("Performance by Line of Business")
        _display_summary(summary_df, table_key="main")

        st.markdown(
            """
            <div style='font-size:0.8em; margin-top:6px; display:flex; gap:12px; flex-wrap:wrap'>
            <span style='background:#C8F0C8; padding:2px 10px; border-radius:12px;
                         color:#1a5e1a; font-weight:600'>■ At / below target</span>
            <span style='background:#FFF4CC; padding:2px 10px; border-radius:12px;
                         color:#7a5c00; font-weight:600'>■ Within 10% of target</span>
            <span style='background:#FFD0D0; padding:2px 10px; border-radius:12px;
                         color:#8b0000; font-weight:600'>■ Exceeds target</span>
            </div>
            """,
            unsafe_allow_html=True,
        )
        st.caption(
            "**AHT** = Avg Handle Time (s) · **ABN%** = Abandon Rate · "
            "**ASA** = Avg Speed to Answer (s) · **Var%** = % variance vs target · "
            "**Analysis** = auto-generated driver for LOBs above ABN% target"
        )
        st.markdown("---")

        # ── Abandon Rate Analysis ──────────────────────────────────────────────
        _display_abn_analysis(summary_df, interval_df=interval_df)

        # ── Per-vendor tables ──────────────────────────────────────────────────
        if vendor_summaries:
            st.markdown("---")
            st.subheader("Performance by Vendor / Supplier")
            vendor_order = ["TELUS", "VXI", "IGT", "HERTZ"]
            vendors_to_show = [v for v in vendor_order if v in vendor_summaries]
            vendors_to_show += [v for v in vendor_summaries if v not in vendor_order]
            for vendor in vendors_to_show:
                st.markdown(f"#### {vendor}")
                vdf = vendor_summaries[vendor]
                # HERTZ: suppress LOB rows that have no calls yet (NCO = 0 / blank)
                if vendor == "HERTZ":
                    mask = (vdf["LOB"] == "Grand Total") | (vdf["NCO"].fillna(0) > 0)
                    vdf = vdf[mask].reset_index(drop=True)
                _display_summary(vdf, table_key=f"vendor_{vendor}")
                _display_abn_analysis(vdf, interval_df=interval_df, vendor=vendor)

# ── Tab 2: Per Interval ───────────────────────────────────────────────────────
with tab2:
    if data_ok and not interval_df.empty:
        all_lobs = sorted(
            l for l in interval_df["LOB"].unique()
            if l not in ("Unknown", "", None)
        )
        all_vendors = sorted(
            v for v in interval_df["Vendor"].unique()
            if v not in ("Unknown", "", None)
        )

        col1, col2 = st.columns([3, 2])
        with col1:
            lob_sel = st.multiselect(
                "Filter by LOB",
                options=all_lobs,
                default=all_lobs,
                key="lob_filter",
            )
        with col2:
            vendor_sel = st.multiselect(
                "Filter by Vendor / Supplier",
                options=all_vendors,
                default=all_vendors,
                key="vendor_filter",
            )

        st.subheader("30-Minute Interval Breakdown")
        _display_interval(interval_df, lob_sel, vendor_sel)
    elif data_ok:
        st.info("No interval data available in the loaded files.")
