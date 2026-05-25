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
# THEME — matches Hertz Dashboard
# ─────────────────────────────────────────
DARK_BG       = "#0a0e1a"
NAVY          = "#0d1b2e"
NAVY_CARD     = "#112240"
NAVY_BORDER   = "#1e3a5f"
YELLOW        = "#FFD700"
YELLOW_HOVER  = "#FFC200"
TEXT_PRIMARY  = "#FFFFFF"
TEXT_SECONDARY= "#a0aec0"
TEXT_MUTED    = "#718096"
SUCCESS       = "#00d4aa"
WARNING       = "#FFD700"
DANGER        = "#ff6b6b"
PENDING       = "#f6ad55"

def inject_css():
    st.markdown(f"""
    <style>
    /* ── Global background ── */
    html, body, [data-testid="stApp"] {{
        background-color: {DARK_BG} !important;
        color: {TEXT_PRIMARY} !important;
    }}

    /* ── Sidebar ── */
    [data-testid="stSidebar"] {{
        background-color: {NAVY} !important;
        border-right: 1px solid {NAVY_BORDER} !important;
    }}
    [data-testid="stSidebar"] * {{
        color: {TEXT_PRIMARY} !important;
    }}
    [data-testid="stSidebar"] .stRadio label {{
        color: {TEXT_SECONDARY} !important;
        font-size: 0.9rem;
    }}

    /* ── Main content area ── */
    [data-testid="stMainBlockContainer"] {{
        background-color: {DARK_BG} !important;
    }}

    /* ── Cards / containers ── */
    [data-testid="stVerticalBlockBorderWrapper"] {{
        background-color: {NAVY_CARD} !important;
        border: 1px solid {NAVY_BORDER} !important;
        border-radius: 8px !important;
    }}

    /* ── Expanders ── */
    [data-testid="stExpander"] {{
        background-color: {NAVY_CARD} !important;
        border: 1px solid {NAVY_BORDER} !important;
        border-radius: 8px !important;
    }}
    [data-testid="stExpander"] summary {{
        color: {TEXT_PRIMARY} !important;
    }}

    /* ── Inputs ── */
    [data-testid="stTextInput"] input,
    [data-testid="stTextArea"] textarea,
    [data-testid="stSelectbox"] div {{
        background-color: {NAVY} !important;
        color: {TEXT_PRIMARY} !important;
        border: 1px solid {NAVY_BORDER} !important;
        border-radius: 6px !important;
    }}

    /* ── Primary buttons → Yellow ── */
    [data-testid="stFormSubmitButton"] button,
    button[kind="primary"] {{
        background-color: {YELLOW} !important;
        color: #000000 !important;
        border: none !important;
        font-weight: 700 !important;
        border-radius: 6px !important;
    }}
    [data-testid="stFormSubmitButton"] button:hover,
    button[kind="primary"]:hover {{
        background-color: {YELLOW_HOVER} !important;
    }}

    /* ── Secondary buttons ── */
    button[kind="secondary"] {{
        background-color: transparent !important;
        color: {YELLOW} !important;
        border: 1px solid {YELLOW} !important;
        border-radius: 6px !important;
        font-weight: 600 !important;
    }}

    /* ── Tabs ── */
    [data-testid="stTabs"] button {{
        color: {TEXT_SECONDARY} !important;
        background-color: transparent !important;
        border-bottom: 2px solid transparent !important;
    }}
    [data-testid="stTabs"] button[aria-selected="true"] {{
        color: {YELLOW} !important;
        border-bottom: 2px solid {YELLOW} !important;
    }}

    /* ── Dividers ── */
    hr {{
        border-color: {NAVY_BORDER} !important;
    }}

    /* ── Text ── */
    p, li, span, label {{
        color: {TEXT_PRIMARY} !important;
    }}
    .stCaption, [data-testid="stCaptionContainer"] {{
        color: {TEXT_MUTED} !important;
    }}

    /* ── Info / warning / success boxes ── */
    [data-testid="stAlert"] {{
        background-color: {NAVY_CARD} !important;
        border-radius: 6px !important;
    }}

    /* ── Logout button ── */
    .logout-btn button {{
        background-color: transparent !important;
        color: {DANGER} !important;
        border: 1px solid {DANGER} !important;
        width: 100% !important;
    }}

    /* ── Scrollbar ── */
    ::-webkit-scrollbar {{ width: 6px; }}
    ::-webkit-scrollbar-track {{ background: {NAVY}; }}
    ::-webkit-scrollbar-thumb {{ background: {NAVY_BORDER}; border-radius: 3px; }}
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
    st.markdown(f"""
    <div style="max-width:420px; margin:80px auto 0 auto; padding:40px;
                background:{NAVY_CARD}; border:1px solid {NAVY_BORDER};
                border-radius:12px; box-shadow:0 8px 32px rgba(0,0,0,0.4);">
        <div style="text-align:center; margin-bottom:32px;">
            <div style="background:{YELLOW}; display:inline-block;
                        padding:8px 24px; border-radius:4px; margin-bottom:12px;">
                <span style="color:#000; font-weight:900; font-size:1.4rem;
                             letter-spacing:2px;">HERTZ</span>
            </div>
            <div style="color:{TEXT_MUTED}; font-size:0.75rem;
                        letter-spacing:1px; margin-top:4px;">
                POWERED BY CALLINSITE
            </div>
            <h2 style="color:{TEXT_PRIMARY}; margin-top:20px;
                       font-size:1.3rem; font-weight:600;">
                RTA Knowledge Base
            </h2>
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
                    with st.spinner("Logging in..."):
                        user = login(email, password)
                    if user:
                        st.session_state.user = user
                        st.rerun()
                    else:
                        st.error("Invalid credentials. Please try again.")


def page_knowledge_base():
    # Header banner — matches dashboard style
    st.markdown(f"""
    <div style="background: linear-gradient(135deg, {NAVY} 0%, #0d2137 100%);
                border: 1px solid {NAVY_BORDER}; border-left: 4px solid {YELLOW};
                border-radius: 8px; padding: 20px 28px; margin-bottom: 24px;">
        <div style="color:{YELLOW}; font-size:0.7rem; font-weight:600;
                    letter-spacing:2px; margin-bottom:6px;">
            HERTZ · POWERED BY CALLINSITE
        </div>
        <div style="color:{TEXT_PRIMARY}; font-size:1.5rem; font-weight:700;">
            📚 RTA Knowledge Base
        </div>
        <div style="color:{TEXT_SECONDARY}; font-size:0.85rem; margin-top:4px;">
            Browse approved processes, reports, and tool guides
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
                st.markdown(
                    f"<p style='color:{TEXT_MUTED}; font-size:0.85rem;'>"
                    f"No documents in this category yet.</p>",
                    unsafe_allow_html=True
                )
                continue
            for doc in docs:
                with st.container(border=True):
                    col1, col2 = st.columns([5, 1])
                    with col1:
                        st.markdown(
                            f"<h4 style='color:{YELLOW}; margin:0 0 4px 0;'>"
                            f"{doc['title']}</h4>",
                            unsafe_allow_html=True
                        )
                        submitter = doc.get("kb_users") or {}
                        submitter_name = submitter.get("name", "Unknown")
                        reviewed = (doc.get("reviewed_at") or "")[:10] or "—"
                        st.markdown(
                            f"<span style='color:{TEXT_MUTED}; font-size:0.78rem;'>"
                            f"Version {doc['version']}  ·  Last updated: {reviewed}"
                            f"  ·  Submitted by: {submitter_name}</span>",
                            unsafe_allow_html=True
                        )
                    with col2:
                        if doc.get("file_url"):
                            st.link_button("📄 Open File", doc["file_url"],
                                           use_container_width=True)
                    if doc.get("content"):
                        st.markdown(doc["content"])


def page_submit_document(user):
    st.markdown(f"""
    <div style="background: linear-gradient(135deg, {NAVY} 0%, #0d2137 100%);
                border: 1px solid {NAVY_BORDER}; border-left: 4px solid {YELLOW};
                border-radius: 8px; padding: 20px 28px; margin-bottom: 24px;">
        <div style="color:{YELLOW}; font-size:0.7rem; font-weight:600;
                    letter-spacing:2px; margin-bottom:6px;">
            HERTZ · POWERED BY CALLINSITE
        </div>
        <div style="color:{TEXT_PRIMARY}; font-size:1.5rem; font-weight:700;">
            📤 Submit Document
        </div>
        <div style="color:{TEXT_SECONDARY}; font-size:0.85rem; margin-top:4px;">
            Your submission will be reviewed by an admin before being published
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
    st.markdown(f"""
    <div style="background: linear-gradient(135deg, {NAVY} 0%, #0d2137 100%);
                border: 1px solid {NAVY_BORDER}; border-left: 4px solid {YELLOW};
                border-radius: 8px; padding: 20px 28px; margin-bottom: 24px;">
        <div style="color:{YELLOW}; font-size:0.7rem; font-weight:600;
                    letter-spacing:2px; margin-bottom:6px;">
            HERTZ · POWERED BY CALLINSITE
        </div>
        <div style="color:{TEXT_PRIMARY}; font-size:1.5rem; font-weight:700;">
            📋 Review Queue
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
            submitter = (doc.get("kb_users") or {})
            submitter_name = submitter.get("name", "Unknown")
            cat_name = (doc.get("kb_categories") or {}).get("name", "—")
            with st.container(border=True):
                st.markdown(
                    f"<h4 style='color:{YELLOW}; margin:0 0 4px 0;'>"
                    f"{doc['title']}</h4>",
                    unsafe_allow_html=True
                )
                st.markdown(
                    f"<span style='color:{TEXT_MUTED}; font-size:0.78rem;'>"
                    f"Category: {cat_name}  ·  Submitted by: {submitter_name}"
                    f"  ·  {doc['submitted_at'][:10]}</span>",
                    unsafe_allow_html=True
                )
                if doc.get("notes"):
                    st.info(f"📝 {doc['notes']}")
                if doc.get("content"):
                    with st.expander("View content"):
                        st.markdown(doc["content"])
                if doc.get("file_url"):
                    st.link_button("📄 View File", doc["file_url"])
                col1, col2, col3 = st.columns([1, 1, 5])
                with col1:
                    if st.button("✅ Approve", key=f"app_{doc['id']}",
                                  type="primary"):
                        approve_doc(doc["id"], user["id"])
                        st.toast("Approved and published!", icon="✅")
                        st.rerun()
                with col2:
                    if st.button("❌ Reject", key=f"rej_{doc['id']}"):
                        reject_doc(doc["id"], user["id"])
                        st.toast("Document rejected.", icon="❌")
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
                    st.markdown(
                        f"<b style='color:{TEXT_PRIMARY};'>{doc['title']}</b>",
                        unsafe_allow_html=True
                    )
                    st.markdown(
                        f"<span style='color:{TEXT_MUTED}; font-size:0.78rem;'>"
                        f"Category: {cat_name}  ·  v{doc['version']}"
                        f"  ·  Approved: {(doc.get('reviewed_at') or '')[:10]}</span>",
                        unsafe_allow_html=True
                    )
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
                    st.markdown(
                        f"<b style='color:{TEXT_PRIMARY};'>{doc['title']}</b>",
                        unsafe_allow_html=True
                    )
                    st.markdown(
                        f"<span style='color:{TEXT_MUTED}; font-size:0.78rem;'>"
                        f"Category: {cat_name}"
                        f"  ·  Rejected: {(doc.get('reviewed_at') or '')[:10]}</span>",
                        unsafe_allow_html=True
                    )
                with col2:
                    if st.button("↩️ Re-approve", key=f"reapp_{doc['id']}"):
                        approve_doc(doc["id"], user["id"])
                        st.rerun()


def page_user_management(user):
    if user["role"] != "super_admin":
        st.error("⛔ Access restricted to Super Admin only.")
        return

    st.markdown(f"""
    <div style="background: linear-gradient(135deg, {NAVY} 0%, #0d2137 100%);
                border: 1px solid {NAVY_BORDER}; border-left: 4px solid {YELLOW};
                border-radius: 8px; padding: 20px 28px; margin-bottom: 24px;">
        <div style="color:{YELLOW}; font-size:0.7rem; font-weight:600;
                    letter-spacing:2px; margin-bottom:6px;">
            HERTZ · POWERED BY CALLINSITE
        </div>
        <div style="color:{TEXT_PRIMARY}; font-size:1.5rem; font-weight:700;">
            👥 User Management
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
            add = st.form_submit_button("Add User", use_container_width=True)
            if add:
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
                        st.success(f"✅ User **{name}** added!")
                    except Exception as e:
                        st.error(f"Error: {e}")

    st.markdown("<br>", unsafe_allow_html=True)
    st.markdown(
        f"<h4 style='color:{TEXT_PRIMARY};'>Current Users</h4>",
        unsafe_allow_html=True
    )

    role_badge = {
        "rta":         f"<span style='background:#1e3a5f;color:{YELLOW};padding:2px 8px;border-radius:4px;font-size:0.75rem;'>RTA</span>",
        "admin":       f"<span style='background:#1e3a5f;color:{SUCCESS};padding:2px 8px;border-radius:4px;font-size:0.75rem;'>ADMIN</span>",
        "super_admin": f"<span style='background:#1e3a5f;color:{DANGER};padding:2px 8px;border-radius:4px;font-size:0.75rem;'>SUPER ADMIN</span>"
    }

    all_users = supabase.table("kb_users").select("*").order("name").execute().data
    for u in all_users:
        with st.container(border=True):
            col1, col2, col3, col4 = st.columns([3, 3, 2, 2])
            with col1:
                st.markdown(
                    f"<b style='color:{TEXT_PRIMARY};'>{u['name']}</b>",
                    unsafe_allow_html=True
                )
            with col2:
                st.markdown(
                    f"<span style='color:{TEXT_MUTED};font-size:0.85rem;'>"
                    f"{u['email']}</span>",
                    unsafe_allow_html=True
                )
            with col3:
                st.markdown(role_badge.get(u["role"], u["role"]),
                            unsafe_allow_html=True)
            with col4:
                if u["id"] != user["id"]:
                    label = "Deactivate" if u["is_active"] else "Activate"
                    if st.button(label, key=f"toggle_{u['id']}"):
                        supabase.table("kb_users").update(
                            {"is_active": not u["is_active"]}
                        ).eq("id", u["id"]).execute()
                        st.rerun()
                else:
                    st.markdown(
                        f"<span style='color:{SUCCESS};'>🟢 You</span>",
                        unsafe_allow_html=True
                    )


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
        # Hertz logo block
        st.markdown(f"""
        <div style="text-align:center; padding: 16px 0 8px 0;">
            <div style="background:{YELLOW}; display:inline-block;
                        padding:6px 20px; border-radius:4px;">
                <span style="color:#000; font-weight:900; font-size:1.2rem;
                             letter-spacing:2px;">HERTZ</span>
            </div>
            <div style="color:{TEXT_MUTED}; font-size:0.65rem;
                        letter-spacing:1px; margin-top:4px;">
                POWERED BY CALLINSITE
            </div>
        </div>
        <hr style="border-color:{NAVY_BORDER}; margin:12px 0;">
        <div style="color:{TEXT_MUTED}; font-size:0.7rem;
                    letter-spacing:1px; margin-bottom:8px;">NAVIGATION</div>
        """, unsafe_allow_html=True)

        nav_options = ["📖 Knowledge Base"]
        if role in ["admin", "super_admin"]:
            nav_options += ["📋 Review Queue", "👥 User Management"]
        else:
            nav_options.append("📤 Submit Document")

        page = st.radio("nav", nav_options, label_visibility="collapsed")

        st.markdown(f"<hr style='border-color:{NAVY_BORDER};'>",
                    unsafe_allow_html=True)

        # User info
        st.markdown(f"""
        <div style="padding:8px 0;">
            <div style="color:{TEXT_SECONDARY}; font-size:0.85rem;">
                👤 <b>{user['name']}</b>
            </div>
            <div style="color:{TEXT_MUTED}; font-size:0.75rem; margin-top:2px;">
                {role.upper().replace('_', ' ')}
            </div>
        </div>
        """, unsafe_allow_html=True)

        # Pending badge
        if role in ["admin", "super_admin"]:
            pending_count = len(get_pending_docs())
            if pending_count > 0:
                st.markdown(f"""
                <div style="background:#2d1f00; border:1px solid {PENDING};
                            border-radius:6px; padding:8px 12px; margin:8px 0;
                            color:{PENDING}; font-size:0.8rem;">
                    ⏳ {pending_count} pending review
                </div>
                """, unsafe_allow_html=True)

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
