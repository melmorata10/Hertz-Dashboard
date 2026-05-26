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
            page = st.radio("Navigation", nav_options, label_visibility="hidden")

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
                col1, col2, col3, col4 = st.columns([5, 1, 1, 1])
                with col1:
                    st.markdown(f"**{doc['title']}**")
                    st.caption(
                        f"Category: {cat_name}  ·  v{doc['version']}"
                        f"  ·  Approved: {(doc.get('reviewed_at') or '')[:10]}"
                    )
                with col2:
                    if st.button("✏️ Edit", key=f"edit_app_{doc['id']}"):
                        st.session_state["editing_doc"] = doc["id"]
                        st.rerun()
                with col3:
                    if st.button("🗑️ Unpublish", key=f"unpub_{doc['id']}"):
                        reject_doc(doc["id"], user["id"])
                        st.rerun()
                with col4:
                    if user["role"] == "super_admin":
                        if st.button("❌ Delete", key=f"del_app_{doc['id']}"):
                            delete_doc(doc["id"])
                            st.toast("Document permanently deleted.", icon="🗑️")
                            st.rerun()

                # ── Inline edit form ──────────────────────────────────────
                if st.session_state.get("editing_doc") == doc["id"]:
                    categories = get_categories()
                    cat_map    = {cat["name"]: cat["id"] for cat in categories}
                    cat_names  = list(cat_map.keys())
                    cur_cat    = cat_name if cat_name in cat_names else cat_names[0]
                    with st.form(key=f"edit_form_{doc['id']}"):
                        st.markdown("#### ✏️ Edit Document")
                        new_title   = st.text_input("Title", value=doc.get("title", ""))
                        new_cat     = st.selectbox("Category", options=cat_names,
                                                    index=cat_names.index(cur_cat))
                        new_content = st.text_area("Content", value=doc.get("content", ""),
                                                    height=300)
                        col_s, col_c = st.columns([1, 1])
                        with col_s:
                            save = st.form_submit_button("💾 Save Changes",
                                                          use_container_width=True,
                                                          type="primary")
                        with col_c:
                            cancel = st.form_submit_button("Cancel",
                                                            use_container_width=True)
                        if save:
                            supabase.table("kb_documents").update({
                                "title":      new_title,
                                "category_id": cat_map[new_cat],
                                "content":    new_content,
                                "version":    (doc.get("version") or 1) + 1,
                                "updated_at": datetime.datetime.now().isoformat()
                            }).eq("id", doc["id"]).execute()
                            st.session_state.pop("editing_doc", None)
                            st.toast("✅ Document updated!", icon="✅")
                            st.rerun()
                        if cancel:
                            st.session_state.pop("editing_doc", None)
                            st.rerun()

    with tab_rejected:
        docs = get_all_docs_by_status("rejected")
        if not docs:
            st.info("No rejected documents.")
        for doc in docs:
            cat_name = (doc.get("kb_categories") or {}).get("name", "—")
            with st.container(border=True):
                col1, col2, col3, col4 = st.columns([5, 1, 1, 1])
                with col1:
                    st.markdown(f"**{doc['title']}**")
                    st.caption(
                        f"Category: {cat_name}"
                        f"  ·  Rejected: {(doc.get('reviewed_at') or '')[:10]}"
                    )
                with col2:
                    if st.button("✏️ Edit", key=f"edit_rej_{doc['id']}"):
                        st.session_state["editing_doc"] = doc["id"]
                        st.rerun()
                with col3:
                    if st.button("↩️ Re-approve", key=f"reapp_{doc['id']}"):
                        approve_doc(doc["id"], user["id"])
                        st.rerun()
                with col4:
                    if user["role"] == "super_admin":
                        if st.button("❌ Delete", key=f"del_rej_{doc['id']}"):
                            delete_doc(doc["id"])
                            st.toast("Document permanently deleted.", icon="🗑️")
                            st.rerun()

                # ── Inline edit form ──────────────────────────────────────
                if st.session_state.get("editing_doc") == doc["id"]:
                    categories = get_categories()
                    cat_map    = {cat["name"]: cat["id"] for cat in categories}
                    cat_names  = list(cat_map.keys())
                    cur_cat    = cat_name if cat_name in cat_names else cat_names[0]
                    with st.form(key=f"edit_form_rej_{doc['id']}"):
                        st.markdown("#### ✏️ Edit Document")
                        new_title   = st.text_input("Title", value=doc.get("title", ""))
                        new_cat     = st.selectbox("Category", options=cat_names,
                                                    index=cat_names.index(cur_cat))
                        new_content = st.text_area("Content", value=doc.get("content", ""),
                                                    height=300)
                        col_s, col_c = st.columns([1, 1])
                        with col_s:
                            save = st.form_submit_button("💾 Save Changes",
                                                          use_container_width=True,
                                                          type="primary")
                        with col_c:
                            cancel = st.form_submit_button("Cancel",
                                                            use_container_width=True)
                        if save:
                            supabase.table("kb_documents").update({
                                "title":      new_title,
                                "category_id": cat_map[new_cat],
                                "content":    new_content,
                                "version":    (doc.get("version") or 1) + 1,
                                "updated_at": datetime.datetime.now().isoformat()
                            }).eq("id", doc["id"]).execute()
                            st.session_state.pop("editing_doc", None)
                            st.toast("✅ Document updated!", icon="✅")
                            st.rerun()
                        if cancel:
                            st.session_state.pop("editing_doc", None)
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

        page = st.radio("Navigation", nav_options, label_visibility="hidden")

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

    # Reset KB state when switching pages
    if "current_page" not in st.session_state:
        st.session_state.current_page = page
    if st.session_state.current_page != page:
        st.session_state.kb_selected_doc = None
        st.session_state.current_page    = page

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
