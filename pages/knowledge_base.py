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
# HELPERS
# ─────────────────────────────────────────
def hash_password(password: str) -> str:
    return hashlib.sha1(password.encode()).hexdigest()

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

def upload_file(file) -> str | None:
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
    st.markdown("<h1 style='text-align:center'>📚 RTA Knowledge Base</h1>", unsafe_allow_html=True)
    st.markdown("<p style='text-align:center; color:gray'>Insite PH — Hertz WFM</p>", unsafe_allow_html=True)
    st.divider()

    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        with st.form("login_form"):
            st.subheader("Login")
            email = st.text_input("Email", placeholder="yourname@callinsite.com")
            password = st.text_input("Password", type="password")
            submit = st.form_submit_button("Login", use_container_width=True)

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
    st.title("📚 Knowledge Base")
    st.caption("Browse approved processes, reports, and tool guides.")
    st.divider()

    categories = get_categories()
    if not categories:
        st.info("No content available yet. Check back after an admin approves submissions.")
        return

    search = st.text_input("🔍 Search", placeholder="Search by title...")

    for cat in categories:
        docs = get_approved_docs(category_id=cat["id"], search=search if search else None)

        with st.expander(f"**{cat['name']}**  —  _{cat['description']}_", expanded=True):
            if not docs:
                st.caption("No documents in this category yet.")
                continue

            for doc in docs:
                with st.container(border=True):
                    col1, col2 = st.columns([5, 1])
                    with col1:
                        st.markdown(f"### {doc['title']}")
                        submitter = doc.get("kb_users", {})
                        submitter_name = submitter.get("name", "Unknown") if submitter else "Unknown"
                        reviewed = doc.get("reviewed_at", "")[:10] if doc.get("reviewed_at") else "—"
                        st.caption(f"Version {doc['version']}  |  Last updated: {reviewed}  |  Submitted by: {submitter_name}")
                    with col2:
                        if doc.get("file_url"):
                            st.link_button("📄 Open File", doc["file_url"], use_container_width=True)

                    if doc.get("content"):
                        st.markdown(doc["content"])


def page_submit_document(user):
    st.title("📤 Submit Document")
    st.info("Your submission will be reviewed by an admin before being published to the team.")

    categories = get_categories()
    cat_map = {cat["name"]: cat["id"] for cat in categories}

    with st.form("submit_form", clear_on_submit=True):
        title = st.text_input("Document Title *", placeholder="e.g. How to Process IGT Allocation")
        category = st.selectbox("Category *", options=list(cat_map.keys()))
        content = st.text_area(
            "Process Steps / Content",
            height=250,
            placeholder="Write the steps here (optional if uploading a file)..."
        )
        file = st.file_uploader("Upload File (PDF or Word .docx)", type=["pdf", "docx"])
        notes = st.text_area("Notes for Reviewer", height=100,
                              placeholder="Any context the reviewer should know...")
        submit = st.form_submit_button("📤 Submit for Review", use_container_width=True)

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
                "title": title,
                "category_id": cat_map[category],
                "content": content,
                "file_url": file_url,
                "file_name": file_name,
                "status": "pending",
                "submitted_by": user["id"],
                "notes": notes,
                "version": 1
            }).execute()

            st.success("✅ Submitted successfully! An admin will review your document.")


def page_review_queue(user):
    st.title("📋 Review Queue")

    tab_pending, tab_approved, tab_rejected = st.tabs([
        "⏳ Pending Review",
        "✅ Approved",
        "❌ Rejected"
    ])

    with tab_pending:
        docs = get_pending_docs()
        if not docs:
            st.success("All clear — no pending submissions.")
        for doc in docs:
            with st.container(border=True):
                submitter = doc.get("kb_users", {})
                submitter_name = submitter.get("name", "Unknown") if submitter else "Unknown"
                cat = doc.get("kb_categories", {})
                cat_name = cat.get("name", "Unknown") if cat else "Unknown"

                st.markdown(f"### {doc['title']}")
                st.caption(f"Category: **{cat_name}**  |  Submitted by: **{submitter_name}**  |  {doc['submitted_at'][:10]}")

                if doc.get("notes"):
                    st.info(f"📝 Submitter notes: {doc['notes']}")
                if doc.get("content"):
                    with st.expander("View content"):
                        st.markdown(doc["content"])
                if doc.get("file_url"):
                    st.link_button("📄 View Uploaded File", doc["file_url"])

                col1, col2, col3 = st.columns([1, 1, 5])
                with col1:
                    if st.button("✅ Approve", key=f"app_{doc['id']}", type="primary"):
                        approve_doc(doc["id"], user["id"])
                        st.toast("Document approved and published!", icon="✅")
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
            cat = doc.get("kb_categories", {})
            cat_name = cat.get("name", "—") if cat else "—"
            with st.container(border=True):
                col1, col2 = st.columns([4, 1])
                with col1:
                    st.markdown(f"**{doc['title']}**")
                    st.caption(f"Category: {cat_name}  |  v{doc['version']}  |  Approved: {doc.get('reviewed_at', '')[:10]}")
                with col2:
                    if st.button("🗑️ Unpublish", key=f"unpub_{doc['id']}"):
                        reject_doc(doc["id"], user["id"])
                        st.rerun()

    with tab_rejected:
        docs = get_all_docs_by_status("rejected")
        if not docs:
            st.info("No rejected documents.")
        for doc in docs:
            cat = doc.get("kb_categories", {})
            cat_name = cat.get("name", "—") if cat else "—"
            with st.container(border=True):
                col1, col2 = st.columns([4, 1])
                with col1:
                    st.markdown(f"**{doc['title']}**")
                    st.caption(f"Category: {cat_name}  |  Rejected: {doc.get('reviewed_at', '')[:10]}")
                with col2:
                    if st.button("↩️ Re-approve", key=f"reapp_{doc['id']}"):
                        approve_doc(doc["id"], user["id"])
                        st.rerun()


def page_user_management(user):
    if user["role"] != "super_admin":
        st.error("⛔ Access restricted to Super Admin only.")
        return

    st.title("👥 User Management")

    with st.expander("➕ Add New User", expanded=False):
        with st.form("add_user_form", clear_on_submit=True):
            col1, col2 = st.columns(2)
            with col1:
                name = st.text_input("Full Name *")
                email = st.text_input("Email *")
            with col2:
                role = st.selectbox("Role", ["rta", "admin", "super_admin"],
                                    help="RTA = submit only | Admin = review & approve | Super Admin = full access")
                password = st.text_input("Initial Password *", type="password")

            add = st.form_submit_button("Add User", use_container_width=True)
            if add:
                if not name or not email or not password:
                    st.error("All fields are required.")
                else:
                    try:
                        supabase.table("kb_users").insert({
                            "name": name,
                            "email": email.lower().strip(),
                            "password": hash_password(password),
                            "role": role,
                            "is_active": True
                        }).execute()
                        st.success(f"✅ User **{name}** added successfully!")
                    except Exception as e:
                        st.error(f"Error: {e}")

    st.divider()
    st.subheader("Current Users")

    all_users = supabase.table("kb_users").select("*").order("name").execute().data

    role_badge = {"rta": "🟦 RTA", "admin": "🟧 Admin", "super_admin": "🟥 Super Admin"}

    for u in all_users:
        with st.container(border=True):
            col1, col2, col3, col4 = st.columns([3, 3, 2, 2])
            with col1:
                st.write(f"**{u['name']}**")
            with col2:
                st.write(u["email"])
            with col3:
                st.write(role_badge.get(u["role"], u["role"]))
            with col4:
                status_label = "🟢 Active" if u["is_active"] else "🔴 Inactive"
                if u["id"] != user["id"]:
                    toggle_label = "Deactivate" if u["is_active"] else "Activate"
                    if st.button(toggle_label, key=f"toggle_{u['id']}"):
                        supabase.table("kb_users").update(
                            {"is_active": not u["is_active"]}
                        ).eq("id", u["id"]).execute()
                        st.rerun()
                else:
                    st.write(status_label)


# ─────────────────────────────────────────
# MAIN APP
# ─────────────────────────────────────────
def main():
    st.set_page_config(
        page_title="RTA Knowledge Base",
        page_icon="📚",
        layout="wide"
    )

    if "user" not in st.session_state:
        st.session_state.user = None

    if not st.session_state.user:
        page_login()
        return

    user = st.session_state.user
    role = user["role"]

    # ── Sidebar ──
    with st.sidebar:
        st.image("https://img.icons8.com/fluency/48/knowledge.png", width=48)
        st.title("RTA Knowledge Base")
        st.caption(f"👤 **{user['name']}**")
        st.caption(f"Role: `{role.upper()}`")
        st.divider()

        # Navigation
        nav_options = ["📖 Knowledge Base"]
        if role in ["admin", "super_admin"]:
            nav_options += ["📋 Review Queue", "👥 User Management"]
        else:
            nav_options.append("📤 Submit Document")

        page = st.radio("Menu", nav_options, label_visibility="collapsed")

        st.divider()

        # Pending badge for admins
        if role in ["admin", "super_admin"]:
            pending_count = len(get_pending_docs())
            if pending_count > 0:
                st.warning(f"⏳ {pending_count} document(s) pending review")

        if st.button("🚪 Logout", use_container_width=True):
            st.session_state.user = None
            st.rerun()

    # ── Page Router ──
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
