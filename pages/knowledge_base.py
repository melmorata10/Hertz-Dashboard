import streamlit as st
from supabase import create_client, Client
import hashlib
import datetime
from io import BytesIO

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
# DOCX → PDF CONVERSION
# ─────────────────────────────────────────
def convert_docx_to_pdf(docx_bytes: bytes) -> bytes:
    """Convert a Word document to PDF using python-docx + reportlab."""
    try:
        from docx import Document
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.lib.units import cm
        from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, HRFlowable
        from reportlab.lib import colors

        doc      = Document(BytesIO(docx_bytes))
        pdf_buf  = BytesIO()
        pdf_doc  = SimpleDocTemplate(
            pdf_buf, pagesize=A4,
            leftMargin=2*cm, rightMargin=2*cm,
            topMargin=2*cm,  bottomMargin=2*cm
        )
        styles   = getSampleStyleSheet()

        h1 = ParagraphStyle("h1", parent=styles["Heading1"],
                             fontSize=16, spaceAfter=10, textColor=colors.HexColor("#0a1628"))
        h2 = ParagraphStyle("h2", parent=styles["Heading2"],
                             fontSize=13, spaceAfter=8,  textColor=colors.HexColor("#1a3a5c"))
        h3 = ParagraphStyle("h3", parent=styles["Heading3"],
                             fontSize=11, spaceAfter=6,  textColor=colors.HexColor("#1a3a5c"))
        body = ParagraphStyle("body", parent=styles["Normal"],
                              fontSize=10, spaceAfter=5, leading=14)

        story = []
        for para in doc.paragraphs:
            text = para.text.strip()
            if not text:
                story.append(Spacer(1, 6))
                continue
            # Escape XML special chars for reportlab
            text = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            style_name = para.style.name if para.style else ""
            if "Heading 1" in style_name:
                story.append(Paragraph(text, h1))
            elif "Heading 2" in style_name:
                story.append(Paragraph(text, h2))
            elif "Heading 3" in style_name:
                story.append(Paragraph(text, h3))
            elif "List" in style_name:
                story.append(Paragraph(f"• {text}", body))
            else:
                story.append(Paragraph(text, body))

        if story:
            pdf_doc.build(story)
            pdf_buf.seek(0)
            return pdf_buf.read()
        return None
    except Exception as e:
        st.warning(f"Could not convert to PDF: {e}. Uploading original Word file.")
        return None

# ─────────────────────────────────────────
# THEME — mirrors app.py exactly
# ─────────────────────────────────────────
def inject_css():
    st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800;900&display=swap');

@keyframes sidebarFlow {
    0%   { background-position: 0% 0%; }
    100% { background-position: 0% 100%; }
}
@keyframes navEntrance {
    from { opacity: 0; transform: translateX(-12px); }
    to   { opacity: 1; transform: translateX(0); }
}
@keyframes logoPulse {
    0%,100% { box-shadow: 0 4px 18px rgba(255,215,0,0.45); }
    50%      { box-shadow: 0 6px 26px rgba(255,215,0,0.65); }
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
@keyframes livePulse {
    0%,100% { box-shadow: 0 0 0 0 rgba(74,222,128,0.55); }
    50%      { box-shadow: 0 0 0 5px rgba(74,222,128,0); }
}
@keyframes particleDrift {
    0%   { background-position: 0 0; }
    100% { background-position: 48px 48px; }
}

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

/* ── Sidebar ─────────────────────────────────────────────────────────── */
section[data-testid="stSidebar"] {
    background: linear-gradient(180deg,
        #040c18 0%, #07111f 15%, #0a1628 35%,
        #112244 60%, #0f2d4a 80%, #07111f 100%) !important;
    background-size: 100% 300% !important;
    animation: sidebarFlow 14s ease-in-out infinite alternate !important;
    border-right: 2px solid rgba(255,215,0,0.45) !important;
    box-shadow: 4px 0 36px rgba(0,0,0,0.5) !important;
}
[data-testid="stSidebarNav"] { padding: 2px 10px 14px !important; }
[data-testid="stSidebarNav"]::before {
    content: "NAVIGATION";
    display: block;
    font-size: 9.5px; font-weight: 800; letter-spacing: 2.5px;
    color: rgba(255,215,0,0.55);
    padding: 10px 6px 8px;
    font-family: 'Inter', sans-serif; text-transform: uppercase;
}
[data-testid="stSidebarNav"] a {
    display: flex !important; align-items: center !important;
    margin: 4px 0 !important; padding: 12px 14px 12px 18px !important;
    border-radius: 10px !important;
    border: 1px solid rgba(255,215,0,0.1) !important;
    background: rgba(255,255,255,0.04) !important;
    text-decoration: none !important;
    transition: all 0.22s ease !important;
    animation: navEntrance 0.4s ease both !important;
    position: relative !important; overflow: hidden !important;
}
[data-testid="stSidebarNav"] a::before {
    content: ''; position: absolute; left: 0; top: 15%; bottom: 15%;
    width: 3px; border-radius: 0 3px 3px 0;
    background: rgba(255,215,0,0.25); transition: all 0.22s ease;
}
[data-testid="stSidebarNav"] a:hover {
    background: rgba(255,215,0,0.09) !important;
    border-color: rgba(255,215,0,0.32) !important;
    transform: translateX(5px) !important;
}
[data-testid="stSidebarNav"] a:hover::before { background: #FFD700; }
[data-testid="stSidebarNav"] a[aria-current="page"] {
    background: linear-gradient(90deg, rgba(255,215,0,0.13), rgba(255,215,0,0.06)) !important;
    border-color: rgba(255,215,0,0.42) !important;
}
[data-testid="stSidebarNav"] a[aria-current="page"]::before {
    background: #FFD700; box-shadow: 0 0 12px rgba(255,215,0,0.8);
}
[data-testid="stSidebarNav"] a li,
[data-testid="stSidebarNav"] a span,
[data-testid="stSidebarNav"] ul li span {
    color: #ccddf8 !important; font-weight: 600 !important;
    font-size: 13.5px !important;
}
[data-testid="stSidebarNav"] a[aria-current="page"] span {
    color: #FFD700 !important;
    text-shadow: 0 0 14px rgba(255,215,0,0.45) !important;
}
/* Hide Verint */
[data-testid="stSidebarNav"] a[href*="Verint"],
[data-testid="stSidebarNav"] a[href*="verint"],
[data-testid="stSidebarNav"] a[href*="2_Verint"],
[data-testid="stSidebarNav"] a[href*="_2_Verint"] { display: none !important; }

section[data-testid="stSidebar"] label,
section[data-testid="stSidebar"] p,
section[data-testid="stSidebar"] span,
section[data-testid="stSidebar"] div,
section[data-testid="stSidebar"] small { color: #c0d4ee !important; }
section[data-testid="stSidebar"] hr { border-color: rgba(255,255,255,0.06) !important; }
section[data-testid="stSidebar"] .stMarkdown h3 {
    color: #FFD700 !important; font-size: 10px !important; font-weight: 800 !important;
    letter-spacing: 2.2px !important; text-transform: uppercase !important;
    border-bottom: 1px solid rgba(255,215,0,0.18); padding-bottom: 6px; margin-bottom: 10px;
}
section[data-testid="stSidebar"] .stRadio label {
    display: flex !important; align-items: center !important;
    padding: 10px 14px 10px 18px !important;
    border-radius: 10px !important;
    border: 1px solid rgba(255,215,0,0.1) !important;
    background: rgba(255,255,255,0.04) !important;
    color: #ccddf8 !important; font-weight: 600 !important;
    font-size: 13.5px !important; cursor: pointer !important;
    transition: all 0.22s ease !important;
}
section[data-testid="stSidebar"] .stRadio label:hover {
    background: rgba(255,215,0,0.09) !important;
    border-color: rgba(255,215,0,0.32) !important;
    transform: translateX(5px) !important;
}
section[data-testid="stSidebar"] .stButton button {
    background: linear-gradient(135deg, #FFD700 0%, #f5c400 55%, #e8b000 100%) !important;
    color: #0a1628 !important; font-weight: 800 !important;
    border: none !important; border-radius: 10px !important;
    width: 100% !important; transition: all 0.25s ease !important;
    box-shadow: 0 3px 14px rgba(255,215,0,0.38) !important;
}
section[data-testid="stSidebar"] .stButton button:hover {
    transform: translateY(-2px) !important;
    box-shadow: 0 7px 22px rgba(255,215,0,0.52) !important;
}

/* ── Main content ─────────────────────────────────────────────────── */
[data-testid="stMainBlockContainer"] { animation: fadeSlideIn 0.4s ease both; }
[data-testid="stVerticalBlockBorderWrapper"] {
    background: white !important;
    border: 1px solid rgba(200,215,235,0.8) !important;
    border-radius: 12px !important;
    box-shadow: 0 2px 12px rgba(0,0,0,0.05) !important;
}
details {
    border: 1px solid rgba(200,215,235,0.8) !important;
    border-radius: 12px !important; overflow: hidden; background: white !important;
}
details[open] summary { border-bottom: 1px solid rgba(200,215,235,0.7); }
summary {
    background: linear-gradient(90deg, #edf3fb 0%, #f5f9fd 100%) !important;
    font-weight: 700 !important; color: #1a3a5c !important;
    padding: 14px 18px !important; border-radius: 12px !important;
}
summary:hover { background: linear-gradient(90deg, #e1edf8 0%, #eaf3fc 100%) !important; }
[data-testid="stTextInput"] input,
[data-testid="stTextArea"] textarea {
    background: white !important;
    border: 1px solid rgba(200,215,235,0.9) !important;
    border-radius: 8px !important; color: #0a1628 !important;
}
[data-testid="stTextInput"] input:focus,
[data-testid="stTextArea"] textarea:focus {
    border-color: #FFD700 !important;
    box-shadow: 0 0 0 2px rgba(255,215,0,0.15) !important;
}
[data-testid="stFormSubmitButton"] button,
button[kind="primary"] {
    background: linear-gradient(135deg, #FFD700 0%, #f5c400 55%, #e8b000 100%) !important;
    color: #0a1628 !important; font-weight: 800 !important;
    border: none !important; border-radius: 10px !important;
    box-shadow: 0 3px 14px rgba(255,215,0,0.38) !important;
    transition: all 0.25s ease !important;
}
[data-testid="stFormSubmitButton"] button:hover,
button[kind="primary"]:hover {
    transform: translateY(-2px) !important;
    box-shadow: 0 7px 22px rgba(255,215,0,0.52) !important;
}
.stTabs [data-baseweb="tab-list"] {
    background: transparent;
    border-bottom: 2px solid rgba(200,215,235,0.85);
    gap: 4px; padding: 0;
}
.stTabs [data-baseweb="tab"] {
    color: #7a90aa !important; font-weight: 600 !important; font-size: 14px !important;
    padding: 11px 26px !important; border-radius: 10px 10px 0 0 !important;
    background: transparent !important; transition: all 0.2s ease !important;
}
.stTabs [aria-selected="true"] {
    background: white !important; color: #0a1628 !important; font-weight: 700 !important;
    border-bottom-color: white !important; margin-bottom: -2px !important;
    box-shadow: inset 0 -3px 0 #FFD700 !important;
}
.stTabs [data-baseweb="tab-panel"] {
    background: white; border: 1px solid rgba(200,215,235,0.8);
    border-top: none; border-radius: 0 10px 10px 10px;
    padding: 28px; box-shadow: 0 8px 36px rgba(0,0,0,0.07);
}
.stAlert { border-radius: 10px !important; }
hr {
    border: none !important; height: 1px !important;
    background: linear-gradient(90deg, transparent, #bfcfe4, transparent) !important;
    margin: 22px 0 !important;
}
h3 { color: #0a1628 !important; font-weight: 800 !important; }
h4 { color: #1a3a5c !important; font-weight: 700 !important;
     border-left: 3px solid #FFD700; padding-left: 12px; }
.stCaption { color: #8099b8 !important; font-size: 12px !important; }

/* ── Hide radio label in sidebar ─────────────────────────────────── */
section[data-testid='stSidebar'] .stRadio > label,
section[data-testid='stSidebar'] [data-testid='stWidgetLabel'] {
    display: none !important;
    height: 0 !important;
    margin: 0 !important;
    padding: 0 !important;
}

/* ── Search result cards ──────────────────────────────────────────── */
.search-result-card {
    background: white;
    border: 1px solid rgba(200,215,235,0.8);
    border-left: 4px solid #FFD700;
    border-radius: 10px;
    padding: 14px 18px;
    margin-bottom: 10px;
    cursor: pointer;
    transition: all 0.2s ease;
    box-shadow: 0 2px 8px rgba(0,0,0,0.04);
}
.search-result-card:hover {
    border-left-color: #e8b000;
    box-shadow: 0 4px 18px rgba(0,0,0,0.1);
    transform: translateX(4px);
}
.search-result-title {
    font-size: 15px; font-weight: 700; color: #0a1628; margin-bottom: 4px;
}
.search-result-meta {
    font-size: 12px; color: #8099b8;
}
.category-chip {
    display: inline-block;
    background: rgba(255,215,0,0.12);
    border: 1px solid rgba(255,215,0,0.3);
    border-radius: 20px;
    padding: 3px 12px;
    font-size: 11px; font-weight: 700;
    color: #7a5c00;
    margin-right: 6px;
}
.faq-card {
    background: white;
    border: 1px solid rgba(200,215,235,0.8);
    border-radius: 12px;
    padding: 16px 20px;
    cursor: pointer;
    transition: all 0.2s ease;
    box-shadow: 0 2px 8px rgba(0,0,0,0.04);
    height: 100%;
}
.faq-card:hover {
    border-color: #FFD700;
    box-shadow: 0 4px 18px rgba(255,215,0,0.15);
    transform: translateY(-2px);
}
.faq-icon { font-size: 24px; margin-bottom: 8px; }
.faq-title { font-size: 13px; font-weight: 700; color: #0a1628; margin-bottom: 4px; }
.faq-cat { font-size: 11px; color: #8099b8; }
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

def search_docs(query: str):
    """Search docs by title or content."""
    results = (
        supabase.table("kb_documents")
        .select("*, kb_categories(name), kb_users!kb_documents_submitted_by_fkey(name)")
        .eq("status", "approved")
        .ilike("title", f"%{query}%")
        .order("updated_at", desc=True)
        .execute()
        .data
    )
    # Also search content
    content_results = (
        supabase.table("kb_documents")
        .select("*, kb_categories(name), kb_users!kb_documents_submitted_by_fkey(name)")
        .eq("status", "approved")
        .ilike("content", f"%{query}%")
        .order("updated_at", desc=True)
        .execute()
        .data
    )
    # Merge and deduplicate by id
    seen = set()
    merged = []
    for doc in results + content_results:
        if doc["id"] not in seen:
            seen.add(doc["id"])
            merged.append(doc)
    return merged

def get_recent_docs(limit=6):
    """Get most recently approved docs for FAQ section."""
    return (
        supabase.table("kb_documents")
        .select("*, kb_categories(name)")
        .eq("status", "approved")
        .order("reviewed_at", desc=True)
        .limit(limit)
        .execute()
        .data
    )

def get_doc_by_id(doc_id: str):
    result = (
        supabase.table("kb_documents")
        .select("*, kb_categories(name), kb_users!kb_documents_submitted_by_fkey(name)")
        .eq("id", doc_id)
        .execute()
    )
    return result.data[0] if result.data else None

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

def extract_text_from_file(file) -> str:
    """Extract text content from PDF or DOCX and return as markdown string."""
    file_bytes = file.read()
    name = file.name.lower()
    text_lines = []

    if name.endswith(".docx"):
        try:
            from docx import Document as DocxDocument
            doc = DocxDocument(BytesIO(file_bytes))
            for para in doc.paragraphs:
                t = para.text.strip()
                if not t:
                    text_lines.append("")
                    continue
                style = para.style.name if para.style else ""
                if "Heading 1" in style:
                    text_lines.append(f"## {t}")
                elif "Heading 2" in style:
                    text_lines.append(f"### {t}")
                elif "Heading 3" in style:
                    text_lines.append(f"#### {t}")
                elif "List" in style:
                    text_lines.append(f"- {t}")
                else:
                    text_lines.append(t)
            # Also extract tables
            for table in doc.tables:
                rows = []
                for i, row in enumerate(table.rows):
                    cells = [c.text.strip() for c in row.cells]
                    rows.append("| " + " | ".join(cells) + " |")
                    if i == 0:
                        rows.append("|" + "|".join(["---"] * len(cells)) + "|")
                text_lines.extend(rows)
                text_lines.append("")
        except Exception as e:
            return f"⚠️ Could not extract text from Word file: {e}"

    elif name.endswith(".pdf"):
        try:
            import pdfplumber
            with pdfplumber.open(BytesIO(file_bytes)) as pdf:
                for page in pdf.pages:
                    page_text = page.extract_text()
                    if page_text:
                        text_lines.extend(page_text.split("\n"))
                    text_lines.append("")
        except Exception:
            try:
                # fallback: PyPDF2
                import PyPDF2
                reader = PyPDF2.PdfReader(BytesIO(file_bytes))
                for page in reader.pages:
                    t = page.extract_text()
                    if t:
                        text_lines.extend(t.split("\n"))
                    text_lines.append("")
            except Exception as e:
                return f"⚠️ Could not extract text from PDF: {e}"

    return "\n".join(text_lines).strip()

def approve_doc(doc_id, reviewer_id):
    supabase.table("kb_documents").update({
        "status":      "approved",
        "reviewed_by": reviewer_id,
        "reviewed_at": datetime.datetime.now().isoformat(),
        "updated_at":  datetime.datetime.now().isoformat()
    }).eq("id", doc_id).execute()

def reject_doc(doc_id, reviewer_id):
    supabase.table("kb_documents").update({
        "status":      "rejected",
        "reviewed_by": reviewer_id,
        "reviewed_at": datetime.datetime.now().isoformat(),
        "updated_at":  datetime.datetime.now().isoformat()
    }).eq("id", doc_id).execute()

def delete_doc(doc_id):
    supabase.table("kb_documents").delete().eq("id", doc_id).execute()

# ─────────────────────────────────────────
# CATEGORY ICONS
# ─────────────────────────────────────────
CAT_ICONS = {
    "HOOP List":  "📋",
    "Reports":    "📊",
    "Tools":      "🔧",
    "Escalation": "🚨",
}

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


def render_header(title: str, subtitle: str = ""):
    sub = f"<p style='font-size:13px;color:rgba(255,255,255,0.55);margin:4px 0 0 0;'>{subtitle}</p>" if subtitle else ""
    html = (
        "<div style='background:#0a1628;padding:22px 36px;border-radius:16px;"
        "margin-bottom:24px;border-bottom:3px solid #FFD700;"
        "box-shadow:0 8px 36px rgba(6,16,34,0.38);'>"
        "<p style='font-size:10px;color:#FFD700;font-weight:800;"
        "letter-spacing:2.8px;text-transform:uppercase;margin:0 0 6px 0;'>"
        "HERTZ &middot; POWERED BY CALLINSITE</p>"
        f"<p style='font-size:26px;font-weight:900;color:white;margin:0;line-height:1.2;'>{title}</p>"
        f"{sub}"
        "</div>"
    )
    st.markdown(html, unsafe_allow_html=True)


def render_doc_detail(doc: dict):
    """Render a single document in full."""
    cat_name = (doc.get("kb_categories") or {}).get("name", "—")
    icon     = CAT_ICONS.get(cat_name, "📄")
    submitter = (doc.get("kb_users") or {}).get("name", "Unknown")
    reviewed  = (doc.get("reviewed_at") or "")[:10] or "—"

    # Back button
    if st.button("← Back to results", key="back_btn"):
        st.session_state.kb_selected_doc = None
        st.rerun()

    st.markdown("<br>", unsafe_allow_html=True)

    # Doc header
    st.markdown(f"""
    <div style="background:white; border:1px solid rgba(200,215,235,0.8);
                border-left:5px solid #FFD700; border-radius:12px;
                padding:20px 24px; margin-bottom:20px;
                box-shadow:0 2px 12px rgba(0,0,0,0.05);">
        <div style="font-size:11px;color:#8099b8;margin-bottom:6px;">
            <span class="category-chip">{icon} {cat_name}</span>
            Version {doc.get('version', 1)}  ·  Last updated: {reviewed}  ·  By: {submitter}
        </div>
        <h2 style="color:#0a1628;margin:0;font-size:1.4rem;font-weight:800;">
            {doc['title']}
        </h2>
    </div>
    """, unsafe_allow_html=True)

    # File download button
    if doc.get("file_url"):
        st.link_button("📄 Open / Download File", doc["file_url"],
                       use_container_width=False)
        st.markdown("<br>", unsafe_allow_html=True)

    # Content
    if doc.get("content"):
        with st.container(border=True):
            st.markdown(doc["content"])
    elif not doc.get("file_url"):
        st.info("No content available for this document.")


def page_knowledge_base():
    render_header("📚 RTA Knowledge Base",
                  "Search for processes, reports, and tool guides")

    # ── Session state init ────────────────────────────────────────────────
    if "kb_search_query" not in st.session_state:
        st.session_state.kb_search_query  = ""
    if "kb_selected_doc" not in st.session_state:
        st.session_state.kb_selected_doc  = None

    # ── If a doc is selected, show full detail view ───────────────────────
    if st.session_state.kb_selected_doc:
        doc = get_doc_by_id(st.session_state.kb_selected_doc)
        if doc:
            render_doc_detail(doc)
        else:
            st.session_state.kb_selected_doc = None
            st.rerun()
        return

    # ── Search bar ────────────────────────────────────────────────────────
    search = st.text_input(
        "🔍 Search",
        value=st.session_state.kb_search_query,
        placeholder="Type to search... e.g. Chat, Allocation, ServiceNow, EOD",
        key="kb_search_input"
    )

    # Update search state
    if search != st.session_state.kb_search_query:
        st.session_state.kb_search_query = search
        st.rerun()

    # ── SEARCH RESULTS VIEW ───────────────────────────────────────────────
    if search.strip():
        results = search_docs(search.strip())
        st.markdown("<br>", unsafe_allow_html=True)

        if not results:
            st.markdown(f"""
            <div style="text-align:center; padding:40px; color:#8099b8;">
                <div style="font-size:32px; margin-bottom:10px;">🔍</div>
                <div style="font-size:16px; font-weight:600; color:#1a3a5c;">
                    No results found for "<b>{search}</b>"
                </div>
                <div style="font-size:13px; margin-top:6px;">
                    Try a different keyword or browse categories below
                </div>
            </div>
            """, unsafe_allow_html=True)
        else:
            st.markdown(
                f"<div style='font-size:13px;color:#7a90aa;margin-bottom:12px;'>"
                f"🔍 <b>{len(results)}</b> result{'s' if len(results) != 1 else ''} "
                f"for <b>\"{search}\"</b> — click to read</div>",
                unsafe_allow_html=True
            )

            for doc in results:
                cat_name = (doc.get("kb_categories") or {}).get("name", "—")
                icon     = CAT_ICONS.get(cat_name, "📄")
                reviewed = (doc.get("reviewed_at") or "")[:10] or "—"

                # Excerpt from content
                content  = doc.get("content") or ""
                excerpt  = ""
                if content:
                    # Find the search term in content and show surrounding text
                    idx = content.lower().find(search.lower())
                    if idx >= 0:
                        start   = max(0, idx - 60)
                        end     = min(len(content), idx + 100)
                        excerpt = "..." + content[start:end].replace("\n", " ") + "..."

                col1, col2 = st.columns([10, 1])
                with col1:
                    st.markdown(f"""
                    <div class="search-result-card">
                        <div class="search-result-title">{doc['title']}</div>
                        <div class="search-result-meta">
                            <span class="category-chip">{icon} {cat_name}</span>
                            Last updated: {reviewed}
                            {"<br><span style='color:#a0aec0;font-style:italic;font-size:11px;margin-top:4px;display:block;'>" + excerpt + "</span>" if excerpt else ""}
                        </div>
                    </div>
                    """, unsafe_allow_html=True)
                with col2:
                    st.markdown("<div style='padding-top:8px'></div>",
                                unsafe_allow_html=True)
                    if st.button("Read →", key=f"read_{doc['id']}",
                                  use_container_width=True):
                        st.session_state.kb_selected_doc = doc["id"]
                        st.rerun()

        st.markdown("---")

    # ── DEFAULT VIEW — all docs sorted latest first ───────────────────────
    if not search.strip():
        # Browse by category chips
        categories = get_categories()
        if categories:
            st.markdown(
                "<p style='font-size:10px;font-weight:800;letter-spacing:2px;"
                "color:#7a90aa;text-transform:uppercase;margin:8px 0 10px 0;'>"
                "🗂️ Browse by Category</p>",
                unsafe_allow_html=True
            )
            cat_cols = st.columns(len(categories))
            for i, cat in enumerate(categories):
                icon = CAT_ICONS.get(cat["name"], "📄")
                with cat_cols[i]:
                    if st.button(f"{icon} {cat['name']}",
                                  key=f"cat_browse_{cat['id']}",
                                  use_container_width=True):
                        st.session_state.kb_search_query = cat["name"]
                        st.rerun()

        st.markdown("<br>", unsafe_allow_html=True)

        # All approved docs, latest first
        all_docs = (
            supabase.table("kb_documents")
            .select("*, kb_categories(name), kb_users!kb_documents_submitted_by_fkey(name)")
            .eq("status", "approved")
            .order("reviewed_at", desc=True)
            .execute()
            .data
        )

        if not all_docs:
            st.info("No documents published yet.")
        else:
            st.markdown(
                f"<p style='font-size:13px;color:#7a90aa;margin-bottom:12px;'>"
                f"📋 <b>{len(all_docs)}</b> document{'s' if len(all_docs) != 1 else ''} "
                f"— sorted latest first — click to read</p>",
                unsafe_allow_html=True
            )
            for doc in all_docs:
                cat_name = (doc.get("kb_categories") or {}).get("name", "—")
                icon     = CAT_ICONS.get(cat_name, "📄")
                reviewed = (doc.get("reviewed_at") or "")[:10] or "—"
                content_preview = (doc.get("content") or "")[:120].replace("\n", " ")
                if content_preview:
                    content_preview = content_preview + "..."

                col1, col2 = st.columns([10, 1])
                with col1:
                    st.markdown(
                        f"<div class='search-result-card'>"
                        f"<div class='search-result-title'>{doc['title']}</div>"
                        f"<div class='search-result-meta'>"
                        f"<span class='category-chip'>{icon} {cat_name}</span>"
                        f"Last updated: {reviewed}"
                        f"{'<br><span style=\'color:#a0aec0;font-style:italic;font-size:11px;\'>'+content_preview+'</span>' if content_preview else ''}"
                        f"</div></div>",
                        unsafe_allow_html=True
                    )
                with col2:
                    st.markdown("<div style='padding-top:8px'></div>",
                                unsafe_allow_html=True)
                    if st.button("Read →", key=f"all_{doc['id']}",
                                  use_container_width=True):
                        st.session_state.kb_selected_doc = doc["id"]
                        st.rerun()


def page_submit_document(user):
    render_header("📤 Submit Document",
                  "Your submission will be reviewed before being published")

    categories = get_categories()
    cat_map    = {cat["name"]: cat["id"] for cat in categories}

    with st.form("submit_form", clear_on_submit=True):
        title    = st.text_input("Document Title *",
                                  placeholder="e.g. How to Process IGT Allocation")
        category = st.selectbox("Category *", options=list(cat_map.keys()))
        content  = st.text_area("Process Steps / Content", height=250,
                                 placeholder="Write the steps here (optional if uploading a file)...")
        file     = st.file_uploader(
            "Upload File — PDF or Word (.docx) · Word files are auto-converted to PDF",
            type=["pdf", "docx"]
        )
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
            final_content = content or ""
            if file:
                with st.spinner("Extracting content from file..."):
                    extracted = extract_text_from_file(file)
                if extracted:
                    final_content = (final_content + "\n\n" + extracted).strip()
                    st.success("✅ File content extracted and added to document!")
            supabase.table("kb_documents").insert({
                "title":        title,
                "category_id":  cat_map[category],
                "content":      final_content,
                "file_url":     None,
                "file_name":    None,
                "status":       "pending",
                "submitted_by": user["id"],
                "notes":        notes,
                "version":      1
            }).execute()
            st.success("✅ Submitted! An admin will review your document.")


def page_review_queue(user):
    render_header("📋 Review Queue")

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
                st.caption(
                    f"Category: {cat_name}  ·  Submitted by: {submitter_name}"
                    f"  ·  {doc['submitted_at'][:10]}"
                )
                if doc.get("notes"):
                    st.info(f"📝 {doc['notes']}")
                if doc.get("content"):
                    with st.expander("View content"):
                        st.markdown(doc["content"])
                if doc.get("file_url"):
                    st.link_button("📄 View File", doc["file_url"])
                col1, col2, _ = st.columns([1, 1, 5])
                with col1:
                    if st.button("✅ Approve", key=f"app_{doc['id']}",
                                  type="primary"):
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
                col1, col2, col3 = st.columns([5, 1, 1])
                with col1:
                    st.markdown(f"**{doc['title']}**")
                    st.caption(
                        f"Category: {cat_name}  ·  v{doc['version']}"
                        f"  ·  Approved: {(doc.get('reviewed_at') or '')[:10]}"
                    )
                with col2:
                    if st.button("🗑️ Unpublish", key=f"unpub_{doc['id']}"):
                        reject_doc(doc["id"], user["id"])
                        st.rerun()
                with col3:
                    if user["role"] == "super_admin":
                        if st.button("❌ Delete", key=f"del_app_{doc['id']}"):
                            delete_doc(doc["id"])
                            st.toast("Document permanently deleted.", icon="🗑️")
                            st.rerun()

    with tab_rejected:
        docs = get_all_docs_by_status("rejected")
        if not docs:
            st.info("No rejected documents.")
        for doc in docs:
            cat_name = (doc.get("kb_categories") or {}).get("name", "—")
            with st.container(border=True):
                col1, col2, col3 = st.columns([5, 1, 1])
                with col1:
                    st.markdown(f"**{doc['title']}**")
                    st.caption(
                        f"Category: {cat_name}"
                        f"  ·  Rejected: {(doc.get('reviewed_at') or '')[:10]}"
                    )
                with col2:
                    if st.button("↩️ Re-approve", key=f"reapp_{doc['id']}"):
                        approve_doc(doc["id"], user["id"])
                        st.rerun()
                with col3:
                    if user["role"] == "super_admin":
                        if st.button("❌ Delete", key=f"del_rej_{doc['id']}"):
                            delete_doc(doc["id"])
                            st.toast("Document permanently deleted.", icon="🗑️")
                            st.rerun()


def page_user_management(user):
    if user["role"] != "super_admin":
        st.error("⛔ Access restricted to Super Admin only.")
        return

    render_header("👥 User Management")

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
    role_options = ["rta", "admin", "super_admin"]

    for u in all_users:
        with st.container(border=True):
            col1, col2, col3, col4, col5 = st.columns([3, 3, 2, 2, 1])
            with col1:
                st.markdown(f"**{u['name']}**")
                st.caption(u["email"])
            with col2:
                if u["id"] != user["id"]:
                    new_role = st.selectbox(
                        "Role",
                        options=role_options,
                        index=role_options.index(u["role"]) if u["role"] in role_options else 0,
                        key=f"role_{u['id']}",
                        label_visibility="collapsed"
                    )
                    if new_role != u["role"]:
                        supabase.table("kb_users").update(
                            {"role": new_role}
                        ).eq("id", u["id"]).execute()
                        st.toast(f"Role updated to {new_role}!", icon="✅")
                        st.rerun()
                else:
                    st.caption("super_admin (you)")
            with col3:
                status = "🟢 Active" if u["is_active"] else "🔴 Inactive"
                st.write(status)
            with col4:
                if u["id"] != user["id"]:
                    label = "Deactivate" if u["is_active"] else "Activate"
                    if st.button(label, key=f"toggle_{u['id']}"):
                        supabase.table("kb_users").update(
                            {"is_active": not u["is_active"]}
                        ).eq("id", u["id"]).execute()
                        st.rerun()
            with col5:
                if u["id"] != user["id"]:
                    if st.button("🗑️", key=f"del_user_{u['id']}",
                                  help="Delete user permanently"):
                        supabase.table("kb_users").delete().eq("id", u["id"]).execute()
                        st.toast(f"User {u['name']} deleted.", icon="🗑️")
                        st.rerun()


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
        st.markdown("""
        <style>
        @keyframes logoPulse {
            0%,100% { box-shadow: 0 4px 18px rgba(255,215,0,0.45); }
            50%      { box-shadow: 0 6px 26px rgba(255,215,0,0.65); }
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

        nav_options = ["📖 Knowledge Base", "📤 Submit Document"]
        if role in ["admin", "super_admin"]:
            nav_options += ["📋 Review Queue", "👥 User Management"]

        st.markdown("""
        <style>
        section[data-testid="stSidebar"] .stRadio > label,
        section[data-testid="stSidebar"] .stRadio > div > label:first-child {
            display: none !important;
        }
        </style>
        """, unsafe_allow_html=True)
        page = st.radio("Navigation", nav_options, label_visibility="collapsed")

        st.markdown("---")

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

        if role in ["admin", "super_admin"]:
            pending_count = len(get_pending_docs())
            if pending_count > 0:
                st.warning(f"⏳ {pending_count} pending review")

        st.markdown("<br>", unsafe_allow_html=True)
        if st.button("🚪 Logout", use_container_width=True):
            st.session_state.user      = None
            st.session_state.pop("kb_search_query",  None)
            st.session_state.pop("kb_selected_doc",  None)
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
