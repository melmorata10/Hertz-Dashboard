import streamlit as st
from supabase import create_client, Client
import hashlib
import datetime
from io import BytesIO

SUPABASE_URL = st.secrets["supabase"]["url"]
SUPABASE_KEY = st.secrets["supabase"]["service_role_key"]

@st.cache_resource
def get_supabase() -> Client:
    return create_client(SUPABASE_URL, SUPABASE_KEY)

supabase = get_supabase()

# ─────────────────────────────────────────
# FILE TEXT EXTRACTION
# ─────────────────────────────────────────
def extract_text_from_file(file) -> str:
    """Extract text from DOCX or PDF preserving formatting as markdown."""
    file_bytes = file.read()
    name = file.name.lower()
    text_lines = []

    if name.endswith(".docx"):
        try:
            from docx import Document as DocxDoc
            from docx.oxml.ns import qn
            doc = DocxDoc(BytesIO(file_bytes))

            # Track numbering — key: (num_id, ilvl), resets when non-list para interrupts
            num_counters = {}
            prev_num_id  = None

            for para in doc.paragraphs:
                t = para.text.strip()
                style = para.style.name if para.style else ""

                # Detect inline bold/italic runs
                rich = ""
                for run in para.runs:
                    rt = run.text
                    if not rt:
                        continue
                    if run.bold and run.italic:
                        rich += f"***{rt}***"
                    elif run.bold:
                        rich += f"**{rt}**"
                    elif run.italic:
                        rich += f"*{rt}*"
                    else:
                        rich += rt
                rich = rich.strip()
                if not rich:
                    # Blank line = list interrupted; reset counters for prev list
                    if prev_num_id:
                        for k in list(num_counters.keys()):
                            if k.startswith(f"{prev_num_id}_"):
                                num_counters[k] = 0
                        prev_num_id = None
                    text_lines.append("")
                    continue

                # Headings
                if "Heading 1" in style:
                    prev_num_id = None
                    text_lines.append(f"## {rich}")
                    continue
                elif "Heading 2" in style:
                    prev_num_id = None
                    text_lines.append(f"### {rich}")
                    continue
                elif "Heading 3" in style:
                    prev_num_id = None
                    text_lines.append(f"#### {rich}")
                    continue

                # Detect numbered list via numPr XML
                num_pr = para._p.find(qn("w:pPr"))
                num_id = None
                ilvl   = 0
                if num_pr is not None:
                    np_el = num_pr.find(qn("w:numPr"))
                    if np_el is not None:
                        ilvl_el  = np_el.find(qn("w:ilvl"))
                        numid_el = np_el.find(qn("w:numId"))
                        if ilvl_el is not None and numid_el is not None:
                            num_id = numid_el.get(qn("w:val"))
                            ilvl   = int(ilvl_el.get(qn("w:val"), 0))

                if num_id is not None:
                    # New list group detected — reset counters for this numId
                    if num_id != prev_num_id and prev_num_id is not None:
                        for k in list(num_counters.keys()):
                            if k.startswith(f"{num_id}_"):
                                num_counters[k] = 0
                    # Reset deeper indent levels when parent level increments
                    for k in list(num_counters.keys()):
                        parts = k.rsplit("_", 1)
                        if len(parts) == 2 and parts[0] == num_id and int(parts[1]) > ilvl:
                            num_counters[k] = 0
                    key = f"{num_id}_{ilvl}"
                    num_counters[key] = num_counters.get(key, 0) + 1
                    prev_num_id = num_id
                    indent = "   " * ilvl
                    text_lines.append(f"{indent}{num_counters[key]}. {rich}")
                    continue

                # Bullet lists
                if "List" in style:
                    prev_num_id = None
                    text_lines.append(f"- {rich}")
                    continue

                # Normal paragraph — reset list tracking
                prev_num_id = None
                text_lines.append(rich)

            # Tables
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
            return f"Could not extract text from Word file: {e}"

    elif name.endswith(".pdf"):
        try:
            import pdfplumber
            with pdfplumber.open(BytesIO(file_bytes)) as pdf:
                for page in pdf.pages:
                    pt = page.extract_text()
                    if pt:
                        text_lines.extend(pt.split("\n"))
                    text_lines.append("")
        except Exception:
            try:
                import PyPDF2
                reader = PyPDF2.PdfReader(BytesIO(file_bytes))
                for page in reader.pages:
                    t = page.extract_text()
                    if t:
                        text_lines.extend(t.split("\n"))
                    text_lines.append("")
            except Exception as e:
                return f"Could not extract text from PDF: {e}"

    return "\n".join(text_lines).strip()

# ─────────────────────────────────────────
# CSS
# ─────────────────────────────────────────
def inject_css():
    st.markdown("""
<style>
/* ── Fonts: DM Sans (sharp, modern) + DM Mono (technical accents) ── */
@import url('https://fonts.googleapis.com/css2?family=DM+Sans:ital,opsz,wght@0,9..40,300;0,9..40,400;0,9..40,500;0,9..40,600;0,9..40,700;0,9..40,800;1,9..40,400&family=DM+Mono:wght@400;500&family=Sora:wght@700;800&display=swap');

/* ── Animations ── */
@keyframes sidebarFlow { 0%{background-position:0% 0%} 100%{background-position:0% 100%} }
@keyframes logoPulse { 0%,100%{box-shadow:0 4px 18px rgba(255,215,0,0.45)} 50%{box-shadow:0 6px 26px rgba(255,215,0,0.65)} }
@keyframes subtitleShift { 0%,100%{color:rgba(255,215,0,0.65)} 50%{color:rgba(255,215,0,0.95)} }
@keyframes fadeUp {
    from { opacity:0; transform:translateY(20px); }
    to   { opacity:1; transform:translateY(0); }
}
@keyframes shimmer {
    0%   { background-position: -200% center; }
    100% { background-position: 200% center; }
}
@keyframes livePulse { 0%,100%{box-shadow:0 0 0 0 rgba(74,222,128,0.55)} 50%{box-shadow:0 0 0 5px rgba(74,222,128,0)} }
@keyframes rowSlide {
    from { opacity:0; transform:translateX(-8px); }
    to   { opacity:1; transform:translateX(0); }
}

/* ── Base — warm off-white with subtle texture ── */
html, body, .stApp {
    font-family: 'DM Sans', sans-serif !important;
    background: #f5f3ef !important;
}
/* Subtle linen-like texture overlay */
.stApp::before {
    content: '';
    position: fixed; inset: 0;
    background-image:
        repeating-linear-gradient(
            0deg,
            transparent,
            transparent 2px,
            rgba(180,170,150,0.035) 2px,
            rgba(180,170,150,0.035) 3px
        );
    pointer-events: none; z-index: 0;
}
/* ── Sidebar ── */
section[data-testid="stSidebar"] {
    background: linear-gradient(180deg, #06101e 0%, #091624 40%, #0d1e30 70%, #06101e 100%) !important;
    background-size: 100% 300% !important;
    animation: sidebarFlow 18s ease-in-out infinite alternate !important;
    border-right: 1px solid rgba(255,215,0,0.25) !important;
    box-shadow: 2px 0 24px rgba(0,0,0,0.4) !important;
}
[data-testid="stSidebarNav"] { padding: 2px 12px 14px !important; }
[data-testid="stSidebarNav"]::before {
    content: "NAVIGATION"; display: block;
    font-family: 'DM Mono', monospace;
    font-size: 9px; font-weight: 500; letter-spacing: 3px;
    color: rgba(255,215,0,0.4); padding: 12px 6px 10px;
    text-transform: uppercase;
}
[data-testid="stSidebarNav"] a {
    display: flex !important; align-items: center !important;
    margin: 3px 0 !important; padding: 11px 14px 11px 16px !important;
    border-radius: 6px !important;
    border: 1px solid transparent !important;
    background: transparent !important;
    text-decoration: none !important;
    transition: all 0.18s ease !important;
    position: relative !important;
}
[data-testid="stSidebarNav"] a:hover {
    background: rgba(255,215,0,0.07) !important;
    border-color: rgba(255,215,0,0.2) !important;
    transform: translateX(4px) !important;
}
[data-testid="stSidebarNav"] a[aria-current="page"] {
    background: rgba(255,215,0,0.1) !important;
    border-color: rgba(255,215,0,0.3) !important;
}
[data-testid="stSidebarNav"] a li,
[data-testid="stSidebarNav"] a span,
[data-testid="stSidebarNav"] ul li span {
    color: #b8cfe8 !important; font-weight: 500 !important;
    font-size: 13px !important; letter-spacing: 0.1px !important;
    font-family: 'DM Sans', sans-serif !important;
}
[data-testid="stSidebarNav"] a[aria-current="page"] span {
    color: #FFD700 !important;
}
[data-testid="stSidebarNav"] a[href*="Verint"],
[data-testid="stSidebarNav"] a[href*="verint"],
[data-testid="stSidebarNav"] a[href*="2_Verint"],
[data-testid="stSidebarNav"] a[href*="_2_Verint"] { display: none !important; }

section[data-testid="stSidebar"] label,
section[data-testid="stSidebar"] p,
section[data-testid="stSidebar"] span,
section[data-testid="stSidebar"] div,
section[data-testid="stSidebar"] small { color: #9bb5cf !important; }
section[data-testid="stSidebar"] hr {
    border: none !important; height: 1px !important;
    background: rgba(255,255,255,0.06) !important; margin: 12px 0 !important;
}

/* ── Sidebar Radio — clean pill style ── */
section[data-testid="stSidebar"] .stRadio div[role="radiogroup"] {
    gap: 3px !important; width: 100% !important;
}
section[data-testid="stSidebar"] .stRadio input[type="radio"] { display: none !important; }
section[data-testid="stSidebar"] .stRadio label > div:first-child { display: none !important; }
section[data-testid="stSidebar"] .stRadio label {
    display: flex !important; align-items: center !important;
    padding: 0 14px 0 16px !important;
    height: 44px !important; min-height: 44px !important; max-height: 44px !important;
    width: 100% !important; border-radius: 6px !important;
    border: 1px solid transparent !important;
    background: transparent !important;
    color: #b8cfe8 !important; font-weight: 500 !important;
    font-size: 13px !important; font-family: 'DM Sans', sans-serif !important;
    cursor: pointer !important; transition: all 0.18s ease !important;
    margin: 0 !important; box-sizing: border-box !important;
    line-height: 1 !important; overflow: hidden !important;
}
section[data-testid="stSidebar"] .stRadio label:has(input:checked) {
    background: rgba(255,215,0,0.1) !important;
    border-color: rgba(255,215,0,0.3) !important;
    color: #FFD700 !important;
}
section[data-testid="stSidebar"] .stRadio label > div {
    display: flex !important; align-items: center !important;
    height: 100% !important; padding: 0 !important; margin: 0 !important; width: 100% !important;
}
section[data-testid="stSidebar"] .stRadio label p {
    margin: 0 !important; padding: 0 !important; line-height: 1 !important;
    font-family: 'DM Sans', sans-serif !important;
}
section[data-testid="stSidebar"] .stRadio label:hover {
    background: rgba(255,215,0,0.07) !important;
    border-color: rgba(255,215,0,0.2) !important;
    transform: translateX(4px) !important;
}
[data-testid="stSidebarNav"] a {
    height: 44px !important; min-height: 44px !important; max-height: 44px !important;
    padding: 0 14px 0 16px !important; width: 100% !important;
    box-sizing: border-box !important; align-items: center !important;
}
section[data-testid="stSidebar"] .stButton button {
    background: linear-gradient(135deg, #FFD700 0%, #f5c400 55%, #e8b000 100%) !important;
    color: #06101e !important; font-weight: 700 !important;
    border: none !important; border-radius: 6px !important;
    width: 100% !important; transition: all 0.2s ease !important;
    font-family: 'DM Sans', sans-serif !important;
    font-size: 13px !important; letter-spacing: 0.2px !important;
    box-shadow: 0 2px 8px rgba(255,215,0,0.25) !important;
}
section[data-testid="stSidebar"] .stButton button:hover {
    transform: translateY(-1px) !important;
    box-shadow: 0 4px 14px rgba(255,215,0,0.4) !important;
}

/* ── Main content ── */
[data-testid="stMainBlockContainer"] { animation: fadeUp 0.35s ease both; }
section.main > div[data-testid="stMainBlockContainer"] > div {
    max-width: 1120px !important; margin: 0 auto !important;
}

/* ── Containers/cards ── */
[data-testid="stVerticalBlockBorderWrapper"] {
    background: #ffffff !important;
    border: 1px solid rgba(180,170,150,0.25) !important;
    border-radius: 8px !important;
    box-shadow: 0 1px 4px rgba(0,0,0,0.06), 0 4px 16px rgba(0,0,0,0.04) !important;
}

/* ── Expanders ── */
details {
    border: 1px solid rgba(180,170,150,0.25) !important;
    border-radius: 8px !important; overflow: hidden;
    background: #ffffff !important;
    box-shadow: 0 1px 4px rgba(0,0,0,0.05) !important;
}
details[open] summary { border-bottom: 1px solid rgba(180,170,150,0.2); }
summary {
    background: #faf9f7 !important;
    font-weight: 600 !important; color: #1a2332 !important;
    padding: 14px 18px !important; border-radius: 8px !important;
    font-family: 'DM Sans', sans-serif !important;
    font-size: 14px !important;
}
summary:hover { background: #f3f1ee !important; }

/* ── Inputs ── */
[data-testid="stTextInput"] input,
[data-testid="stTextArea"] textarea {
    background: #ffffff !important;
    border: 1px solid rgba(180,170,150,0.35) !important;
    border-radius: 6px !important; color: #1a2332 !important;
    font-family: 'DM Sans', sans-serif !important;
    font-size: 14px !important;
    transition: border-color 0.15s ease, box-shadow 0.15s ease !important;
}
[data-testid="stTextInput"] input:focus,
[data-testid="stTextArea"] textarea:focus {
    border-color: #c9a800 !important;
    box-shadow: 0 0 0 3px rgba(255,215,0,0.12) !important;
}

/* ── Primary buttons ── */
[data-testid="stFormSubmitButton"] button, button[kind="primary"] {
    background: linear-gradient(135deg, #FFD700 0%, #f5c400 55%, #e8b000 100%) !important;
    color: #06101e !important; font-weight: 700 !important;
    border: none !important; border-radius: 6px !important;
    font-family: 'DM Sans', sans-serif !important;
    font-size: 14px !important; letter-spacing: 0.2px !important;
    box-shadow: 0 2px 8px rgba(255,215,0,0.25) !important;
    transition: all 0.2s ease !important;
}
[data-testid="stFormSubmitButton"] button:hover, button[kind="primary"]:hover {
    transform: translateY(-1px) !important;
    box-shadow: 0 4px 14px rgba(255,215,0,0.4) !important;
}

/* ── Tabs ── */
.stTabs [data-baseweb="tab-list"] {
    background: transparent; gap: 2px; padding: 0;
    border-bottom: 2px solid rgba(180,170,150,0.2);
}
.stTabs [data-baseweb="tab"] {
    color: #8a9ab0 !important; font-weight: 500 !important;
    font-size: 13.5px !important; padding: 10px 22px !important;
    border-radius: 6px 6px 0 0 !important; background: transparent !important;
    font-family: 'DM Sans', sans-serif !important;
    transition: all 0.18s ease !important;
}
.stTabs [data-baseweb="tab"]:hover { color: #1a2332 !important; background: rgba(0,0,0,0.03) !important; }
.stTabs [aria-selected="true"] {
    background: #fff !important; color: #1a2332 !important;
    font-weight: 700 !important; border-bottom-color: #fff !important;
    margin-bottom: -2px !important; box-shadow: inset 0 -3px 0 #FFD700 !important;
}
.stTabs [data-baseweb="tab-panel"] {
    background: #fff; border: 1px solid rgba(180,170,150,0.2);
    border-top: none; border-radius: 0 8px 8px 8px;
    padding: 24px; box-shadow: 0 4px 20px rgba(0,0,0,0.05);
}

/* ── Misc ── */
.stAlert { border-radius: 8px !important; }
hr {
    border: none !important; height: 1px !important;
    background: linear-gradient(90deg, transparent, rgba(180,170,150,0.4), transparent) !important;
    margin: 20px 0 !important;
}
h3 {
    color: #0a1628 !important; font-weight: 700 !important;
    font-family: 'Sora', sans-serif !important;
}
h4 {
    color: #1a3a5c !important; font-weight: 700 !important;
    font-family: 'DM Sans', sans-serif !important;
    border-left: 3px solid #FFD700; padding-left: 12px;
}
.stCaption { color: #9a9080 !important; font-size: 12px !important; }

/* ── Category chips ── */
.category-chip {
    display: inline-block;
    background: rgba(255,215,0,0.1);
    border: 1px solid rgba(200,160,0,0.25);
    border-radius: 4px;
    padding: 2px 10px;
    font-size: 10.5px; font-weight: 600;
    color: #7a5c00; margin-right: 6px;
    font-family: 'DM Mono', monospace;
    letter-spacing: 0.3px;
    text-transform: uppercase;
}

/* ── List rows (FAQ, search, category) ── */
.kb-list-container {
    background: #fff;
    border: 1px solid rgba(180,170,150,0.25);
    border-radius: 8px;
    overflow: hidden;
    box-shadow: 0 1px 4px rgba(0,0,0,0.06);
}

/* ── Recent panel items ── */
.recent-item {
    padding: 12px 16px;
    border-bottom: 1px solid rgba(180,170,150,0.15);
    transition: background 0.15s ease;
    cursor: pointer;
}
.recent-item:last-child { border-bottom: none; }
.recent-item:hover { background: #faf7f0; }
.recent-title {
    font-size: 13px; font-weight: 600; color: #1a2332;
    line-height: 1.4; margin-bottom: 4px;
    font-family: 'DM Sans', sans-serif;
}
.recent-meta {
    font-size: 11px; color: #9a9080;
    font-family: 'DM Mono', monospace;
}
</style>
""", unsafe_allow_html=True)

# ─────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────
def hash_password(p): return hashlib.sha256(p.encode()).hexdigest()

def login(email, password):
    r = supabase.table("kb_users").select("*").eq("email", email.lower().strip()).eq("password", hash_password(password)).eq("is_active", True).execute()
    return r.data[0] if r.data else None

def get_categories():
    return supabase.table("kb_categories").select("*").order("order_num").execute().data

def search_docs(query):
    """Search docs by title and content, ranked by relevance."""
    q = query.lower().strip()
    r1 = supabase.table("kb_documents").select("*, kb_categories(name), kb_users!kb_documents_submitted_by_fkey(name)").eq("status","approved").ilike("title",f"%{query}%").execute().data
    r2 = supabase.table("kb_documents").select("*, kb_categories(name), kb_users!kb_documents_submitted_by_fkey(name)").eq("status","approved").ilike("content",f"%{query}%").execute().data

    # Merge deduped
    seen = set(); merged = []
    for doc in r1 + r2:
        if doc["id"] not in seen:
            seen.add(doc["id"]); merged.append(doc)

    # Score each doc
    def score(doc):
        title   = (doc.get("title")   or "").lower()
        content = (doc.get("content") or "").lower()
        s = 0
        # Exact title match = highest
        if title == q:                        s += 100
        # Title starts with query
        elif title.startswith(q):             s += 80
        # Query is a whole word in title
        elif f" {q} " in f" {title} ":       s += 60
        # Query appears anywhere in title
        elif q in title:                      s += 40
        # Query in first 200 chars of content (intro/summary)
        if q in content[:200]:                s += 20
        # Count occurrences in content (frequency signal)
        s += min(content.count(q) * 3, 15)
        # Recency bonus — newer docs rank slightly higher on ties
        reviewed = doc.get("reviewed_at") or ""
        s += 5 if reviewed else 0
        return s

    merged.sort(key=score, reverse=True)
    return merged

def get_docs_by_category(category_id):
    return supabase.table("kb_documents").select("*, kb_categories(name), kb_users!kb_documents_submitted_by_fkey(name)").eq("status","approved").eq("category_id",category_id).order("reviewed_at",desc=True).execute().data

def get_all_approved():
    return supabase.table("kb_documents").select("*, kb_categories(name), kb_users!kb_documents_submitted_by_fkey(name)").eq("status","approved").order("reviewed_at",desc=True).execute().data

def get_doc_by_id(doc_id):
    r = supabase.table("kb_documents").select("*, kb_categories(name), kb_users!kb_documents_submitted_by_fkey(name)").eq("id",doc_id).execute()
    return r.data[0] if r.data else None

def get_pending_docs():
    return supabase.table("kb_documents").select("*, kb_categories(name), kb_users!kb_documents_submitted_by_fkey(name)").eq("status","pending").order("submitted_at").execute().data

def get_all_docs_by_status(status):
    return supabase.table("kb_documents").select("*, kb_categories(name), kb_users!kb_documents_submitted_by_fkey(name)").eq("status",status).order("submitted_at",desc=True).execute().data

def approve_doc(doc_id, reviewer_id):
    supabase.table("kb_documents").update({"status":"approved","reviewed_by":reviewer_id,"reviewed_at":datetime.datetime.now().isoformat(),"updated_at":datetime.datetime.now().isoformat()}).eq("id",doc_id).execute()

def reject_doc(doc_id, reviewer_id):
    supabase.table("kb_documents").update({"status":"rejected","reviewed_by":reviewer_id,"reviewed_at":datetime.datetime.now().isoformat(),"updated_at":datetime.datetime.now().isoformat()}).eq("id",doc_id).execute()

def delete_doc(doc_id):
    supabase.table("kb_documents").delete().eq("id",doc_id).execute()

def update_doc(doc_id, title, category_id, content, current_version):
    supabase.table("kb_documents").update({"title":title,"category_id":category_id,"content":content,"version":(current_version or 1)+1,"updated_at":datetime.datetime.now().isoformat()}).eq("id",doc_id).execute()

CAT_ICONS = {"HOOP List":"📋","Reports":"📊","Tools":"🔧","Escalation":"🚨"}

# ─────────────────────────────────────────
# RENDER HELPERS
# ─────────────────────────────────────────
def render_header(title, subtitle=""):
    sub = (
        f"<p style='font-size:13px;color:rgba(255,255,255,0.45);margin:6px 0 0 0;"
        f"font-family:DM Sans,sans-serif;font-weight:400;letter-spacing:0.1px;'>{subtitle}</p>"
    ) if subtitle else ""
    st.markdown(
        f"<div style='"
        f"background:linear-gradient(135deg,#06101e 0%,#0d1e30 50%,#091624 100%);"
        f"padding:24px 36px 22px;border-radius:10px;"
        f"margin-bottom:24px;"
        f"border-bottom:2px solid #c9a800;"
        f"box-shadow:0 4px 24px rgba(0,0,0,0.18),0 1px 0 rgba(255,215,0,0.1);"
        f"position:relative;overflow:hidden;'>"
        f"<div style='position:absolute;top:0;right:0;width:200px;height:100%;"
        f"background:linear-gradient(135deg,transparent 40%,rgba(255,215,0,0.04));'></div>"
        f"<p style='font-family:DM Mono,monospace;font-size:9.5px;font-weight:500;"
        f"color:rgba(255,215,0,0.5);letter-spacing:3px;text-transform:uppercase;"
        f"margin:0 0 8px 0;'>HERTZ &nbsp;&middot;&nbsp; POWERED BY CALLINSITE</p>"
        f"<p style='font-family:Sora,sans-serif;font-size:24px;font-weight:800;"
        f"color:#ffffff;margin:0;line-height:1.15;letter-spacing:-0.3px;'>{title}</p>"
        f"{sub}</div>",
        unsafe_allow_html=True
    )

def render_doc_card(doc, btn_key_prefix):
    import re
    cat_name    = (doc.get("kb_categories") or {}).get("name","—")
    icon        = CAT_ICONS.get(cat_name,"📄")
    reviewed    = (doc.get("reviewed_at") or "")[:10] or "—"
    raw_preview = (doc.get("content") or "")[:300]
    raw_preview = re.sub(r"[#]+ *", "", raw_preview)
    raw_preview = re.sub(r"[*]+([^*]+)[*]+", r"\1", raw_preview)
    raw_preview = raw_preview.replace("\n", " ").strip()
    preview     = (raw_preview[:130] + "...") if len(raw_preview) > 130 else raw_preview

    uid = f"{btn_key_prefix}_{doc['id']}"
    st.markdown(f"""
    <style>
    div[data-key="{uid}"] button {{
        background: white !important;
        border: none !important;
        border-bottom: 1px solid rgba(200,215,235,0.7) !important;
        border-radius: 0 !important;
        padding: 14px 8px 14px 16px !important;
        text-align: left !important;
        white-space: normal !important;
        height: auto !important;
        line-height: 1.5 !important;
        color: #0a1628 !important;
        font-weight: 400 !important;
        box-shadow: none !important;
        transition: background 0.15s ease !important;
        margin: 0 !important;
        width: 100% !important;
        position: relative !important;
    }}
    div[data-key="{uid}"] button:hover {{
        background: #f0f5ff !important;
        border-bottom-color: #FFD700 !important;
        box-shadow: none !important;
        transform: none !important;
    }}
    div[data-key="{uid}"] button:hover::after {{
        content: "›";
        position: absolute;
        right: 16px;
        top: 50%;
        transform: translateY(-50%);
        color: #FFD700;
        font-size: 20px;
    }}
    </style>
    """, unsafe_allow_html=True)

    label = (
        f"**{doc['title']}**  \n"
        f"*{icon} {cat_name} · {reviewed}*"
        + (f"  \n{preview}" if preview else "")
    )
    if st.button(label, key=uid, use_container_width=True):
        st.session_state.kb_selected_doc = doc["id"]
        st.rerun()

def render_content(content_text: str):
    """Render article content with clean KB-styled formatting."""
    if not content_text:
        st.info("No content available for this document.")
        return

    st.markdown("""
    <style>
    .kb-content { font-family: 'Inter', sans-serif; color: #1a2332; line-height: 1.75; }
    .kb-content h2 {
        font-size: 1.25rem; font-weight: 800; color: #0a1628;
        border-bottom: 2px solid #FFD700; padding-bottom: 8px;
        margin: 28px 0 14px 0;
    }
    .kb-content h3 {
        font-size: 1.05rem; font-weight: 700; color: #1a3a5c;
        border-left: 3px solid #FFD700; padding-left: 10px;
        margin: 22px 0 10px 0;
    }
    .kb-content h4 {
        font-size: 0.95rem; font-weight: 700; color: #2d5480;
        margin: 18px 0 8px 0;
    }
    .kb-content p { margin: 8px 0; color: #1a2332; }
    .kb-content ol {
        padding-left: 22px; margin: 10px 0;
        counter-reset: none;
    }
    .kb-content ol li {
        margin: 6px 0; padding-left: 4px;
        color: #1a2332; line-height: 1.65;
    }
    .kb-content ul { padding-left: 20px; margin: 10px 0; }
    .kb-content ul li {
        margin: 5px 0; color: #1a2332;
        list-style-type: disc;
    }
    .kb-content strong { color: #0a1628; font-weight: 700; }
    .kb-content em { color: #2d5480; }
    .kb-content code {
        background: #f0f4fa; border: 1px solid #dce6f0;
        border-radius: 4px; padding: 2px 6px;
        font-family: monospace; font-size: 0.88rem; color: #c7254e;
    }
    .kb-content blockquote {
        border-left: 4px solid #FFD700; background: #fffdf0;
        padding: 10px 16px; margin: 12px 0; border-radius: 0 8px 8px 0;
        color: #5a4a00; font-style: italic;
    }
    .kb-content table {
        width: 100%; border-collapse: collapse; margin: 16px 0;
        font-size: 0.9rem;
    }
    .kb-content th {
        background: #0a1628; color: #FFD700; font-weight: 700;
        padding: 10px 14px; text-align: left; border: 1px solid #1e3a5f;
    }
    .kb-content td {
        padding: 8px 14px; border: 1px solid #dce6f0;
        background: white; color: #1a2332;
    }
    .kb-content tr:nth-child(even) td { background: #f7faff; }
    .kb-content a { color: #1a6fbf; text-decoration: underline; }
    .kb-content hr {
        border: none; border-top: 1px solid #dce6f0; margin: 20px 0;
    }
    </style>
    """, unsafe_allow_html=True)

    # Wrap in styled div and render markdown
    st.markdown(
        f"<div class='kb-content'>",
        unsafe_allow_html=True
    )
    st.markdown(content_text)
    st.markdown("</div>", unsafe_allow_html=True)


def render_doc_detail(doc, user=None):
    cat_name  = (doc.get("kb_categories") or {}).get("name","—")
    icon      = CAT_ICONS.get(cat_name,"📄")
    submitter = (doc.get("kb_users") or {}).get("name","Unknown")
    reviewed  = (doc.get("reviewed_at") or "")[:10] or "—"
    is_admin  = user and user.get("role") in ["admin","super_admin"]

    # Top action bar
    col_back, col_edit, col_spacer = st.columns([1, 1, 8])
    with col_back:
        if st.button("← Back", key="back_btn"):
            st.session_state.kb_selected_doc = None
            st.session_state.pop("kb_inline_edit", None)
            st.rerun()
    with col_edit:
        if is_admin:
            edit_active = st.session_state.get("kb_inline_edit") == doc["id"]
            label = "✏️ Editing..." if edit_active else "✏️ Edit"
            if st.button(label, key="detail_edit_btn"):
                if edit_active:
                    st.session_state.pop("kb_inline_edit", None)
                else:
                    st.session_state["kb_inline_edit"] = doc["id"]
                st.rerun()

    st.markdown("<br>", unsafe_allow_html=True)

    # Doc header
    st.markdown(
        f"<div style='background:white;border:1px solid rgba(200,215,235,0.8);"
        f"border-left:5px solid #FFD700;border-radius:12px;padding:20px 24px;"
        f"margin-bottom:20px;box-shadow:0 2px 12px rgba(0,0,0,0.05);'>"
        f"<div style='font-size:11px;color:#8099b8;margin-bottom:6px;'>"
        f"<span class='category-chip'>{icon} {cat_name}</span>"
        f"Version {doc.get('version',1)} · Last updated: {reviewed} · By: {submitter}</div>"
        f"<h2 style='color:#0a1628;margin:0;font-size:1.4rem;font-weight:800;'>{doc['title']}</h2>"
        f"</div>",
        unsafe_allow_html=True
    )

    # Inline edit form
    if is_admin and st.session_state.get("kb_inline_edit") == doc["id"]:
        render_edit_form(doc, f"inline_edit_{doc['id']}")
        st.markdown("---")

    # Content
    st.markdown("""
    <div style='background:white;border:1px solid rgba(200,215,235,0.8);
                border-radius:12px;padding:28px 32px;
                box-shadow:0 2px 12px rgba(0,0,0,0.04);'>
    """, unsafe_allow_html=True)
    render_content(doc.get("content",""))
    st.markdown("</div>", unsafe_allow_html=True)

def render_edit_form(doc, form_key):
    categories = get_categories()
    cat_map    = {cat["name"]: cat["id"] for cat in categories}
    cat_names  = list(cat_map.keys())
    cur_cat    = (doc.get("kb_categories") or {}).get("name", cat_names[0])
    if cur_cat not in cat_names:
        cur_cat = cat_names[0]

    st.markdown("#### ✏️ Edit Document")

    # File upload must be OUTSIDE st.form (Streamlit limitation)
    extract_key   = f"extracted_{form_key}"
    uploaded_file = st.file_uploader(
        "📎 Upload new version — PDF or Word (replaces content below)",
        type=["pdf", "docx"],
        key=f"upload_{form_key}"
    )
    if uploaded_file is not None:
        with st.spinner("Extracting content from file..."):
            extracted = extract_text_from_file(uploaded_file)
        if extracted:
            st.session_state[extract_key] = extracted
            st.success("✅ Content extracted — review and save below")
        else:
            st.warning("Could not extract text. Paste content manually.")

    prefill_content = st.session_state.get(extract_key, doc.get("content", ""))

    with st.form(key=form_key):
        new_title   = st.text_input("Title", value=doc.get("title", ""))
        new_cat     = st.selectbox("Category", options=cat_names,
                                    index=cat_names.index(cur_cat))
        new_content = st.text_area("Content", value=prefill_content, height=300)
        col_s, col_c = st.columns([1, 1])
        with col_s:
            save = st.form_submit_button("💾 Save Changes",
                                          use_container_width=True, type="primary")
        with col_c:
            cancel = st.form_submit_button("Cancel", use_container_width=True)
        if save:
            update_doc(doc["id"], new_title, cat_map[new_cat],
                       new_content, doc.get("version", 1))
            st.session_state.pop("editing_doc", None)
            st.session_state.pop(extract_key, None)
            st.toast("✅ Document updated!", icon="✅")
            st.rerun()
        if cancel:
            st.session_state.pop("editing_doc", None)
            st.session_state.pop(extract_key, None)
            st.rerun()

# ─────────────────────────────────────────
# PAGES
# ─────────────────────────────────────────
def page_login():
    st.markdown("""
    <div style="max-width:400px;margin:80px auto 0 auto;">
        <div style="text-align:center;margin-bottom:32px;">
            <div style="background:linear-gradient(135deg,#FFD700 0%,#e8b000 100%);
                        display:inline-block;padding:7px 22px;border-radius:4px;
                        box-shadow:0 2px 12px rgba(255,215,0,0.3);">
                <span style="font-family:Arial Black,Impact,sans-serif;
                             font-size:22px;font-weight:900;color:#06101e;letter-spacing:3px;">HERTZ</span>
            </div>
            <div style="font-family:'DM Mono',monospace;font-size:9px;letter-spacing:3px;
                        margin-top:8px;text-transform:uppercase;color:#9a9080;">
                Powered by Callinsite
            </div>
        </div>
        <div style="background:#fff;border:1px solid rgba(180,170,150,0.3);
                    border-radius:10px;padding:36px 40px;
                    box-shadow:0 2px 8px rgba(0,0,0,0.07),0 12px 40px rgba(0,0,0,0.05);">
            <h2 style="font-family:'Sora',sans-serif;color:#0a1628;
                       margin:0 0 4px 0;font-size:1.2rem;font-weight:800;">
                RTA Knowledge Base
            </h2>
            <p style="font-family:'DM Sans',sans-serif;color:#9a9080;
                      font-size:13px;margin:0 0 24px 0;">
                Sign in to access process guides and reports
            </p>
        </div>
    </div>
    """, unsafe_allow_html=True)
    col1, col2, col3 = st.columns([1,1.2,1])
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


def render_recent_uploads_panel():
    """Right panel — compact list of recently submitted docs, each row is clickable."""
    st.markdown("""
    <p style='font-family:DM Mono,monospace;font-size:9px;font-weight:500;
              letter-spacing:3px;color:#9a9080;text-transform:uppercase;
              margin:0 0 14px 0;'>
        Recently Added
    </p>
    <div style='background:#fff;border:1px solid rgba(180,170,150,0.25);
                border-radius:8px;overflow:hidden;
                box-shadow:0 1px 4px rgba(0,0,0,0.05);'>
    """, unsafe_allow_html=True)

    recent = (
        supabase.table("kb_documents")
        .select("id, title, submitted_at, kb_categories(name), kb_users!kb_documents_submitted_by_fkey(name)")
        .eq("status", "approved")
        .order("submitted_at", desc=True)
        .limit(8)
        .execute()
        .data
    )

    st.markdown("</div>", unsafe_allow_html=True)

    if not recent:
        st.caption("No documents yet.")
        return

    for i, doc in enumerate(recent):
        cat_name  = (doc.get("kb_categories") or {}).get("name", "—")
        icon      = CAT_ICONS.get(cat_name, "📄")
        submitter = (doc.get("kb_users") or {}).get("name", "Unknown")
        submitted = (doc.get("submitted_at") or "")[:10] or "—"
        is_last   = i == len(recent) - 1
        border_b  = "none" if is_last else "1px solid rgba(200,215,235,0.6)"

        uid = f"recent_{doc['id']}"
        st.markdown(f"""
        <style>
        div[data-key="{uid}"] button {{
            background: transparent !important;
            border: none !important;
            border-bottom: {border_b} !important;
            border-radius: 0 !important;
            padding: 10px 4px !important;
            text-align: left !important;
            white-space: normal !important;
            height: auto !important;
            line-height: 1.5 !important;
            color: #0a1628 !important;
            font-weight: 400 !important;
            box-shadow: none !important;
            transition: background 0.15s !important;
            margin: 0 !important;
            width: 100% !important;
        }}
        div[data-key="{uid}"] button:hover {{
            background: #f0f5ff !important;
            box-shadow: none !important;
            transform: none !important;
        }}
        </style>
        """, unsafe_allow_html=True)

        label = (
            f"**{doc['title'][:45]}{'...' if len(doc['title'])>45 else ''}**  \n"
            f"*{icon} {cat_name}*  \n"
            f"{submitted} · {submitter}"
        )
        if st.button(label, key=uid, use_container_width=True):
            st.session_state.kb_selected_doc = doc["id"]
            st.rerun()


def _doc_to_faq_question(doc: dict) -> str:
    """Convert a document title into a natural FAQ question."""
    title = doc.get("title", "")
    # Map common patterns to question format
    mappings = [
        ("How to ", "How do I "),
        ("EOD ", "How do I complete the EOD "),
        ("Hourly Intraday", "How do I send the Hourly Intraday Report?"),
        ("Daily Correspondence", "How do I update Daily Correspondence Performance?"),
        ("Contact Ratio", "How do I track Contact Ratio?"),
        ("NonPhone", "How do I update NonPhone Data?"),
        ("Replacement Account", "How do I run the Replacement Account Report?"),
        ("Channel Support", "What are the Channel Support & HOOP details?"),
        ("Escalation", "How does the Escalation process work?"),
        ("ServiceNow", "How do I create a ServiceNow ticket?"),
        ("RingCentral", "How do I use RingCentral for allocation?"),
        ("PC Excalibur", "How do I unlock PC Excalibur?"),
        ("NICE IEX", "How do I use NICE IEX?"),
        ("ASA", "How do I calculate ASA & Allocation?"),
        ("RTA Governance", "What is the RTA Start of Shift checklist?"),
    ]
    for key, question in mappings:
        if key.lower() in title.lower():
            return question
    # Default: convert title to question
    if title.lower().startswith("how"):
        return title + "?"
    return f"How do I use: {title}?"


def page_knowledge_base():
    render_header("📚 RTA Knowledge Base", "Search for processes, reports, and tool guides")

    if "kb_search_query"    not in st.session_state:
        st.session_state.kb_search_query    = ""
    if "kb_selected_doc"    not in st.session_state:
        st.session_state.kb_selected_doc    = None
    if "kb_category_filter" not in st.session_state:
        st.session_state.kb_category_filter = None

    # Full-width article detail view
    if st.session_state.kb_selected_doc:
        doc = get_doc_by_id(st.session_state.kb_selected_doc)
        if doc:
            render_doc_detail(doc, user=st.session_state.get("user"))
        else:
            st.session_state.kb_selected_doc = None
            st.rerun()
        return

    # ── Two-column layout ─────────────────────────────────────────────────
    left_col, right_col = st.columns([3, 1])

    with left_col:
        # Category chips
        categories = get_categories()
        if categories:
            st.markdown(
                "<p style='font-family:DM Mono,monospace;font-size:9px;font-weight:500;"
                "letter-spacing:3px;color:#9a9080;text-transform:uppercase;margin:0 0 10px 0;'>"
                "Browse by Category</p>",
                unsafe_allow_html=True
            )
            num_cats = len(categories)
            cat_cols = st.columns(num_cats)
            for i, cat in enumerate(categories):
                icon      = CAT_ICONS.get(cat["name"], "📄")
                is_active = st.session_state.kb_category_filter == cat["id"]
                label     = f"{'✅ ' if is_active else ''}{icon} {cat['name']}"
                with cat_cols[i]:
                    if st.button(label, key=f"cat_{cat['id']}", use_container_width=True):
                        if is_active:
                            st.session_state.kb_category_filter = None
                        else:
                            st.session_state.kb_category_filter = cat["id"]
                            st.session_state.kb_search_query    = ""
                        st.rerun()

        # Search bar
        def _on_search_change():
            val = st.session_state.get("_kb_search_widget", "")
            st.session_state.kb_search_query    = val
            st.session_state.kb_category_filter = None

        st.text_input(
            "🔍 Search",
            value=st.session_state.kb_search_query,
            placeholder="Start typing — results appear after 3 characters...",
            key="_kb_search_widget",
            on_change=_on_search_change
        )
        search     = st.session_state.kb_search_query
        cat_filter = st.session_state.kb_category_filter

        st.markdown("<div style='margin-top:16px;'></div>", unsafe_allow_html=True)

        # ── Category filter results ───────────────────────────────────────
        if cat_filter:
            cat_name = next((c["name"] for c in categories if c["id"] == cat_filter), "")
            icon     = CAT_ICONS.get(cat_name, "📄")
            docs     = get_docs_by_category(cat_filter)
            st.markdown(
                f"<p style='font-size:13px;color:#7a90aa;margin-bottom:12px;'>"
                f"{icon} <b>{cat_name}</b> — <b>{len(docs)}</b> document{'s' if len(docs)!=1 else ''}</p>",
                unsafe_allow_html=True
            )
            if not docs:
                st.info(f"No documents in {cat_name} yet.")
            for doc in docs:
                render_doc_card(doc, "cat")

        # ── Keyword search results ────────────────────────────────────────
        elif search.strip() and len(search.strip()) >= 3:
            results = search_docs(search.strip())
            if not results:
                st.info(f"No results for \"{search}\". Try a different keyword.")
            else:
                st.markdown(
                    f"<p style='font-size:13px;color:#7a90aa;margin-bottom:12px;'>"
                    f"🔍 <b>{len(results)}</b> result{'s' if len(results)!=1 else ''} "
                    f"for <b>\"{search}\"</b></p>",
                    unsafe_allow_html=True
                )
                for doc in results:
                    render_doc_card(doc, "search")

        # ── Default: FAQ cards ────────────────────────────────────────────
        else:
            faq_docs = get_all_approved()[:6]
            if not faq_docs:
                st.info("No documents published yet.")
            else:
                st.markdown(
                    "<p style='font-family:DM Mono,monospace;font-size:9px;font-weight:500;"
                    "letter-spacing:3px;color:#9a9080;text-transform:uppercase;margin:0 0 14px 0;'>"
                    "Frequently Asked</p>",
                    unsafe_allow_html=True
                )
                # Wrap FAQ in a styled container
                st.markdown("""
                <div style='background:white;border:1px solid rgba(200,215,235,0.8);
                            border-radius:10px;overflow:hidden;
                            box-shadow:0 2px 8px rgba(0,0,0,0.04);'>
                </div>
                """, unsafe_allow_html=True)
                for i, doc in enumerate(faq_docs):
                    cat_name  = (doc.get("kb_categories") or {}).get("name", "—")
                    icon      = CAT_ICONS.get(cat_name, "📄")
                    question  = _doc_to_faq_question(doc)
                    is_last   = i == len(faq_docs) - 1
                    border_b  = "none" if is_last else "1px solid rgba(200,215,235,0.6)"
                    uid       = f"faq_{doc['id']}"
                    st.markdown(f"""
                    <style>
                    div[data-key="{uid}"] button {{
                        background: white !important;
                        border: none !important;
                        border-bottom: {border_b} !important;
                        border-radius: 0 !important;
                        padding: 14px 16px !important;
                        text-align: left !important;
                        white-space: normal !important;
                        height: auto !important;
                        line-height: 1.6 !important;
                        color: #0a1628 !important;
                        font-weight: 400 !important;
                        box-shadow: none !important;
                        transition: background 0.15s ease, border-left 0.15s ease !important;
                        margin: 0 !important;
                        width: 100% !important;
                        border-left: 3px solid transparent !important;
                    }}
                    div[data-key="{uid}"] button:hover {{
                        background: #f7faff !important;
                        border-left: 3px solid #FFD700 !important;
                        box-shadow: none !important;
                        transform: none !important;
                    }}
                    </style>
                    """, unsafe_allow_html=True)
                    label = f"**{question}**  \n*{icon} {cat_name}*"
                    if st.button(label, key=uid, use_container_width=True):
                        st.session_state.kb_selected_doc = doc["id"]
                        st.rerun()

                st.markdown(
                    "<p style='font-size:12px;color:#a0aec0;text-align:center;"
                    "margin-top:8px;'>Use search or category filters to browse all articles</p>",
                    unsafe_allow_html=True
                )

    with right_col:
        with st.container(border=True):
            render_recent_uploads_panel()



def page_submit_document(user):
    render_header("📤 Submit Document", "Your submission will be reviewed before being published")
    categories = get_categories()
    cat_map    = {cat["name"]: cat["id"] for cat in categories}
    with st.form("submit_form", clear_on_submit=True):
        title    = st.text_input("Document Title *", placeholder="e.g. How to Process IGT Allocation")
        category = st.selectbox("Category *", options=list(cat_map.keys()))
        content  = st.text_area("Process Steps / Content", height=250,
                                 placeholder="Write the steps here (optional if uploading a file)...")
        file     = st.file_uploader("Upload File — PDF or Word (.docx) · Text will be extracted inline", type=["pdf","docx"])
        notes    = st.text_area("Notes for Reviewer", height=100, placeholder="Any context the reviewer should know...")
        submit   = st.form_submit_button("📤 Submit for Review", use_container_width=True)
        if submit:
            if not title:
                st.error("Document title is required."); return
            if not content and not file:
                st.error("Please add content or upload a file."); return
            final_content = content or ""
            if file:
                with st.spinner("Extracting content from file..."):
                    extracted = extract_text_from_file(file)
                if extracted:
                    final_content = (final_content + "\n\n" + extracted).strip()
                    st.success("✅ File content extracted!")
            supabase.table("kb_documents").insert({
                "title": title, "category_id": cat_map[category],
                "content": final_content, "file_url": None, "file_name": None,
                "status": "pending", "submitted_by": user["id"],
                "notes": notes, "version": 1
            }).execute()
            st.success("✅ Submitted! An admin will review your document.")


def page_review_queue(user):
    render_header("📋 Review Queue")
    tab_pending, tab_approved, tab_rejected = st.tabs(["⏳ Pending Review","✅ Approved","❌ Rejected"])

    with tab_pending:
        docs = get_pending_docs()
        if not docs:
            st.success("All clear — no pending submissions.")
        for doc in docs:
            submitter_name = (doc.get("kb_users") or {}).get("name","Unknown")
            cat_name       = (doc.get("kb_categories") or {}).get("name","—")
            with st.container(border=True):
                st.markdown(f"#### {doc['title']}")
                st.caption(f"Category: {cat_name} · Submitted by: {submitter_name} · {doc['submitted_at'][:10]}")
                if doc.get("notes"):
                    st.info(f"📝 {doc['notes']}")
                if doc.get("content"):
                    with st.expander("View content"):
                        st.markdown(doc["content"])
                col1, col2, _ = st.columns([1,1,5])
                with col1:
                    if st.button("✅ Approve", key=f"app_{doc['id']}", type="primary"):
                        approve_doc(doc["id"], user["id"])
                        st.toast("Approved!", icon="✅"); st.rerun()
                with col2:
                    if st.button("❌ Reject", key=f"rej_{doc['id']}"):
                        reject_doc(doc["id"], user["id"])
                        st.toast("Rejected.", icon="❌"); st.rerun()

    with tab_approved:
        docs = get_all_docs_by_status("approved")
        if not docs:
            st.info("No approved documents yet.")
        for doc in docs:
            cat_name = (doc.get("kb_categories") or {}).get("name","—")
            with st.container(border=True):
                col1, col2, col3, col4 = st.columns([5,1,1,1])
                with col1:
                    st.markdown(f"**{doc['title']}**")
                    st.caption(f"Category: {cat_name} · v{doc['version']} · Approved: {(doc.get('reviewed_at') or '')[:10]}")
                with col2:
                    if st.button("✏️ Edit", key=f"edit_app_{doc['id']}"):
                        st.session_state["editing_doc"] = doc["id"]
                        st.rerun()
                with col3:
                    if st.button("🗑️ Unpublish", key=f"unpub_{doc['id']}"):
                        reject_doc(doc["id"], user["id"]); st.rerun()
                with col4:
                    if user["role"] == "super_admin":
                        if st.button("❌ Delete", key=f"del_app_{doc['id']}"):
                            delete_doc(doc["id"])
                            st.toast("Deleted.", icon="🗑️"); st.rerun()
                if st.session_state.get("editing_doc") == doc["id"]:
                    render_edit_form(doc, f"edit_form_app_{doc['id']}")

    with tab_rejected:
        docs = get_all_docs_by_status("rejected")
        if not docs:
            st.info("No rejected documents.")
        for doc in docs:
            cat_name = (doc.get("kb_categories") or {}).get("name","—")
            with st.container(border=True):
                col1, col2, col3, col4 = st.columns([5,1,1,1])
                with col1:
                    st.markdown(f"**{doc['title']}**")
                    st.caption(f"Category: {cat_name} · Rejected: {(doc.get('reviewed_at') or '')[:10]}")
                with col2:
                    if st.button("✏️ Edit", key=f"edit_rej_{doc['id']}"):
                        st.session_state["editing_doc"] = doc["id"]
                        st.rerun()
                with col3:
                    if st.button("↩️ Re-approve", key=f"reapp_{doc['id']}"):
                        approve_doc(doc["id"], user["id"]); st.rerun()
                with col4:
                    if user["role"] == "super_admin":
                        if st.button("❌ Delete", key=f"del_rej_{doc['id']}"):
                            delete_doc(doc["id"])
                            st.toast("Deleted.", icon="🗑️"); st.rerun()
                if st.session_state.get("editing_doc") == doc["id"]:
                    render_edit_form(doc, f"edit_form_rej_{doc['id']}")


def page_user_management(user):
    if user["role"] != "super_admin":
        st.error("⛔ Access restricted to Super Admin only."); return
    render_header("👥 User Management")

    # ── Category Management ───────────────────────────────────────────────
    with st.expander("🗂️ Manage Categories", expanded=False):
        cats = get_categories()
        if cats:
            st.markdown("**Existing Categories:**")
            for cat in cats:
                icon = CAT_ICONS.get(cat["name"], "📄")
                col1, col2 = st.columns([5, 1])
                with col1:
                    st.write(f"{icon} **{cat['name']}** — {cat['description']}")
                with col2:
                    if st.button("🗑️", key=f"del_cat_{cat['id']}", help="Delete category"):
                        supabase.table("kb_categories").delete().eq("id", cat["id"]).execute()
                        st.toast(f"Category '{cat['name']}' deleted.", icon="🗑️")
                        st.rerun()
        st.markdown("---")
        st.markdown("**Add New Category:**")
        with st.form("add_cat_form", clear_on_submit=True):
            col1, col2 = st.columns(2)
            with col1:
                new_cat_name = st.text_input("Category Name *", placeholder="e.g. Vendor Management")
            with col2:
                new_cat_desc = st.text_input("Description", placeholder="Short description of this category")
            new_cat_order = st.number_input("Display Order", min_value=1, max_value=20,
                                             value=len(cats)+1 if cats else 1)
            if st.form_submit_button("➕ Add Category", use_container_width=True):
                if not new_cat_name:
                    st.error("Category name is required.")
                else:
                    supabase.table("kb_categories").insert({
                        "name": new_cat_name,
                        "description": new_cat_desc,
                        "order_num": new_cat_order
                    }).execute()
                    st.success(f"✅ Category '{new_cat_name}' added!")
                    st.rerun()

    st.markdown("---")

    with st.expander("➕ Add New User", expanded=False):
        with st.form("add_user_form", clear_on_submit=True):
            col1, col2 = st.columns(2)
            with col1:
                name     = st.text_input("Full Name *")
                email    = st.text_input("Email *")
            with col2:
                role     = st.selectbox("Role", ["rta","admin","super_admin"])
                password = st.text_input("Initial Password *", type="password")
            if st.form_submit_button("Add User", use_container_width=True):
                if not name or not email or not password:
                    st.error("All fields are required.")
                else:
                    try:
                        supabase.table("kb_users").insert({
                            "name":name,"email":email.lower().strip(),
                            "password":hash_password(password),"role":role,"is_active":True
                        }).execute()
                        st.success(f"✅ {name} added!")
                    except Exception as e:
                        st.error(f"Error: {e}")

    st.markdown("---")
    st.subheader("Current Users")

    all_users  = supabase.table("kb_users").select("*").order("name").execute().data
    role_opts  = ["rta","admin","super_admin"]

    for u in all_users:
        with st.container(border=True):
            col1, col2, col3, col4, col5 = st.columns([3,3,2,2,1])
            with col1:
                st.markdown(f"**{u['name']}**")
                st.caption(u["email"])
            with col2:
                if u["id"] != user["id"]:
                    new_role = st.selectbox(
                        "Role", options=role_opts,
                        index=role_opts.index(u["role"]) if u["role"] in role_opts else 0,
                        key=f"role_{u['id']}", label_visibility="collapsed"
                    )
                    if new_role != u["role"]:
                        supabase.table("kb_users").update({"role":new_role}).eq("id",u["id"]).execute()
                        st.toast(f"Role updated to {new_role}!", icon="✅"); st.rerun()
                else:
                    st.caption("super_admin (you)")
            with col3:
                st.write("🟢 Active" if u["is_active"] else "🔴 Inactive")
            with col4:
                if u["id"] != user["id"]:
                    label = "Deactivate" if u["is_active"] else "Activate"
                    if st.button(label, key=f"toggle_{u['id']}"):
                        supabase.table("kb_users").update({"is_active":not u["is_active"]}).eq("id",u["id"]).execute()
                        st.rerun()
            with col5:
                if u["id"] != user["id"]:
                    if st.button("🗑️", key=f"del_user_{u['id']}", help="Delete user"):
                        supabase.table("kb_users").delete().eq("id",u["id"]).execute()
                        st.toast(f"{u['name']} deleted.", icon="🗑️"); st.rerun()


# ─────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────
def main():
    st.set_page_config(page_title="RTA Knowledge Base", page_icon="📚", layout="wide")
    inject_css()

    if "user" not in st.session_state:
        st.session_state.user = None
    if not st.session_state.user:
        page_login(); return

    user = st.session_state.user
    role = user["role"]

    with st.sidebar:
        st.markdown("""
        <style>
        @keyframes logoPulse { 0%,100%{box-shadow:0 4px 18px rgba(255,215,0,0.45)} 50%{box-shadow:0 6px 26px rgba(255,215,0,0.65)} }
        @keyframes subtitleShift { 0%,100%{color:rgba(255,215,0,0.65)} 50%{color:rgba(255,215,0,0.95)} }
        </style>
        <div style='text-align:center;padding:22px 0 12px'>
          <div style='display:inline-block;
                      background:linear-gradient(135deg,#FFD700 0%,#f5c400 60%,#e8b000 100%);
                      padding:8px 26px;border-radius:7px;animation:logoPulse 3s ease-in-out infinite;'>
            <span style='font-family:Arial Black,Impact,sans-serif;
                         font-size:28px;font-weight:900;color:#0a1220;letter-spacing:3px;line-height:1'>HERTZ</span>
          </div>
          <div style='font-size:9px;letter-spacing:3.5px;margin-top:10px;
                      text-transform:uppercase;font-weight:700;animation:subtitleShift 3s ease-in-out infinite;'>
            Powered by Callinsite
          </div>
        </div>
        """, unsafe_allow_html=True)
        st.markdown("---")
        st.markdown("### 🗂️ Knowledge Base")

        nav_options = ["📖 Knowledge Base","📤 Submit Document"]
        if role in ["admin","super_admin"]:
            nav_options += ["📋 Review Queue","👥 User Management"]

        page = st.radio("Navigation", nav_options, label_visibility="hidden")

        st.markdown("---")
        st.markdown(f"""
        <div style='padding:4px 0 8px 0;'>
            <div style='color:#c0d4ee;font-size:0.85rem;'>👤 <b>{user['name']}</b></div>
            <div style='color:rgba(255,215,0,0.6);font-size:0.72rem;margin-top:2px;
                        letter-spacing:1px;text-transform:uppercase;'>{role.replace('_',' ')}</div>
        </div>
        """, unsafe_allow_html=True)

        if role in ["admin","super_admin"]:
            pending_count = len(get_pending_docs())
            if pending_count > 0:
                st.warning(f"⏳ {pending_count} pending review")

        st.markdown("<br>", unsafe_allow_html=True)
        if st.button("🚪 Logout", use_container_width=True):
            for k in ["user","kb_search_query","kb_selected_doc","editing_doc","current_page"]:
                st.session_state.pop(k, None)
            st.rerun()

    # Reset KB state on page switch
    if "current_page" not in st.session_state:
        st.session_state.current_page = page
    if st.session_state.current_page != page:
        st.session_state.kb_selected_doc = None
        st.session_state.pop("editing_doc", None)
        st.session_state.current_page = page

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
