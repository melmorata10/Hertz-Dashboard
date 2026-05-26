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

            # Track numbering counters per abstract/num level
            num_counters = {}

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
                    text_lines.append("")
                    continue

                # Headings
                if "Heading 1" in style:
                    text_lines.append(f"## {rich}")
                    continue
                elif "Heading 2" in style:
                    text_lines.append(f"### {rich}")
                    continue
                elif "Heading 3" in style:
                    text_lines.append(f"#### {rich}")
                    continue

                # Numbered lists — detect via paragraph numPr XML
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
                    key = f"{num_id}_{ilvl}"
                    num_counters[key] = num_counters.get(key, 0) + 1
                    indent = "   " * ilvl
                    text_lines.append(f"{indent}{num_counters[key]}. {rich}")
                    continue

                # Bullet lists
                if "List" in style or style.startswith("List"):
                    indent = "   " * max(0, style.count("Bullet") - 1 + style.count("Number") - 1)
                    text_lines.append(f"- {rich}")
                    continue

                # Normal paragraph
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
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800;900&display=swap');
@keyframes sidebarFlow { 0%{background-position:0% 0%} 100%{background-position:0% 100%} }
@keyframes logoPulse { 0%,100%{box-shadow:0 4px 18px rgba(255,215,0,0.45)} 50%{box-shadow:0 6px 26px rgba(255,215,0,0.65)} }
@keyframes subtitleShift { 0%,100%{color:rgba(255,215,0,0.65)} 50%{color:rgba(255,215,0,0.95)} }
@keyframes fadeSlideIn { from{opacity:0;transform:translateY(14px)} to{opacity:1;transform:translateY(0)} }
@keyframes particleDrift { 0%{background-position:0 0} 100%{background-position:48px 48px} }
@keyframes livePulse { 0%,100%{box-shadow:0 0 0 0 rgba(74,222,128,0.55)} 50%{box-shadow:0 0 0 5px rgba(74,222,128,0)} }

html, body, .stApp {
    font-family: 'Inter', sans-serif !important;
    background: linear-gradient(135deg,#e6ecf5 0%,#eef2f8 50%,#e3edf6 100%) !important;
}
.stApp::before {
    content:''; position:fixed; inset:0;
    background-image:radial-gradient(circle,rgba(26,58,92,0.055) 1px,transparent 1px);
    background-size:28px 28px; animation:particleDrift 18s linear infinite;
    pointer-events:none; z-index:0;
}
section[data-testid="stSidebar"] {
    background:linear-gradient(180deg,#040c18 0%,#07111f 15%,#0a1628 35%,#112244 60%,#0f2d4a 80%,#07111f 100%) !important;
    background-size:100% 300% !important;
    animation:sidebarFlow 14s ease-in-out infinite alternate !important;
    border-right:2px solid rgba(255,215,0,0.45) !important;
    box-shadow:4px 0 36px rgba(0,0,0,0.5) !important;
}
[data-testid="stSidebarNav"] { padding:2px 10px 14px !important; }
[data-testid="stSidebarNav"]::before {
    content:"NAVIGATION"; display:block;
    font-size:9.5px; font-weight:800; letter-spacing:2.5px;
    color:rgba(255,215,0,0.55); padding:10px 6px 8px;
    text-transform:uppercase;
}
[data-testid="stSidebarNav"] a {
    display:flex !important; align-items:center !important;
    margin:4px 0 !important; padding:12px 14px 12px 18px !important;
    border-radius:10px !important; border:1px solid rgba(255,215,0,0.1) !important;
    background:rgba(255,255,255,0.04) !important; text-decoration:none !important;
    transition:all 0.22s ease !important; position:relative !important; overflow:hidden !important;
}
[data-testid="stSidebarNav"] a::before {
    content:''; position:absolute; left:0; top:15%; bottom:15%;
    width:3px; border-radius:0 3px 3px 0; background:rgba(255,215,0,0.25);
}
[data-testid="stSidebarNav"] a:hover {
    background:rgba(255,215,0,0.09) !important;
    border-color:rgba(255,215,0,0.32) !important;
    transform:translateX(5px) !important;
}
[data-testid="stSidebarNav"] a:hover::before { background:#FFD700; }
[data-testid="stSidebarNav"] a[aria-current="page"] {
    background:linear-gradient(90deg,rgba(255,215,0,0.13),rgba(255,215,0,0.06)) !important;
    border-color:rgba(255,215,0,0.42) !important;
}
[data-testid="stSidebarNav"] a[aria-current="page"]::before { background:#FFD700; }
[data-testid="stSidebarNav"] a li,
[data-testid="stSidebarNav"] a span,
[data-testid="stSidebarNav"] ul li span {
    color:#ccddf8 !important; font-weight:600 !important; font-size:13.5px !important;
}
[data-testid="stSidebarNav"] a[aria-current="page"] span {
    color:#FFD700 !important; text-shadow:0 0 14px rgba(255,215,0,0.45) !important;
}
[data-testid="stSidebarNav"] a[href*="Verint"],
[data-testid="stSidebarNav"] a[href*="verint"],
[data-testid="stSidebarNav"] a[href*="2_Verint"],
[data-testid="stSidebarNav"] a[href*="_2_Verint"] { display:none !important; }

section[data-testid="stSidebar"] label,
section[data-testid="stSidebar"] p,
section[data-testid="stSidebar"] span,
section[data-testid="stSidebar"] div,
section[data-testid="stSidebar"] small { color:#c0d4ee !important; }
section[data-testid="stSidebar"] hr { border-color:rgba(255,255,255,0.06) !important; }
section[data-testid="stSidebar"] .stMarkdown h3 {
    color:#FFD700 !important; font-size:10px !important; font-weight:800 !important;
    letter-spacing:2.2px !important; text-transform:uppercase !important;
    border-bottom:1px solid rgba(255,215,0,0.18); padding-bottom:6px; margin-bottom:10px;
}
section[data-testid="stSidebar"] .stRadio label {
    display:flex !important; align-items:center !important;
    padding:10px 14px 10px 18px !important; border-radius:10px !important;
    border:1px solid rgba(255,215,0,0.1) !important;
    background:rgba(255,255,255,0.04) !important;
    color:#ccddf8 !important; font-weight:600 !important; font-size:13.5px !important;
    cursor:pointer !important; transition:all 0.22s ease !important;
}
section[data-testid="stSidebar"] .stRadio label:hover {
    background:rgba(255,215,0,0.09) !important;
    border-color:rgba(255,215,0,0.32) !important;
    transform:translateX(5px) !important;
}
section[data-testid="stSidebar"] .stButton button {
    background:linear-gradient(135deg,#FFD700 0%,#f5c400 55%,#e8b000 100%) !important;
    color:#0a1628 !important; font-weight:800 !important;
    border:none !important; border-radius:10px !important;
    width:100% !important; transition:all 0.25s ease !important;
    box-shadow:0 3px 14px rgba(255,215,0,0.38) !important;
}
section[data-testid="stSidebar"] .stButton button:hover {
    transform:translateY(-2px) !important;
    box-shadow:0 7px 22px rgba(255,215,0,0.52) !important;
}
[data-testid="stMainBlockContainer"] { animation:fadeSlideIn 0.4s ease both; }
[data-testid="stVerticalBlockBorderWrapper"] {
    background:white !important; border:1px solid rgba(200,215,235,0.8) !important;
    border-radius:12px !important; box-shadow:0 2px 12px rgba(0,0,0,0.05) !important;
}
details { border:1px solid rgba(200,215,235,0.8) !important; border-radius:12px !important; overflow:hidden; background:white !important; }
details[open] summary { border-bottom:1px solid rgba(200,215,235,0.7); }
summary {
    background:linear-gradient(90deg,#edf3fb 0%,#f5f9fd 100%) !important;
    font-weight:700 !important; color:#1a3a5c !important;
    padding:14px 18px !important; border-radius:12px !important;
}
[data-testid="stTextInput"] input,
[data-testid="stTextArea"] textarea {
    background:white !important; border:1px solid rgba(200,215,235,0.9) !important;
    border-radius:8px !important; color:#0a1628 !important;
}
[data-testid="stTextInput"] input:focus,
[data-testid="stTextArea"] textarea:focus {
    border-color:#FFD700 !important; box-shadow:0 0 0 2px rgba(255,215,0,0.15) !important;
}
[data-testid="stFormSubmitButton"] button, button[kind="primary"] {
    background:linear-gradient(135deg,#FFD700 0%,#f5c400 55%,#e8b000 100%) !important;
    color:#0a1628 !important; font-weight:800 !important;
    border:none !important; border-radius:10px !important;
    box-shadow:0 3px 14px rgba(255,215,0,0.38) !important; transition:all 0.25s ease !important;
}
.stTabs [data-baseweb="tab-list"] { background:transparent; border-bottom:2px solid rgba(200,215,235,0.85); gap:4px; padding:0; }
.stTabs [data-baseweb="tab"] { color:#7a90aa !important; font-weight:600 !important; font-size:14px !important; padding:11px 26px !important; border-radius:10px 10px 0 0 !important; background:transparent !important; transition:all 0.2s ease !important; }
.stTabs [aria-selected="true"] { background:white !important; color:#0a1628 !important; font-weight:700 !important; border-bottom-color:white !important; margin-bottom:-2px !important; box-shadow:inset 0 -3px 0 #FFD700 !important; }
.stTabs [data-baseweb="tab-panel"] { background:white; border:1px solid rgba(200,215,235,0.8); border-top:none; border-radius:0 10px 10px 10px; padding:28px; box-shadow:0 8px 36px rgba(0,0,0,0.07); }
.stAlert { border-radius:10px !important; }
hr { border:none !important; height:1px !important; background:linear-gradient(90deg,transparent,#bfcfe4,transparent) !important; margin:22px 0 !important; }
h3 { color:#0a1628 !important; font-weight:800 !important; }
h4 { color:#1a3a5c !important; font-weight:700 !important; border-left:3px solid #FFD700; padding-left:12px; }
.stCaption { color:#8099b8 !important; font-size:12px !important; }
.search-result-card { background:white; border:1px solid rgba(200,215,235,0.8); border-left:4px solid #FFD700; border-radius:10px; padding:14px 18px; margin-bottom:10px; box-shadow:0 2px 8px rgba(0,0,0,0.04); }
.search-result-title { font-size:15px; font-weight:700; color:#0a1628; margin-bottom:4px; }
.search-result-meta { font-size:12px; color:#8099b8; }
.category-chip { display:inline-block; background:rgba(255,215,0,0.12); border:1px solid rgba(255,215,0,0.3); border-radius:20px; padding:3px 12px; font-size:11px; font-weight:700; color:#7a5c00; margin-right:6px; }
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
    r1 = supabase.table("kb_documents").select("*, kb_categories(name), kb_users!kb_documents_submitted_by_fkey(name)").eq("status","approved").ilike("title",f"%{query}%").order("reviewed_at",desc=True).execute().data
    r2 = supabase.table("kb_documents").select("*, kb_categories(name), kb_users!kb_documents_submitted_by_fkey(name)").eq("status","approved").ilike("content",f"%{query}%").order("reviewed_at",desc=True).execute().data
    seen = set(); merged = []
    for doc in r1 + r2:
        if doc["id"] not in seen:
            seen.add(doc["id"]); merged.append(doc)
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
    sub = f"<p style='font-size:13px;color:rgba(255,255,255,0.55);margin:4px 0 0 0;'>{subtitle}</p>" if subtitle else ""
    st.markdown(
        f"<div style='background:#0a1628;padding:22px 36px;border-radius:16px;"
        f"margin-bottom:24px;border-bottom:3px solid #FFD700;"
        f"box-shadow:0 8px 36px rgba(6,16,34,0.38);'>"
        f"<p style='font-size:10px;color:#FFD700;font-weight:800;"
        f"letter-spacing:2.8px;text-transform:uppercase;margin:0 0 6px 0;'>"
        f"HERTZ &middot; POWERED BY CALLINSITE</p>"
        f"<p style='font-size:26px;font-weight:900;color:white;margin:0;line-height:1.2;'>{title}</p>"
        f"{sub}</div>",
        unsafe_allow_html=True
    )

def render_doc_card(doc, btn_key_prefix):
    cat_name = (doc.get("kb_categories") or {}).get("name","—")
    icon     = CAT_ICONS.get(cat_name,"📄")
    reviewed = (doc.get("reviewed_at") or "")[:10] or "—"
    preview  = (doc.get("content") or "")[:120].replace("\n"," ")
    if preview: preview += "..."
    col1, col2 = st.columns([10,1])
    with col1:
        st.markdown(
            f"<div class='search-result-card'>"
            f"<div class='search-result-title'>{doc['title']}</div>"
            f"<div class='search-result-meta'>"
            f"<span class='category-chip'>{icon} {cat_name}</span>"
            f"Last updated: {reviewed}"
            + (f"<br><span style='color:#a0aec0;font-style:italic;font-size:11px;'>{preview}</span>" if preview else "")
            + "</div></div>",
            unsafe_allow_html=True
        )
    with col2:
        st.markdown("<div style='padding-top:8px'></div>", unsafe_allow_html=True)
        if st.button("Read →", key=f"{btn_key_prefix}_{doc['id']}", use_container_width=True):
            st.session_state.kb_selected_doc = doc["id"]
            st.rerun()

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
    if doc.get("content"):
        with st.container(border=True):
            st.markdown(doc["content"])
    else:
        st.info("No content available for this document.")

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
    <div style="max-width:420px;margin:80px auto 0 auto;padding:40px;
                background:white;border:1px solid rgba(200,215,235,0.9);
                border-radius:16px;box-shadow:0 8px 36px rgba(0,0,0,0.1);">
        <div style="text-align:center;margin-bottom:32px;">
            <div style="background:linear-gradient(135deg,#FFD700 0%,#f5c400 60%,#e8b000 100%);
                        display:inline-block;padding:8px 26px;border-radius:7px;
                        box-shadow:0 4px 18px rgba(255,215,0,0.45);">
                <span style="font-family:Arial Black,Impact,sans-serif;
                             font-size:24px;font-weight:900;color:#0a1220;letter-spacing:3px;">HERTZ</span>
            </div>
            <div style="font-size:9px;letter-spacing:3.5px;margin-top:10px;
                        text-transform:uppercase;font-weight:700;color:#7a90aa;">
                Powered by Callinsite
            </div>
            <h2 style="color:#0a1628;margin-top:20px;font-size:1.3rem;font-weight:700;">RTA Knowledge Base</h2>
            <p style="color:#7a90aa;font-size:0.85rem;margin-top:4px;">Sign in to access process guides</p>
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


def page_knowledge_base():
    render_header("📚 RTA Knowledge Base", "Search for processes, reports, and tool guides")

    if "kb_search_query"    not in st.session_state:
        st.session_state.kb_search_query    = ""
    if "kb_selected_doc"    not in st.session_state:
        st.session_state.kb_selected_doc    = None
    if "kb_category_filter" not in st.session_state:
        st.session_state.kb_category_filter = None

    if st.session_state.kb_selected_doc:
        doc = get_doc_by_id(st.session_state.kb_selected_doc)
        if doc:
            render_doc_detail(doc, user=st.session_state.get("user"))
        else:
            st.session_state.kb_selected_doc = None
            st.rerun()
        return

    # Category chips
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
    search = st.text_input(
        "🔍 Search",
        value=st.session_state.kb_search_query,
        placeholder="Type to search... e.g. Chat, Allocation, EOD"
    )
    if search != st.session_state.kb_search_query:
        st.session_state.kb_search_query    = search
        st.session_state.kb_category_filter = None
        st.rerun()

    st.markdown("<br>", unsafe_allow_html=True)
    cat_filter = st.session_state.kb_category_filter

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

    elif search.strip():
        results = search_docs(search.strip())
        if not results:
            st.info(f"No results found for '{search}'. Try a different keyword.")
        else:
            st.markdown(
                f"<p style='font-size:13px;color:#7a90aa;margin-bottom:12px;'>"
                f"🔍 <b>{len(results)}</b> result{'s' if len(results)!=1 else ''} "
                f"for <b>\"{search}\"</b> \u2014 click to read</p>",
                unsafe_allow_html=True
            )
            for doc in results:
                render_doc_card(doc, "search")
    else:
        docs = get_all_approved()
        if not docs:
            st.info("No documents published yet.")
        else:
            st.markdown(
                f"<p style='font-size:13px;color:#7a90aa;margin-bottom:12px;'>"
                f"📋 <b>{len(docs)}</b> document{'s' if len(docs)!=1 else ''} — sorted latest first</p>",
                unsafe_allow_html=True
            )
            for doc in docs:
                render_doc_card(doc, "all")

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
