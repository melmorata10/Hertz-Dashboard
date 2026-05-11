"""Insurance Needs Assessment — one-question-per-page survey with email submission."""
import re
import streamlit as st
from src.survey_helpers import (
    PACKAGES, GOAL_OPTIONS, EMPLOYMENT_TYPES, GUARDIAN_EMPLOYMENT_TYPES,
    GUARDIAN_RELATIONS, recommend, pkg_card_html, send_email,
)

st.set_page_config(page_title="Insurance Needs Assessment", page_icon="🛡️", layout="centered")

# ── CSS ───────────────────────────────────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');
html,body,.stApp{font-family:'Inter',sans-serif!important;background:#f0f4f8}
#MainMenu,footer,header{visibility:hidden}
section[data-testid="stSidebar"]{display:none!important}
.block-container{max-width:580px!important;padding:1.5rem 1.5rem 3rem}
/* Buttons */
.stButton>button{
  background:linear-gradient(135deg,#1a73e8,#1557b0)!important;
  color:white!important;border:none!important;border-radius:10px!important;
  padding:11px 28px!important;font-weight:600!important;font-size:15px!important;
  width:100%!important;transition:all .2s!important;
}
.stButton>button:hover{box-shadow:0 4px 14px rgba(26,115,232,.4)!important}
/* Inputs */
.stTextInput>div>div>input,.stNumberInput>div>div>input{
  border-radius:10px!important;border:1.5px solid #cbd5e1!important;
  padding:10px 14px!important;font-size:15px!important;
}
.stTextInput>div>div>input:focus,.stNumberInput>div>div>input:focus{
  border-color:#1a73e8!important;box-shadow:0 0 0 3px rgba(26,115,232,.15)!important;
}
/* Radio & checkbox */
.stRadio>div{gap:6px}.stRadio label{font-size:15px!important}
.stCheckbox label{font-size:15px!important}
/* Progress */
.prog-wrap{background:#e2e8f0;border-radius:3px;height:5px;margin-bottom:6px}
.prog-fill{height:100%;border-radius:3px;background:linear-gradient(90deg,#1a73e8,#0d47a1)}
.step-lbl{font-size:11px;color:#94a3b8;font-weight:600;letter-spacing:1px;
           text-transform:uppercase;margin-bottom:18px}
h2{color:#0f172a!important;font-size:22px!important;font-weight:700!important;margin-bottom:2px!important}
/* Divider label */
.section-divider{color:#64748b;font-weight:600;font-size:13px;margin:16px 0 6px;
                  padding:4px 0;border-bottom:1px solid #e2e8f0}
</style>
""", unsafe_allow_html=True)

TOTAL_STEPS = 7

# ── Session state ─────────────────────────────────────────────────────────────
for k, v in {"step": 0, "ans": {}, "done": False}.items():
    if k not in st.session_state:
        st.session_state[k] = v


# ── Micro-helpers ─────────────────────────────────────────────────────────────
def go(n):
    st.session_state.step = n
    st.rerun()


def save(d: dict):
    st.session_state.ans.update(d)


def g(key, default=""):
    return st.session_state.ans.get(key, default)


def letters_ok(v: str) -> bool:
    return bool(re.match(r"^[A-Za-z\s.\-,/()'&]+$", v)) if v.strip() else True


def valid_email(v: str) -> bool:
    return bool(re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", v))


def valid_mobile(v: str) -> bool:
    return bool(re.match(r"^(\+63|0)\d{10}$", v.replace(" ", "")))


def progress(n: int, label: str):
    pct = int(n / TOTAL_STEPS * 100)
    st.markdown(
        f"<div class='prog-wrap'><div class='prog-fill' style='width:{pct}%'></div></div>"
        f"<div class='step-lbl'>Step {n} of {TOTAL_STEPS} — {label}</div>",
        unsafe_allow_html=True,
    )


def nav_back(back_step: int) -> "st.delta_generator.DeltaGenerator":
    """Render Back | [spacer] and return the right column for the Next button."""
    c1, c2 = st.columns(2)
    with c1:
        if st.button("← Back", key=f"back_{back_step}"):
            go(back_step)
    return c2


def radio_idx(options: list, key: str) -> int:
    stored = g(key)
    return options.index(stored) if stored in options else 0


def build_submission(ans: dict) -> dict:
    """Flatten session answers into a human-readable dict for the email."""
    d: dict = {
        "Full Name":    ans.get("full_name", ""),
        "Email":        ans.get("email", ""),
        "Mobile":       ans.get("mobile", ""),
        "Consent":      ans.get("consent", ""),
        "Age":          f"{ans.get('age', '')} years old",
    }
    if ans.get("profile") == "minor":
        d.update({
            "Guardian Name":             ans.get("guardian_name", ""),
            "Guardian Relationship":     ans.get("guardian_relation", ""),
            "Guardian Occupation":       ans.get("guardian_job", ""),
            "Guardian Employment Type":  ans.get("guardian_position", ""),
            "Guardian Years in Service": ans.get("guardian_years", ""),
            "Monthly Household Income":  f"₱{int(ans.get('monthly_income', 0)):,}",
        })
    else:
        d.update({
            "Employment Type":    ans.get("job_type", ""),
            "Job Title/Business": ans.get("job_title", ""),
            "Years in Service":   ans.get("years_service", ""),
            "Monthly Income":     f"₱{int(ans.get('monthly_income', 0)):,}",
        })
    d["Financial Goals"] = ", ".join(ans.get("goals", []))
    if ans.get("interest"):
        d["Plan of Interest"] = ans.get("interest", "")
    return d


# ═══════════════════════════════════════════════════════════════════════════════
# Confirmation screen
# ═══════════════════════════════════════════════════════════════════════════════
if st.session_state.done:
    st.markdown("""
    <div style='text-align:center;padding:60px 20px'>
      <div style='font-size:66px;margin-bottom:16px'>✅</div>
      <h2 style='color:#0f172a!important;font-size:26px!important'>Thank you!</h2>
      <p style='color:#64748b;font-size:16px;max-width:380px;margin:12px auto;line-height:1.6'>
        Your information has been submitted successfully. We'll prepare a personalized
        insurance proposal and reach out to you soon.
      </p>
    </div>""", unsafe_allow_html=True)
    if st.button("Start a new survey"):
        st.session_state.step = 0
        st.session_state.ans = {}
        st.session_state.done = False
        st.rerun()
    st.stop()

step = st.session_state.step

# ═══════════════════════════════════════════════════════════════════════════════
# Step 0 — Welcome
# ═══════════════════════════════════════════════════════════════════════════════
if step == 0:
    st.markdown("""
    <div style='text-align:center;padding:40px 0 28px'>
      <div style='font-size:62px;margin-bottom:16px'>🛡️</div>
      <h2 style='color:#0f172a!important;font-size:26px!important'>Find Your Perfect Insurance Plan</h2>
      <p style='color:#64748b;font-size:16px;max-width:400px;margin:12px auto;line-height:1.6'>
        Answer a few simple questions and we'll recommend the best insurance plan tailored just for you.
        Takes less than 5 minutes!
      </p>
    </div>""", unsafe_allow_html=True)
    if st.button("Let's Get Started →"):
        go(1)
    st.stop()

# ═══════════════════════════════════════════════════════════════════════════════
# Step 1 — Contact Details
# ═══════════════════════════════════════════════════════════════════════════════
if step == 1:
    progress(1, "Contact Details")
    st.markdown("## 👤 Tell us about yourself")
    name   = st.text_input("Full Name *",       value=g("full_name"), placeholder="e.g. Juan dela Cruz")
    email  = st.text_input("Email Address *",   value=g("email"),     placeholder="e.g. juan@email.com")
    mobile = st.text_input("Mobile Number *",   value=g("mobile"),    placeholder="e.g. 09171234567")

    errs = []
    if name   and not letters_ok(name):       errs.append("Name should contain letters only.")
    if email  and not valid_email(email):     errs.append("Please enter a valid email address.")
    if mobile and not valid_mobile(mobile):   errs.append("Mobile: use format 09XXXXXXXXX or +639XXXXXXXXX.")
    for e in errs:
        st.error(e)

    if st.button("Next →"):
        missing = [f for f, v in [("full name", name), ("email", email), ("mobile number", mobile)] if not v.strip()]
        if missing:
            st.error(f"Please enter your {missing[0]}.")
        elif not errs:
            save({"full_name": name.strip(), "email": email.strip(), "mobile": mobile.strip()})
            go(2)
    st.stop()

# ═══════════════════════════════════════════════════════════════════════════════
# Step 2 — Privacy Consent
# ═══════════════════════════════════════════════════════════════════════════════
if step == 2:
    progress(2, "Privacy Consent")
    st.markdown("## 🔒 Privacy Consent")
    st.markdown("""
We need your permission before we continue.

**We will use your information to:**
- Assess your specific insurance needs
- Prepare a personalized insurance proposal for you
- Contact you with relevant plan options and recommendations

Your data is kept strictly confidential and will **not** be shared with any third party without your permission.
    """)
    opts = ["Yes, I agree", "No, I do not agree"]
    consent = st.radio(
        "Do you allow us to collect and use your information for the above purposes?",
        opts, index=radio_idx(opts, "consent"),
    )
    c2 = nav_back(1)
    with c2:
        if st.button("Next →", key="n2"):
            if consent == opts[1]:
                st.warning("We cannot proceed without your consent. Please close this survey if you prefer not to continue.")
            else:
                save({"consent": consent})
                go(3)
    st.stop()

# ═══════════════════════════════════════════════════════════════════════════════
# Step 3 — Age
# ═══════════════════════════════════════════════════════════════════════════════
if step == 3:
    progress(3, "Your Age")
    st.markdown("## 🎂 How old are you?")
    age = st.number_input("Age (in years)", min_value=1, max_value=100,
                          value=int(g("age")) if g("age") else 25, step=1)
    c2 = nav_back(2)
    with c2:
        if st.button("Next →", key="n3"):
            save({"age": age})
            go(4)
    st.stop()

# ═══════════════════════════════════════════════════════════════════════════════
# Step 4 — Guardian (minor) OR Employment (adult)
# ═══════════════════════════════════════════════════════════════════════════════
if step == 4:
    age = int(g("age", 25))

    if age < 18:
        # ── Minor branch ──────────────────────────────────────────────────────
        progress(4, "Guardian's Details")
        st.markdown("## 👨‍👩‍👧 Legal Guardian's Information")
        st.caption(f"Since you are {age} years old, we need your legal guardian's details.")

        g_name = st.text_input("Guardian's Full Name *", value=g("guardian_name"), placeholder="e.g. Maria dela Cruz")
        g_rel  = st.radio("Relationship to You", GUARDIAN_RELATIONS, index=radio_idx(GUARDIAN_RELATIONS, "guardian_relation"))
        g_job  = st.text_input("Occupation / Job Title *", value=g("guardian_job"), placeholder="e.g. Teacher, Nurse, Store Owner")
        g_pos  = st.radio("Employment Type", GUARDIAN_EMPLOYMENT_TYPES, index=radio_idx(GUARDIAN_EMPLOYMENT_TYPES, "guardian_position"))
        g_yrs  = st.number_input("Years in Current Job / Business", min_value=0, max_value=60,
                                  value=int(g("guardian_years")) if g("guardian_years") else 0, step=1)
        g_inc  = st.number_input("Monthly Income (₱)", min_value=0,
                                  value=int(g("monthly_income")) if g("monthly_income") else 0, step=500,
                                  help="Approximate monthly take-home income in Philippine Peso")

        errs = []
        if g_name and not letters_ok(g_name): errs.append("Guardian's name should contain letters only.")
        if g_job  and not letters_ok(g_job):  errs.append("Occupation should contain letters only.")
        for e in errs:
            st.error(e)

        c2 = nav_back(3)
        with c2:
            if st.button("Next →", key="n4m"):
                if not g_name.strip():
                    st.error("Please enter the guardian's full name.")
                elif not g_job.strip():
                    st.error("Please enter the guardian's occupation.")
                elif not errs:
                    save({"guardian_name": g_name.strip(), "guardian_relation": g_rel,
                          "guardian_job": g_job.strip(), "guardian_position": g_pos,
                          "guardian_years": g_yrs, "monthly_income": g_inc, "profile": "minor"})
                    go(5)

    else:
        # ── Adult branch ──────────────────────────────────────────────────────
        progress(4, "Employment Details")
        st.markdown("## 💼 Employment / Business Details")

        job_type = st.radio("Which best describes your work?", EMPLOYMENT_TYPES,
                            index=radio_idx(EMPLOYMENT_TYPES, "job_type"))
        job_title = st.text_input(
            "Job Title / Nature of Business *", value=g("job_title"),
            placeholder="e.g. Accountant, Restaurant Owner, Nurse",
            disabled=(job_type == EMPLOYMENT_TYPES[-1]),
        )
        yrs = st.number_input("Years in Current Job / Business", min_value=0, max_value=60,
                               value=int(g("years_service")) if g("years_service") else 0, step=1)
        inc = st.number_input("Monthly Income (₱)", min_value=0,
                               value=int(g("monthly_income")) if g("monthly_income") else 0, step=500,
                               help="Approximate monthly take-home income in Philippine Peso")

        errs = []
        if job_title and not letters_ok(job_title): errs.append("Job title should contain letters only.")
        for e in errs:
            st.error(e)

        c2 = nav_back(3)
        with c2:
            if st.button("Next →", key="n4a"):
                needs_title = job_type != EMPLOYMENT_TYPES[-1]
                if needs_title and not job_title.strip():
                    st.error("Please enter your job title or nature of business.")
                elif not errs:
                    save({"job_type": job_type, "job_title": job_title.strip(),
                          "years_service": yrs, "monthly_income": inc, "profile": "adult"})
                    go(5)
    st.stop()

# ═══════════════════════════════════════════════════════════════════════════════
# Step 5 — Financial Goals
# ═══════════════════════════════════════════════════════════════════════════════
if step == 5:
    progress(5, "Financial Goals")
    st.markdown("## 🎯 What are your financial goals?")
    st.caption("Select all that apply. This helps us match you with the right plan.")

    selected = g("goals") or []
    checks = {
        opt: st.checkbox(opt, value=opt in selected, key=f"goal_{i}")
        for i, opt in enumerate(GOAL_OPTIONS)
    }

    c2 = nav_back(4)
    with c2:
        if st.button("Next →", key="n5"):
            chosen = [opt for opt, checked in checks.items() if checked]
            if not chosen:
                st.error("Please select at least one financial goal.")
            else:
                save({"goals": chosen})
                go(6)
    st.stop()

# ═══════════════════════════════════════════════════════════════════════════════
# Step 6 — Package Recommendations
# ═══════════════════════════════════════════════════════════════════════════════
if step == 6:
    progress(6, "Plan Recommendations")
    st.markdown("## 📋 Insurance Plans For You")

    rec, other = recommend(st.session_state.ans)

    if rec:
        st.caption("Based on your profile and goals, these plans match you best:")
        for pkg in rec:
            st.markdown(pkg_card_html(pkg, highlighted=True), unsafe_allow_html=True)
    else:
        st.info("We have a range of plans that can be customized to fit your needs. See all options below.")

    if other:
        with st.expander("View other available plans"):
            for pkg in other:
                st.markdown(pkg_card_html(pkg), unsafe_allow_html=True)

    interest = st.text_input(
        "Any particular plan you'd like to know more about? (optional)",
        value=g("interest"),
        placeholder="e.g. Health & Wellness Shield",
    )

    c2 = nav_back(5)
    with c2:
        if st.button("Next →", key="n6"):
            save({"interest": interest.strip()})
            go(7)
    st.stop()

# ═══════════════════════════════════════════════════════════════════════════════
# Step 7 — Review & Submit
# ═══════════════════════════════════════════════════════════════════════════════
if step == 7:
    progress(7, "Review & Submit")
    st.markdown("## 📝 Review Your Information")
    st.caption("Please review everything below. You can edit any field before submitting.")

    ans = st.session_state.ans
    edited: dict = {}

    st.markdown("<div class='section-divider'>Contact Information</div>", unsafe_allow_html=True)
    edited["full_name"] = st.text_input("Full Name",     value=ans.get("full_name", ""))
    edited["email"]     = st.text_input("Email Address", value=ans.get("email",     ""))
    edited["mobile"]    = st.text_input("Mobile Number", value=ans.get("mobile",    ""))
    st.markdown(f"**Consent:** {ans.get('consent', '')}")
    st.markdown(f"**Age:** {ans.get('age', '')} years old")

    if ans.get("profile") == "minor":
        st.markdown("<div class='section-divider'>Guardian's Information</div>", unsafe_allow_html=True)
        edited["guardian_name"] = st.text_input("Guardian's Full Name", value=ans.get("guardian_name", ""))
        st.markdown(f"**Relationship:** {ans.get('guardian_relation', '')} &nbsp;|&nbsp; **Employment Type:** {ans.get('guardian_position', '')}")
        edited["guardian_job"]   = st.text_input("Guardian's Occupation", value=ans.get("guardian_job", ""))
        edited["guardian_years"] = st.number_input("Years in Job/Business", min_value=0, max_value=60,
                                                    value=int(ans.get("guardian_years", 0)), key="ey")
        edited["monthly_income"] = st.number_input("Monthly Income (₱)", min_value=0,
                                                    value=int(ans.get("monthly_income", 0)), step=500, key="ei")
    else:
        st.markdown("<div class='section-divider'>Employment Information</div>", unsafe_allow_html=True)
        st.markdown(f"**Employment Type:** {ans.get('job_type', '')}")
        edited["job_title"]     = st.text_input("Job Title / Business", value=ans.get("job_title", ""))
        edited["years_service"] = st.number_input("Years in Job/Business", min_value=0, max_value=60,
                                                   value=int(ans.get("years_service", 0)), key="ey")
        edited["monthly_income"] = st.number_input("Monthly Income (₱)", min_value=0,
                                                    value=int(ans.get("monthly_income", 0)), step=500, key="ei")

    st.markdown("<div class='section-divider'>Goals & Interest</div>", unsafe_allow_html=True)
    st.markdown(f"**Financial Goals:** {', '.join(ans.get('goals', []))}")
    if ans.get("interest"):
        st.markdown(f"**Plan of Interest:** {ans.get('interest', '')}")

    st.markdown("")
    c2 = nav_back(6)
    with c2:
        if st.button("Submit ✓", key="submit"):
            # Validation on edited fields
            errs = []
            if not edited.get("full_name", "").strip():  errs.append("Full name is required.")
            if not valid_email(edited.get("email", "")): errs.append("Invalid email address.")
            if not valid_mobile(edited.get("mobile", "")): errs.append("Invalid mobile number.")
            if errs:
                for e in errs:
                    st.error(e)
            else:
                # Persist edits
                for k, v in edited.items():
                    if v is not None:
                        st.session_state.ans[k] = v

                data = build_submission(st.session_state.ans)
                ok, err = send_email(data)

                if not ok and err == "not_configured":
                    st.warning(
                        "Email delivery is not configured yet. Your response has been recorded. "
                        "Ask your agent to set up email settings."
                    )
                elif not ok:
                    st.error(f"Submission saved, but email delivery failed: {err}")

                st.session_state.done = True
                st.rerun()
