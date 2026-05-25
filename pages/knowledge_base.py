import streamlit as st
from supabase import create_client, Client
import hashlib
import datetime

# ─────────────────────────────────────────
# CONFIG
# ─────────────────────────────────────────
SUPABASE_URL = st.secrets["supabase"]["url"]
SUPABASE_KEY = st.secrets["supabase"]["service_role_key"]

@st.cache_resource
def get_supabase() -> Client:
    return create_client(SUPABASE_URL, SUPABASE_KEY)

supabase = get_supabase()

# ─────────────────────────────────────────
# THEME — mirrors app.py exactly
# ─────────────────────────────────────────
def inject_css():
    st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800;900&display=swap');

/* ══ Animations ══════════════════════════════════════════════════════════ */
@keyframes sidebarFlow {
    0%   { background-position: 0% 0%; }
    100% { background-position: 0% 100%; }
}
@keyframes navEntrance {
    from { opacity: 0; transform: translateX(-12px); }
    to   { opacity: 1; transform: translateX(0); }
}
@keyframes logoPulse {
    0%,100% { box-shadow: 0 4px 18px rgba(255,215,0,0.45), 0 0 0 0 rgba(255,215,0,0.2); }
    50%      { box-shadow: 0 6px 26px rgba(255,215,0,0.65), 0 0 18px rgba(255,215,0,0.18); }
}
@keyframes subtitleShift {
    0%,100% { color: rgba(255,215,0,0.65); }
    50%      { color: rgba(255,215,0,0.95); }
}
@keyframes fadeSlideIn {
    from { opacity: 0; transform: translateY(14px); }
    to   { opacity: 1; transform: translateY(0); }
}
@keyframes hdrGradient {
    0%   { background-position: 0% 50%; }
    50%  { background-position: 100% 50%; }
    100% { background-position: 0% 50%; }
}
@keyframes hdrBeam {
    0%   { left: -55%; opacity: 0; }
    15%  { opacity: 1; }
    85%  { opacity: 1; }
    100% { left: 130%; opacity: 0; }
}
@keyframes particleDrift {
    0%   { background-position: 0 0; }
    100% { background-position: 48px 48px; }
}

/* ══ Base ════════════════════════════════════════════════════════════════ */
html, body, .stApp {
    font-family: 'Inter', sans-serif !important;
    background: linear-gradient(135deg, #e6ecf5 0%, #eef2f8 50%, #e3edf6 100%) !important;
}
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

/* ══ Sidebar ═════════════════════════════════════════════════════════════ */
section[data-testid="stSidebar"] {
    background: linear-gradient(180deg,
        #040c18 0%, #07111f 15%, #0a1628 35%,
        #112244 60%, #0f2d4a 80%, #07111f 100%) !important;
    background-size: 100% 300% !important;
    animation: sidebarFlow 14s ease-in-out infinite alternate !important;
    border-right: 2px solid rgba(255,215,0,0.45) !important;
    box-shadow: 4px 0 36px rgba(0,0,0,0.5) !important;
}

/* ── Global Nav Links (stSidebarNav) ─────────────────────────────────── */
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
[data-testid="stSidebarNav"] a::before {
    content: '';
    position: absolute;
    left: 0; top: 15%; bottom: 15%;
    width: 3px;
    border-radius: 0 3px 3px 0;
    background: rgba(255,215,0,0.25);
    transition: all 0.22s ease;
}
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

/* ── Hide Verint + underscore pages from nav ─────────────────────────── */
[data-testid="stSidebarNav"] a[href*="Verint"],
[data-testid="stSidebarNav"] a[href*="verint"],
[data-testid="stSidebarNav"] a[href*="2_Verint"],
[data-testid="stSidebarNav"] a[href*="_2_Verint"] { display: none !important; }

/* ── Sidebar text ─────────────────────────────────────────────────────── */
section[data-testid="stSidebar"] label,
section[data-testid="stSidebar"] p,
section[data-testid="stSidebar"] span,
section[data-testid="stSidebar"] div,
section[data-testid="stSidebar"] small { color: #c0d4ee !important; }
section[data-testid="stSidebar"] hr {
    border-color: rgba(255,255,255,0.06) !important;
}
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

/* ── Sidebar radio nav ───────────────────────────────────────────────── */
section[data-testid="stSidebar"] .stRadio > div {
    gap: 4px !important;
}
section[data-testid="stSidebar"] .stRadio label {
    display: flex !important;
    align-items: center !important;
    padding: 10px 14px 10px 18px !important;
    border-radius: 10px !important;
    border: 1px solid rgba(255,215,0,0.1) !important;
    background: rgba(255,255,255,0.04) !important;
    color: #ccddf8 !important;
    font-weight: 600 !important;
    font-size: 13.5px !important;
    cursor: pointer !important;
    transition: all 0.22s ease !important;
    position: relative !important;
}
section[data-testid="stSidebar"] .stRadio label:hover {
    background: rgba(255,215,0,0.09) !important;
    border-color: rgba(255,215,0,0.32) !important;
    transform: translateX(5px) !important;
}
section[data-testid="stSidebar"] [data-testid="stRadio"] input:checked + div {
    color: #FFD700 !important;
}

/* ── Sidebar buttons ─────────────────────────────────────────────────── */
section[data-testid="stSidebar"] .stButton button {
    background: linear-gradient(135deg, #FFD700 0%, #f5c400 55%, #e8b000 100%) !important;
    color: #0a1628 !important;
    font-weight: 800 !important;
    border: none !important;
    border-radius: 10px !important;
    width: 100% !important;
    transition: all 0.25s ease !important;
    box-shadow: 0 3px 14px rgba(255,215,0,0.38), 0 1px 4px rgba(0,0,0,0.22) !important;
}
section[data-testid="stSidebar"] .stButton button:hover {
    transform: translateY(-2px) !important;
    box-shadow: 0 7px 22px rgba(255,215,0,0.52) !important;
}

/* ══ Main content ════════════════════════════════════════════════════════ */
[data-testid="stMainBlockContainer"] {
    animation: fadeSlideIn 0.4s ease both;
}

/* ── Expanders ───────────────────────────────────────────────────────── */
details {
    border: 1px solid rgba(200,215,235,0.8) !important;
    border-radius: 12px !important;
    overflow: hidden;
    background: white !important;
}
details[open] summary { border-bottom: 1px solid rgba(200,215,235,0.7); }
summary {
    background: linear-gradient(90deg, #edf3fb 0%, #f5f9fd 100%) !important;
    font-weight: 700 !important;
    color: #1a3a5c !important;
    padding: 14px 18px !important;
    border-radius: 12px !important;
}
summary:hover { background: linear-gradient(90deg, #e1edf8 0%, #eaf3fc 100%) !important; }

/* ── Containers / cards ──────────────────────────────────────────────── */
[data-testid="stVerticalBlockBorderWrapper"] {
    background: white !important;
    border: 1px solid rgba(200,215,235,0.8) !important;
    border-radius: 12px !important;
    box-shadow: 0 2px 12px rgba(0,0,0,0.05) !important;
}

/* ── Inputs ──────────────────────────────────────────────────────────── */
[data-testid="stTextInput"] input,
[data-testid="stTextArea"] textarea {
    background: white !important;
    border: 1px solid rgba(200,215,235,0.9) !important;
    border-radius: 8px !important;
    color: #0a1628 !important;
}
[data-testid="stTextInput"] input:focus,
[data-testid="stTextArea"] textarea:focus {
    border-color: #FFD700 !important;
    box-shadow: 0 0 0 2px rgba(255,215,0,0.15) !important;
}

/* ── Primary button → Gold ───────────────────────────────────────────── */
[data-testid="stFormSubmitButton"] button,
button[kind="primary"] {
    background: linear-gradient(135deg, #FFD700 0%, #f5c400 55%, #e8b000 100%) !important;
    color: #0a1628 !important;
    font-weight: 800 !important;
    border: none !important;
    border-radius: 10px !important;
    box-shadow: 0 3px 14px rgba(255,215,0,0.38) !important;
    transition: all 0.25s ease !important;
}
[data-testid="stFormSubmitButton"] button:hover,
button[kind="primary"]:hover {
    transform: translateY(-2px) !important;
    box-shadow: 0 7px 22px rgba(255,215,0,0.52) !important;
}

/* ── Tabs ────────────────────────────────────────────────────────────── */
.stTabs [data-baseweb="tab-list"] {
    background: transparent;
    border-bottom: 2px solid rgba(200,215,235,0.85);
    gap: 4px; padding: 0;
}
.stTabs [data-baseweb="tab"] {
    color: #7a90aa !important;
    font-weight: 600 !important;
    font-size: 14px !important;
    padding: 11px 26px !important;
    border-radius: 10px 10px 0 0 !important;
    background: transparent !important;
    transition: all 0.2s ease !important;
}
.stTabs [data-baseweb="tab"]:hover { color: #1a3a5c !important; }
.stTabs [aria-selected="true"] {
    background: white !important;
    color: #0a1628 !important;
    font-weight: 700 !important;
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
}

/* ── Alert boxes ─────────────────────────────────────────────────────── */
.stAlert { border-radius: 10px !important; }

/* ── Dividers ────────────────────────────────────────────────────────── */
hr {
    border: none !important;
    height: 1px !important;
    background: linear-gradient(90deg, transparent, #bfcfe4, transparent) !important;
    margin: 22px 0 !important;
}

/* ── Text ────────────────────────────────────────────────────────────── */
h3 { color: #0a1628 !important; font-weight: 800 !important; }
h4 { color: #1a3a5c !important; font-weight: 700 !important;
     border-left: 3px solid #FFD700; padding-left: 12px; }
.stCaption { color: #8099b8 !important; font-size: 12px !important; }
</style>
""", unsafe_allow_html=True)

# ─────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────
def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()

def login(email: str, password: str):
    hashed = hash_password(password)
    result = (
        supabase.table("kb_users")
        .select("*")
        .eq("email", email.lower().strip())
        .eq("password", hashed)
        .eq("is_active", True)
        .execute()
    )
    return result.data[0] if result.data else None

def get_categories():
    return supabase.table("kb_categories").select("*").order("order_num").execute().data

def get_approved_docs(category_id=None, search=None):
    query = (
        supabase.table("kb_documents")
        .select("*, kb_categories(name), kb_users!kb_documents_submitted_by_fkey(name)")
        .eq("status", "approved")
    )
    if category_id:
        query = query.eq("category_id", category_id)
    if search:
        query = query.ilike("title", f"%{search}%")
    return query.order("updated_at", desc=True).execute().data

def get_pending_docs():
    return (
        supabase.table("kb_documents")
        .select("*, kb_categories(name), kb_users!kb_documents_submitted_by_fkey(name)")
        .eq("status", "pending")
        .order("submitted_at")
        .execute()
        .data
    )

def get_all_docs_by_status(status):
    return (
        supabase.table("kb_documents")
        .select("*, kb_categories(name), kb_users!kb_documents_submitted_by_fkey(name)")
        .eq("status", status)
        .order("submitted_at", desc=True)
        .execute()
        .data
    )

def upload_file(file):
    try:
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        file_name = f"{timestamp}_{file.name.replace(' ', '_')}"
        file_bytes = file.read()
        supabase.storage.from_("kb-documents").upload(
            file_name, file_bytes, {"content-type": file.type}
        )
        return supabase.storage.from_("kb-documents").get_public_url(file_name), file_name
    except Exception as e:
        st.error(f"File upload failed: {e}")
        return None, None

def approve_doc(doc_id, reviewer_id):
    supabase.table("kb_documents").update({
        "status": "approved",
        "reviewed_by": reviewer_id,
        "reviewed_at": datetime.datetime.now().isoformat(),
        "updated_at": datetime.datetime.now().isoformat()
    }).eq("id", doc_id).execute()

def reject_doc(doc_id, reviewer_id):
    supabase.table("kb_documents").update({
        "status": "rejected",
        "reviewed_by": reviewer_id,
        "reviewed_at": datetime.datetime.now().isoformat(),
        "updated_at": datetime.datetime.now().isoformat()
    }).eq("id", doc_id).execute()

# ─────────────────────────────────────────
# PAGES
# ─────────────────────────────────────────

def page_login():
    st.markdown("""
    <div style="max-width:420px; margin:80px auto 0 auto; padding:40px;
                background:white; border:1px solid rgba(200,215,235,0.9);
                border-radius:16px; box-shadow:0 8px 36px rgba(0,0,0,0.1);">
        <div style="text-align:center; margin-bottom:32px;">
            <div style="background:linear-gradient(135deg,#FFD700 0%,#f5c400 60%,#e8b000 100%);
                        display:inline-block; padding:8px 26px; border-radius:7px;
                        box-shadow:0 4px 18px rgba(255,215,0,0.45);">
                <span style="font-family:Arial Black,Impact,sans-serif;
                             font-size:24px; font-weight:900; color:#0a1220;
                             letter-spacing:3px;">HERTZ</span>
            </div>
            <div style="font-size:9px; letter-spacing:3.5px; margin-top:10px;
                        text-transform:uppercase; font-weight:700; color:#7a90aa;">
                Powered by Callinsite
            </div>
            <h2 style="color:#0a1628; margin-top:20px; font-size:1.3rem; font-weight:700;">
                RTA Knowledge Base
            </h2>
            <p style="color:#7a90aa; font-size:0.85rem; margin-top:4px;">
                Sign in to access process guides and reports
            </p>
        </div>
    </div>
    """, unsafe_allow_html=True)

    col1, col2, col3 = st.columns([1, 1.2, 1])
    with col2:
        with st.form("login_form"):
            email    = st.text_input("Email", placeholder="yourname@callinsite.com")
            password = st.text_input("Password", type="password")
            submit   = st.form_submit_button("Login", use_container_width=True)
            if submit:
                if not email or not password:
                    st.error("Please enter both email and password.")
                else:
                    with st.spinner("Signing in..."):
                        user = login(email, password)
                    if user:
                        st.session_state.user = user
                        st.rerun()
                    else:
                        st.error("Invalid credentials. Please try again.")


def page_knowledge_base():
    st.markdown("""
    <style>
    @keyframes hdrGradient {
        0%   { background-position: 0% 50%; }
        50%  { background-position: 100% 50%; }
        100% { background-position: 0% 50%; }
    }
    @keyframes hdrBeam {
        0%   { left: -55%; opacity: 0; }
        15%  { opacity: 1; }
        85%  { opacity: 1; }
        100% { left: 130%; opacity: 0; }
    }
    @keyframes livePulse {
        0%,100% { box-shadow: 0 0 0 0 rgba(74,222,128,0.55); }
        50%      { box-shadow: 0 0 0 5px rgba(74,222,128,0); }
    }
    .kb-hdr-wrap {
        background: linear-gradient(-50deg, #040d1a, #0a1628, #193860, #1d4675, #112244, #040d1a);
        background-size: 350% 350%;
        animation: hdrGradient 10s ease infinite;
        padding: 22px 36px;
        border-radius: 16px;
        margin-bottom: 18px;
        border-bottom: 3px solid #FFD700;
        box-shadow: 0 8px 36px rgba(6,16,34,0.38);
        display: flex;
        align-items: center;
        justify-content: space-between;
        position: relative;
        overflow: hidden;
    }
    .kb-hdr-beam {
        position: absolute;
        top: 0; left: -55%;
        width: 40%; height: 100%;
        background: linear-gradient(90deg, transparent, rgba(255,215,0,0.06), transparent);
        animation: hdrBeam 7s ease-in-out infinite;
        pointer-events: none;
    }
    .kb-hdr-eyebrow {
        font-size: 10px; color: #FFD700; font-weight: 800;
        letter-spacing: 2.8px; text-transform: uppercase;
        margin-bottom: 5px; opacity: 0.92;
    }
    .kb-hdr-title {
        font-size: 27px; font-weight: 900; color: white;
        line-height: 1.1; letter-spacing: -0.6px;
    }
    .kb-hdr-sub {
        font-size: 13px; color: rgba(255,255,255,0.55); margin-top: 4px;
    }
    .kb-live-badge {
        display: flex; align-items: center; gap: 8px;
        background: rgba(255,215,0,0.12);
        border: 1px solid rgba(255,215,0,0.35);
        border-radius: 10px; padding: 7px 16px;
        font-size: 12px; color: #FFD700; font-weight: 700; letter-spacing: 1px;
    }
    .kb-live-dot {
        width: 8px; height: 8px; border-radius: 50%;
        background: #4ade80;
        animation: livePulse 2s ease-in-out infinite;
    }
    </style>
    <div class="kb-hdr-wrap">
        <div class="kb-hdr-beam"></div>
        <div>
            <div class="kb-hdr-eyebrow">Hertz &nbsp;·&nbsp; Powered by Callinsite</div>
            <div class="kb-hdr-title">📚 RTA Knowledge Base</div>
            <div class="kb-hdr-sub">Browse approved processes, reports, and tool guides</div>
        </div>
        <div class="kb-live-badge">
            <div class="kb-live-dot"></div>
            LIVE
        </div>
    </div>
    """, unsafe_allow_html=True)

    categories = get_categories()
    if not categories:
        st.info("No content available yet.")
        return

    search = st.text_input("🔍 Search", placeholder="Search by title...")
    st.markdown("<br>", unsafe_allow_html=True)

    for cat in categories:
        docs = get_approved_docs(
            category_id=cat["id"],
            search=search if search else None
        )
        with st.expander(f"**{cat['name']}**  —  _{cat['description']}_", expanded=True):
            if not docs:
                st.caption("No documents in this category yet.")
                continue
            for doc in docs:
                with st.container(border=True):
                    col1, col2 = st.columns([5, 1])
                    with col1:
                        st.markdown(
                            f"<h4 style='margin:0 0 4px 0;'>{doc['title']}</h4>",
                            unsafe_allow_html=True
                        )
                        submitter = doc.get("kb_users") or {}
                        submitter_name = submitter.get("name", "Unknown")
                        reviewed = (doc.get("reviewed_at") or "")[:10] or "—"
                        st.caption(
                            f"Version {doc['version']}  ·  Last updated: {reviewed}"
                            f"  ·  Submitted by: {submitter_name}"
                        )
                    with col2:
                        if doc.get("file_url"):
                            st.link_button("📄 Open File", doc["file_url"],
                                           use_container_width=True)
                    if doc.get("content"):
                        st.markdown(doc["content"])


def page_submit_document(user):
    st.markdown("""
    <div class="kb-hdr-wrap">
        <div class="kb-hdr-beam"></div>
        <div>
            <div class="kb-hdr-eyebrow">Hertz &nbsp;·&nbsp; Powered by Callinsite</div>
            <div class="kb-hdr-title">📤 Submit Document</div>
            <div class="kb-hdr-sub">Your submission will be reviewed before being published</div>
        </div>
    </div>
    """, unsafe_allow_html=True)

    categories = get_categories()
    cat_map    = {cat["name"]: cat["id"] for cat in categories}

    with st.form("submit_form", clear_on_submit=True):
        title    = st.text_input("Document Title *",
                                  placeholder="e.g. How to Process IGT Allocation")
        category = st.selectbox("Category *", options=list(cat_map.keys()))
        content  = st.text_area("Process Steps / Content", height=250,
                                 placeholder="Write the steps here...")
        file     = st.file_uploader("Upload File (PDF or Word .docx)",
                                     type=["pdf", "docx"])
        notes    = st.text_area("Notes for Reviewer", height=100,
                                 placeholder="Any context the reviewer should know...")
        submit   = st.form_submit_button("📤 Submit for Review",
                                          use_container_width=True)

        if submit:
            if not title:
                st.error("Document title is required.")
                return
            if not content and not file:
                st.error("Please add content or upload a file.")
                return
            file_url, file_name = None, None
            if file:
                with st.spinner("Uploading file..."):
                    file_url, file_name = upload_file(file)
            supabase.table("kb_documents").insert({
                "title":       title,
                "category_id": cat_map[category],
                "content":     content,
                "file_url":    file_url,
                "file_name":   file_name,
                "status":      "pending",
                "submitted_by": user["id"],
                "notes":       notes,
                "version":     1
            }).execute()
            st.success("✅ Submitted! An admin will review your document.")


def page_review_queue(user):
    st.markdown("""
    <div class="kb-hdr-wrap">
        <div class="kb-hdr-beam"></div>
        <div>
            <div class="kb-hdr-eyebrow">Hertz &nbsp;·&nbsp; Powered by Callinsite</div>
            <div class="kb-hdr-title">📋 Review Queue</div>
        </div>
    </div>
    """, unsafe_allow_html=True)

    tab_pending, tab_approved, tab_rejected = st.tabs([
        "⏳ Pending Review", "✅ Approved", "❌ Rejected"
    ])

    with tab_pending:
        docs = get_pending_docs()
        if not docs:
            st.success("All clear — no pending submissions.")
        for doc in docs:
            submitter_name = (doc.get("kb_users") or {}).get("name", "Unknown")
            cat_name       = (doc.get("kb_categories") or {}).get("name", "—")
            with st.container(border=True):
                st.markdown(f"#### {doc['title']}")
                st.caption(f"Category: {cat_name}  ·  Submitted by: {submitter_name}  ·  {doc['submitted_at'][:10]}")
                if doc.get("notes"):
                    st.info(f"📝 {doc['notes']}")
                if doc.get("content"):
                    with st.expander("View content"):
                        st.markdown(doc["content"])
                if doc.get("file_url"):
                    st.link_button("📄 View File", doc["file_url"])
                col1, col2, _ = st.columns([1, 1, 5])
                with col1:
                    if st.button("✅ Approve", key=f"app_{doc['id']}", type="primary"):
                        approve_doc(doc["id"], user["id"])
                        st.toast("Approved and published!", icon="✅")
                        st.rerun()
                with col2:
                    if st.button("❌ Reject", key=f"rej_{doc['id']}"):
                        reject_doc(doc["id"], user["id"])
                        st.toast("Rejected.", icon="❌")
                        st.rerun()

    with tab_approved:
        docs = get_all_docs_by_status("approved")
        if not docs:
            st.info("No approved documents yet.")
        for doc in docs:
            cat_name = (doc.get("kb_categories") or {}).get("name", "—")
            with st.container(border=True):
                col1, col2 = st.columns([4, 1])
                with col1:
                    st.markdown(f"**{doc['title']}**")
                    st.caption(f"Category: {cat_name}  ·  v{doc['version']}  ·  Approved: {(doc.get('reviewed_at') or '')[:10]}")
                with col2:
                    if st.button("🗑️ Unpublish", key=f"unpub_{doc['id']}"):
                        reject_doc(doc["id"], user["id"])
                        st.rerun()

    with tab_rejected:
        docs = get_all_docs_by_status("rejected")
        if not docs:
            st.info("No rejected documents.")
        for doc in docs:
            cat_name = (doc.get("kb_categories") or {}).get("name", "—")
            with st.container(border=True):
                col1, col2 = st.columns([4, 1])
                with col1:
                    st.markdown(f"**{doc['title']}**")
                    st.caption(f"Category: {cat_name}  ·  Rejected: {(doc.get('reviewed_at') or '')[:10]}")
                with col2:
                    if st.button("↩️ Re-approve", key=f"reapp_{doc['id']}"):
                        approve_doc(doc["id"], user["id"])
                        st.rerun()


def page_user_management(user):
    if user["role"] != "super_admin":
        st.error("⛔ Access restricted to Super Admin only.")
        return

    st.markdown("""
    <div class="kb-hdr-wrap">
        <div class="kb-hdr-beam"></div>
        <div>
            <div class="kb-hdr-eyebrow">Hertz &nbsp;·&nbsp; Powered by Callinsite</div>
            <div class="kb-hdr-title">👥 User Management</div>
        </div>
    </div>
    """, unsafe_allow_html=True)

    with st.expander("➕ Add New User", expanded=False):
        with st.form("add_user_form", clear_on_submit=True):
            col1, col2 = st.columns(2)
            with col1:
                name     = st.text_input("Full Name *")
                email    = st.text_input("Email *")
            with col2:
                role     = st.selectbox("Role", ["rta", "admin", "super_admin"])
                password = st.text_input("Initial Password *", type="password")
            if st.form_submit_button("Add User", use_container_width=True):
                if not name or not email or not password:
                    st.error("All fields are required.")
                else:
                    try:
                        supabase.table("kb_users").insert({
                            "name":      name,
                            "email":     email.lower().strip(),
                            "password":  hash_password(password),
                            "role":      role,
                            "is_active": True
                        }).execute()
                        st.success(f"✅ **{name}** added successfully!")
                    except Exception as e:
                        st.error(f"Error: {e}")

    st.markdown("---")
    st.subheader("Current Users")

    all_users = supabase.table("kb_users").select("*").order("name").execute().data
    for u in all_users:
        with st.container(border=True):
            col1, col2, col3, col4 = st.columns([3, 3, 2, 2])
            with col1:
                st.markdown(f"**{u['name']}**")
            with col2:
                st.caption(u["email"])
            with col3:
                role_colors = {
                    "rta":         "🟦 RTA",
                    "admin":       "🟧 Admin",
                    "super_admin": "🟥 Super Admin"
                }
                st.write(role_colors.get(u["role"], u["role"]))
            with col4:
                if u["id"] != user["id"]:
                    label = "Deactivate" if u["is_active"] else "Activate"
                    if st.button(label, key=f"toggle_{u['id']}"):
                        supabase.table("kb_users").update(
                            {"is_active": not u["is_active"]}
                        ).eq("id", u["id"]).execute()
                        st.rerun()
                else:
                    st.write("🟢 You")


# ─────────────────────────────────────────
# MAIN APP
# ─────────────────────────────────────────
def main():
    st.set_page_config(
        page_title="RTA Knowledge Base",
        page_icon="📚",
        layout="wide"
    )
    inject_css()

    if "user" not in st.session_state:
        st.session_state.user = None

    if not st.session_state.user:
        page_login()
        return

    user = st.session_state.user
    role = user["role"]

    with st.sidebar:
        # Hertz logo — matches app.py exactly
        st.markdown("""
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
          <div style='display:inline-block;
                      background:linear-gradient(135deg,#FFD700 0%,#f5c400 60%,#e8b000 100%);
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
        """, unsafe_allow_html=True)

        st.markdown("---")
        st.markdown("### 🗂️ Knowledge Base")

        nav_options = ["📖 Knowledge Base"]
        if role in ["admin", "super_admin"]:
            nav_options += ["📋 Review Queue", "👥 User Management"]
        else:
            nav_options.append("📤 Submit Document")

        page = st.radio("nav", nav_options, label_visibility="collapsed")

        st.markdown("---")

        # User info
        st.markdown(f"""
        <div style="padding:4px 0 8px 0;">
            <div style="color:#c0d4ee; font-size:0.85rem;">
                👤 <b>{user['name']}</b>
            </div>
            <div style="color:rgba(255,215,0,0.6); font-size:0.72rem;
                        margin-top:2px; letter-spacing:1px; text-transform:uppercase;">
                {role.replace('_', ' ')}
            </div>
        </div>
        """, unsafe_allow_html=True)

        # Pending badge for admins
        if role in ["admin", "super_admin"]:
            pending_count = len(get_pending_docs())
            if pending_count > 0:
                st.warning(f"⏳ {pending_count} pending review")

        st.markdown("<br>", unsafe_allow_html=True)
        if st.button("🚪 Logout", use_container_width=True):
            st.session_state.user = None
            st.rerun()

    if page == "📖 Knowledge Base":
        page_knowledge_base()
    elif page == "📤 Submit Document":
        page_submit_document(user)
    elif page == "📋 Review Queue":
        page_review_queue(user)
    elif page == "👥 User Management":
        page_user_management(user)


if __name__ == "__main__":
    main()
