import io
import os
import subprocess
import sys
from datetime import date, timedelta

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components


@st.cache_resource(show_spinner="Installing browser (first run only)…")
def _install_playwright_browser() -> None:
    """Install Chromium binaries on first run — needed on Streamlit Cloud."""
    subprocess.run(
        [sys.executable, "-m", "playwright", "install", "chromium"],
        capture_output=True,
    )


_install_playwright_browser()

st.set_page_config(
    page_title="Verint Social Media — Hertz",
    page_icon="📱",
    layout="wide",
)

# Move sidebar logo above nav links
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
    reorder();
    setTimeout(reorder, 300);
    setTimeout(reorder, 900);
})();
</script>
""", height=0)


st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800;900&display=swap');

/* ── Animations ── */
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

html, body, .stApp { font-family: 'Inter', sans-serif !important; }
.stApp {
    background: linear-gradient(135deg, #e6ecf5 0%, #eef2f8 50%, #e3edf6 100%) !important;
}
.stApp::before {
    content: '';
    position: fixed; inset: 0;
    background-image: radial-gradient(circle, rgba(26,58,92,0.055) 1px, transparent 1px);
    background-size: 28px 28px;
    animation: particleDrift 18s linear infinite;
    pointer-events: none; z-index: 0;
}

/* ── Sidebar ── */
section[data-testid="stSidebar"] {
    background: linear-gradient(180deg,
        #040c18 0%, #07111f 15%, #0a1628 35%,
        #112244 60%, #0f2d4a 80%, #07111f 100%) !important;
    background-size: 100% 300% !important;
    animation: sidebarFlow 14s ease-in-out infinite alternate !important;
    border-right: 2px solid rgba(255,215,0,0.45) !important;
    box-shadow: 4px 0 36px rgba(0,0,0,0.5) !important;
}

/* ── Nav Links ── */
[data-testid="stSidebarNav"] { padding: 2px 10px 14px !important; }
[data-testid="stSidebarNav"]::before {
    content: "NAVIGATION";
    display: block; font-size: 9.5px; font-weight: 800;
    letter-spacing: 2.5px; color: rgba(255,215,0,0.55);
    padding: 10px 6px 8px; font-family: 'Inter', sans-serif; text-transform: uppercase;
}
[data-testid="stSidebarNav"] a {
    display: flex !important; align-items: center !important;
    margin: 4px 0 !important; padding: 12px 14px 12px 18px !important;
    border-radius: 10px !important; border: 1px solid rgba(255,215,0,0.1) !important;
    background: rgba(255,255,255,0.04) !important;
    text-decoration: none !important; transition: all 0.22s ease !important;
    animation: navEntrance 0.4s ease both !important;
    position: relative !important; overflow: hidden !important;
}
[data-testid="stSidebarNav"] a::before {
    content: ''; position: absolute; left: 0; top: 15%; bottom: 15%;
    width: 3px; border-radius: 0 3px 3px 0;
    background: rgba(255,215,0,0.25); transition: all 0.22s ease;
}
[data-testid="stSidebarNav"] a::after {
    content: ''; position: absolute; top: 0; left: -80%;
    width: 50%; height: 100%;
    background: linear-gradient(90deg, transparent, rgba(255,215,0,0.06), transparent);
    transition: left 0.4s ease;
}
[data-testid="stSidebarNav"] a:hover {
    background: rgba(255,215,0,0.09) !important;
    border-color: rgba(255,215,0,0.32) !important;
    transform: translateX(5px) !important;
    box-shadow: 0 4px 18px rgba(0,0,0,0.25) !important;
}
[data-testid="stSidebarNav"] a:hover::before { background: #FFD700; box-shadow: 0 0 10px rgba(255,215,0,0.7); }
[data-testid="stSidebarNav"] a:hover::after  { left: 140%; }
[data-testid="stSidebarNav"] a[aria-current="page"] {
    background: linear-gradient(90deg, rgba(255,215,0,0.13), rgba(255,215,0,0.06)) !important;
    border-color: rgba(255,215,0,0.42) !important;
    box-shadow: 0 4px 18px rgba(0,0,0,0.22) !important;
}
[data-testid="stSidebarNav"] a[aria-current="page"]::before {
    background: #FFD700; box-shadow: 0 0 12px rgba(255,215,0,0.8);
}
[data-testid="stSidebarNav"] a li,
[data-testid="stSidebarNav"] a span,
[data-testid="stSidebarNav"] ul li span {
    color: #ccddf8 !important; font-weight: 600 !important;
    font-size: 13.5px !important; letter-spacing: 0.2px !important;
}
[data-testid="stSidebarNav"] a[aria-current="page"] li,
[data-testid="stSidebarNav"] a[aria-current="page"] span {
    color: #FFD700 !important; text-shadow: 0 0 14px rgba(255,215,0,0.45) !important;
}

/* ── Sidebar text ── */
section[data-testid="stSidebar"] label,
section[data-testid="stSidebar"] p,
section[data-testid="stSidebar"] span,
section[data-testid="stSidebar"] div,
section[data-testid="stSidebar"] caption,
section[data-testid="stSidebar"] small { color: #c0d4ee !important; }
section[data-testid="stSidebar"] .stMarkdown h3 {
    color: #FFD700 !important; font-size: 10px !important; font-weight: 800 !important;
    letter-spacing: 2.2px !important; text-transform: uppercase !important;
    border-bottom: 1px solid rgba(255,215,0,0.18); padding-bottom: 6px; margin-bottom: 10px;
}
section[data-testid="stSidebar"] hr { border-color: rgba(255,255,255,0.06) !important; }
section[data-testid="stSidebar"] .stDownloadButton button,
section[data-testid="stSidebar"] .stButton button {
    background: linear-gradient(135deg, #FFD700 0%, #f5c400 55%, #e8b000 100%) !important;
    color: #0a1628 !important; font-weight: 800 !important; border: none !important;
    border-radius: 10px !important; width: 100% !important;
    transition: all 0.25s ease !important;
    box-shadow: 0 3px 14px rgba(255,215,0,0.38), 0 1px 4px rgba(0,0,0,0.22) !important;
}
section[data-testid="stSidebar"] .stDownloadButton button:hover,
section[data-testid="stSidebar"] .stButton button:hover {
    transform: translateY(-2px) !important;
    box-shadow: 0 7px 22px rgba(255,215,0,0.52) !important;
}

hr { border: none !important; height: 1px !important;
     background: linear-gradient(90deg, transparent, #bfcfe4, transparent) !important;
     margin: 22px 0 !important; }
.stCaption { color: #8099b8 !important; font-size: 12px !important; }
h3 { color: #0a1628 !important; font-weight: 800 !important; }

/* ── Date picker ── */
[data-testid="stDateInput"] > div {
    border: 1.5px solid #b0bec5 !important; border-radius: 8px !important;
    background: #ffffff !important; padding: 2px 8px !important;
}
[data-testid="stDateInput"] > div:focus-within {
    border-color: #1a3a5c !important;
    box-shadow: 0 0 0 2px rgba(26,58,92,0.15) !important;
}
</style>
""", unsafe_allow_html=True)

# ── Constants ─────────────────────────────────────────────────────────────────
import importlib
from pathlib import Path
import src.conversocial_scraper as _scraper_mod
importlib.reload(_scraper_mod)
from src.conversocial_scraper import ALL_PLATFORMS, DEFAULT_QUEUES, PLAYWRIGHT_OK, AUTH_DIR

SESSION_OK = PLAYWRIGHT_OK  # auto-login handles expired sessions

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
            Verint Social Media
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.markdown("---")

    st.markdown("### 🔐 Verint Login")
    st.caption("Enter your Verint credentials before extracting.")
    sidebar_username = st.text_input("Username", value="", key="vc_user")
    sidebar_password = st.text_input("Password", value="", type="password", key="vc_pass")

    st.markdown("---")

    if not PLAYWRIGHT_OK:
        st.warning(
            "Playwright not installed.\n\n"
            "```\npy -m pip install playwright\npy -m playwright install chromium\n```"
        )

# ── Header ────────────────────────────────────────────────────────────────────
yesterday = date.today() - timedelta(days=1)
yesterday_str = yesterday.strftime("%B %d, %Y")

# Header date updates after buttons are rendered (session state tracks last run)
header_date = st.session_state.get("last_extract_date", yesterday_str)

# ── Platform & Queue filters (main pane) ─────────────────────────────────────
col_plat, col_queue = st.columns([1, 1])
with col_plat:
    st.markdown("#### 📱 Platforms")
    platforms_sel = st.multiselect(
        "platforms",
        options=ALL_PLATFORMS,
        default=ALL_PLATFORMS,
        label_visibility="collapsed",
    )
with col_queue:
    st.markdown("#### 🗂️ Queues")
    st.caption("One queue per line.")
    queues_raw = st.text_area(
        "queues",
        value="\n".join(DEFAULT_QUEUES),
        height=180,
        label_visibility="collapsed",
    )
    queues_sel = [q.strip() for q in queues_raw.strip().splitlines() if q.strip()]

st.markdown("---")

st.markdown(
    f"""
    <div style='background:linear-gradient(120deg,#0a1628 0%,#1a3a5c 60%,#1d4675 100%);
                padding:20px 32px; border-radius:14px; margin-bottom:16px;
                border-bottom:3px solid #FFD700;
                box-shadow:0 6px 28px rgba(10,22,40,0.28);
                display:flex; align-items:center; justify-content:space-between'>
      <div>
        <div style='font-size:10px;color:#FFD700;font-weight:800;
                    letter-spacing:2.5px;text-transform:uppercase;margin-bottom:4px;opacity:0.9'>
          Hertz &nbsp;·&nbsp; Verint Social Analytics
        </div>
        <div style='font-size:26px;font-weight:800;color:white;line-height:1.1;letter-spacing:-0.5px'>
          Daily Extract &nbsp;·&nbsp; {header_date}
        </div>
      </div>
      <div style='background:rgba(255,215,0,0.15);border:1px solid rgba(255,215,0,0.35);
                  border-radius:8px;padding:6px 14px;font-size:12px;
                  color:#FFD700;font-weight:600;letter-spacing:0.5px'>
        {len(platforms_sel)} PLATFORMS
      </div>
    </div>
    """,
    unsafe_allow_html=True,
)

st.markdown(
    "Logs into Conversocial, loops through each selected platform, extracts all 10 metric cards "
    "and outputs an Excel file ready for tracking. **Takes ~2 min to run.**"
)
st.markdown("---")

# ── Persistent results (shown above extraction controls so they never get hidden) ──
if st.session_state.get("pending_dupes"):
    dupes = st.session_state["pending_dupes"]
    dupe_str = ", ".join(f"{d[0]} / {d[1]}" for d in dupes)
    st.warning(f"**Duplicate rows found:** {dupe_str}")
    st.caption("These Date + Platform combinations already exist. Replace them or keep the existing data?")
    col_rep, col_keep, _ = st.columns([1, 1, 2])
    with col_rep:
        if st.button("🔄 Replace", type="primary", use_container_width=True):
            existing = st.session_state.get("accumulated_df", pd.DataFrame())
            new_df   = st.session_state["pending_df"]
            dupe_idx = existing.set_index(["Date","Platform"]).index.isin(
                new_df.set_index(["Date","Platform"]).index
            )
            st.session_state["accumulated_df"] = pd.concat(
                [existing[~dupe_idx], new_df], ignore_index=True
            )
            st.session_state.pop("pending_df", None)
            st.session_state.pop("pending_dupes", None)
            st.rerun()
    with col_keep:
        if st.button("⛔ Keep Existing", use_container_width=True):
            existing = st.session_state.get("accumulated_df", pd.DataFrame())
            new_df   = st.session_state["pending_df"]
            non_dupe = new_df[
                ~new_df.set_index(["Date","Platform"]).index.isin(
                    existing.set_index(["Date","Platform"]).index
                )
            ]
            if not non_dupe.empty:
                st.session_state["accumulated_df"] = pd.concat(
                    [existing, non_dupe], ignore_index=True
                )
            st.session_state.pop("pending_df", None)
            st.session_state.pop("pending_dupes", None)
            st.rerun()

if "accumulated_df" in st.session_state and not st.session_state["accumulated_df"].empty:
    acc = st.session_state["accumulated_df"].sort_values(
        ["Date", "Platform"], ignore_index=True
    )
    col_res, col_clear = st.columns([5, 1])
    with col_res:
        st.markdown("### Results")
    with col_clear:
        if st.button("🗑️ Clear Data", use_container_width=True):
            st.session_state.pop("accumulated_df", None)
            st.session_state.pop("pending_df", None)
            st.session_state.pop("pending_dupes", None)
            st.rerun()
    st.dataframe(acc, use_container_width=True, hide_index=True)
    buf = io.BytesIO()
    dates = sorted(acc["Date"].astype(str).unique().tolist())
    fname = (
        f"social_analytics_{dates[0]}.xlsx" if len(dates) == 1
        else f"social_analytics_{dates[0]}_to_{dates[-1]}.xlsx"
    )
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        acc.to_excel(writer, sheet_name="Social Analytics", index=False)
        ws = writer.sheets["Social Analytics"]
        for col_cells in ws.columns:
            max_len = max(len(str(c.value)) if c.value else 0 for c in col_cells)
            ws.column_dimensions[col_cells[0].column_letter].width = min(max_len + 4, 40)
    buf.seek(0)
    st.download_button(
        "⬇️ Download Excel", data=buf, file_name=fname,
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        type="primary",
    )

st.markdown("---")

# ── Extract buttons ───────────────────────────────────────────────────────────
_btn_disabled = not PLAYWRIGHT_OK or not platforms_sel

col_left, col_right = st.columns(2)
with col_left:
    run_btn = st.button(
        "🔄 Extract Yesterday's Data",
        disabled=_btn_disabled,
        type="primary",
        use_container_width=True,
    )
with col_right:
    range_btn = st.button(
        "📆 Extract Date Range",
        disabled=_btn_disabled,
        use_container_width=True,
    )
    col_start, col_end = st.columns(2)
    with col_start:
        range_start = st.date_input(
            "Start",
            value=yesterday - timedelta(days=6),
            max_value=yesterday,
            key="range_start_input",
        )
    with col_end:
        range_end = st.date_input(
            "End",
            value=yesterday,
            max_value=yesterday,
            key="range_end_input",
        )

# Validate range
if range_btn and range_start > range_end:
    st.error("Start date must be on or before the end date.")
    range_btn = False

# ── Run extraction ────────────────────────────────────────────────────────────
def _merge_into_accumulated(new_df: pd.DataFrame) -> None:
    existing = st.session_state.get("accumulated_df", pd.DataFrame())
    if existing.empty:
        st.session_state["accumulated_df"] = new_df
        st.session_state.pop("pending_df", None)
        st.session_state.pop("pending_dupes", None)
    else:
        dupes = new_df[
            new_df.set_index(["Date", "Platform"]).index.isin(
                existing.set_index(["Date", "Platform"]).index
            )
        ][["Date", "Platform"]].values.tolist()
        if dupes:
            st.session_state["pending_df"]   = new_df
            st.session_state["pending_dupes"] = dupes
        else:
            st.session_state["accumulated_df"] = pd.concat(
                [existing, new_df], ignore_index=True
            )
            st.session_state.pop("pending_df", None)
            st.session_state.pop("pending_dupes", None)


if run_btn or range_btn:
    from src.conversocial_scraper import ConversocialScraper
    from datetime import timedelta as _td

    progress_bar = st.progress(0.0, text="Opening browser…")
    status_box   = st.empty()

    # Build the dates list and display label
    if range_btn:
        _d, _dates = range_start, []
        while _d <= range_end:
            _dates.append(_d.strftime("%Y-%m-%d"))
            _d += _td(days=1)
        display_label = (
            f"{range_start.strftime('%B %d')} – {range_end.strftime('%B %d, %Y')}"
        )
    else:
        _dates = None
        display_label = yesterday_str

    st.session_state["last_extract_date"] = display_label
    _target = None
    _total  = (len(_dates) if _dates else 1) * len(platforms_sel)

    def _on_progress(step: int, platform: str, date_str: str = "", total: int = _total) -> None:
        pct  = step / total if total else 0
        label = f"{date_str} · " if date_str else ""
        progress_bar.progress(pct, text=f"{label}Extracting {platform}… ({step + 1}/{total})")

    def _on_status(msg: str) -> None:
        progress_bar.progress(0.0, text=msg)

    try:
        _headless = os.getenv("STREAMLIT_SHARING_MODE") == "true" or os.getenv("HOME") == "/home/appuser"
        scraper = ConversocialScraper(headless=_headless)
        new_df = scraper.run(
            platforms=platforms_sel,
            queues=queues_sel,
            on_progress=_on_progress,
            on_status=_on_status,
            target_date=_target,
            dates=_dates,
            username=sidebar_username or None,
            password=sidebar_password or None,
        )
        progress_bar.progress(1.0, text="Done!")
        n_rows = len(new_df)
        n_days = new_df["Date"].nunique() if not new_df.empty else 0
        status_box.success(
            f"Extracted {n_rows} row(s) across {n_days} day(s) for {display_label}.",
            icon="✅",
        )
        _merge_into_accumulated(new_df)

    except Exception as exc:
        progress_bar.empty()
        st.error(f"Extraction failed: {exc}")
        st.caption(
            "If this is a login error, check credentials in `.streamlit/secrets.toml`. "
            "If it's a selector error, the Conversocial UI may need a selector update — "
            "contact your developer."
        )

    # Results and download are displayed above the extraction controls.
