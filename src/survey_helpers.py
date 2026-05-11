"""Insurance survey — package definitions, recommendation engine, and email sender."""
import os, smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

# ── Insurance packages ────────────────────────────────────────────────────────
PACKAGES = [
    {
        "name": "Pure Protection Plan", "icon": "🛡️",
        "desc": "Maximum life coverage at the most affordable cost — ideal if protecting your family is the top priority.",
        "ideal": "Young professionals and sole breadwinners",
        "features": ["Term life coverage until retirement", "Accidental death & dismemberment benefit", "Affordable monthly premiums"],
        "goals": {"protection"}, "min_income": 0,
    },
    {
        "name": "Health & Wellness Shield", "icon": "❤️",
        "desc": "Comprehensive health plan with critical illness and hospitalization benefits.",
        "ideal": "Anyone prioritizing health and medical security",
        "features": ["Hospitalization reimbursement", "Critical illness lump-sum payout", "Daily hospital income benefit"],
        "goals": {"health"}, "min_income": 0,
    },
    {
        "name": "Life & Savings Builder", "icon": "💰",
        "desc": "Whole life plan that grows your savings while keeping your family protected.",
        "ideal": "Those who want insurance and savings in one plan",
        "features": ["Lifetime protection", "Guaranteed cash value growth", "Paid-up option after premium period"],
        "goals": {"savings", "protection"}, "min_income": 15000,
    },
    {
        "name": "Education Protector", "icon": "🎓",
        "desc": "Guarantees your child's education fund no matter what happens to you.",
        "ideal": "Parents with children aged 0–12",
        "features": ["Education fund guarantee", "Premium waiver on death/disability", "Flexible payout schedule"],
        "goals": {"education"}, "min_income": 0,
    },
    {
        "name": "Investment-Linked Plan (VUL)", "icon": "📈",
        "desc": "Grow your wealth through market-linked investments while maintaining life insurance coverage.",
        "ideal": "Mid-to-high income earners with long-term financial goals",
        "features": ["Market-linked investment returns", "Life insurance coverage", "Flexible fund switching"],
        "goals": {"investment", "retirement"}, "min_income": 30000,
    },
]

GOAL_MAP = {
    "Protection (family's financial security)": "protection",
    "Health coverage": "health",
    "Savings": "savings",
    "Education fund": "education",
    "Investment / wealth growth": "investment",
    "Retirement planning": "retirement",
}

GOAL_OPTIONS = list(GOAL_MAP.keys())

EMPLOYMENT_TYPES = [
    "Regular / Permanent Employee",
    "Contractual / Probationary Employee",
    "Self-Employed / Business Owner",
    "Freelancer / Independent Contractor",
    "OFW / Overseas Worker",
    "Currently Not Employed",
]

GUARDIAN_EMPLOYMENT_TYPES = [
    "Regular / Permanent Employee",
    "Contractual / Probationary Employee",
    "Self-Employed / Business Owner",
    "OFW / Overseas Worker",
    "Retired",
]

GUARDIAN_RELATIONS = ["Parent", "Grandparent", "Sibling", "Other Relative"]


def recommend(answers: dict) -> tuple[list, list]:
    """Return (recommended, other) package lists based on goals and income."""
    goal_keys = {GOAL_MAP.get(g, "") for g in answers.get("goals", [])}
    income = int(answers.get("monthly_income", 0) or 0)
    rec, other = [], []
    for pkg in PACKAGES:
        if income >= pkg["min_income"] and pkg["goals"] & goal_keys:
            rec.append(pkg)
        else:
            other.append(pkg)
    return rec, other


def pkg_card_html(pkg: dict, highlighted: bool = False) -> str:
    """Render a package as an HTML card string."""
    border = "#1a73e8" if highlighted else "#e2e8f0"
    bg = "#eff6ff" if highlighted else "#f8fafc"
    badge = (
        "<span style='font-size:11px;background:#dbeafe;color:#1e40af;"
        "padding:2px 9px;border-radius:20px;font-weight:600;margin-left:8px'>✓ Recommended</span>"
        if highlighted else ""
    )
    feats = "".join(
        f"<li style='color:#475569;font-size:13px;margin-bottom:2px'>{f}</li>"
        for f in pkg["features"]
    )
    return (
        f"<div style='border:2px solid {border};border-radius:12px;padding:14px 16px;"
        f"margin-bottom:10px;background:{bg}'>"
        f"<div style='font-weight:700;font-size:15px;color:#0f172a'>"
        f"{pkg['icon']} {pkg['name']}{badge}</div>"
        f"<div style='color:#64748b;font-size:13px;margin:4px 0 6px'>{pkg['desc']}</div>"
        f"<div style='font-size:12px;color:#64748b;font-weight:600'>Ideal for: {pkg['ideal']}</div>"
        f"<ul style='margin:8px 0 0 18px;padding:0'>{feats}</ul>"
        f"</div>"
    )


def build_email_html(data: dict) -> str:
    rows = "".join(
        f"<tr><td style='padding:7px 12px;border:1px solid #e2e8f0;font-weight:600;"
        f"white-space:nowrap;background:#f8fafc;color:#0f172a'>{k}</td>"
        f"<td style='padding:7px 12px;border:1px solid #e2e8f0;color:#334155'>{v}</td></tr>"
        for k, v in data.items()
    )
    return (
        "<div style='font-family:Arial,sans-serif;max-width:600px'>"
        "<h2 style='color:#0f172a;border-bottom:2px solid #1a73e8;padding-bottom:8px'>"
        "📋 New Insurance Survey Response</h2>"
        f"<table style='border-collapse:collapse;width:100%;font-size:14px'>{rows}</table>"
        "<p style='color:#94a3b8;font-size:12px;margin-top:16px'>Sent via Insurance Needs Assessment Form</p>"
        "</div>"
    )


def send_email(data: dict) -> tuple[bool, str]:
    """Send survey results via SMTP. Returns (success, error_message)."""
    try:
        import streamlit as st
        cfg = dict(st.secrets.get("email", {}))
    except Exception:
        cfg = {}

    to   = cfg.get("to",        os.environ.get("SURVEY_TO_EMAIL", ""))
    host = cfg.get("smtp_host", os.environ.get("SMTP_HOST",       "smtp.gmail.com"))
    port = int(cfg.get("smtp_port", os.environ.get("SMTP_PORT",   "465")))
    user = cfg.get("smtp_user", os.environ.get("SMTP_USER",       ""))
    pwd  = cfg.get("smtp_pass", os.environ.get("SMTP_PASS",       ""))

    if not (to and user and pwd):
        return False, "not_configured"

    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"Insurance Survey — {data.get('Full Name', 'Unknown')}"
    msg["From"]    = user
    msg["To"]      = to
    msg.attach(MIMEText(build_email_html(data), "html"))

    try:
        if port == 465:
            with smtplib.SMTP_SSL(host, port) as s:
                s.login(user, pwd)
                s.sendmail(user, to, msg.as_string())
        else:
            with smtplib.SMTP(host, port) as s:
                s.starttls()
                s.login(user, pwd)
                s.sendmail(user, to, msg.as_string())
        return True, ""
    except Exception as exc:
        return False, str(exc)
