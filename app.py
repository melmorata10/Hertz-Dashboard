from datetime import datetime, timezone, timedelta
import io

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
import streamlit.components.v1 as components

from src.data_processor import prepare
from src.mapping import SKILL_TO_LOB as _BUILTIN_MAPPING, LOB_DISPLAY_ORDER as _LOB_ORDER, TARGETS as _BUILTIN_TARGETS
from src.persistence import (
    load_comments, save_comments, clear_comments,
    load_custom_mapping, save_custom_mapping,
    load_mapping_df, save_mapping_df, clear_custom_mapping,
    load_targets, save_targets, clear_targets, load_targets_mtime,
)

# SharePoint connector
try:
    from src.sharepoint import acquire_token as _sp_acquire_token
    from src.sharepoint import get_valid_token as _sp_get_valid_token
    from src.sharepoint import load_all_csvs as _sp_load
    from src.sharepoint import HOSTNAME as _SP_HOSTNAME
    _SP_AVAILABLE = True
except ImportError:
    _SP_AVAILABLE = False

# ── Page config ──────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Daily Performance Report",
    page_icon="🚗",
    layout="wide",
)

# ── Load shared server-side state on first visit ──────────────────────────────
# session_state is per-browser; disk files are shared across ALL users.
# We seed session_state from disk once per session so every RTA sees the
# mapping and comments saved by whoever last updated them.
if "lob_comments" not in st.session_state:
    st.session_state["lob_comments"] = load_comments()

if "custom_mapping" not in st.session_state:
    _persisted_mapping = load_custom_mapping()
    if _persisted_mapping is not None:
        # Auto-sync: push any new or changed built-in entries into the saved mapping
        # so newly added LOBs / remapped skills are reflected without a manual Reset.
        _cm_changed = False
        for _k, _v in _BUILTIN_MAPPING.items():
            if _persisted_mapping.get(_k) != _v:
                _persisted_mapping[_k] = _v
                _cm_changed = True
        if _cm_changed:
            save_custom_mapping(_persisted_mapping)
        st.session_state["custom_mapping"] = _persisted_mapping

if "mapping_df" not in st.session_state:
    _persisted_df = load_mapping_df()
    if _persisted_df is not None:
        st.session_state["mapping_df"] = _persisted_df

# Live-sync targets: on every rerun, check if the disk file is newer than what
# this session last loaded.  If so, reload — this means a change saved by any
# other RTA is picked up automatically without a browser refresh.
_disk_targets_mtime = load_targets_mtime()
if _disk_targets_mtime != st.session_state.get("_targets_mtime", -1.0):
    _persisted_targets = load_targets()
    st.session_state["_targets_mtime"] = _disk_targets_mtime
    if _persisted_targets is not None:
        st.session_state["custom_targets"] = _persisted_targets
    else:
        # File was deleted (Reset clicked by someone else) — revert to built-in
        st.session_state.pop("custom_targets", None)
    # Drop cached editor df so it re-seeds from the freshly loaded targets
    st.session_state.pop("targets_df", None)

# Move sidebar logo above nav links + rename "app" nav label
components.html("""
<script>
(function() {
    function reorder() {
        try {
            var doc = window.parent.document;
            var nav = doc.querySelector('[data-testid="stSidebarNav"]');
            var uc  = doc.querySelector('[data-testid="stSidebarUserContent"]');
            if (nav && uc && uc.compareDocumentPosition(nav) & 4) {
                uc.parentNode.insertBefore(nav, uc);
            }
        } catch(e) {}
    }
    function renameAppLabel() {
        try {
            var doc = window.parent.document;
            var nav = doc.querySelector('[data-testid="stSidebarNav"]');
            if (!nav) return;
            var walker = doc.createTreeWalker(nav, NodeFilter.SHOW_TEXT, null, false);
            var node;
            while ((node = walker.nextNode())) {
                if (node.textContent.trim() === 'app') {
                    node.textContent = 'Daily Performance Dashboard';
                }
            }
        } catch(e) {}
    }
    function run() { reorder(); renameAppLabel(); }
    run();
    setTimeout(run, 300);
    setTimeout(run, 900);
    setTimeout(run, 2000);
})();
</script>
""", height=0)

# ── Global theme — Premium v2 ─────────────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800;900&display=swap');

/* ══ Keyframe Animations ══════════════════════════════════════════════════ */
@keyframes gradientShift {
    0%   { background-position: 0% 50%; }
    50%  { background-position: 100% 50%; }
    100% { background-position: 0% 50%; }
}
@keyframes glowPulse {
    0%,100% { box-shadow: 0 2px 12px rgba(0,0,0,0.07), 0 0 0 0 rgba(255,215,0,0); }
    50%      { box-shadow: 0 8px 28px rgba(0,0,0,0.13), 0 0 22px rgba(255,215,0,0.16); }
}
@keyframes shimmerSweep {
    0%   { transform: translateX(-120%); }
    100% { transform: translateX(280%); }
}
@keyframes fadeSlideIn {
    from { opacity: 0; transform: translateY(14px); }
    to   { opacity: 1; transform: translateY(0); }
}
@keyframes pulseDot {
    0%,100% { opacity: 1;   transform: scale(1);    box-shadow: 0 0 0 0 rgba(74,222,128,0.6); }
    50%      { opacity: 0.7; transform: scale(0.88); box-shadow: 0 0 0 5px rgba(74,222,128,0); }
}
@keyframes sidebarFlow {
    0%   { background-position: 0% 0%; }
    100% { background-position: 0% 100%; }
}
@keyframes navEntrance {
    from { opacity: 0; transform: translateX(-12px); }
    to   { opacity: 1; transform: translateX(0); }
}
@keyframes particleDrift {
    0%   { background-position: 0 0; }
    100% { background-position: 48px 48px; }
}
@keyframes borderBeam {
    0%,100% { opacity: 0.6; }
    50%      { opacity: 1; }
}
@keyframes headerBeam {
    0%   { left: -60%; }
    100% { left: 140%; }
}

/* ══ Base ═════════════════════════════════════════════════════════════════ */
html, body, .stApp { font-family: 'Inter', sans-serif !important; }
.stApp {
    background: linear-gradient(135deg, #e6ecf5 0%, #eef2f8 50%, #e3edf6 100%) !important;
}
/* Subtle animated dot grid across the whole page */
.stApp::before {
    content: '';
    position: fixed;
    inset: 0;
    background-image: radial-gradient(circle, rgba(26,58,92,0.055) 1px, transparent 1px);
    background-size: 28px 28px;
    animation: particleDrift 18s linear infinite;
    pointer-events: none;
    z-index: 0;
}

/* ══ Sidebar ══════════════════════════════════════════════════════════════ */
section[data-testid="stSidebar"] {
    background: linear-gradient(180deg,
        #040c18 0%, #07111f 15%, #0a1628 35%,
        #112244 60%, #0f2d4a 80%, #07111f 100%) !important;
    background-size: 100% 300% !important;
    animation: sidebarFlow 14s ease-in-out infinite alternate !important;
    border-right: 2px solid rgba(255,215,0,0.45) !important;
    box-shadow: 4px 0 36px rgba(0,0,0,0.5) !important;
}

/* ── Sidebar Nav Links ────────────────────────────────────────────────── */
[data-testid="stSidebarNav"] {
    padding: 2px 10px 14px !important;
}
[data-testid="stSidebarNav"]::before {
    content: "NAVIGATION";
    display: block;
    font-size: 9.5px;
    font-weight: 800;
    letter-spacing: 2.5px;
    color: rgba(255,215,0,0.55);
    padding: 10px 6px 8px;
    font-family: 'Inter', sans-serif;
    text-transform: uppercase;
}
[data-testid="stSidebarNav"] a {
    display: flex !important;
    align-items: center !important;
    margin: 4px 0 !important;
    padding: 12px 14px 12px 18px !important;
    border-radius: 10px !important;
    border: 1px solid rgba(255,215,0,0.1) !important;
    background: rgba(255,255,255,0.04) !important;
    text-decoration: none !important;
    transition: all 0.22s ease !important;
    animation: navEntrance 0.4s ease both !important;
    position: relative !important;
    overflow: hidden !important;
}
/* Gold left accent bar */
[data-testid="stSidebarNav"] a::before {
    content: '';
    position: absolute;
    left: 0; top: 15%; bottom: 15%;
    width: 3px;
    border-radius: 0 3px 3px 0;
    background: rgba(255,215,0,0.25);
    transition: all 0.22s ease;
}
/* Shimmer on hover */
[data-testid="stSidebarNav"] a::after {
    content: '';
    position: absolute;
    top: 0; left: -80%;
    width: 50%; height: 100%;
    background: linear-gradient(90deg, transparent, rgba(255,215,0,0.06), transparent);
    transition: left 0.4s ease;
}
[data-testid="stSidebarNav"] a:hover {
    background: rgba(255,215,0,0.09) !important;
    border-color: rgba(255,215,0,0.32) !important;
    transform: translateX(5px) !important;
    box-shadow: 0 4px 18px rgba(0,0,0,0.25), inset 0 0 20px rgba(255,215,0,0.03) !important;
}
[data-testid="stSidebarNav"] a:hover::before { background: #FFD700; box-shadow: 0 0 10px rgba(255,215,0,0.7); }
[data-testid="stSidebarNav"] a:hover::after  { left: 140%; }
[data-testid="stSidebarNav"] a[aria-current="page"] {
    background: linear-gradient(90deg, rgba(255,215,0,0.13), rgba(255,215,0,0.06)) !important;
    border-color: rgba(255,215,0,0.42) !important;
    box-shadow: 0 4px 18px rgba(0,0,0,0.22), 0 0 24px rgba(255,215,0,0.06) !important;
}
[data-testid="stSidebarNav"] a[aria-current="page"]::before {
    background: #FFD700;
    box-shadow: 0 0 12px rgba(255,215,0,0.8);
}
[data-testid="stSidebarNav"] a li,
[data-testid="stSidebarNav"] a span,
[data-testid="stSidebarNav"] ul li span {
    color: #ccddf8 !important;
    font-weight: 600 !important;
    font-size: 13.5px !important;
    letter-spacing: 0.2px !important;
}
[data-testid="stSidebarNav"] a[aria-current="page"] li,
[data-testid="stSidebarNav"] a[aria-current="page"] span {
    color: #FFD700 !important;
    text-shadow: 0 0 14px rgba(255,215,0,0.45) !important;
}

/* ── Rename "app" nav label → "Daily Performance Dashboard" ──────────── */
[data-testid="stSidebarNav"] a[href="/"] span { font-size: 0 !important; }
[data-testid="stSidebarNav"] a[href="/"] span::after {
    content: "Daily Performance Dashboard";
    font-size: 13.5px;
    font-weight: 600;
    letter-spacing: 0.2px;
}

/* ── Hide Verint Social Media nav link ───────────────────────────────── */
[data-testid="stSidebarNav"] a[href*="Verint"],
[data-testid="stSidebarNav"] a[href*="verint"],
[data-testid="stSidebarNav"] a[href*="2_Verint"] { display: none !important; }

/* ── Always-visible fullscreen toolbar on tables ─────────────────────── */
[data-testid="stElementToolbar"] {
    opacity: 1 !important;
    visibility: visible !important;
}

/* ── Sidebar text ─────────────────────────────────────────────────────── */
section[data-testid="stSidebar"] label,
section[data-testid="stSidebar"] p,
section[data-testid="stSidebar"] span,
section[data-testid="stSidebar"] div,
section[data-testid="stSidebar"] caption,
section[data-testid="stSidebar"] small { color: #c0d4ee !important; }
section[data-testid="stSidebar"] .stRadio label,
section[data-testid="stSidebar"] .stFileUploader label { color: #dceeff !important; font-weight: 500 !important; }
section[data-testid="stSidebar"] .stMarkdown h3 {
    color: #FFD700 !important;
    font-size: 10px !important;
    font-weight: 800 !important;
    letter-spacing: 2.2px !important;
    text-transform: uppercase !important;
    border-bottom: 1px solid rgba(255,215,0,0.18);
    padding-bottom: 6px;
    margin-bottom: 10px;
}
section[data-testid="stSidebar"] hr { border-color: rgba(255,255,255,0.06) !important; }
section[data-testid="stSidebar"] .stDownloadButton button,
section[data-testid="stSidebar"] .stButton button {
    background: linear-gradient(135deg, #FFD700 0%, #f5c400 55%, #e8b000 100%) !important;
    color: #0a1628 !important;
    font-weight: 800 !important;
    border: none !important;
    border-radius: 10px !important;
    width: 100% !important;
    transition: all 0.25s ease !important;
    box-shadow: 0 3px 14px rgba(255,215,0,0.38), 0 1px 4px rgba(0,0,0,0.22) !important;
    letter-spacing: 0.3px !important;
}
section[data-testid="stSidebar"] .stDownloadButton button:hover,
section[data-testid="stSidebar"] .stButton button:hover {
    transform: translateY(-2px) !important;
    box-shadow: 0 7px 22px rgba(255,215,0,0.52), 0 2px 6px rgba(0,0,0,0.25) !important;
}

/* ══ Tabs ═════════════════════════════════════════════════════════════════ */
.stTabs [data-baseweb="tab-list"] {
    background: transparent;
    border-bottom: 2px solid rgba(200,215,235,0.85);
    gap: 4px;
    padding: 0;
}
.stTabs [data-baseweb="tab"] {
    color: #7a90aa !important;
    font-weight: 600 !important;
    font-size: 14px !important;
    padding: 11px 26px !important;
    border-radius: 10px 10px 0 0 !important;
    border: 1px solid transparent !important;
    border-bottom: none !important;
    background: transparent !important;
    transition: all 0.2s ease !important;
}
.stTabs [data-baseweb="tab"]:hover {
    color: #1a3a5c !important;
    background: rgba(26,58,92,0.07) !important;
}
.stTabs [aria-selected="true"] {
    background: white !important;
    color: #0a1628 !important;
    font-weight: 700 !important;
    border-color: rgba(200,215,235,0.9) !important;
    border-bottom-color: white !important;
    margin-bottom: -2px !important;
    box-shadow: inset 0 -3px 0 #FFD700 !important;
}
.stTabs [data-baseweb="tab-panel"] {
    background: white;
    border: 1px solid rgba(200,215,235,0.8);
    border-top: none;
    border-radius: 0 10px 10px 10px;
    padding: 28px;
    box-shadow: 0 8px 36px rgba(0,0,0,0.07);
    animation: fadeSlideIn 0.32s ease;
}

/* ══ Headings ════════════════════════════════════════════════════════════ */
h3 { color: #0a1628 !important; font-weight: 800 !important; letter-spacing: -0.3px !important; }
h4 { color: #1a3a5c !important; font-weight: 700 !important;
     border-left: 3px solid #FFD700; padding-left: 12px; }

/* ══ KPI metric cards ════════════════════════════════════════════════════ */
div[data-testid="metric-container"] {
    background: linear-gradient(145deg, #ffffff 0%, #f8fbff 100%);
    border-radius: 14px;
    padding: 18px 22px 16px;
    border: 1px solid rgba(205,218,238,0.8);
    border-top: 3px solid #FFD700;
    box-shadow: 0 2px 12px rgba(0,0,0,0.06);
    transition: all 0.28s ease;
    animation: glowPulse 4.5s ease-in-out infinite;
    position: relative;
    overflow: hidden;
}
/* Shimmer sweep across each card */
div[data-testid="metric-container"]::after {
    content: '';
    position: absolute;
    top: 0; left: -80%;
    width: 55%; height: 100%;
    background: linear-gradient(90deg, transparent, rgba(255,215,0,0.07), transparent);
    animation: shimmerSweep 6s ease-in-out infinite;
}
div[data-testid="metric-container"]:hover {
    transform: translateY(-4px) scale(1.01) !important;
    box-shadow: 0 14px 36px rgba(0,0,0,0.12), 0 0 0 2px rgba(255,215,0,0.35) !important;
    border-top-color: #ffe552 !important;
    animation: none !important;
}
div[data-testid="metric-container"] [data-testid="stMetricLabel"] {
    font-size: 11px !important; font-weight: 700 !important;
    color: #7a90aa !important; text-transform: uppercase; letter-spacing: 1.1px;
}
div[data-testid="metric-container"] [data-testid="stMetricValue"] {
    font-size: 28px !important; font-weight: 900 !important;
    color: #0a1628 !important; letter-spacing: -0.5px !important; line-height: 1.1 !important;
}
div[data-testid="metric-container"] [data-testid="stMetricDelta"] { font-size: 12px !important; font-weight: 500 !important; }

/* ══ Table / data-editor ═════════════════════════════════════════════════ */
.stDataFrame, .stDataEditor {
    border-radius: 12px !important;
    box-shadow: 0 4px 22px rgba(0,0,0,0.07) !important;
    border: 1px solid rgba(205,218,238,0.7) !important;
    overflow: hidden !important;
}

/* ══ Expander ════════════════════════════════════════════════════════════ */
details { border: 1px solid rgba(200,215,235,0.8) !important; border-radius: 12px !important; overflow: hidden; transition: all 0.2s ease; }
details[open] summary { border-bottom: 1px solid rgba(200,215,235,0.7); }
summary {
    background: linear-gradient(90deg, #edf3fb 0%, #f5f9fd 100%) !important;
    font-weight: 700 !important; color: #1a3a5c !important;
    padding: 14px 18px !important; border-radius: 12px !important; letter-spacing: 0.1px !important;
}
summary:hover { background: linear-gradient(90deg, #e1edf8 0%, #eaf3fc 100%) !important; }

/* ══ Dividers ════════════════════════════════════════════════════════════ */
hr {
    border: none !important;
    height: 1px !important;
    background: linear-gradient(90deg, transparent, #bfcfe4, transparent) !important;
    margin: 22px 0 !important;
}

/* ══ Caption ═════════════════════════════════════════════════════════════ */
.stCaption { color: #8099b8 !important; font-size: 12px !important; }

/* ══ Alert boxes ═════════════════════════════════════════════════════════ */
.stAlert { border-radius: 10px !important; animation: fadeSlideIn 0.35s ease !important; }

/* ══ Sidebar file uploader ═══════════════════════════════════════════════ */
section[data-testid="stSidebar"] [data-testid="stFileUploader"] {
    background: rgba(255,255,255,0.05) !important; border-radius: 10px !important; padding: 4px !important;
}
section[data-testid="stSidebar"] [data-testid="stFileUploaderDropzone"] {
    background: rgba(255,255,255,0.04) !important;
    border: 1.5px dashed rgba(255,215,0,0.38) !important;
    border-radius: 8px !important; transition: all 0.22s ease !important;
}
section[data-testid="stSidebar"] [data-testid="stFileUploaderDropzone"]:hover {
    border-color: rgba(255,215,0,0.62) !important;
    background: rgba(255,215,0,0.03) !important;
}
section[data-testid="stSidebar"] [data-testid="stFileUploaderDropzoneInstructions"] span,
section[data-testid="stSidebar"] [data-testid="stFileUploaderDropzoneInstructions"] p,
section[data-testid="stSidebar"] [data-testid="stFileUploaderDropzone"] span,
section[data-testid="stSidebar"] [data-testid="stFileUploaderDropzone"] p,
section[data-testid="stSidebar"] [data-testid="stFileUploaderDropzone"] small {
    color: #a8c8ea !important; font-weight: 500 !important;
}
section[data-testid="stSidebar"] [data-testid="stFileUploaderDropzone"] button {
    background: rgba(255,215,0,0.12) !important;
    border: 1px solid rgba(255,215,0,0.42) !important;
    color: #FFD700 !important; border-radius: 6px !important; font-weight: 600 !important;
    transition: all 0.2s ease !important;
}
section[data-testid="stSidebar"] [data-testid="stFileUploaderDropzone"] button:hover {
    background: rgba(255,215,0,0.2) !important;
}
section[data-testid="stSidebar"] .stCaption,
section[data-testid="stSidebar"] [data-testid="stCaptionContainer"] { color: #7aaacb !important; }

/* ══ Entrance animation on all main content blocks ═══════════════════════ */
section.main > div > div > div > div > div { animation: fadeSlideIn 0.4s ease both; }
</style>
""", unsafe_allow_html=True)


# ── Helpers ───────────────────────────────────────────────────────────────────
def _ct_now() -> str:
    ct = datetime.now(timezone(timedelta(hours=-5)))
    hour = ct.strftime("%I%p").lstrip("0")  # cross-platform: strip leading zero
    return f"Hertz Performance as of {hour} CT"


def _data_as_of(interval_df: pd.DataFrame, call_date: str = None) -> str:
    """Use the latest interval time + call date from the data; fall back to system clock."""
    if interval_df is None or interval_df.empty or "Interval" not in interval_df.columns:
        return _ct_now()
    valid = interval_df["Interval"].dropna()
    valid = valid[valid != "N/A"]
    if valid.empty:
        return _ct_now()
    latest = valid.max()  # "HH:MM" strings sort correctly lexicographically
    try:
        t = datetime.strptime(latest, "%H:%M")
        hour_str = t.strftime("%I:%M%p").lstrip("0").replace(":00", "")
        if call_date:
            try:
                d = datetime.strptime(str(call_date), "%m/%d/%Y")
                date_str = f"{d.strftime('%b')} {d.day}"  # e.g. "May 9"
            except Exception:
                date_str = str(call_date)
            return f"Hertz Performance · {date_str} · {hour_str} CT"
        return f"Hertz Performance as of {hour_str} CT"
    except Exception:
        return _ct_now()


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

    # AHT — same green/yellow/red as AHT Var%
    if "AHT" in cols and "AHT Var%" in cols:
        aht_var = row["AHT Var%"]
        if pd.notna(aht_var):
            idx = cols.index("AHT")
            styles[idx] = _colour_aht_var(aht_var)
    elif "AHT" in cols and "Target AHT" in cols:
        aht, tgt = row["AHT"], row["Target AHT"]
        if pd.notna(aht) and pd.notna(tgt) and tgt > 0:
            var = (aht - tgt) / tgt * 100
            idx = cols.index("AHT")
            styles[idx] = _colour_aht_var(var)

    # ABN% and ASA vs their targets
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


def _summary_to_html_table(
    df: pd.DataFrame,
    show_greeting: bool = True,
    lob_col_label: str = "LOB",
    table_key: str = None,
) -> str:
    """HTML table with inline conditional colours — pastes into Outlook/Word/Excel
    with green/yellow/red cells preserved, matching the dashboard display.

    Parameters
    ----------
    show_greeting   : prepend "Hi Team, See performance below:" (main table only)
    lob_col_label   : header text for the LOB column (use vendor name for vendor tables)
    table_key       : session-state key prefix for saved lob_comments lookup
    """
    import re as _re

    # ── Sort: NCO descending, Grand Total pinned last (mirrors _display_summary) ──
    _gt   = df[df["LOB"] == "Grand Total"]
    _lobs = df[df["LOB"] != "Grand Total"].sort_values("NCO", ascending=False)
    df    = pd.concat([_lobs, _gt], ignore_index=True)

    display_cols = [
        "LOB", "NCO", "NCH",
        "Target AHT", "AHT", "AHT Var%",
        "ABN", "Target ABN%", "ABN%",
        "Target ASA", "ASA", "Comment / Action",
    ]
    data_cols = [c for c in display_cols if c in df.columns or c == "Comment / Action"]

    # Mid-tone blue — readable in Outlook light mode, still clearly a header
    HDR_BG    = "#2e75b6"
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
        return str(val) if pd.notna(val) else "—"

    def _get_comment(row) -> str:
        """Return the saved comment or auto-generated analysis for this row."""
        lob = str(row.get("LOB", ""))
        if lob == "Grand Total":
            return ""
        # 1. Try the persisted / user-typed comment
        if table_key:
            saved = st.session_state.get("lob_comments", {}).get(f"{table_key}:{lob}", "")
            if saved:
                return _re.sub(r"\*\*(.+?)\*\*", r"\1", saved)  # strip markdown bold
        # 2. Fall back to the auto-generated driver brief
        brief = _abn_driver_brief(row)
        return _re.sub(r"\*\*(.+?)\*\*", r"\1", brief)

    rows_html = []

    # Header row — replace "LOB" column label with lob_col_label
    def _col_label(c):
        return lob_col_label if c == "LOB" else c

    ths = "".join(
        f'<th style="background:{HDR_BG};color:white;padding:7px 10px;'
        f'border:1px solid #888;white-space:nowrap;font-weight:bold">{_col_label(c)}</th>'
        for c in data_cols
    )
    rows_html.append(f"<tr>{ths}</tr>")

    for _, row in df.iterrows():
        is_total = str(row.get("LOB", "")) == "Grand Total"
        base_bg  = TOTAL_BG if is_total else "white"
        fw       = "bold"   if is_total else "normal"
        tds = []
        for col in data_cols:
            if col == "Comment / Action":
                val     = float("nan")
                fmt_val = _get_comment(row)
                bg, fg  = None, None
            else:
                val     = row.get(col, float("nan"))
                bg, fg  = _cell_colors(col, val, row) if not is_total else (None, None)
                fmt_val = _fmt(col, val)
            cell_bg = bg or base_bg
            cell_fg = fg or "inherit"
            align   = "left" if col in ("LOB", "Comment / Action") else "center"
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
    prefix = (
        "<p><strong>Hi Team,</strong></p><p>See performance below:</p>"
        if show_greeting else ""
    )
    return prefix + table


# ── Mapping Manager helpers ────────────────────────────────────────────────────
_VENDOR_OPTIONS = ["TELUS", "VXI", "ATAIN", "HERTZ", "Other"]
_LOB_OPTIONS    = list(_LOB_ORDER) + ["Unknown"]


def _mapping_to_df(mapping_dict: dict) -> pd.DataFrame:
    """Convert a SKILL_TO_LOB-style dict to a display DataFrame."""
    rows = []
    for skill_key, entry in mapping_dict.items():
        parts = skill_key.split(": ", 1)
        skill_id   = parts[0].strip() if len(parts) == 2 else ""
        queue_name = parts[1].strip() if len(parts) == 2 else skill_key
        rows.append({
            "Skill ID":   skill_id,
            "Queue Name": queue_name,
            "LOB":        entry.get("lob",    ""),
            "Vendor":     entry.get("vendor", ""),
        })
    return pd.DataFrame(rows, columns=["Skill ID", "Queue Name", "LOB", "Vendor"])


def _df_to_mapping(df: pd.DataFrame) -> dict:
    """Convert the editable DataFrame back to a SKILL_TO_LOB-compatible dict."""
    mapping = {}
    for _, row in df.iterrows():
        skill_id   = str(row.get("Skill ID",   "")).strip()
        queue_name = str(row.get("Queue Name", "")).strip()
        lob        = str(row.get("LOB",        "")).strip()
        vendor     = str(row.get("Vendor",     "")).strip()
        if not queue_name or queue_name.lower() in ("nan", "none", ""):
            continue
        key = f"{skill_id}: {queue_name}" if skill_id else queue_name
        mapping[key] = {"lob": lob, "vendor": vendor}
    return mapping


def _get_mapping_df() -> pd.DataFrame:
    """Return the working mapping DataFrame from session state,
    seeding from the built-in mapping on first use."""
    if "mapping_df" not in st.session_state:
        st.session_state["mapping_df"] = _mapping_to_df(_BUILTIN_MAPPING)
        return st.session_state["mapping_df"]

    # Auto-sync once per session: update LOBs/Vendors and append new entries from built-in.
    if not st.session_state.get("_mapping_df_synced"):
        _mdf = st.session_state["mapping_df"].copy()
        _builtin_df = _mapping_to_df(_BUILTIN_MAPPING)
        _bl = {str(r["Queue Name"]).strip(): (str(r["LOB"]), str(r["Vendor"]))
               for _, r in _builtin_df.iterrows()}
        _qns = _mdf["Queue Name"].astype(str).str.strip()
        # Update LOB/Vendor for rows that exist in built-in
        for i, qn in _qns.items():
            if qn in _bl:
                _mdf.at[i, "LOB"]    = _bl[qn][0]
                _mdf.at[i, "Vendor"] = _bl[qn][1]
        # Append built-in entries not yet in the df
        _existing = set(_qns)
        _new_rows = _builtin_df[
            ~_builtin_df["Queue Name"].astype(str).str.strip().isin(_existing)
        ]
        if not _new_rows.empty:
            _mdf = pd.concat([_mdf, _new_rows], ignore_index=True)
        st.session_state["mapping_df"] = _mdf
        save_mapping_df(_mdf)
        st.session_state["_mapping_df_synced"] = True

    return st.session_state["mapping_df"]


def _import_from_tableau(file, current_df: pd.DataFrame) -> pd.DataFrame:
    """Parse a Tableau Excel export and merge into current_df.

    • Existing rows (matched by Skill ID) keep their LOB; Vendor is updated from the file.
    • New skills are appended with a blank LOB so the team can fill them in.
    • Returns the merged DataFrame.
    """
    raw = pd.read_excel(file)
    raw.columns = [str(c).strip() for c in raw.columns]

    # Resolve skill-key column
    for cand in ("Skill Name and Number", "Skill Name and Number (H)", "SkillName"):
        if cand in raw.columns:
            skill_col = cand
            break
    else:
        raise ValueError(f"No skill column found. Columns: {list(raw.columns)}")

    vendor_col = next((c for c in ("SupplierName", "Supplier Name", "Vendor") if c in raw.columns), None)
    id_col     = next((c for c in ("ExternalSkillID", "CustomSkillID") if c in raw.columns), None)

    # Deduplicate: one row per unique skill key
    seen_keys: set = set()
    new_rows = []
    for _, row in raw.iterrows():
        skill_key = str(row.get(skill_col, "")).strip()
        if not skill_key or skill_key.lower() in ("nan", "none") or skill_key in seen_keys:
            continue
        seen_keys.add(skill_key)

        parts      = skill_key.split(": ", 1)
        skill_id   = str(row.get(id_col, parts[0].strip() if len(parts) == 2 else "")).strip() if id_col else (parts[0].strip() if len(parts) == 2 else "")
        queue_name = parts[1].strip() if len(parts) == 2 else skill_key
        vendor     = str(row.get(vendor_col, "")).strip() if vendor_col else ""
        new_rows.append({"Skill ID": skill_id, "Queue Name": queue_name, "_vendor_import": vendor})

    imported = pd.DataFrame(new_rows) if new_rows else pd.DataFrame(
        columns=["Skill ID", "Queue Name", "_vendor_import"])

    # Build a lookup from the current editable table: Skill ID → (LOB, Vendor)
    existing_lookup = {}
    for _, r in current_df.iterrows():
        sid = str(r.get("Skill ID", "")).strip()
        if sid:
            existing_lookup[sid] = (str(r.get("LOB", "")), str(r.get("Vendor", "")))

    merged_rows = []
    for _, r in imported.iterrows():
        sid = str(r["Skill ID"]).strip()
        existing_lob, existing_vendor = existing_lookup.get(sid, ("", ""))
        merged_rows.append({
            "Skill ID":   sid,
            "Queue Name": str(r["Queue Name"]).strip(),
            "LOB":        existing_lob,                          # preserve existing LOB
            "Vendor":     str(r["_vendor_import"]).strip() or existing_vendor,
        })

    return pd.DataFrame(merged_rows, columns=["Skill ID", "Queue Name", "LOB", "Vendor"])


# ── Targets Manager helpers ────────────────────────────────────────────────────

def _targets_to_df(targets: dict) -> pd.DataFrame:
    """Convert a TARGETS-style dict to an editable DataFrame.
    ABN is stored internally as a ratio; displayed as % for readability.
    """
    from src.mapping import LOB_DISPLAY_ORDER as _order
    rows = []
    # Display in LOB order, then any extras
    ordered = list(_order) + [l for l in targets if l not in _order]
    for lob in ordered:
        if lob not in targets:
            continue
        t = targets[lob]
        rows.append({
            "LOB":            lob,
            "Target AHT (s)": int(t.get("aht", 400)),
            "Target ASA (s)": int(t.get("asa", 30)),
            "Target ABN%":    round(t.get("abn", 0.05) * 100, 2),
        })
    return pd.DataFrame(rows, columns=["LOB", "Target AHT (s)", "Target ASA (s)", "Target ABN%"])


def _df_to_targets(df: pd.DataFrame) -> dict:
    """Convert the editable targets DataFrame back to the internal dict format."""
    targets = {}
    for _, row in df.iterrows():
        lob = str(row.get("LOB", "")).strip()
        if not lob or lob.lower() in ("nan", "none", ""):
            continue
        try:
            targets[lob] = {
                "aht": float(row.get("Target AHT (s)", 400)),
                "asa": float(row.get("Target ASA (s)", 30)),
                "abn": round(float(row.get("Target ABN%", 5)) / 100, 4),
            }
        except (ValueError, TypeError):
            continue
    return targets


def _get_targets_df() -> pd.DataFrame:
    """Return the working targets DataFrame, seeding from built-in on first use."""
    if "targets_df" not in st.session_state:
        active = st.session_state.get("custom_targets") or _BUILTIN_TARGETS
        st.session_state["targets_df"] = _targets_to_df(active)

    # Auto-sync: add new built-in LOBs missing from the targets df
    if not st.session_state.get("_targets_df_synced"):
        _tdf = st.session_state["targets_df"]
        _existing_lobs = set(_tdf["LOB"].astype(str).str.strip())
        _new_lob_rows = [
            {"LOB": lob,
             "Target AHT (s)": int(t.get("aht", 400)),
             "Target ASA (s)": int(t.get("asa", 30)),
             "Target ABN%":    round(t.get("abn", 0.05) * 100, 2)}
            for lob, t in _BUILTIN_TARGETS.items()
            if lob not in _existing_lobs
        ]
        if _new_lob_rows:
            _tdf = pd.concat([_tdf, pd.DataFrame(_new_lob_rows)], ignore_index=True)
            st.session_state["targets_df"] = _tdf
            _ct = _df_to_targets(_tdf)
            st.session_state["custom_targets"] = _ct
            save_targets(_ct)
        st.session_state["_targets_df_synced"] = True

    return st.session_state["targets_df"]


def _parse_targets_upload(file) -> dict:
    """Parse an Excel or CSV file into a targets dict.

    Expected columns (case-insensitive): LOB, AHT, ASA, ABN (or ABN%)
    ABN may be stored as ratio (0.03) or percentage (3) — auto-detected.
    """
    fname = getattr(file, "name", "").lower()
    if fname.endswith((".xlsx", ".xls")):
        df = pd.read_excel(file)
    else:
        df = pd.read_csv(file)
    df.columns = [str(c).strip() for c in df.columns]
    cols_l = {c.lower(): c for c in df.columns}

    lob_col = next((cols_l[k] for k in cols_l if k in ("lob", "line of business")), None)
    aht_col = next((cols_l[k] for k in cols_l if "aht" in k), None)
    asa_col = next((cols_l[k] for k in cols_l if "asa" in k), None)
    abn_col = next((cols_l[k] for k in cols_l if "abn" in k), None)

    if not lob_col:
        raise ValueError(f"No LOB column found. Columns: {list(df.columns)}")

    targets = {}
    for _, row in df.iterrows():
        lob = str(row.get(lob_col, "")).strip()
        if not lob or lob.lower() in ("nan", "none", ""):
            continue
        aht = float(row[aht_col]) if aht_col and pd.notna(row.get(aht_col)) else 400
        asa = float(row[asa_col]) if asa_col and pd.notna(row.get(asa_col)) else 30
        abn_raw = float(row[abn_col]) if abn_col and pd.notna(row.get(abn_col)) else 5
        # Auto-detect: if ABN ≥ 1 assume it's already a percentage, divide by 100
        abn_ratio = abn_raw / 100 if abn_raw >= 1 else abn_raw
        targets[lob] = {"aht": aht, "asa": asa, "abn": round(abn_ratio, 4)}

    if not targets:
        raise ValueError("No valid LOB rows found in the uploaded file.")
    return targets


_COL_WIDTHS = {
    "LOB":         160,
    "NCO":          80,
    "NCH":          80,
    "Target AHT":   80,
    "AHT":          80,
    "AHT Var%":     80,
    "ABN":          80,
    "Target ABN%":  80,
    "ABN%":         80,
    "Target ASA":   80,
    "ASA":          80,
    "Analysis":    500,
}

# LOBs hidden from all tabs — Grand Total row is always kept
_HIDDEN_LOBS = {"OPERATIONS"}


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

    # Persistent comment store — survives new file uploads, cleared only by Clear button
    if "lob_comments" not in st.session_state:
        st.session_state["lob_comments"] = {}

    # ── Capture any pending edits BEFORE re-rendering ─────────────────────────
    # Streamlit's data_editor stores the delta (edited_rows) in session state
    # keyed by the widget key. We flush those deltas into lob_comments NOW,
    # using the LOB order recorded on the previous render.  This prevents edits
    # from being lost when the Styler object changes between reruns.
    _order_key  = f"lob_order_{table_key}"
    _prev_lobs  = st.session_state.get(_order_key, [])
    _widget_state = st.session_state.get(f"editor_{table_key}", {})
    _comments_changed = False
    for _idx_str, _changes in _widget_state.get("edited_rows", {}).items():
        if "Analysis" in _changes:
            try:
                _idx = int(_idx_str)
                if 0 <= _idx < len(_prev_lobs):
                    _lob = _prev_lobs[_idx]
                    if _lob:
                        st.session_state["lob_comments"][f"{table_key}:{_lob}"] = str(_changes["Analysis"])
                        _comments_changed = True
            except (ValueError, TypeError):
                pass
    if _comments_changed:
        save_comments(st.session_state["lob_comments"])

    df = df.copy()
    # Populate Analysis: use saved comment if present, else auto-generate
    df["Analysis"] = df.apply(
        lambda row: st.session_state["lob_comments"].get(
            f"{table_key}:{row.get('LOB', '')}",
            _abn_driver_brief(row)
        ),
        axis=1,
    )

    present = [c for c in display_cols if c in df.columns]
    view    = df[present].copy()

    # Record the LOB order used this render so the next render can map
    # edited_rows indices back to LOB names
    st.session_state[_order_key] = list(view["LOB"])

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
    _row_h = 36
    _tbl_h = (len(view) + 1) * _row_h + 4
    result = st.data_editor(
        styled,
        column_config=col_cfg,
        disabled=disabled_cols,
        hide_index=True,
        use_container_width=True,
        height=_tbl_h,
        key=f"editor_{table_key}",
        num_rows="fixed",
    )

    # Secondary save: iterate the full result as a fallback (covers the case
    # where edits arrive via result but not via edited_rows delta)
    if result is not None and "LOB" in result.columns and "Analysis" in result.columns:
        _sec_changed = False
        for _, row in result.iterrows():
            lob = str(row.get("LOB", ""))
            # Only persist non-empty values so we don't overwrite a comment with ""
            val = str(row.get("Analysis", "")).strip()
            if lob and val:
                old = st.session_state["lob_comments"].get(f"{table_key}:{lob}", "")
                if val != old:
                    st.session_state["lob_comments"][f"{table_key}:{lob}"] = val
                    _sec_changed = True
        if _sec_changed:
            save_comments(st.session_state["lob_comments"])


def _copy_email_button(
    df: pd.DataFrame,
    key: str,
    show_greeting: bool = True,
    lob_col_label: str = "LOB",
    table_key: str = None,
) -> None:
    """Render a 'Copy for Email' button.

    Clicking it copies the summary table as rich HTML to the clipboard.
    Green / yellow / red cell colours are preserved when pasting into
    Outlook, Gmail, Word, or any HTML-aware email client.

    Uses document.execCommand('copy') on a selected hidden div — this
    works inside Streamlit's sandboxed iframe (the newer Clipboard API
    does not without explicit allow="clipboard-write" on the iframe).
    """
    import json as _json

    html_content = _summary_to_html_table(
        df,
        show_greeting=show_greeting,
        lob_col_label=lob_col_label,
        table_key=table_key,
    )
    html_js      = _json.dumps(html_content)   # properly escaped JS string literal
    fn           = f"doCopy_{key}"
    bid          = f"copybtn_{key}"

    components.html(f"""
<style>
  body {{ margin:0; padding:0; }}
  .cbwrap button {{
    background: linear-gradient(135deg, #1a3a5c 0%, #0a1628 100%);
    color: #FFD700;
    border: 1.5px solid rgba(255,215,0,0.45);
    border-radius: 8px;
    padding: 5px 10px;
    font-size: 12px;
    font-weight: 700;
    cursor: pointer;
    font-family: Inter, Arial, sans-serif;
    letter-spacing: 0.3px;
    width: 100%;
    white-space: nowrap;
    transition: all 0.2s ease;
  }}
  .cbwrap button:hover {{
    background: linear-gradient(135deg, #264a72 0%, #152238 100%);
    border-color: #FFD700;
    box-shadow: 0 3px 12px rgba(255,215,0,0.25);
  }}
</style>
<div class="cbwrap">
  <button id="{bid}" onclick="{fn}()">📋 Copy for Email</button>
</div>
<script>
function {fn}() {{
  var html = {html_js};
  // Create a hidden element with the formatted HTML table
  var el = document.createElement('div');
  el.innerHTML = html;
  el.style.position = 'fixed';
  el.style.left = '-9999px';
  el.style.top  = '0';
  document.body.appendChild(el);
  // Select the element and copy — preserves rich HTML in clipboard
  var range = document.createRange();
  range.selectNodeContents(el);
  var sel = window.getSelection();
  sel.removeAllRanges();
  sel.addRange(range);
  var ok = false;
  try {{ ok = document.execCommand('copy'); }} catch(e) {{}}
  sel.removeAllRanges();
  document.body.removeChild(el);
  // Visual feedback
  var btn = document.getElementById('{bid}');
  if (ok) {{
    btn.textContent = '✅ Copied!';
    btn.style.background = 'linear-gradient(135deg,#1a5e1a,#2a7a2a)';
    btn.style.color = '#fff';
    btn.style.borderColor = '#4ade80';
  }} else {{
    btn.textContent = '⚠️ Press Ctrl+C';
    btn.style.borderColor = '#ffa500';
  }}
  setTimeout(function() {{
    btn.textContent = '📋 Copy for Email';
    btn.style.background = '';
    btn.style.color = '';
    btn.style.borderColor = '';
  }}, 2500);
}}
</script>
""", height=36, scrolling=False)


def _merge_editor_edits(df: pd.DataFrame, table_key: str) -> pd.DataFrame:
    """Overlay user edits from st.data_editor session state onto df."""
    state = st.session_state.get(f"editor_{table_key}", {})
    edited = state.get("edited_rows", {})
    df = df.copy()
    for row_idx_str, changes in edited.items():
        row_idx = int(row_idx_str)
        for col, val in changes.items():
            if row_idx < len(df) and col in df.columns:
                df.at[row_idx, col] = val
    return df


@st.dialog("📊 Performance by Line of Business", width="large")
def _summary_dialog(df: pd.DataFrame, table_key: str):
    """Render full table as static HTML — no internal scroll, screenshot-ready."""
    # Force dialog to 92vw so Analysis column shows fully
    st.markdown("""
    <style>
    div[role="dialog"] { max-width: 92vw !important; width: 92vw !important; }
    </style>
    """, unsafe_allow_html=True)

    df = df.copy()
    df["Analysis"] = df.apply(_abn_driver_brief, axis=1)

    gt   = df[df["LOB"] == "Grand Total"]
    lobs = df[df["LOB"] != "Grand Total"].sort_values("NCO", ascending=False)
    df   = pd.concat([lobs, gt], ignore_index=True)

    # Overlay any user edits from the live data_editor
    df = _merge_editor_edits(df, table_key)

    display_cols = ["LOB", "NCO", "NCH", "Target AHT", "AHT", "AHT Var%",
                    "ABN", "Target ABN%", "ABN%", "Target ASA", "ASA", "Analysis"]
    present = [c for c in display_cols if c in df.columns]

    HDR_BG    = "#1a3a5c"
    TOTAL_BG  = "#cce8e8"
    GREEN_BG  = "#C8F0C8"; GREEN_FG  = "#1a5e1a"
    YELLOW_BG = "#FFF4CC"; YELLOW_FG = "#7a5c00"
    RED_BG    = "#FFD0D0"; RED_FG    = "#8b0000"

    def _cell_color(col, val, row):
        if pd.isna(val):
            return None, None
        if col == "AHT Var%":
            if val <= 0:  return GREEN_BG,  GREEN_FG
            if val <= 5:  return YELLOW_BG, YELLOW_FG
            return RED_BG, RED_FG
        if col == "AHT":
            # Color AHT the same shade as its variance (mirrors main table _colour_row)
            try:
                aht_var = float(row.get("AHT Var%", float("nan")))
            except (TypeError, ValueError):
                aht_var = float("nan")
            if pd.isna(aht_var):
                return None, None
            if aht_var <= 0:  return GREEN_BG,  GREEN_FG
            if aht_var <= 5:  return YELLOW_BG, YELLOW_FG
            return RED_BG, RED_FG
        if col in ("ABN%", "ASA"):
            tgt_col = "Target ABN%" if col == "ABN%" else "Target ASA"
            tgt = row.get(tgt_col, float("nan"))
            if pd.notna(tgt):
                if val <= tgt:        return GREEN_BG,  GREEN_FG
                if val <= tgt * 1.1:  return YELLOW_BG, YELLOW_FG
                return RED_BG, RED_FG
        return None, None

    def _fmt_cell(col, val):
        if col in ("Target AHT", "AHT"):               return _fmt_seconds_int(val)
        if col in ("Target ASA", "ASA"):               return _fmt_seconds(val)
        if col in ("AHT Var%", "ABN%", "Target ABN%"): return _fmt_pct(val)
        if col in ("NCO", "NCH", "ABN"):               return _fmt_int(val)
        if col == "Analysis":                          return str(val) if val else ""
        return str(val) if pd.notna(val) else "—"

    # Proportional widths for table-layout:fixed;width:100% at 92vw.
    # LOB=130, 10 metrics=72px each (uniform), Analysis=450 → ratios preserved at full width.
    _DLG_W = {
        "LOB": 130, "NCO": 72, "NCH": 72,
        "Target AHT": 72, "AHT": 72, "AHT Var%": 72,
        "ABN": 72, "Target ABN%": 72, "ABN%": 72,
        "Target ASA": 72, "ASA": 72, "Analysis": 450,
    }
    left_cols   = {"LOB", "Analysis"}
    col_labels  = {"Analysis": "Analysis / Notes"}

    cols_html = "".join(f'<col style="width:{_DLG_W.get(c, 53)}px">' for c in present)
    ths = "".join(
        f'<th style="background:{HDR_BG};color:white;padding:5px 6px;'
        f'border:1px solid #667;font-size:11px;font-weight:700;'
        f'text-align:{"left" if c in left_cols else "center"}">'
        f'{col_labels.get(c, c)}</th>'
        for c in present
    )
    rows_html = [f"<tr>{ths}</tr>"]

    for _, row in df.iterrows():
        is_total = str(row.get("LOB", "")) == "Grand Total"
        base_bg  = TOTAL_BG if is_total else "white"
        fw       = "bold"   if is_total else "normal"
        tds = []
        for col in present:
            val = row.get(col, float("nan"))
            if col == "Analysis":
                bg, fg = None, None
            else:
                try:
                    raw_val = float(val)
                except (TypeError, ValueError):
                    raw_val = float("nan")
                bg, fg = _cell_color(col, raw_val, row) if not is_total else (None, None)
            cell_bg = bg or base_bg
            cell_fg = fg or "inherit"
            align   = "left" if col in left_cols else "center"
            fmt_val = _fmt_cell(col, val)
            tds.append(
                f'<td style="background:{cell_bg};color:{cell_fg};padding:4px 6px;'
                f'border:1px solid #dde;text-align:{align};font-weight:{fw};'
                f'font-size:11px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">'
                f'{fmt_val}</td>'
            )
        rows_html.append(f"<tr>{''.join(tds)}</tr>")

    table_html = (
        '<div style="overflow:hidden;width:100%">'
        '<table style="border-collapse:collapse;font-family:Inter,Arial,sans-serif;'
        'table-layout:fixed;width:100%">'
        f'<colgroup>{cols_html}</colgroup>'
        + "".join(rows_html)
        + "</table></div>"
    )
    st.markdown(table_html, unsafe_allow_html=True)
    st.markdown(
        "<div style='font-size:0.78em;margin-top:10px;display:flex;gap:10px;flex-wrap:wrap'>"
        "<span style='background:#C8F0C8;padding:2px 8px;border-radius:10px;color:#1a5e1a;font-weight:600'>■ At / below target</span>"
        "<span style='background:#FFF4CC;padding:2px 8px;border-radius:10px;color:#7a5c00;font-weight:600'>■ Within 10% of target</span>"
        "<span style='background:#FFD0D0;padding:2px 8px;border-radius:10px;color:#8b0000;font-weight:600'>■ Exceeds target</span>"
        "</div>",
        unsafe_allow_html=True,
    )


@st.dialog("⏱️ 30-Minute Interval Breakdown", width="large")
def _interval_dialog(df: pd.DataFrame):
    """Render interval table as static HTML — no internal scroll, screenshot-ready."""
    st.markdown("""
    <style>
    div[role="dialog"] { max-width: 92vw !important; width: 92vw !important; }
    </style>
    """, unsafe_allow_html=True)

    display_cols = ["Interval", "LOB", "Vendor", "NCO", "NCH",
                    "Target AHT", "AHT", "AHT Var%",
                    "ABN", "Target ABN%", "ABN%", "Target ASA", "ASA"]
    present = [c for c in display_cols if c in df.columns]

    HDR_BG    = "#1a3a5c"
    GREEN_BG  = "#C8F0C8"; GREEN_FG  = "#1a5e1a"
    YELLOW_BG = "#FFF4CC"; YELLOW_FG = "#7a5c00"
    RED_BG    = "#FFD0D0"; RED_FG    = "#8b0000"

    def _cell_color(col, val, row):
        if pd.isna(val):
            return None, None
        if col == "AHT Var%":
            if val <= 0:  return GREEN_BG,  GREEN_FG
            if val <= 5:  return YELLOW_BG, YELLOW_FG
            return RED_BG, RED_FG
        if col == "AHT":
            try:
                aht_var = float(row.get("AHT Var%", float("nan")))
            except (TypeError, ValueError):
                aht_var = float("nan")
            if pd.isna(aht_var):
                return None, None
            if aht_var <= 0:  return GREEN_BG,  GREEN_FG
            if aht_var <= 5:  return YELLOW_BG, YELLOW_FG
            return RED_BG, RED_FG
        if col in ("ABN%", "ASA"):
            tgt_col = "Target ABN%" if col == "ABN%" else "Target ASA"
            tgt = row.get(tgt_col, float("nan"))
            if pd.notna(tgt):
                if val <= tgt:        return GREEN_BG,  GREEN_FG
                if val <= tgt * 1.1:  return YELLOW_BG, YELLOW_FG
                return RED_BG, RED_FG
        return None, None

    def _fmt_cell(col, val):
        if col in ("Target AHT", "AHT"):               return _fmt_seconds_int(val)
        if col in ("Target ASA", "ASA"):               return _fmt_seconds(val)
        if col in ("AHT Var%", "ABN%", "Target ABN%"): return _fmt_pct(val)
        if col in ("NCO", "NCH", "ABN"):               return _fmt_int(val)
        return str(val) if pd.notna(val) else "—"

    _iv_widths = {
        "Interval": 65, "LOB": 120, "Vendor": 80,
        "NCO": 72, "NCH": 72,
        "Target AHT": 72, "AHT": 72, "AHT Var%": 72,
        "ABN": 72, "Target ABN%": 72, "ABN%": 72,
        "Target ASA": 72, "ASA": 72,
    }
    left_cols_iv = {"LOB", "Vendor", "Interval"}

    cols_html = "".join(f'<col style="width:{_iv_widths.get(c, 53)}px">' for c in present)
    ths = "".join(
        f'<th style="background:{HDR_BG};color:white;padding:5px 6px;'
        f'border:1px solid #667;font-size:11px;font-weight:700;'
        f'text-align:{"left" if c in left_cols_iv else "center"}">{c}</th>'
        for c in present
    )
    rows_html = [f"<tr>{ths}</tr>"]
    for _, row in df.iterrows():
        tds = []
        for col in present:
            val = row.get(col, float("nan"))
            try:
                num_val = float(val)
            except (TypeError, ValueError):
                num_val = float("nan")
            bg, fg = _cell_color(col, num_val, row)
            cell_bg = bg or "white"
            cell_fg = fg or "inherit"
            align = "left" if col in left_cols_iv else "center"
            tds.append(
                f'<td style="background:{cell_bg};color:{cell_fg};padding:4px 6px;'
                f'border:1px solid #dde;text-align:{align};font-size:11px;'
                f'overflow:hidden;text-overflow:ellipsis;white-space:nowrap">'
                f'{_fmt_cell(col, val)}</td>'
            )
        rows_html.append(f"<tr>{''.join(tds)}</tr>")

    st.markdown(
        '<div style="overflow:hidden;width:100%">'
        '<table style="border-collapse:collapse;font-family:Inter,Arial,sans-serif;'
        'table-layout:fixed;width:100%">'
        f'<colgroup>{cols_html}</colgroup>'
        + "".join(rows_html)
        + "</table></div>",
        unsafe_allow_html=True,
    )


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
    st.markdown(
        """
        <style>
        @keyframes logoPulse {
            0%,100% { box-shadow: 0 4px 18px rgba(255,215,0,0.45), 0 0 0 0 rgba(255,215,0,0.2); }
            50%      { box-shadow: 0 6px 26px rgba(255,215,0,0.65), 0 0 18px rgba(255,215,0,0.18); }
        }
        @keyframes subtitleShift {
            0%,100% { color: rgba(255,215,0,0.65); }
            50%      { color: rgba(255,215,0,0.95); }
        }
        </style>
        <div style='text-align:center; padding:22px 0 12px'>
          <div style='display:inline-block; background:linear-gradient(135deg,#FFD700 0%,#f5c400 60%,#e8b000 100%);
                      padding:8px 26px; border-radius:7px;
                      animation:logoPulse 3s ease-in-out infinite;'>
            <span style='font-family:Arial Black,Impact,sans-serif;
                         font-size:28px; font-weight:900; color:#0a1220;
                         letter-spacing:3px; line-height:1'>HERTZ</span>
          </div>
          <div style='font-size:9px; letter-spacing:3.5px; margin-top:10px;
                      text-transform:uppercase; font-weight:700;
                      animation:subtitleShift 3s ease-in-out infinite;'>
            Powered by Callinsite
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.markdown("---")

    # ── Data source toggle ────────────────────────────────────────────────────
    st.markdown("### 📂 Data Source")
    data_source = st.radio(
        "data_source",
        options=["📁 Upload CSV", "☁️ SharePoint"],
        index=0,
        label_visibility="collapsed",
    )

    uploaded = None
    sp_load_clicked = False

    if data_source == "📁 Upload CSV":
        st.markdown("**Upload CSV files**")
        uploaded = st.file_uploader(
            "Upload one or more CSV files",
            type="csv",
            accept_multiple_files=True,
            label_visibility="collapsed",
        )
        # Persist uploaded bytes in session state so refreshes don't wipe the data
        if uploaded:
            st.session_state["stored_files"] = [
                {"name": f.name, "data": f.read()} for f in uploaded
            ]
        # Clear button — only show when data is stored
        if st.session_state.get("stored_files"):
            if st.button("🗑️ Clear Data", use_container_width=True):
                st.session_state.pop("stored_files", None)
                st.session_state.pop("sp_raw", None)
                st.session_state.pop("lob_comments", None)
                clear_comments()   # also wipe disk so other users see clean state
                st.rerun()
        st.caption("Columns: SkillName, SupplierName, Interval, NCO, NCH, AHT, ABN, ASA")

    else:  # SharePoint
        st.markdown(f"**Connect to SharePoint**")
        st.caption(f"📂 `{_SP_HOSTNAME}/sites/HertzWFM`")

        _token_info = st.session_state.get("sp_token_info")
        _logged_in  = _token_info and _sp_get_valid_token() is not None

        if _logged_in:
            # ── Already authenticated ──────────────────────────────────────
            st.success(f"✅ Signed in as **{_token_info['username']}**")
            sp_load_clicked = st.button(
                "🔄 Load / Refresh Data",
                use_container_width=True,
                key="sp_load_btn",
            )
            if st.button("🔓 Sign Out", use_container_width=True, key="sp_signout_btn"):
                st.session_state.pop("sp_token_info", None)
                st.session_state.pop("sp_raw",        None)
                st.rerun()
        else:
            # ── Login form ─────────────────────────────────────────────────
            st.markdown("Sign in with your Microsoft 365 account:")
            _sp_user = st.text_input(
                "Email", key="sp_username",
                placeholder="you@callinsite.com",
                label_visibility="collapsed",
            )
            _sp_pass = st.text_input(
                "Password", key="sp_password",
                type="password",
                placeholder="Password",
                label_visibility="collapsed",
            )
            if st.button("🔐 Connect to SharePoint", use_container_width=True, key="sp_login_btn"):
                if not _sp_user or not _sp_pass:
                    st.error("Enter your email and password.")
                else:
                    with st.spinner("Signing in…"):
                        try:
                            _tok = _sp_acquire_token(_sp_user.strip(), _sp_pass)
                            st.session_state["sp_token_info"] = _tok
                            st.rerun()
                        except Exception as _e:
                            st.error(str(_e))
            st.caption(
                "⚠️ Your account must not have MFA enforced, "
                "or use an **App Password** instead of your regular password."
            )

# ── Load & process ────────────────────────────────────────────────────────────
summary_df = pd.DataFrame()
vendor_summaries: dict = {}
interval_df = pd.DataFrame()
data_ok = False
call_date: str = None

if data_source == "📁 Upload CSV":
    stored = st.session_state.get("stored_files")
    if stored:
        import io as _io
        frames = []
        for f in stored:
            try:
                frames.append(pd.read_csv(_io.BytesIO(f["data"])))
            except Exception as e:
                st.sidebar.warning(f"Could not read {f['name']}: {e}")
        raw = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
        if not raw.empty:
            if "CallDate" in raw.columns:
                try:
                    call_date = pd.to_datetime(raw["CallDate"], errors="coerce").max().strftime("%m/%d/%Y")
                except Exception:
                    call_date = None
            _active_mapping  = st.session_state.get("custom_mapping")   # None → use built-in
            _active_targets  = st.session_state.get("custom_targets")   # None → use built-in
            summary_df, vendor_summaries, interval_df = prepare(
                raw, custom_mapping=_active_mapping, custom_targets=_active_targets
            )
            data_ok = True
        else:
            st.warning("No data could be read from the stored files.")
    else:
        st.info("⬆️ Upload your CSV files from the sidebar to load the dashboard.")

else:  # SharePoint
    _cur_token = _sp_get_valid_token()
    if _cur_token:
        # Load on button click OR re-use previously loaded data stored in session
        if sp_load_clicked:
            st.session_state.pop("sp_raw_df", None)   # force fresh pull

        if "sp_raw_df" not in st.session_state:
            if sp_load_clicked or st.session_state.get("sp_auto_load"):
                try:
                    with st.spinner("Loading CSVs from SharePoint…"):
                        _raw_sp = _sp_load(_cur_token)
                    st.session_state["sp_raw_df"]   = _raw_sp
                    st.session_state["sp_auto_load"] = True
                except Exception as _exc:
                    st.error(f"SharePoint error: {_exc}")

        _raw_sp = st.session_state.get("sp_raw_df")
        if _raw_sp is not None and not _raw_sp.empty:
            if "CallDate" in _raw_sp.columns:
                try:
                    call_date = (
                        pd.to_datetime(_raw_sp["CallDate"], errors="coerce")
                        .max().strftime("%m/%d/%Y")
                    )
                except Exception:
                    call_date = None
            _active_mapping  = st.session_state.get("custom_mapping")
            _active_targets  = st.session_state.get("custom_targets")
            summary_df, vendor_summaries, interval_df = prepare(
                _raw_sp, custom_mapping=_active_mapping, custom_targets=_active_targets
            )
            data_ok = True
        elif _raw_sp is not None:
            st.warning("No CSV files found in the SharePoint folder.")
        else:
            st.info("☁️ Click **🔄 Load / Refresh Data** in the sidebar to fetch data.")
    elif st.session_state.get("sp_token_info"):
        # Token expired
        st.warning("⏱️ SharePoint session expired — please sign in again in the sidebar.")
    else:
        st.info("☁️ Sign in to SharePoint using the sidebar to load data.")

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
    <style>
    @keyframes hdrGradient {{
        0%   {{ background-position: 0% 50%; }}
        50%  {{ background-position: 100% 50%; }}
        100% {{ background-position: 0% 50%; }}
    }}
    @keyframes hdrBeam {{
        0%   {{ left: -55%; opacity: 0; }}
        15%  {{ opacity: 1; }}
        85%  {{ opacity: 1; }}
        100% {{ left: 130%; opacity: 0; }}
    }}
    @keyframes livePulse {{
        0%,100% {{ box-shadow: 0 0 0 0 rgba(74,222,128,0.55); }}
        50%      {{ box-shadow: 0 0 0 5px rgba(74,222,128,0); }}
    }}
    .hdr-wrap {{
        background: linear-gradient(-50deg, #040d1a, #0a1628, #193860, #1d4675, #112244, #040d1a);
        background-size: 350% 350%;
        animation: hdrGradient 10s ease infinite;
        padding: 22px 36px;
        border-radius: 16px;
        margin-bottom: 18px;
        border-bottom: 3px solid #FFD700;
        box-shadow: 0 8px 36px rgba(6,16,34,0.38), 0 2px 8px rgba(0,0,0,0.2);
        display: flex;
        align-items: center;
        justify-content: space-between;
        position: relative;
        overflow: hidden;
    }}
    .hdr-beam {{
        position: absolute;
        top: 0; left: -55%;
        width: 40%; height: 100%;
        background: linear-gradient(90deg, transparent, rgba(255,215,0,0.06), rgba(255,255,255,0.04), transparent);
        animation: hdrBeam 7s ease-in-out infinite;
        pointer-events: none;
    }}
    .hdr-eyebrow {{
        font-size: 10px; color: #FFD700; font-weight: 800;
        letter-spacing: 2.8px; text-transform: uppercase;
        margin-bottom: 5px; opacity: 0.92;
    }}
    .hdr-title {{
        font-size: 27px; font-weight: 900; color: white;
        line-height: 1.1; letter-spacing: -0.6px;
    }}
    .live-badge {{
        display: flex; align-items: center; gap: 8px;
        background: rgba(255,215,0,0.12);
        border: 1px solid rgba(255,215,0,0.35);
        border-radius: 10px; padding: 7px 16px;
        font-size: 12px; color: #FFD700; font-weight: 700; letter-spacing: 1px;
    }}
    .live-dot {{
        width: 8px; height: 8px; border-radius: 50%;
        background: #4ade80;
        animation: livePulse 2s ease-in-out infinite;
        flex-shrink: 0;
    }}
    </style>
    <div class="hdr-wrap">
      <div class="hdr-beam"></div>
      <div>
        <div class="hdr-eyebrow">Hertz &nbsp;·&nbsp; Powered by Callinsite</div>
        <div class="hdr-title">{_data_as_of(interval_df, call_date)}</div>
      </div>
      <div class="live-badge">
        <div class="live-dot"></div>
        LIVE
      </div>
    </div>
    """,
    unsafe_allow_html=True,
)

# ── Refresh warning banner (only when data is loaded) ────────────────────────
if data_ok:
    st.markdown(
        """
        <div style='background:rgba(255,193,7,0.1); border:1px solid rgba(255,193,7,0.35);
                    border-left:4px solid #FFD700; border-radius:10px;
                    padding:11px 18px; margin-bottom:14px;
                    display:flex; align-items:center; gap:12px'>
          <span style='font-size:17px'>⚠️</span>
          <span style='font-size:13px; color:#5a4200; font-weight:500; line-height:1.4'>
            <strong>Do not refresh the page</strong> — uploaded data will be lost.
            Use the <strong>🗑️ Clear Data</strong> button in the sidebar to reset the dashboard.
          </span>
        </div>
        """,
        unsafe_allow_html=True,
    )

tab1, tab2, tab3, tab4 = st.tabs([
    "📊 Voice Performance Summary",
    "⏱️ Per Interval",
    "🗺️ Mapping Manager",
    "🎯 Targets Editor",
])

# ── Tab 1: Voice Performance Summary ─────────────────────────────────────────
with tab1:
    if data_ok and not summary_df.empty:
        # ── KPI headline tiles ─────────────────────────────────────────────────
        _kpi_cards(summary_df)
        st.markdown("<div style='margin-top:20px'></div>", unsafe_allow_html=True)

        _main_df = summary_df[
            (summary_df["LOB"] == "Grand Total") | (~summary_df["LOB"].isin(_HIDDEN_LOBS))
        ].reset_index(drop=True)

        hdr_col, copy_col, btn_col = st.columns([7, 2, 1])
        with hdr_col:
            st.subheader("Performance by Line of Business")
        with copy_col:
            st.markdown("<div style='padding-top:6px'></div>", unsafe_allow_html=True)
            _copy_email_button(
                _main_df, "main",
                show_greeting=True,
                lob_col_label="LOB",
                table_key="main",
            )
        with btn_col:
            st.markdown("<div style='padding-top:8px'></div>", unsafe_allow_html=True)
            if st.button("⛶", key="fs_main", help="Expand table to full screen", use_container_width=True):
                _summary_dialog(_main_df, "main")

        _display_summary(_main_df, table_key="main")

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
        _display_abn_analysis(
            summary_df[~summary_df["LOB"].isin(_HIDDEN_LOBS)],
            interval_df=interval_df,
        )

        # ── Per-vendor tables ──────────────────────────────────────────────────
        if vendor_summaries:
            st.markdown("---")
            st.subheader("Performance by Vendor / Supplier")
            vendor_order = ["TELUS", "VXI", "ATAIN", "HERTZ"]
            vendors_to_show = [v for v in vendor_order if v in vendor_summaries]
            vendors_to_show += [v for v in vendor_summaries if v not in vendor_order]
            for vendor in vendors_to_show:
                vdf = vendor_summaries[vendor]
                # Hide LOBs in _HIDDEN_LOBS (keep Grand Total)
                vdf = vdf[
                    (vdf["LOB"] == "Grand Total") | (~vdf["LOB"].isin(_HIDDEN_LOBS))
                ].reset_index(drop=True)
                # HERTZ: suppress LOB rows that have no calls yet (NCO = 0 / blank)
                if vendor == "HERTZ":
                    mask = (vdf["LOB"] == "Grand Total") | (vdf["NCO"].fillna(0) > 0)
                    vdf = vdf[mask].reset_index(drop=True)

                v_hdr, v_copy, v_btn = st.columns([7, 2, 1])
                with v_hdr:
                    st.markdown(f"#### {vendor}")
                with v_copy:
                    st.markdown("<div style='padding-top:4px'></div>", unsafe_allow_html=True)
                    _copy_email_button(
                        vdf, f"vendor_{vendor}",
                        show_greeting=False,
                        lob_col_label=vendor,
                        table_key=f"vendor_{vendor}",
                    )
                with v_btn:
                    st.markdown("<div style='padding-top:6px'></div>", unsafe_allow_html=True)
                    if st.button("⛶", key=f"fs_vendor_{vendor}", help="Expand table to full screen", use_container_width=True):
                        _summary_dialog(vdf, f"vendor_{vendor}")

                _display_summary(vdf, table_key=f"vendor_{vendor}")
                _display_abn_analysis(vdf, interval_df=interval_df, vendor=vendor)

# ── Tab 2: Per Interval ───────────────────────────────────────────────────────
with tab2:
    if data_ok and not interval_df.empty:
        all_lobs = sorted(
            l for l in interval_df["LOB"].unique()
            if l not in ("Unknown", "", None) and l not in _HIDDEN_LOBS
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

        iv_hdr, iv_btn = st.columns([9, 1])
        with iv_hdr:
            st.subheader("30-Minute Interval Breakdown")
        with iv_btn:
            st.markdown("<div style='padding-top:8px'></div>", unsafe_allow_html=True)
            _iv_filtered = interval_df.copy()
            if lob_sel:
                _iv_filtered = _iv_filtered[_iv_filtered["LOB"].isin(lob_sel)]
            if vendor_sel:
                _iv_filtered = _iv_filtered[_iv_filtered["Vendor"].isin(vendor_sel)]
            if st.button("⛶", key="fs_interval", help="Expand table to full screen", use_container_width=True):
                _interval_dialog(_iv_filtered)
        _display_interval(interval_df, lob_sel, vendor_sel)
    elif data_ok:
        st.info("No interval data available in the loaded files.")

# ── Tab 3: Mapping Manager ────────────────────────────────────────────────────
with tab3:
    st.subheader("Skill → LOB Mapping")
    st.caption(
        "Edit the mapping below to control how each skill queue is assigned to a Line of Business "
        "and Vendor. Click **💾 Apply** to make it the active mapping for all report calculations. "
        "Click **↩️ Reset** to revert to the built-in defaults."
    )

    # ── Status banner ─────────────────────────────────────────────────────────
    _custom = st.session_state.get("custom_mapping")
    if _custom:
        n = len(_custom)
        st.success(f"✅ **Custom mapping active** — {n:,} skill entries in use")
    else:
        n = len(_BUILTIN_MAPPING)
        st.info(f"ℹ️ **Built-in mapping active** — {n:,} skill entries")

    st.markdown("---")

    # ── Import from Tableau Excel ─────────────────────────────────────────────
    with st.expander("📥 Import / update from Tableau Excel", expanded=False):
        st.markdown(
            "Upload the **Skill Name and ID from Tableau.xlsx** file to add or update entries. "
            "Existing LOB assignments are preserved — only new skills are added (with a blank LOB "
            "you can fill in below). Vendor is updated from the file."
        )
        xl_upload = st.file_uploader(
            "Upload Tableau mapping Excel",
            type=["xlsx", "xls"],
            key="mapping_xl_upload",
            label_visibility="collapsed",
        )
        if xl_upload:
            try:
                current = _get_mapping_df()
                merged  = _import_from_tableau(xl_upload, current)
                st.session_state["mapping_df"] = merged
                save_mapping_df(merged)   # persist so other users see the import
                blank_lob = (merged["LOB"] == "").sum()
                st.success(
                    f"✅ Imported {len(merged):,} unique skills. "
                    + (f"**{blank_lob} new skills** have a blank LOB — fill them in below and click Apply." if blank_lob else "All LOBs are mapped.")
                )
                st.rerun()
            except Exception as _err:
                st.error(f"Could not import: {_err}")

    st.markdown("---")

    # ── Editable mapping table ─────────────────────────────────────────────────
    _mdf = _get_mapping_df()

    _map_col_cfg = {
        "Skill ID": st.column_config.TextColumn(
            "Skill ID",
            width=120,
            help="Numeric skill ID (e.g. 20687271). Used to build the lookup key.",
        ),
        "Queue Name": st.column_config.TextColumn(
            "Queue Name",
            width=310,
            help="Skill/queue name (e.g. US_Hertz_VXI_Roadside_TNC).",
        ),
        "LOB": st.column_config.SelectboxColumn(
            "LOB",
            options=_LOB_OPTIONS,
            width=160,
            help="Line of Business this skill maps to.",
        ),
        "Vendor": st.column_config.SelectboxColumn(
            "Vendor",
            options=_VENDOR_OPTIONS,
            width=110,
            help="Vendor / Supplier handling this skill.",
        ),
    }

    _map_h = min(600, max(300, len(_mdf) * 36 + 40))

    # ── Search bar ────────────────────────────────────────────────────────────
    _search_query = st.text_input(
        "🔍 Search skills",
        placeholder="Type a Skill ID or Queue Name to check if it's mapped…",
        key="mapping_search",
        label_visibility="collapsed",
    )

    if _search_query.strip():
        _q = _search_query.strip().lower()
        _match = _mdf[
            _mdf["Skill ID"].astype(str).str.lower().str.contains(_q, na=False) |
            _mdf["Queue Name"].astype(str).str.lower().str.contains(_q, na=False)
        ]
        if _match.empty:
            st.error(f"❌ No match found for **{_search_query}** — this skill is not in the mapping yet.")
        else:
            st.success(f"✅ **{len(_match):,} match{'es' if len(_match) != 1 else ''}** found for **{_search_query}**")
            st.dataframe(
                _match.reset_index(drop=True),
                use_container_width=True,
                hide_index=True,
                height=min(300, (len(_match) + 1) * 36 + 4),
            )
        st.markdown("---")

    st.caption(
        f"**{len(_mdf):,} entries** · "
        "Double-click any cell to edit · "
        "Use the ➕ row at the bottom to add new entries · "
        "Click **💾 Apply** when done"
    )

    _edited_map = st.data_editor(
        _mdf,
        column_config=_map_col_cfg,
        num_rows="dynamic",        # enables ➕ add-row button at bottom
        hide_index=True,
        use_container_width=True,
        height=_map_h,
        key="mapping_data_editor",
    )

    # ── LOB coverage summary ───────────────────────────────────────────────────
    if not _edited_map.empty:
        _blank = (_edited_map["LOB"].isna() | (_edited_map["LOB"] == "")).sum()
        if _blank > 0:
            st.warning(f"⚠️ {_blank} skill(s) have no LOB assigned — they will be excluded from report calculations.")

    st.markdown("---")

    # ── Apply / Reset / Group-by summary ──────────────────────────────────────
    _act_col, _rst_col, _sum_col = st.columns([2, 1, 3])

    with _act_col:
        if st.button("💾 Apply as Active Mapping", type="primary", use_container_width=True):
            st.session_state["mapping_df"]     = _edited_map.copy()
            st.session_state["custom_mapping"] = _df_to_mapping(_edited_map)
            # ── persist to disk so ALL users instantly get the new mapping ──
            save_custom_mapping(st.session_state["custom_mapping"])
            save_mapping_df(_edited_map)
            _n = len(st.session_state["custom_mapping"])
            st.success(f"✅ Mapping applied — {_n:,} entries active for all users.")
            st.rerun()

    with _rst_col:
        if st.button("↩️ Reset to Built-in", use_container_width=True):
            st.session_state.pop("mapping_df",     None)
            st.session_state.pop("custom_mapping", None)
            clear_custom_mapping()   # wipe disk too
            st.rerun()

    with _sum_col:
        # Quick breakdown: # skills per LOB
        if not _edited_map.empty:
            _grp = (
                _edited_map.groupby("LOB", dropna=False)
                .size()
                .reset_index(name="# Skills")
                .sort_values("# Skills", ascending=False)
                .reset_index(drop=True)
            )
            st.caption("**Skills per LOB (current edits)**")
            st.dataframe(_grp, hide_index=True, use_container_width=True, height=180)

# ── Tab 4: Targets Editor ─────────────────────────────────────────────────────
with tab4:
    st.subheader("Performance Targets by LOB")
    st.caption(
        "Edit AHT, ASA, and Abandon Rate targets per Line of Business. "
        "Click **💾 Apply** to activate — all users and all calculations update instantly. "
        "Click **↩️ Reset** to revert to the built-in targets."
    )

    # ── Status banner ─────────────────────────────────────────────────────────
    _ct = st.session_state.get("custom_targets")
    if _ct:
        st.success(f"✅ **Custom targets active** — {len(_ct):,} LOBs defined")
    else:
        st.info(f"ℹ️ **Built-in targets active** — {len(_BUILTIN_TARGETS):,} LOBs")

    st.markdown("---")

    # ── Upload targets file ───────────────────────────────────────────────────
    with st.expander("📥 Upload targets from Excel / CSV", expanded=False):
        st.markdown(
            "Upload a file with columns **LOB**, **AHT** (seconds), **ASA** (seconds), "
            "and **ABN%** (abandon rate — either as ratio like `0.03` or percentage like `3`). "
            "The upload replaces all targets; unmapped LOBs fall back to the built-in default."
        )
        _tgt_file = st.file_uploader(
            "Upload targets file",
            type=["xlsx", "xls", "csv"],
            key="targets_file_upload",
            label_visibility="collapsed",
        )
        if _tgt_file:
            try:
                _uploaded_targets = _parse_targets_upload(_tgt_file)
                st.session_state["custom_targets"] = _uploaded_targets
                st.session_state["targets_df"]     = _targets_to_df(_uploaded_targets)
                save_targets(_uploaded_targets)
                st.success(f"✅ Loaded targets for {len(_uploaded_targets):,} LOBs. Click **💾 Apply** to confirm.")
                st.rerun()
            except Exception as _te:
                st.error(f"Could not parse file: {_te}")

    st.markdown("---")

    # ── Editable targets table ────────────────────────────────────────────────
    _tdf = _get_targets_df()

    _tgt_col_cfg = {
        "LOB": st.column_config.TextColumn("LOB", width=200),
        "Target AHT (s)": st.column_config.NumberColumn(
            "Target AHT (s)", min_value=0, max_value=3600, step=1, width=130,
            help="Average Handle Time target in seconds.",
        ),
        "Target ASA (s)": st.column_config.NumberColumn(
            "Target ASA (s)", min_value=0, max_value=3600, step=1, width=130,
            help="Average Speed to Answer target in seconds.",
        ),
        "Target ABN%": st.column_config.NumberColumn(
            "Target ABN%", min_value=0.0, max_value=100.0, step=0.1,
            format="%.1f%%", width=130,
            help="Abandon Rate target as a percentage (e.g. 3.0 = 3%).",
        ),
    }

    _tgt_h = min(700, max(300, len(_tdf) * 36 + 40))

    st.caption(
        f"**{len(_tdf):,} LOBs** · "
        "Double-click any cell to edit · "
        "AHT & ASA in seconds · "
        "ABN% as a percentage (e.g. 3.0 = 3%)"
    )

    _edited_tgt = st.data_editor(
        _tdf,
        column_config=_tgt_col_cfg,
        num_rows="dynamic",
        hide_index=True,
        use_container_width=True,
        height=_tgt_h,
        key="targets_data_editor",
    )

    st.markdown("---")

    # ── Apply / Reset ─────────────────────────────────────────────────────────
    _ta_col, _tr_col, _ts_col = st.columns([2, 1, 3])

    with _ta_col:
        if st.button("💾 Apply as Active Targets", type="primary", use_container_width=True):
            _new_targets = _df_to_targets(_edited_tgt)
            if _new_targets:
                st.session_state["custom_targets"] = _new_targets
                st.session_state["targets_df"]     = _edited_tgt.copy()
                save_targets(_new_targets)
                st.success(f"✅ Targets applied — {len(_new_targets):,} LOBs active for all users.")
                st.rerun()
            else:
                st.error("No valid targets found — check your edits.")

    with _tr_col:
        if st.button("↩️ Reset to Built-in", use_container_width=True, key="reset_targets_btn"):
            st.session_state.pop("custom_targets", None)
            st.session_state.pop("targets_df",     None)
            clear_targets()
            st.rerun()

    with _ts_col:
        # Preview: current targets as a quick-reference table
        if not _edited_tgt.empty:
            st.caption("**Current targets preview**")
            st.dataframe(
                _edited_tgt.style.format({
                    "Target AHT (s)": "{:.0f}s",
                    "Target ASA (s)": "{:.0f}s",
                    "Target ABN%":    "{:.1f}%",
                }),
                hide_index=True,
                use_container_width=True,
                height=200,
            )
