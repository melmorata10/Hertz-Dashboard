from datetime import datetime, timezone, timedelta
import io

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
import streamlit.components.v1 as components

from src.daily_forecast import (
    parse_daily_forecast, forecast_pivot, add_forecast_cols,
    resolve_vendor_site as _fc_resolve_vendor_site,
    SITE_RENAME as _FC_SITE_RENAME,
)
from src.exception_rules import (
    RULE_TYPE_RENAME as _RULE_RENAME,
    RULE_TYPE_HIDE as _RULE_HIDE,
    DEFAULT_RULES as _DEFAULT_RULES,
    parse_rules_text as _parse_rules_text,
    rules_to_text as _rules_to_text,
    lob_renames as _rules_lob_renames,
    lob_hides as _rules_lob_hides,
    build_mapping_network as _build_mapping_network,
    apply_to_mapping as _rules_apply_to_mapping,
    apply_to_forecast_df as _rules_apply_to_forecast,
    build_forecast_lob_map as _rules_forecast_lob_map,
)
from src.data_processor import prepare
from src.mapping import SKILL_TO_LOB as _BUILTIN_MAPPING, LOB_DISPLAY_ORDER as _LOB_ORDER, TARGETS as _BUILTIN_TARGETS
from src.persistence import (
    load_comments, save_comments, clear_comments,
    load_custom_mapping, save_custom_mapping, clear_custom_mapping,
    load_mapping_df, save_mapping_df, clear_mapping_df, load_mapping_mtime,
    load_targets, save_targets, clear_targets, load_targets_mtime,
    load_daily_forecast, save_daily_forecast,
    clear_daily_forecast, load_daily_forecast_mtime,
    load_exception_rules, save_exception_rules, load_exception_rules_mtime,
    restore_missing_from_backup,
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
    page_title="Weekly Business Review",
    page_icon="🚗",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# WBR: the sidebar is hidden entirely — data source & upload live on the main
# page. Also hide the expand-sidebar chevron so it can't be reopened.
st.markdown(
    "<style>[data-testid='stSidebar'], [data-testid='stSidebarCollapsedControl'], "
    "[data-testid='stExpandSidebarButton'] { display: none !important; }</style>",
    unsafe_allow_html=True,
)

# ── Restore wiped state from the off-container backup ────────────────────────
# A deploy/reboot wipes the disk; any state file that is missing is pulled
# back from the Supabase backup before anything below reads it. Attempted
# once per session; a no-op when all files exist or no backup is configured.
if not st.session_state.get("_backup_restore_done"):
    _restored = restore_missing_from_backup()
    st.session_state["_backup_restore_done"] = True
    if _restored:
        st.toast(f"♻️ Restored after redeploy: {', '.join(_restored)}")

# ── Load shared server-side state on first visit ──────────────────────────────
# session_state is per-browser; disk files are shared across ALL users.
# We seed session_state from disk once per session so every RTA sees the
# mapping and comments saved by whoever last updated them.
if "lob_comments" not in st.session_state:
    st.session_state["lob_comments"] = load_comments()

# Live-sync mapping (same mechanism as targets/rules): reload whenever the
# disk files are newer than what this session last loaded, so a mapping
# applied, imported, or deleted by any user reaches every open session
# without a refresh.
_disk_mapping_mtime = load_mapping_mtime()
if _disk_mapping_mtime != st.session_state.get("_mapping_mtime", -1.0):
    _persisted_mapping = load_custom_mapping()
    if _persisted_mapping is not None:
        # Add-only sync: append built-in entries that don't exist yet so newly
        # shipped skills appear automatically. Never overwrite a saved
        # assignment — RTA remaps and fresh imports must survive new sessions.
        _cm_changed = False
        for _k, _v in _BUILTIN_MAPPING.items():
            if _k not in _persisted_mapping:
                _persisted_mapping[_k] = _v
                _cm_changed = True
        if _cm_changed:
            save_custom_mapping(_persisted_mapping)
        st.session_state["custom_mapping"] = _persisted_mapping
    else:
        st.session_state.pop("custom_mapping", None)

    _persisted_df = load_mapping_df()
    if _persisted_df is not None:
        st.session_state["mapping_df"] = _persisted_df
    else:
        st.session_state.pop("mapping_df", None)

    st.session_state["_mapping_mtime"] = load_mapping_mtime()

# Live-sync exception rules (same mechanism as targets): reload whenever the
# disk file is newer than what this session last loaded, so rules applied by
# any user reach every open session without a refresh.
_disk_rules_mtime = load_exception_rules_mtime()
if (
    "exception_rules" not in st.session_state
    or _disk_rules_mtime != st.session_state.get("_rules_mtime", -1.0)
):
    _persisted_rules = load_exception_rules()
    if _persisted_rules is None:
        _seed_rules = [dict(r) for r in _DEFAULT_RULES]
        st.session_state["exception_rules"] = _seed_rules
        st.session_state["exception_rules_text"] = _rules_to_text(_seed_rules)
    else:
        st.session_state["exception_rules"] = _persisted_rules["rules"]
        st.session_state["exception_rules_text"] = (
            _persisted_rules.get("text") or _rules_to_text(_persisted_rules["rules"])
        )
    st.session_state["_rules_mtime"] = _disk_rules_mtime

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
def _coverage_header(date_range) -> str:
    """WBR header: the coverage period of the loaded data (no as-of time).

    ``date_range`` is a (min_date, max_date) tuple of pandas Timestamps or
    None when no data is loaded.
    """
    if not date_range or pd.isna(date_range[0]) or pd.isna(date_range[1]):
        return "Hertz · Weekly Business Review"
    lo, hi = date_range
    if lo.date() == hi.date():
        return f"Hertz WBR · Coverage: {lo.strftime('%b')} {lo.day}, {lo.year}"
    if lo.year != hi.year:
        lo_str = f"{lo.strftime('%b')} {lo.day}, {lo.year}"
    elif lo.month != hi.month:
        lo_str = f"{lo.strftime('%b')} {lo.day}"
    else:
        lo_str = f"{lo.strftime('%b')} {lo.day}"
    hi_str = f"{hi.strftime('%b')} {hi.day}, {hi.year}"
    return f"Hertz WBR · Coverage: {lo_str} – {hi_str}"


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

    # SL% — fixed 80% threshold: at/above = green, below = red
    if "SL%" in cols:
        val = row["SL%"]
        if pd.notna(val):
            idx = cols.index("SL%")
            styles[idx] = (
                "background-color: #C8F0C8; color: #1a5e1a" if val >= 80
                else "background-color: #FFD0D0; color: #8b0000"
            )
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


def _wbr_narrative(
    summary_df: pd.DataFrame,
    interval_df: pd.DataFrame,
    focus_week: str = None,
) -> str:
    """Auto-written executive analysis for the WBR — Key Wins / Risks /
    Outlook — generated from the summary table, forecast columns, and the
    week-over-week movement in the weekly breakdown.

    ``focus_week`` is the week picker's ISO week-start: week-over-week
    deltas compare THAT week to the one before it, and streaks count up to
    it. None (all weeks) anchors on the latest week in the data."""
    lobs = summary_df[summary_df["LOB"] != "Grand Total"].copy()
    _gt_rows = summary_df[summary_df["LOB"] == "Grand Total"]
    gt = _gt_rows.iloc[0] if not _gt_rows.empty else None
    wins, risks, outlook = [], [], []

    # ── Service level ─────────────────────────────────────────────────────────
    if "SL%" in lobs.columns and lobs["SL%"].notna().any():
        sl = lobs[lobs["SL%"].notna()]
        good = sl[sl["SL%"] >= 80]
        bad = sl[sl["SL%"] < 80].sort_values("NCO", ascending=False)
        if len(bad) == 0 and len(good) > 0:
            wins.append(
                f"**100% SL attainment** — all {len(good)} LOBs with SL data "
                f"at or above the 80% threshold."
            )
        elif len(good) > 0:
            wins.append(
                f"**{len(good)} of {len(sl)} LOBs** at or above the 80% "
                f"service-level threshold."
            )
        for _, r in bad.head(3).iterrows():
            risks.append(
                f"**{r['LOB']}** service level at **{r['SL%']:.1f}%** "
                f"on {int(r['NCO']):,} offered calls."
            )

    # ── AHT vs target ─────────────────────────────────────────────────────────
    if "AHT Var%" in lobs.columns and lobs["AHT Var%"].notna().any():
        ahtv = lobs[lobs["AHT Var%"].notna()]
        under = ahtv[ahtv["AHT Var%"] <= 0]
        if len(under) > 0:
            best = under.sort_values("AHT Var%").iloc[0]
            _plural = "s" if len(under) != 1 else ""
            wins.append(
                f"**{len(under)} LOB{_plural} at or under AHT target**, led by "
                f"{best['LOB']} ({best['AHT Var%']:+.1f}% vs target)."
            )
        over = ahtv[ahtv["AHT Var%"] > 5].sort_values("NCO", ascending=False)
        for _, r in over.head(3).iterrows():
            risks.append(
                f"**{r['LOB']}** AHT {int(round(r['AHT']))}s vs "
                f"{int(round(r['Target AHT']))}s target "
                f"(**{r['AHT Var%']:+.1f}%**)."
            )

    # ── Abandonment ───────────────────────────────────────────────────────────
    if gt is not None and pd.notna(gt.get("ABN%")) and pd.notna(gt.get("Target ABN%")):
        if gt["ABN%"] <= gt["Target ABN%"]:
            wins.append(
                f"Overall abandonment **{gt['ABN%']:.1f}%**, inside the "
                f"{gt['Target ABN%']:.1f}% average target."
            )
        else:
            risks.append(
                f"Overall abandonment **{gt['ABN%']:.1f}%** vs "
                f"{gt['Target ABN%']:.1f}% average target."
            )
    _abn_cols_ok = lobs["ABN%"].notna() & lobs["Target ABN%"].notna()
    _abn_bad = lobs[_abn_cols_ok & (lobs["ABN%"] > lobs["Target ABN%"] * 1.1)]
    if not _abn_bad.empty:
        w = (
            _abn_bad.assign(_gap=_abn_bad["ABN%"] - _abn_bad["Target ABN%"])
            .sort_values("_gap", ascending=False).iloc[0]
        )
        risks.append(
            f"**{w['LOB']}** abandonment {w['ABN%']:.1f}% is "
            f"**{w['_gap']:.1f}pp above target**."
        )

    # ── Forecast accuracy ─────────────────────────────────────────────────────
    if (
        gt is not None
        and "Forecast Variance" in summary_df.columns
        and pd.notna(gt.get("Forecast Variance"))
    ):
        fv = gt["Forecast Variance"]
        if 90 <= fv <= 110:
            wins.append(
                f"Volume ran **{fv:.0f}% of forecast** — solid forecast accuracy."
            )
        elif fv > 110:
            risks.append(
                f"Volume at **{fv:.0f}% of forecast** — offered calls well "
                f"above plan, pressuring capacity."
            )
        else:
            outlook.append(
                f"Volume at **{fv:.0f}% of forecast** — running under plan."
            )

    # ── Week-over-week movement (needs 2+ weeks in the breakdown) ────────────
    overall = []
    if interval_df is not None and not interval_df.empty and interval_df["Interval"].nunique() >= 2:
        t = interval_df.copy()
        t["_ahtw"]  = t["NCH"].fillna(0) * t["AHT"].fillna(0)
        t["_asaw"]  = t["NCH"].fillna(0) * t["ASA"].fillna(0)
        # SL% x NCO / 100 reconstructs the exact within-threshold call count,
        # so weekly SL re-weights correctly instead of averaging percentages.
        t["_slc"]   = t["SL%"] * t["NCO"] / 100.0
        t["_slnco"] = t["NCO"].where(t["SL%"].notna())
        wk = t.groupby("Interval", sort=True).agg(
            NCO=("NCO", "sum"), NCH=("NCH", "sum"), ABN=("ABN", "sum"),
            _ahtw=("_ahtw", "sum"), _asaw=("_asaw", "sum"),
            _slc=("_slc", "sum"), _slnco=("_slnco", "sum"),
        )
        _nch = wk["NCH"].replace(0, float("nan"))
        _nco = wk["NCO"].replace(0, float("nan"))
        wk["AHT"]  = wk["_ahtw"] / _nch
        wk["ASA"]  = wk["_asaw"] / _nch
        wk["ABN%"] = wk["ABN"] / _nco * 100
        wk["SL%"]  = wk["_slc"] / wk["_slnco"].replace(0, float("nan")) * 100
        # Anchor on the presented week (week picker); default to the latest.
        _wk_list = list(wk.index)
        _pos = _wk_list.index(focus_week) if focus_week in _wk_list else len(_wk_list) - 1
        _weeks_upto = _wk_list[: _pos + 1]
        last = wk.iloc[_pos]
        prev = wk.iloc[_pos - 1] if _pos > 0 else None
        if prev is None:
            _d_sl = _d_aht = _d_asa = _d_abn = float("nan")
            overall.append(
                f"Week of {_wk_list[0]} is the first week in the loaded "
                "period — no prior week to compare against."
            )
        else:
            _d_sl  = last["SL%"] - prev["SL%"]
            _d_aht = last["AHT"] - prev["AHT"]
            _d_asa = last["ASA"] - prev["ASA"]
            _d_abn = last["ABN%"] - prev["ABN%"]

        # Headline: direction of travel + the metric moves behind it
        _drivers = []
        if pd.notna(_d_aht) and abs(_d_aht) >= 3:
            _drivers.append(f"AHT {_d_aht:+.0f}s")
        if pd.notna(_d_asa) and abs(_d_asa) >= 3:
            _drivers.append(f"ASA {_d_asa:+.0f}s")
        if pd.notna(_d_abn) and abs(_d_abn) >= 0.3:
            _drivers.append(f"abandonment {_d_abn:+.1f}pp")
        _drv_txt = f", with {', '.join(_drivers)}" if _drivers else ""
        if pd.notna(_d_sl) and _d_sl <= -1:
            overall.append(
                f"Performance **declined week-over-week** — SL {_d_sl:+.1f}pp "
                f"to **{last['SL%']:.1f}%**{_drv_txt}."
            )
        elif pd.notna(_d_sl) and _d_sl >= 1:
            overall.append(
                f"Performance **improved week-over-week** — SL {_d_sl:+.1f}pp "
                f"to **{last['SL%']:.1f}%**{_drv_txt}."
            )
        elif pd.notna(_d_sl):
            overall.append(
                f"Performance **held steady week-over-week** — SL at "
                f"**{last['SL%']:.1f}%** ({_d_sl:+.1f}pp){_drv_txt}."
            )
        elif _drivers:
            overall.append(f"Week-over-week movement: {', '.join(_drivers)}.")

        # Per-LOB SL consistency: every-week achievers vs consecutive-miss streaks
        if t["SL%"].notna().any():
            lobwk = t.dropna(subset=["SL%"]).groupby(["LOB", "Interval"]).agg(
                _slc=("_slc", "sum"), _n=("_slnco", "sum"),
            )
            lobwk["SL%"] = lobwk["_slc"] / lobwk["_n"].replace(0, float("nan")) * 100
            _weeks = _weeks_upto
            _streaks, _steady = [], []
            for _lob, _grp in lobwk.reset_index().groupby("LOB"):
                _by_wk = _grp.set_index("Interval")["SL%"]
                _by_wk = _by_wk[_by_wk.index.isin(_weeks_upto)]
                if len(_by_wk) < 2:
                    continue
                if (_by_wk >= 80).all():
                    _steady.append(str(_lob))
                    continue
                _run = 0
                for _w in reversed(_weeks):
                    if _w in _by_wk.index and _by_wk[_w] < 80:
                        _run += 1
                    else:
                        break
                if _run >= 2:
                    _streaks.append((str(_lob), _run))
            if _steady:
                _more = "…" if len(_steady) > 3 else ""
                _plural = "s" if len(_steady) != 1 else ""
                overall.append(
                    f"**{len(_steady)} LOB{_plural} met the 80% SL threshold in every "
                    f"week** of the period ({', '.join(_steady[:3])}{_more})."
                )
            for _lob, _run in sorted(_streaks, key=lambda x: -x[1])[:2]:
                overall.append(
                    f"**{_lob}** has missed the 80% SL threshold for "
                    f"**{_run} consecutive weeks**."
                )
        if pd.notna(_d_aht) and _d_aht <= -5:
            wins.append(f"AHT improved **{abs(_d_aht):.0f}s week-over-week** vs the prior week.")
        elif pd.notna(_d_aht) and _d_aht >= 5:
            risks.append(f"AHT up **{_d_aht:.0f}s week-over-week** vs the prior week.")
        if pd.notna(_d_abn) and _d_abn <= -0.5:
            wins.append(f"Abandon rate down **{abs(_d_abn):.1f}pp** vs prior week.")
        elif pd.notna(_d_abn) and _d_abn >= 0.5:
            risks.append(f"Abandon rate up **{_d_abn:.1f}pp** vs prior week.")
        if prev is not None and prev["NCO"] > 0:
            _d_nco = (last["NCO"] - prev["NCO"]) / prev["NCO"] * 100
            outlook.append(
                f"Week of {last.name}: **{int(last['NCO']):,} offered** "
                f"({_d_nco:+.0f}% vs prior week)."
            )

    # ── Coverage totals ───────────────────────────────────────────────────────
    if gt is not None:
        _sl_txt = f", SL **{gt['SL%']:.1f}%**" if pd.notna(gt.get("SL%")) else ""
        outlook.append(
            f"Period total: **{int(gt['NCO']):,} offered / "
            f"{int(gt['NCH']):,} handled**{_sl_txt}."
        )

    def _bullets(items, empty_msg):
        items = items or [empty_msg]
        return "\n".join(f"- {i}" for i in items)

    return (
        "#### 📈 Overall Performance\n"
        + _bullets(
            overall[:4],
            "Single-week view — load multiple weeks for week-over-week observations.",
        )
        + "\n\n#### 🔑 Key Wins\n"
        + _bullets(wins[:4], "No target-beating highlights this period.")
        + "\n\n#### ⚠️ Primary Risks & Pressure Points\n"
        + _bullets(risks[:5], "No LOB is materially off target — clean period.")
        + "\n\n#### 🔭 Outlook\n"
        + _bullets(outlook[:3], "Load more than one week of data for trend outlook.")
    )


def _summary_to_tsv(df: pd.DataFrame) -> str:
    """Tab-separated + formatted — plain-text fallback for clipboard."""
    display_cols = [
        "LOB", "NCO", "NCH", "SL%", "Forecast Volume", "Forecast Variance",
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
    for col in ("AHT Var%", "ABN%", "Target ABN%", "Forecast Variance", "SL%"):
        if col in view.columns:
            view[col] = view[col].apply(_fmt_pct)
    for col in ("NCO", "NCH", "ABN", "Forecast Volume"):
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
        "LOB", "NCO", "NCH", "SL%", "Forecast Volume", "Forecast Variance",
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
        if col == "SL%":
            if val >= 80: return GREEN_BG, GREEN_FG
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
        if col in ("AHT Var%", "ABN%", "Target ABN%", "Forecast Variance", "SL%"): return _fmt_pct(val)
        if col in ("NCO", "NCH", "ABN", "Forecast Volume"):               return _fmt_int(val)
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
        f'border:1px solid #888;white-space:nowrap;font-weight:bold;'
        f'text-align:{"left" if c in ("LOB", "Comment / Action") else "center"}">{_col_label(c)}</th>'
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

    # Auto-sync once per session: append any new built-in skills not yet in the df.
    # Existing rows are never overwritten, so RTA edits to LOB/Vendor are preserved.
    if not st.session_state.get("_mapping_df_synced"):
        _mdf = st.session_state["mapping_df"].copy()
        _builtin_df = _mapping_to_df(_BUILTIN_MAPPING)
        _existing = set(_mdf["Queue Name"].astype(str).str.strip())
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
    """Parse a mapping Excel and merge into current_df.

    Accepts two formats:
    • The Tableau export ("Skill Name and Number" column): existing rows
      (matched by Skill ID) keep their LOB; Vendor is updated from the file;
      new skills are appended with a blank LOB so the team can fill them in.
    • The Mapping Manager's own "Download Excel" file (Skill ID / Queue Name /
      LOB / Vendor): a full restore — the file's LOB and Vendor assignments
      are applied as-is, falling back to the current table where blank.
    """
    raw = pd.read_excel(file)
    raw.columns = [str(c).strip() for c in raw.columns]

    def _clean(v) -> str:
        s = str(v).strip()
        return "" if s.lower() in ("nan", "none") else s

    # Round-trip restore path: the dashboard's own export
    if "Queue Name" in raw.columns:
        existing = {}
        for _, r in current_df.iterrows():
            q = _clean(r.get("Queue Name"))
            if q:
                existing[q] = (_clean(r.get("LOB")), _clean(r.get("Vendor")))
        rows, seen = [], set()
        for _, row in raw.iterrows():
            queue = _clean(row.get("Queue Name"))
            if not queue or queue in seen:
                continue
            seen.add(queue)
            sid = _clean(row.get("Skill ID"))
            if sid.endswith(".0"):          # Excel round-trips IDs as floats
                sid = sid[:-2]
            ex_lob, ex_ven = existing.get(queue, ("", ""))
            rows.append({
                "Skill ID":   sid,
                "Queue Name": queue,
                "LOB":        _clean(row.get("LOB")) or ex_lob,
                "Vendor":     _clean(row.get("Vendor")) or ex_ven,
            })
        return pd.DataFrame(rows, columns=["Skill ID", "Queue Name", "LOB", "Vendor"])

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


# Uniform table layout: every metric column is the same width and centered;
# only LOB and Analysis are left-aligned (and sized for text).
_METRIC_COL_WIDTH = 90

# Display labels shortened to fit the uniform column width without truncation.
# Underlying DataFrame column names are unchanged.
_COL_LABELS = {
    "Forecast Volume":   "Fcst Vol",
    "Forecast Variance": "Fcst Var%",
}
_COL_WIDTHS = {
    "LOB":         160,
    "NCO":          _METRIC_COL_WIDTH,
    "NCH":          _METRIC_COL_WIDTH,
    "SL%":          _METRIC_COL_WIDTH,
    "Forecast Volume":   _METRIC_COL_WIDTH,
    "Forecast Variance": _METRIC_COL_WIDTH,
    "Target AHT":   _METRIC_COL_WIDTH,
    "AHT":          _METRIC_COL_WIDTH,
    "AHT Var%":     _METRIC_COL_WIDTH,
    "ABN":          _METRIC_COL_WIDTH,
    "Target ABN%":  _METRIC_COL_WIDTH,
    "ABN%":         _METRIC_COL_WIDTH,
    "Target ASA":   _METRIC_COL_WIDTH,
    "ASA":          _METRIC_COL_WIDTH,
    "Analysis":    500,
}

# LOBs excluded from ALL outputs, including Grand Total — their raw rows are
# filtered out before aggregation in prepare(). Driven by "hide <LOB>" rules
# on the Mapping Network tab (OPERATIONS is a default rule).
_HIDDEN_LOBS = _rules_lob_hides(st.session_state.get("exception_rules", []))


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
        "LOB", "NCO", "NCH", "SL%", "Forecast Volume", "Forecast Variance",
        "Target AHT", "AHT", "AHT Var%",
        "ABN", "Target ABN%", "ABN%",
        "Target ASA", "ASA",
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

    # Build colour styles from the NUMERIC values first, then convert every
    # cell to a display string ourselves — st.data_editor renders NaN cells as
    # the literal text "None" instead of honouring Styler.format's na_rep, so
    # missing values are pre-formatted to "—" and the colours are applied to
    # the string copy positionally.
    if "ABN%" in view.columns:
        _cell_styles = view.apply(_colour_row, axis=1, result_type="expand")
        _cell_styles.columns = view.columns
    else:
        _cell_styles = pd.DataFrame("", index=view.index, columns=view.columns)
    if "AHT Var%" in view.columns:
        _cell_styles["AHT Var%"] = view["AHT Var%"].map(_colour_aht_var)
    if len(view) > 0:
        _last = view.index[-1]
        _cell_styles.loc[_last] = [
            f"{s}; font-weight: bold" if s else "font-weight: bold"
            for s in _cell_styles.loc[_last]
        ]

    fmt = {}
    for col in ("Target AHT", "AHT"):
        if col in view.columns:
            fmt[col] = _fmt_seconds_int
    for col in ("Target ASA", "ASA"):
        if col in view.columns:
            fmt[col] = _fmt_seconds
    for col in ("AHT Var%", "ABN%", "Target ABN%", "Forecast Variance", "SL%"):
        if col in view.columns:
            fmt[col] = _fmt_pct
    for col in ("NCO", "NCH", "ABN", "Forecast Volume"):
        if col in view.columns:
            fmt[col] = _fmt_int
    disp = view.copy()
    for col, f in fmt.items():
        disp[col] = view[col].apply(f)
    disp = disp.fillna("—")

    styled = disp.style.apply(lambda _: _cell_styles, axis=None)

    # Column config — Analysis is editable, everything else locked.
    # Metric columns are uniformly sized and centered; LOB/Analysis left.
    col_cfg = {}
    for c, w in _COL_WIDTHS.items():
        if c not in present:
            continue
        if c == "Analysis":
            col_cfg[c] = st.column_config.TextColumn(
                "Analysis / Notes",
                width=w,
                alignment="left",
                help="Auto-generated from metrics. Click any cell to edit or add your own notes.",
            )
        else:
            col_cfg[c] = st.column_config.TextColumn(
                _COL_LABELS.get(c, c), width=w,
                alignment="left" if c == "LOB" else "center",
            )

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
    """Render a 'Copy for Email' button for a KPI summary table.

    Clicking it copies the summary table as rich HTML to the clipboard.
    Green / yellow / red cell colours are preserved when pasting into
    Outlook, Gmail, Word, or any HTML-aware email client.
    """
    _copy_html_button(
        _summary_to_html_table(
            df,
            show_greeting=show_greeting,
            lob_col_label=lob_col_label,
            table_key=table_key,
        ),
        key,
    )


def _copy_html_button(html_content: str, key: str) -> None:
    """Render a button that copies the given rich HTML to the clipboard.

    Uses document.execCommand('copy') on a selected hidden div — this
    works inside Streamlit's sandboxed iframe (the newer Clipboard API
    does not without explicit allow="clipboard-write" on the iframe).
    """
    import json as _json

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

    display_cols = ["LOB", "NCO", "NCH", "SL%", "Forecast Volume", "Forecast Variance", "Target AHT", "AHT", "AHT Var%",
                    "ABN", "Target ABN%", "ABN%", "Target ASA", "ASA"]
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
        if col == "SL%":
            if val >= 80: return GREEN_BG, GREEN_FG
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
        if col in ("AHT Var%", "ABN%", "Target ABN%", "Forecast Variance", "SL%"): return _fmt_pct(val)
        if col in ("NCO", "NCH", "ABN", "Forecast Volume"):               return _fmt_int(val)
        if col == "Analysis":                          return str(val) if val else ""
        return str(val) if pd.notna(val) else "—"

    # Proportional widths for table-layout:fixed;width:100% at 92vw.
    # LOB=130, all metrics=72px each (uniform), Analysis=450 → ratios preserved at full width.
    _DLG_W = {
        "LOB": 130, "NCO": 72, "NCH": 72, "SL%": 72,
        "Forecast Volume": 72, "Forecast Variance": 72,
        "Target AHT": 72, "AHT": 72, "AHT Var%": 72,
        "ABN": 72, "Target ABN%": 72, "ABN%": 72,
        "Target ASA": 72, "ASA": 72, "Analysis": 450,
    }
    left_cols   = {"LOB", "Analysis"}
    col_labels  = {"Analysis": "Analysis / Notes", **_COL_LABELS}

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


@st.dialog("📆 Weekly Breakdown", width="large")
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
        if col in ("AHT Var%", "ABN%", "Target ABN%", "Forecast Variance"): return _fmt_pct(val)
        if col in ("NCO", "NCH", "ABN", "Forecast Volume"):               return _fmt_int(val)
        return str(val) if pd.notna(val) else "—"

    _iv_labels = {"Interval": "Week Starting"}
    _iv_widths = {
        "Interval": 100, "LOB": 120, "Vendor": 80,
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
        f'text-align:{"left" if c in left_cols_iv else "center"}">{_iv_labels.get(c, c)}</th>'
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
    # Checkbox semantics: the selections ARE the filter — an empty selection
    # means nothing is shown (unlike the old multiselect, where empty meant
    # "no filter").
    filtered = df[
        df["LOB"].isin(lob_filter) & df["Vendor"].isin(vendor_filter)
    ].copy()

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
                xaxis_title="Week Starting",
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
                xaxis_title="Week Starting",
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
                xaxis_title="Week Starting",
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
    view = view.rename(columns={"Interval": "Week Starting"})

    styled = _style_interval(view)
    fmt = {}
    for col in ("Target AHT", "AHT"):          # whole numbers
        if col in view.columns:
            fmt[col] = _fmt_seconds_int
    for col in ("Target ASA", "ASA"):           # 1 decimal
        if col in view.columns:
            fmt[col] = _fmt_seconds
    for col in ("AHT Var%", "ABN%", "Target ABN%", "Forecast Variance"):
        if col in view.columns:
            fmt[col] = _fmt_pct
    for col in ("NCO", "NCH", "ABN", "Forecast Volume"):
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
            st.warning(f"Could not read {f.name}: {e}")
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()



# ── Main-page data source panel (WBR has no sidebar) ─────────────────────────
# The header is rendered later in the script (it needs the coverage dates),
# but this container reserves the top slot so it still appears first on page.
_hdr_slot = st.container()

_ds_exp = st.expander(
    "📂 Data Source & Upload",
    expanded=not st.session_state.get("stored_files"),
)
with _ds_exp:
    data_source = st.radio(
        "data_source",
        options=["📁 Upload CSV", "☁️ SharePoint"],
        index=0,
        horizontal=True,
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
        # Persist uploaded bytes in session state so refreshes don't wipe the
        # data. Stored gzip-compressed: multi-week WBR files are large, and
        # raw bytes held alongside the parsed DataFrames can OOM the container.
        if uploaded:
            import gzip as _gzip
            st.session_state["stored_files"] = [
                {"name": f.name, "gz": _gzip.compress(f.read())} for f in uploaded
            ]
        # Clear button — only show when data is stored
        if st.session_state.get("stored_files"):
            if st.button("🗑️ Clear Data", use_container_width=True):
                st.session_state.pop("stored_files", None)
                st.session_state.pop("sp_raw", None)
                st.session_state.pop("lob_comments", None)
                clear_comments()   # also wipe disk so other users see clean state
                st.rerun()
        st.caption("Columns: SkillName, SupplierName, Interval, NCO, NCH, AHT, ABN, ASA, TotalServiceLevelCalls")

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
call_date_range = None   # (min CallDate, max CallDate) — drives the WBR coverage header

_PERF_CSV_COLS = {
    # every raw header spelling the pipeline understands (lowercased)
    "skillname", "skill name and number", "skill name and number (h)",
    "suppliername", "interval", "intervalstarttime", "calldate",
    "nco", "numbero ffered", "nch", "numberhandled", "aht", "abn", "asa",
    "speedofanswer", "totalservicelevelcalls", "total service level calls",
    "servicelevelcalls",
}


def _read_perf_csv(buf) -> pd.DataFrame:
    """Read only the columns the pipeline uses. Multi-week exports carry
    dozens of extra columns; skipping them at parse time keeps read_csv's
    memory peak inside the 1 GB container."""
    header = pd.read_csv(buf, nrows=0)
    buf.seek(0)
    use = [c for c in header.columns if str(c).strip().lower() in _PERF_CSV_COLS]
    return pd.read_csv(buf, usecols=use or None)


_WBR_ALL_WEEKS = "__ALL__"
_wbr_week_options: list[str] = []   # ISO Monday week-starts found in the data


def _apply_week_scope(raw: pd.DataFrame) -> pd.DataFrame:
    """Apply the presenter's week picker (Voice Performance Summary tab).

    Populates the global week list for the picker and returns only the rows
    of the selected Monday-start week — or everything for "All weeks". The
    Weekly Breakdown is fed the unfiltered data separately so it always
    shows every week regardless of the picker.
    """
    global _wbr_week_options
    if "CallDate" in raw.columns:
        _d = pd.to_datetime(raw["CallDate"], errors="coerce")
    elif "Interval" in raw.columns:
        _d = pd.to_datetime(raw["Interval"], errors="coerce")
    else:
        return raw
    wk = (
        (_d - pd.to_timedelta(_d.dt.weekday, unit="D"))
        .dt.normalize()
        .dt.strftime("%Y-%m-%d")
    )
    _wbr_week_options = sorted(w for w in wk.dropna().unique())
    pick = st.session_state.get("wbr_week_select", _WBR_ALL_WEEKS)
    if pick == _WBR_ALL_WEEKS or pick not in _wbr_week_options:
        return raw
    return raw[wk == pick]


# LOBs unticked in the summary's "LOBs to include" filter (session-scoped).
# Applied as extra hidden LOBs to the SUMMARY scope only — the Weekly
# Breakdown keeps its own independent checkbox filters.
_vps_excluded = {
    l for l in st.session_state.get("vps_lob_universe", [])
    if st.session_state.get(f"vps_lob_{l}") is False
}


if data_source == "📁 Upload CSV":
    stored = st.session_state.get("stored_files")
    if stored:
        import io as _io
        import gzip as _gzip
        frames = []
        for f in stored:
            try:
                _bytes = _gzip.decompress(f["gz"]) if "gz" in f else f["data"]
                frames.append(_read_perf_csv(_io.BytesIO(_bytes)))
            except Exception as e:
                st.warning(f"Could not read {f['name']}: {e}")
        raw = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
        if not raw.empty:
            # Scope the summary (and header/forecast dates) to the presented
            # week; the Weekly Breakdown below always gets the full data.
            raw_scope = _apply_week_scope(raw)
            if "CallDate" in raw_scope.columns:
                try:
                    _dates = pd.to_datetime(raw_scope["CallDate"], errors="coerce").dropna()
                    call_date = _dates.max().strftime("%m/%d/%Y")
                    call_date_range = (_dates.min(), _dates.max())
                except Exception:
                    call_date = None
                    call_date_range = None
            _active_mapping  = st.session_state.get("custom_mapping")   # None → use built-in
            if _active_mapping:
                # Exception rules: LOB renames apply before aggregation
                _active_mapping = _rules_apply_to_mapping(
                    _active_mapping, st.session_state.get("exception_rules", [])
                )
            _active_targets  = st.session_state.get("custom_targets")   # None → use built-in
            summary_df, vendor_summaries, interval_df = prepare(
                raw_scope, custom_mapping=_active_mapping, custom_targets=_active_targets,
                hidden_lobs=set(_HIDDEN_LOBS) | _vps_excluded,
            )
            if len(raw_scope) != len(raw) or _vps_excluded:
                _, _, interval_df = prepare(
                    raw, custom_mapping=_active_mapping, custom_targets=_active_targets,
                    hidden_lobs=_HIDDEN_LOBS,
                )
            data_ok = True
        else:
            st.warning("No data could be read from the stored files.")
    else:
        st.info("⬆️ Upload your CSV files in the **Data Source & Upload** panel above to load the dashboard.")

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
            raw_scope = _apply_week_scope(_raw_sp)
            if "CallDate" in raw_scope.columns:
                try:
                    _dates = pd.to_datetime(raw_scope["CallDate"], errors="coerce").dropna()
                    call_date = _dates.max().strftime("%m/%d/%Y")
                    call_date_range = (_dates.min(), _dates.max())
                except Exception:
                    call_date = None
                    call_date_range = None
            _active_mapping  = st.session_state.get("custom_mapping")
            if _active_mapping:
                _active_mapping = _rules_apply_to_mapping(
                    _active_mapping, st.session_state.get("exception_rules", [])
                )
            _active_targets  = st.session_state.get("custom_targets")
            summary_df, vendor_summaries, interval_df = prepare(
                raw_scope, custom_mapping=_active_mapping, custom_targets=_active_targets,
                hidden_lobs=set(_HIDDEN_LOBS) | _vps_excluded,
            )
            if len(raw_scope) != len(_raw_sp) or _vps_excluded:
                _, _, interval_df = prepare(
                    _raw_sp, custom_mapping=_active_mapping, custom_targets=_active_targets,
                    hidden_lobs=_HIDDEN_LOBS,
                )
            data_ok = True
        elif _raw_sp is not None:
            st.warning("No CSV files found in the SharePoint folder.")
        else:
            st.info("☁️ Click **🔄 Load / Refresh Data** in the Data Source panel above to fetch data.")
    elif st.session_state.get("sp_token_info"):
        # Token expired
        st.warning("⏱️ SharePoint session expired — please sign in again in the Data Source panel above.")
    else:
        st.info("☁️ Sign in to SharePoint in the Data Source panel above to load data.")

# Grow the summary LOB universe additively so excluded LOBs keep their
# checkbox (an excluded LOB vanishes from summary_df, but must stay listed
# or it could never be re-enabled).
if data_ok and not summary_df.empty:
    _vps_now = set(summary_df["LOB"]) - {"Grand Total"}
    st.session_state["vps_lob_universe"] = sorted(
        set(st.session_state.get("vps_lob_universe", [])) | _vps_now | _vps_excluded
    )

# ── Daily Forecast → Forecast Volume / Forecast Variance enrichment ──────────
# The forecast is persisted server-side (like the mapping): an upload by one
# user is saved to disk and every session loads it from there — no re-upload
# needed until a new file replaces it. Parsing/loading happens BEFORE the tabs
# render so the Voice Performance Summary tables can use it on the same rerun.
# The uploader widget lives in the Daily Forecast tab; its key is versioned so
# "Remove saved forecast" can reset it.
_fc_rev = st.session_state.setdefault("daily_forecast_upload_rev", 0)
_fc_upload = st.session_state.get(f"daily_forecast_upload_{_fc_rev}")
if _fc_upload is not None:
    _fc_sig = (_fc_upload.name, getattr(_fc_upload, "size", None))
    if st.session_state.get("daily_forecast_sig") != _fc_sig:
        try:
            _fc_parsed = parse_daily_forecast(_fc_upload)
            save_daily_forecast(_fc_parsed, _fc_upload.name)
            st.session_state["daily_forecast_df"] = _fc_parsed
            st.session_state["daily_forecast_name"] = _fc_upload.name
            st.session_state["daily_forecast_sig"] = _fc_sig
            st.session_state["daily_forecast_mtime"] = load_daily_forecast_mtime()
            st.session_state.pop("daily_forecast_err", None)
        except Exception as _fc_exc:
            st.session_state["daily_forecast_err"] = str(_fc_exc)
            st.session_state.pop("daily_forecast_df", None)
            st.session_state.pop("daily_forecast_sig", None)

# Sync with the server copy: first visit loads it, and a newer save by another
# user (mtime changed) live-reloads it; a cleared file drops it everywhere.
# Guarded: the saved forecast is shared state auto-loaded by EVERY session at
# startup, so a corrupted file must degrade to a warning — never crash the app.
try:
    _fc_disk_mtime = load_daily_forecast_mtime()
    if _fc_disk_mtime > 0:
        if st.session_state.get("daily_forecast_mtime") != _fc_disk_mtime:
            _fc_loaded = load_daily_forecast()
            if _fc_loaded is not None:
                _fc_loaded_df, _fc_loaded_name = _fc_loaded
                # Forecasts saved before a sheet rename (e.g. IGT → ATAIN) keep
                # the old site name on disk — normalize on the way in. LOB
                # renames are handled live by the exception rules.
                _fc_loaded_df["Site"] = _fc_loaded_df["Site"].replace(_FC_SITE_RENAME)
                st.session_state["daily_forecast_df"] = _fc_loaded_df
                st.session_state["daily_forecast_name"] = _fc_loaded_name
                st.session_state["daily_forecast_mtime"] = _fc_disk_mtime
    elif st.session_state.get("daily_forecast_mtime"):
        for _fc_key in ("daily_forecast_df", "daily_forecast_name", "daily_forecast_mtime"):
            st.session_state.pop(_fc_key, None)
except Exception as _fc_load_exc:
    for _fc_key in ("daily_forecast_df", "daily_forecast_name", "daily_forecast_mtime"):
        st.session_state.pop(_fc_key, None)
    st.warning(
        "⚠️ The saved Daily Forecast could not be loaded and was skipped "
        f"({_fc_load_exc}). Re-upload it on the Daily Forecast tab."
    )

# Forecast Volume / Forecast Variance appear only for PAST-DATED reports:
# once the raw data's CallDate is behind today's date (Central Time, matching
# the rest of the dashboard) the day is finished, so actuals vs the full-day
# forecast is a fair comparison. For a same-day (intraday) load neither
# column is added.
# Exception rules are applied to the forecast on the fly: LOB renames adjust
# the labels, link rules adjust which forecast column feeds which LOB.
_fc_rules = st.session_state.get("exception_rules", [])
_fc_saved_df = st.session_state.get("daily_forecast_df")
_fc_data = (
    _rules_apply_to_forecast(_fc_saved_df, _fc_rules)
    if _fc_saved_df is not None else None
)
_fc_lob_map = _rules_forecast_lob_map(_fc_rules)
_fc_report_date = None
_fc_not_past: str | None = None   # report date label when it isn't past yet
if data_ok and _fc_data is not None and call_date:
    try:
        _fc_report_date = pd.to_datetime(call_date).date()
    except Exception:
        _fc_report_date = None
    if _fc_report_date is not None:
        _fc_today = datetime.now(timezone(timedelta(hours=-5))).date()
        if _fc_report_date < _fc_today:
            # WBR: the forecast window is the WHOLE coverage span of the
            # uploaded data, not just its final day — actuals and forecast
            # must cover the same dates for the variance to mean anything.
            _fc_span = (
                (call_date_range[0].date(), call_date_range[1].date())
                if call_date_range else _fc_report_date
            )
            # Guarded: a bad forecast may cost its columns, never the dashboard.
            try:
                summary_df = add_forecast_cols(
                    summary_df, _fc_data, _fc_span, "Consolidated",
                    lob_map=_fc_lob_map,
                )
                _fc_sites = _fc_data["Site"].unique()
                for _fc_vendor in list(vendor_summaries):
                    _fc_sheet = _fc_resolve_vendor_site(_fc_vendor, _fc_sites)
                    if _fc_sheet:
                        vendor_summaries[_fc_vendor] = add_forecast_cols(
                            vendor_summaries[_fc_vendor], _fc_data, _fc_span, _fc_sheet,
                            lob_map=_fc_lob_map,
                        )
            except Exception as _fc_apply_exc:
                st.warning(
                    "⚠️ Forecast columns were skipped — the saved Daily Forecast "
                    f"could not be applied ({_fc_apply_exc}). Re-upload it on the "
                    "Daily Forecast tab."
                )
        else:
            _fc_not_past = _fc_report_date.strftime("%b %d, %Y")

# ── Export buttons & notes (only when data is ready) ─────────────────────────
if data_ok and not summary_df.empty:
    import json as _json
    with _ds_exp:
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

# ── Header — rendered into the slot reserved at the top of the page ──────────
_hdr_slot.markdown(
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
        <div class="hdr-eyebrow">Hertz &nbsp;·&nbsp; Weekly Business Review</div>
        <div class="hdr-title">{_coverage_header(call_date_range)}</div>
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
            Use the <strong>🗑️ Clear Data</strong> button in the Data Source panel to reset the dashboard.
          </span>
        </div>
        """,
        unsafe_allow_html=True,
    )

tab1, tab2, tab3, tab4, tab7, tab8 = st.tabs([
    "📊 Voice Performance Summary",
    "📆 Weekly Breakdown",
    "🗺️ Mapping Manager",
    "🎯 Targets Editor",
    "📅 Daily Forecast",
    "🕸️ Mapping Network",
])

# ── Tab 1: Voice Performance Summary ─────────────────────────────────────────
with tab1:
    if data_ok and _wbr_week_options:
        # Presenting-week picker: scopes the KPIs, tables, header, and
        # forecast window to one week. Weekly Breakdown always shows all.
        def _wk_option_label(v: str) -> str:
            if v == _WBR_ALL_WEEKS:
                return "All weeks (full period)"
            _ws = pd.Timestamp(v)
            _we = _ws + pd.Timedelta(days=6)
            return f"Week of {_ws.strftime('%b %d')} – {_we.strftime('%b %d, %Y')}"

        _wk_col, _lob_inc_col = st.columns([1, 2])
        with _wk_col:
            st.selectbox(
                "📆 Week to present",
                options=[_WBR_ALL_WEEKS] + _wbr_week_options,
                key="wbr_week_select",
                format_func=_wk_option_label,
                help="Scopes the KPIs, summary and vendor tables, header, and "
                     "forecast to one week. The Weekly Breakdown tab always "
                     "shows every week.",
            )
        with _lob_inc_col:
            _vps_universe = st.session_state.get("vps_lob_universe", [])
            if _vps_universe:
                st.markdown(
                    "<div style='padding-top:28px'></div>", unsafe_allow_html=True
                )
                with st.expander("🔍 LOBs to include", expanded=False):
                    _iba, _ibn, _ = st.columns([1, 1, 2])
                    if _iba.button("✅ Select all", key="vps_lob_all_btn", use_container_width=True):
                        for _l in _vps_universe:
                            st.session_state[f"vps_lob_{_l}"] = True
                        st.rerun()
                    if _ibn.button("⬜ Clear all", key="vps_lob_none_btn", use_container_width=True):
                        for _l in _vps_universe:
                            st.session_state[f"vps_lob_{_l}"] = False
                        st.rerun()
                    _inc_cols = st.columns(3)
                    _inc_count = 0
                    for _i, _l in enumerate(_vps_universe):
                        if _inc_cols[_i % 3].checkbox(_l, value=True, key=f"vps_lob_{_l}"):
                            _inc_count += 1
                if _inc_count < len(_vps_universe):
                    st.caption(
                        f"Including **{_inc_count} of {len(_vps_universe)}** LOBs — "
                        "Grand Total, KPIs, vendor tables, and the analysis "
                        "reflect only the ticked LOBs."
                    )

    if data_ok and not summary_df.empty:
        # ── KPI headline tiles ─────────────────────────────────────────────────
        _kpi_cards(summary_df)
        st.markdown("<div style='margin-top:20px'></div>", unsafe_allow_html=True)

        _main_df = summary_df[
            (summary_df["LOB"] == "Grand Total") | (~summary_df["LOB"].isin(_HIDDEN_LOBS))
        ].reset_index(drop=True)

        # Table on the left, auto-written executive analysis on the right
        _tbl_col, _an_col = st.columns([7, 3], gap="medium")
        with _tbl_col:
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

            if _fc_not_past is not None:
                st.caption(
                    f"ℹ️ **Forecast Volume / Forecast Variance appear once the day closes** — "
                    f"the loaded data is for {_fc_not_past}, which isn't a past date yet. "
                    f"Past-dated reports show both columns automatically."
                )
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
                "**ASA** = Avg Speed to Answer (s) · **Var%** = % variance vs target"
            )
        with _an_col:
            _wk_pick = st.session_state.get("wbr_week_select", _WBR_ALL_WEEKS)
            _nar_iv = (
                interval_df[~interval_df["LOB"].isin(_vps_excluded)]
                if _vps_excluded else interval_df
            )
            st.markdown(_wbr_narrative(
                _main_df, _nar_iv,
                focus_week=None if _wk_pick == _WBR_ALL_WEEKS else _wk_pick,
            ))
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

# ── Tab 2: Weekly Breakdown ───────────────────────────────────────────────────
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

        # ── Checkbox filters (replaces the old multiselect pill chips) ─────────
        _flt_lob_col, _flt_vendor_col = st.columns([3, 2])
        with _flt_lob_col:
            with st.expander("🔍 Filter by LOB", expanded=False):
                _ba, _bn, _ = st.columns([1, 1, 3])
                if _ba.button("✅ Select all", key="wk_lob_all_btn", use_container_width=True):
                    for _l in all_lobs:
                        st.session_state[f"wk_lob_{_l}"] = True
                if _bn.button("⬜ Clear all", key="wk_lob_none_btn", use_container_width=True):
                    for _l in all_lobs:
                        st.session_state[f"wk_lob_{_l}"] = False
                _lob_cols = st.columns(4)
                lob_sel = []
                for _i, _l in enumerate(all_lobs):
                    if _lob_cols[_i % 4].checkbox(_l, value=True, key=f"wk_lob_{_l}"):
                        lob_sel.append(_l)
            st.caption(f"Showing **{len(lob_sel)} of {len(all_lobs)}** LOBs")
        with _flt_vendor_col:
            with st.expander("🔍 Filter by Vendor / Supplier", expanded=False):
                _vnd_cols = st.columns(2)
                vendor_sel = []
                for _i, _v in enumerate(all_vendors):
                    if _vnd_cols[_i % 2].checkbox(_v, value=True, key=f"wk_vendor_{_v}"):
                        vendor_sel.append(_v)
            st.caption(f"Showing **{len(vendor_sel)} of {len(all_vendors)}** vendors")

        iv_hdr, iv_btn = st.columns([9, 1])
        with iv_hdr:
            st.subheader("Weekly Breakdown")
        with iv_btn:
            st.markdown("<div style='padding-top:8px'></div>", unsafe_allow_html=True)
            _iv_filtered = interval_df[
                interval_df["LOB"].isin(lob_sel)
                & interval_df["Vendor"].isin(vendor_sel)
            ].copy()
            if st.button("⛶", key="fs_interval", help="Expand table to full screen", use_container_width=True):
                _interval_dialog(_iv_filtered)
        _display_interval(interval_df, lob_sel, vendor_sel)
    elif data_ok:
        st.info("No weekly data available in the loaded files.")

# ── Tab 3: Mapping Manager ────────────────────────────────────────────────────
with tab3:
    st.subheader("Skill → LOB Mapping")
    st.caption(
        "Edit the mapping below to control how each skill queue is assigned to a Line of Business "
        "and Vendor. Click **💾 Apply** to make it the active mapping for all report calculations."
    )

    # ── Status banner ─────────────────────────────────────────────────────────
    _custom = st.session_state.get("custom_mapping")
    if _custom:
        n = len(_custom)
        st.success(f"✅ **Custom mapping active** — {n:,} skill entries in use")
    else:
        st.warning(
            "⚠️ **No mapping loaded** — import your mapping Excel below (or add rows "
            "manually) and click **💾 Apply**. Until then, calls can't be assigned "
            "to a LOB and the summary tables will be empty."
        )

    st.markdown("---")

    # ── Import from Tableau Excel ─────────────────────────────────────────────
    with st.expander("📥 Import / update from Tableau Excel", expanded=False):
        st.markdown(
            "Upload the **Skill Name and ID from Tableau.xlsx** file to add or update entries. "
            "Existing LOB assignments are preserved — only new skills are added (with a blank LOB "
            "you can fill in below). Vendor is updated from the file.  \n"
            "You can also re-upload the **Excel downloaded from this Mapping Manager** to restore "
            "a saved mapping — its LOB and Vendor assignments are applied as-is. "
            "Either way, click **💾 Apply** afterwards to make it the active mapping."
        )
        xl_upload = st.file_uploader(
            "Upload Tableau mapping Excel",
            type=["xlsx", "xls"],
            key="mapping_xl_upload",
            label_visibility="collapsed",
        )
        _fresh_import = st.checkbox(
            "🆕 Start fresh — replace the entire existing mapping with this file",
            key="mapping_xl_replace",
            help="Unchecked: merge into the current table (existing assignments kept). "
                 "Checked: the mapping becomes exactly what's in the file — nothing "
                 "from the current table is carried over.",
        )
        if xl_upload:
            _xl_sig = (xl_upload.name, xl_upload.size, _fresh_import)
            if st.session_state.get("_mapping_import_sig") == _xl_sig:
                st.info("✅ File imported — review below and click **💾 Apply** to activate.")
            else:
                try:
                    current = (
                        pd.DataFrame(columns=["Skill ID", "Queue Name", "LOB", "Vendor"])
                        if _fresh_import else _get_mapping_df()
                    )
                    merged = _import_from_tableau(xl_upload, current)
                    st.session_state["mapping_df"] = merged
                    if _fresh_import:
                        # a fresh import IS the full list — don't re-append built-ins
                        st.session_state["_mapping_df_synced"] = True
                    save_mapping_df(merged)   # persist so other users see the import
                    st.session_state["_mapping_import_sig"] = _xl_sig
                    blank_lob = (merged["LOB"] == "").sum()
                    st.success(
                        f"✅ Imported {len(merged):,} unique skills"
                        + (" (fresh — previous mapping replaced)." if _fresh_import else ". ")
                        + (f" **{blank_lob} skills** have a blank LOB — fill them in below and click Apply." if blank_lob else " All LOBs are mapped.")
                    )
                    st.rerun()
                except Exception as _err:
                    st.error(f"Could not import: {_err}")

    # ── Delete saved mapping ──────────────────────────────────────────────────
    with st.expander("🗑️ Delete saved mapping", expanded=False):
        st.markdown(
            "Deletes the saved mapping **for all users**, leaving the mapping **empty** — "
            "there is no built-in fallback, so calls report under *Unknown* until a new "
            "mapping is imported and applied. To replace it with a file in one step, use "
            "**🆕 Start fresh** in the import section above."
        )
        _map_del_ok = st.checkbox(
            "I understand this removes the saved mapping for all users",
            key="map_del_confirm",
        )
        if st.button(
            "🗑️ Delete custom mapping",
            disabled=not _map_del_ok,
            key="map_del_btn",
        ):
            clear_custom_mapping()
            clear_mapping_df()
            for _map_k in (
                "mapping_df", "custom_mapping",
                "_mapping_df_synced", "_mapping_import_sig",
            ):
                st.session_state.pop(_map_k, None)
            st.rerun()

    st.markdown("---")

    # ── Editable mapping table ─────────────────────────────────────────────────
    _mdf = _get_mapping_df().reset_index(drop=True)
    _mdf_numbered = _mdf.copy()
    _mdf_numbered.insert(0, "#", range(1, len(_mdf_numbered) + 1))

    # Dropdown options = the known lists PLUS whatever values are already in
    # the table — a SelectboxColumn renders any value missing from its options
    # as a blank cell, which would hide LOBs/Vendors introduced by an import.
    _lob_opts_dyn = list(dict.fromkeys(
        _LOB_OPTIONS
        + [v for v in _mdf["LOB"].fillna("").astype(str).str.strip() if v]
    ))
    _vendor_opts_dyn = list(dict.fromkeys(
        _VENDOR_OPTIONS
        + [v for v in _mdf["Vendor"].fillna("").astype(str).str.strip() if v]
    ))

    _map_col_cfg = {
        "#": st.column_config.NumberColumn(
            "#",
            width=50,
            disabled=True,
            help="Row number — for locating entries only, not saved.",
        ),
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
            options=_lob_opts_dyn,
            width=160,
            help="Line of Business this skill maps to.",
        ),
        "Vendor": st.column_config.SelectboxColumn(
            "Vendor",
            options=_vendor_opts_dyn,
            width=110,
            help="Vendor / Supplier handling this skill.",
        ),
    }

    _map_h = min(600, max(300, len(_mdf_numbered) * 36 + 40))

    # ── Search bar ────────────────────────────────────────────────────────────
    _search_query = st.text_input(
        "🔍 Search skills",
        placeholder="Type a Skill ID or Queue Name to check if it's mapped…",
        key="mapping_search",
        label_visibility="collapsed",
    )

    if _search_query.strip():
        _q = _search_query.strip().lower()
        _match = _mdf_numbered[
            _mdf_numbered["Skill ID"].astype(str).str.lower().str.contains(_q, na=False) |
            _mdf_numbered["Queue Name"].astype(str).str.lower().str.contains(_q, na=False)
        ]
        if _match.empty:
            st.error(f"❌ No match found for **{_search_query}** — this skill is not in the mapping yet.")
        else:
            st.success(f"✅ **{len(_match):,} match{'es' if len(_match) != 1 else ''}** found for **{_search_query}** — use the **#** to find it in the table below")
            st.dataframe(
                _match,
                use_container_width=True,
                hide_index=True,
                height=min(300, (len(_match) + 1) * 36 + 4),
            )
        st.markdown("---")

    _cap_col, _dl_col = st.columns([4, 1])
    with _cap_col:
        st.caption(
            f"**{len(_mdf):,} entries** · "
            "Double-click any cell to edit · "
            "Use the ➕ row at the bottom to add new entries · "
            "Click **💾 Apply** when done"
        )
    with _dl_col:
        _mapping_xl_buf = io.BytesIO()
        with pd.ExcelWriter(_mapping_xl_buf, engine="openpyxl") as _xl_writer:
            _mdf.to_excel(_xl_writer, index=False, sheet_name="Mapping")
        st.download_button(
            "⬇️ Download Excel",
            data=_mapping_xl_buf.getvalue(),
            file_name=f"skill_lob_mapping_{datetime.now().strftime('%Y%m%d')}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True,
        )

    _edited_map_raw = st.data_editor(
        _mdf_numbered,
        column_config=_map_col_cfg,
        num_rows="dynamic",        # enables ➕ add-row button at bottom
        hide_index=True,
        use_container_width=True,
        height=_map_h,
        key="mapping_data_editor",
    )
    _edited_map = _edited_map_raw.drop(columns=["#"], errors="ignore")

    # ── LOB coverage summary ───────────────────────────────────────────────────
    if not _edited_map.empty:
        _blank = (_edited_map["LOB"].isna() | (_edited_map["LOB"] == "")).sum()
        if _blank > 0:
            st.warning(f"⚠️ {_blank} skill(s) have no LOB assigned — they will be excluded from report calculations.")

    st.markdown("---")

    # ── Apply / Group-by summary ───────────────────────────────────────────────
    _act_col, _sum_col = st.columns([1, 3])

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

    # ── Apply / Reset / Download ──────────────────────────────────────────────
    _ta_col, _tr_col, _td_col, _ts_col = st.columns([2, 1, 1, 2])

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

    with _td_col:
        # Export the table exactly as the upload parser expects it
        # (LOB / AHT / ASA / ABN%), so a downloaded file re-imports as-is.
        _tgt_csv = (
            _edited_tgt.rename(columns={
                "Target AHT (s)": "AHT",
                "Target ASA (s)": "ASA",
                "Target ABN%":    "ABN%",
            })
            .to_csv(index=False)
            .encode("utf-8")
        )
        st.download_button(
            "⬇️ Download CSV",
            data=_tgt_csv,
            file_name=f"hertz_targets_{datetime.now().strftime('%Y-%m-%d')}.csv",
            mime="text/csv",
            use_container_width=True,
            key="targets_download_btn",
        )

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

# ── Tab 7: Daily Forecast ─────────────────────────────────────────────────────
with tab7:
    st.subheader("Daily Forecast")
    st.caption(
        "Upload the **Daily Forecast** workbook (.xlsx) — one sheet per site "
        "(Consolidated, VXI, TELUS, IGT) with forecast call volumes per LOB per day. "
        "Once loaded, the **Voice Performance Summary** tables gain a "
        "**Forecast Volume** column (the forecast for the report date) and a "
        "**Forecast Variance** column (forecast vs actual offered). "
        "Both columns appear only when the report date in the raw data is a "
        "past date — same-day (intraday) loads don't show them."
    )

    _fc_file = st.file_uploader(
        "Upload Daily Forecast (.xlsx)",
        type=["xlsx"],
        key=f"daily_forecast_upload_{st.session_state['daily_forecast_upload_rev']}",
        help="Saved on the server and shared with all users — upload again only to replace it.",
    )

    if st.session_state.get("daily_forecast_err"):
        st.error(f"Could not read the file: {st.session_state['daily_forecast_err']}")

    _fc_df = _fc_data   # saved forecast with exception rules applied
    if _fc_df is None or _fc_df.empty:
        st.info("⬆️ Upload the Daily Forecast workbook to see the forecast view.")
    else:
        _fc_dates = sorted(_fc_df["Date"].unique())
        _fc_ok_col, _fc_del_col = st.columns([8, 2])
        with _fc_ok_col:
            st.success(
                f"💾 **{st.session_state.get('daily_forecast_name', 'Daily Forecast')}** saved for all users — "
                f"{_fc_dates[0].strftime('%b %d, %Y')} to {_fc_dates[-1].strftime('%b %d, %Y')} · "
                f"{len(_fc_dates)} days · {_fc_df['Site'].nunique()} sites"
            )
        with _fc_del_col:
            if st.button(
                "🗑️ Remove", key="daily_forecast_clear", use_container_width=True,
                help="Delete the saved forecast for all users",
            ):
                clear_daily_forecast()
                for _fc_key in (
                    "daily_forecast_df", "daily_forecast_name",
                    "daily_forecast_mtime", "daily_forecast_sig",
                    "daily_forecast_err",
                ):
                    st.session_state.pop(_fc_key, None)
                st.session_state["daily_forecast_upload_rev"] += 1
                st.rerun()

        _fc_sites = list(dict.fromkeys(_fc_df["Site"]))
        _fc_months = sorted({(d.year, d.month) for d in _fc_dates})

        _fc_c1, _fc_c2 = st.columns([2, 3])
        with _fc_c1:
            _fc_site_sel = st.selectbox("Site", _fc_sites, key="daily_forecast_site")
        with _fc_c2:
            _fc_month_sel = st.multiselect(
                "Month", _fc_months,
                default=_fc_months,
                format_func=lambda ym: pd.Timestamp(ym[0], ym[1], 1).strftime("%B %Y"),
                key="daily_forecast_months",
            )

        _fc_sel = _fc_df[
            (_fc_df["Site"] == _fc_site_sel)
            & _fc_df["Date"].map(lambda d: (d.year, d.month) in set(_fc_month_sel))
        ]
        if _fc_sel.empty:
            st.warning("No data for the selected filters.")
        else:
            _fc_view = forecast_pivot(_fc_sel)
            st.caption(
                f"{len(_fc_view) - 1} days · volumes rounded to whole calls · "
                "LOBs with zero volume for this site are hidden"
            )
            st.dataframe(
                _fc_view,
                use_container_width=True, hide_index=True,
                height=min(38 * (len(_fc_view) + 1) + 4, 620),
                column_config={
                    c: st.column_config.NumberColumn(format="%d")
                    for c in _fc_view.columns if c != "Date"
                },
            )
            st.download_button(
                "⬇️ Download Forecast View (.csv)",
                data=_fc_view.to_csv(index=False).encode("utf-8-sig"),
                file_name=f"daily_forecast_{_fc_site_sel.lower()}.csv",
                mime="text/csv",
            )

# ── Tab 8: Mapping Network ────────────────────────────────────────────────────
with tab8:
    st.subheader("Mapping Network")
    st.caption(
        "The whole reference chain in one glance — every dashboard LOB, how many "
        "skills feed it, which labels the convention rules fold into it, and which "
        "forecast column(s) power its Forecast Volume / Forecast Variance. "
        "⚠️ rows show broken links to fix."
    )

    _net_rules = st.session_state.get("exception_rules", [])
    _net_fc_lobs = (
        set(_fc_data["LOB"].astype(str).unique()) if _fc_data is not None else None
    )
    _net_mdf = _get_mapping_df()
    _net_df, _net_unmatched = _build_mapping_network(_net_mdf, _net_rules, _net_fc_lobs)

    if _net_df.empty:
        st.info(
            "🗺️ No skills mapped yet — import a mapping in the **Mapping Manager** "
            "tab and the network will appear here."
        )
    else:
        _n_linked = int((_net_df["Status"] == "✅ linked").sum())
        _n_warn = int(_net_df["Status"].astype(str).str.startswith("⚠️").sum())
        st.markdown(
            f"**{len(_net_df)} dashboard LOBs** · {int(_net_df['Skills'].sum()):,} skills · "
            f"✅ {_n_linked} linked to forecast · ⚠️ {_n_warn} need attention"
            + ("" if _net_fc_lobs is not None else " · 📄 upload a forecast to check links")
        )
        st.dataframe(
            _net_df,
            hide_index=True,
            use_container_width=True,
            height=min(38 * (len(_net_df) + 1) + 4, 560),
        )

        if _net_unmatched:
            st.warning(
                "**Forecast columns not feeding any LOB:** "
                + ", ".join(_net_unmatched)
                + "  \nAdd a rule below (e.g. `forecast <column> counts toward <LOB>`) "
                "or name a mapping LOB to match."
            )

        # ── Drill-down: skills behind one LOB ─────────────────────────────────
        _net_sel = st.selectbox(
            "🔍 Drill into a LOB to see its skills",
            ["—"] + list(_net_df["Dashboard LOB"]),
            key="net_drill",
        )
        if _net_sel != "—":
            _net_ren = _rules_lob_renames(_net_rules)
            _net_skills = _net_mdf[
                _net_mdf["LOB"].astype(str).str.strip()
                .map(lambda x: _net_ren.get(x, x) if x else "(no LOB assigned)")
                == _net_sel
            ][["Skill ID", "Queue Name", "LOB", "Vendor"]].reset_index(drop=True)
            st.caption(f"**{len(_net_skills)} skill(s)** report under **{_net_sel}**")
            st.dataframe(
                _net_skills,
                hide_index=True,
                use_container_width=True,
                height=min(38 * (len(_net_skills) + 1) + 4, 420),
            )

    st.markdown("---")

    # ── Convention rules (plain-text) — these define the network's links ──────
    with st.expander("✏️ Convention rules — edit the connections", expanded=False):
        st.caption(
            "One rule per line; whatever the dashboard understands is applied for "
            "**all users** and the network above updates. Lines starting with `#` "
            "are comments.  \n"
            "Examples: `CSCC in Forecast and Mapping needs to be labeled Billing/Disputes` · "
            "`CSSD in mapping is CUSTOMER SPECIAL SERVICES DEPARTMENT in Forecast` · "
            "`label CSCC as Billing/Disputes` · `forecast CSSD counts toward International` · "
            "`hide OPERATIONS` *(excluded everywhere, including Grand Total)*"
        )
        _rules_rev = st.session_state.setdefault("exception_rules_rev", 0)
        _rules_text_val = st.text_area(
            "Rules",
            value=st.session_state.get("exception_rules_text", ""),
            height=220,
            key=f"exception_rules_text_area_{_rules_rev}",
            label_visibility="collapsed",
            placeholder="One rule per line, e.g.\nCSCC in Forecast and Mapping needs to be labeled Billing/Disputes",
        )

        # Live interpretation of what's currently typed (applied only on Apply)
        _rules_preview, _rules_bad = _parse_rules_text(_rules_text_val)
        if _rules_preview:
            st.markdown("**How the dashboard reads this:**")
            for _r in _rules_preview:
                if _r["Rule Type"] == _RULE_RENAME:
                    st.markdown(f"- 🔁 **{_r['From']}** is shown as **{_r['To']}** everywhere")
                elif _r["Rule Type"] == _RULE_HIDE:
                    st.markdown(
                        f"- 🙈 **{_r['From']}** is excluded everywhere — "
                        "no row, and not counted in Grand Total"
                    )
                else:
                    st.markdown(
                        f"- 🔗 forecast column **{_r['From']}** counts toward LOB **{_r['To']}**"
                    )
        if _rules_bad:
            st.warning(
                "These lines were **not understood** and will be skipped:  \n"
                + "  \n".join(f"• {l}" for l in _rules_bad)
            )

        _r_apply, _r_reset, _r_info = st.columns([1, 1, 3])
        with _r_apply:
            if st.button("💾 Apply Rules", type="primary", use_container_width=True,
                         key="rules_apply_btn"):
                st.session_state["exception_rules"] = _rules_preview
                st.session_state["exception_rules_text"] = _rules_text_val
                save_exception_rules(_rules_text_val, _rules_preview)
                st.rerun()
        with _r_reset:
            if st.button("↩️ Reset to defaults", use_container_width=True,
                         key="rules_reset_btn"):
                _def_rules = [dict(r) for r in _DEFAULT_RULES]
                _def_text = _rules_to_text(_def_rules)
                st.session_state["exception_rules"] = _def_rules
                st.session_state["exception_rules_text"] = _def_text
                save_exception_rules(_def_text, _def_rules)
                st.session_state["exception_rules_rev"] += 1
                st.rerun()
        with _r_info:
            _active_rules = st.session_state.get("exception_rules", [])
            _n_ren = sum(1 for r in _active_rules if r.get("Rule Type") == _RULE_RENAME)
            st.caption(
                f"**{len(_active_rules)} rule(s) currently active** — {_n_ren} rename, "
                f"{len(_active_rules) - _n_ren} forecast link. Edits take effect "
                "when you click Apply."
            )
