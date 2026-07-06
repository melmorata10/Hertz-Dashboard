"""User-editable exception / convention rules (Exception Rules tab).

Users write rules as plain text, one per line; the parser turns each line
into a dict with keys Rule Type / From / To / Notes. Rules are persisted
server-side (shared by all users) and applied:

• "Rename LOB" — every occurrence of the *From* label, whether it comes from
  the skill mapping or a forecast column, is treated and displayed as *To*.
• "Forecast → LOB link" — the forecast workbook column *From* counts toward
  the dashboard LOB *To* when computing Forecast Volume / Forecast Variance.
"""

import re

import pandas as pd

from src.daily_forecast import FORECAST_LOB_MAP

RULE_TYPE_RENAME = "Rename LOB"
RULE_TYPE_LINK = "Forecast → LOB link"
RULE_TYPES = [RULE_TYPE_RENAME, RULE_TYPE_LINK]

RULE_COLUMNS = ["Rule Type", "From", "To", "Notes"]

# Conventions in force today — used when no rules have been saved yet, and by
# the tab's "Reset to defaults" button.
DEFAULT_RULES = [
    {
        "Rule Type": RULE_TYPE_RENAME,
        "From": "CSCC",
        "To": "Billing/Disputes",
        "Notes": "CSCC (forecast or mapping) is shown as Billing/Disputes",
    },
    {
        "Rule Type": RULE_TYPE_RENAME,
        "From": "CSCC TNC",
        "To": "TNC Billing and Dispute",
        "Notes": "TNC flavour of the CSCC rename",
    },
    {
        "Rule Type": RULE_TYPE_RENAME,
        "From": "CUSTOMER SPECIAL SERVICES DEPARTMENT",
        "To": "CSSD",
        "Notes": "Same department — older forecast files spell it out in full",
    },
]


def _clean(v) -> str:
    s = str(v).strip()
    return "" if s.lower() in ("nan", "none") else s


# ── Plain-text rule parsing ────────────────────────────────────────────────────
# One rule per line. Understood phrasings (case-insensitive, "the"/trailing
# "on the dashboard" are ignored):
#   Link a forecast column to a dashboard LOB:
#     "CSSD in mapping is CUSTOMER SPECIAL SERVICES DEPARTMENT in Forecast"
#     "CUSTOMER SPECIAL SERVICES DEPARTMENT in forecast is CSSD in mapping"
#     "forecast CSSD counts toward International"
#   Rename a label everywhere:
#     "CSCC in Forecast and Mapping needs to be labeled Billing/Disputes"
#     "label CSCC as Billing/Disputes" / "rename CSCC to Billing/Disputes"
#     "CSCC = Billing/Disputes" / "CSCC -> Billing/Disputes"

_RE_LINK_MAP_FIRST = re.compile(
    r"^(?:the\s+)?(.+?)\s+in\s+(?:the\s+)?mapping\s+is\s+(?:the\s+)?(.+?)\s+in\s+(?:the\s+)?forecast$",
    re.I,
)
_RE_LINK_FC_FIRST = re.compile(
    r"^(?:the\s+)?(.+?)\s+in\s+(?:the\s+)?forecast\s+is\s+(?:the\s+)?(.+?)\s+in\s+(?:the\s+)?mapping$",
    re.I,
)
_RE_LINK_COUNTS = re.compile(
    r"^(?:the\s+)?(?:forecast\s+(?:column\s+)?)?(.+?)\s+(?:in\s+(?:the\s+)?forecast\s+)?"
    r"(?:counts?\s+(?:toward|towards|to|as|under)|feeds|links?\s+to)\s+(?:the\s+)?(.+)$",
    re.I,
)
_RE_RENAME_VERB = re.compile(
    r"^(?:rename|label|relabel|show)\s+(.+?)\s+(?:to|as)\s+(.+)$",
    re.I,
)
_RE_RENAME_LABELED = re.compile(
    r"^(?:the\s+)?(.+?)(?:\s+in\s+.+?)?\s+"
    r"(?:needs?\s+to\s+be|should\s+be|must\s+be|will\s+be|is|are)?\s*"
    r"(?:re)?labell?ed(?:\s+as)?\s+(.+)$",
    re.I,
)
_RE_RENAME_ARROW = re.compile(r"^(.+?)\s*(?:=|->|→|=>)\s*(.+)$")


def _parse_line(line: str) -> dict | None:
    """Parse one text line into a rule dict, or None if not understood."""
    line = re.sub(r"\s+on\s+(?:the\s+)?dashboard\.?$", "", line.strip(), flags=re.I)
    line = line.rstrip(".").strip()
    if not line:
        return None

    m = _RE_LINK_MAP_FIRST.match(line)
    if m:  # "<LOB> in mapping is <column> in forecast"
        return {"Rule Type": RULE_TYPE_LINK, "From": m.group(2).strip(),
                "To": m.group(1).strip(), "Notes": ""}
    m = _RE_LINK_FC_FIRST.match(line)
    if m:  # "<column> in forecast is <LOB> in mapping"
        return {"Rule Type": RULE_TYPE_LINK, "From": m.group(1).strip(),
                "To": m.group(2).strip(), "Notes": ""}
    m = _RE_RENAME_VERB.match(line)
    if m:
        return {"Rule Type": RULE_TYPE_RENAME, "From": m.group(1).strip(),
                "To": m.group(2).strip(), "Notes": ""}
    m = _RE_LINK_COUNTS.match(line)
    if m and re.search(r"counts?\s|feeds|links?\s", line, re.I):
        return {"Rule Type": RULE_TYPE_LINK, "From": m.group(1).strip(),
                "To": m.group(2).strip(), "Notes": ""}
    m = _RE_RENAME_LABELED.match(line)
    if m and re.search(r"labell?ed", line, re.I):
        return {"Rule Type": RULE_TYPE_RENAME, "From": m.group(1).strip(),
                "To": m.group(2).strip(), "Notes": ""}
    m = _RE_RENAME_ARROW.match(line)
    if m:
        return {"Rule Type": RULE_TYPE_RENAME, "From": m.group(1).strip(),
                "To": m.group(2).strip(), "Notes": ""}
    return None


def parse_rules_text(text: str) -> tuple[list, list]:
    """Parse the rules textarea → (valid rules, lines not understood).

    Blank lines and lines starting with # are ignored; an inline " # comment"
    is stripped before parsing.
    """
    rules, bad = [], []
    for raw in str(text or "").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        line = line.split(" #")[0].strip()
        parsed = _parse_line(line)
        if parsed is None:
            bad.append(raw.strip())
        else:
            rules.append(parsed)
    return clean_rules(rules), bad


def rules_to_text(rules) -> str:
    """Render rules back to canonical text lines (used to seed the textarea)."""
    lines = []
    for r in rules:
        note = f"  # {r['Notes']}" if r.get("Notes") else ""
        if r.get("Rule Type") == RULE_TYPE_LINK:
            lines.append(f"forecast {r['From']} counts toward {r['To']}{note}")
        else:
            lines.append(f"label {r['From']} as {r['To']}{note}")
    return "\n".join(lines)


def clean_rules(rows) -> list:
    """Validate editor rows into a rules list — drops incomplete rows."""
    cleaned = []
    for row in rows:
        rtype = _clean(row.get("Rule Type"))
        src = _clean(row.get("From"))
        dst = _clean(row.get("To"))
        if rtype in RULE_TYPES and src and dst and src != dst:
            cleaned.append({
                "Rule Type": rtype, "From": src, "To": dst,
                "Notes": _clean(row.get("Notes")),
            })
    return cleaned


def lob_renames(rules) -> dict:
    """{from_label: to_label} for all rename rules."""
    return {
        r["From"]: r["To"]
        for r in rules
        if r.get("Rule Type") == RULE_TYPE_RENAME and r.get("From") and r.get("To")
    }


def forecast_links(rules) -> dict:
    """{forecast_column: dashboard_lob} for all link rules."""
    return {
        r["From"]: r["To"]
        for r in rules
        if r.get("Rule Type") == RULE_TYPE_LINK and r.get("From") and r.get("To")
    }


def apply_to_mapping(mapping: dict, rules) -> dict:
    """Return the skill mapping with LOB values renamed per the rules."""
    ren = lob_renames(rules)
    if not ren or not mapping:
        return mapping
    out = {}
    for skill, entry in mapping.items():
        entry = dict(entry)
        entry["lob"] = ren.get(str(entry.get("lob", "")).strip(), entry.get("lob", ""))
        out[skill] = entry
    return out


def apply_to_forecast_df(fc_df: pd.DataFrame, rules) -> pd.DataFrame:
    """Return the forecast frame with LOB labels renamed per the rules."""
    ren = lob_renames(rules)
    if not ren or fc_df is None:
        return fc_df
    out = fc_df.copy()
    out["LOB"] = out["LOB"].replace(ren)
    return out


def build_forecast_lob_map(rules, base: dict = None) -> dict:
    """Merge the built-in FORECAST_LOB_MAP with the user's link rules.

    Renames are applied to the base map's keys and column names so lookups
    match the renamed labels; a forecast column named in a link rule is
    removed from every base entry first (the user's link wins), then added
    to its target LOB.
    """
    base = FORECAST_LOB_MAP if base is None else base
    ren = lob_renames(rules)
    links = forecast_links(rules)

    merged: dict = {}
    for lob, cols in base.items():
        lob2 = ren.get(lob, lob)
        cols2 = [ren.get(c, c) for c in cols if c not in links and ren.get(c, c) not in links]
        merged.setdefault(lob2, [])
        for c in cols2:
            if c not in merged[lob2]:
                merged[lob2].append(c)

    for col, lob in links.items():
        lob2 = ren.get(lob, lob)
        col2 = ren.get(col, col)
        merged.setdefault(lob2, [])
        if col2 not in merged[lob2]:
            merged[lob2].append(col2)

    return {lob: cols for lob, cols in merged.items() if cols}
