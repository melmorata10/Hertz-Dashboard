"""User-editable exception / convention rules (Exception Rules tab).

Rules are a list of dicts with keys: Rule Type / From / To / Notes.
They are persisted server-side (shared by all users) and applied:

• "Rename LOB" — every occurrence of the *From* label, whether it comes from
  the skill mapping or a forecast column, is treated and displayed as *To*.
• "Forecast → LOB link" — the forecast workbook column *From* counts toward
  the dashboard LOB *To* when computing Forecast Volume / Forecast Variance.
"""

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
        "Rule Type": RULE_TYPE_LINK,
        "From": "CUSTOMER SPECIAL SERVICES DEPARTMENT",
        "To": "International",
        "Notes": "CSSD queues report under the International LOB",
    },
    {
        "Rule Type": RULE_TYPE_LINK,
        "From": "CSSD",
        "To": "International",
        "Notes": "Newer forecast files shorten the CSSD column name",
    },
]


def _clean(v) -> str:
    s = str(v).strip()
    return "" if s.lower() in ("nan", "none") else s


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
