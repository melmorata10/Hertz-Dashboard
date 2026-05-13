import pandas as pd
from src.mapping import SKILL_TO_LOB, TARGETS, DEFAULT_TARGET, LOB_DISPLAY_ORDER

# Case-insensitive column name normalisation.
# Priority rule: 'Skill Name and Number' wins over plain 'SkillName'
# because it includes the numeric ID prefix that matches SKILL_TO_LOB keys.
_RAW_COLS = {
    "suppliername":         "SupplierName",
    "interval":             "Interval",
    "intervalstarttime":    "Interval",   # alternate name used in real CSVs
    "nco":                  "NCO",
    "numbero ffered":       "NCO",        # typo variant
    "nch":                  "NCH",
    "numberhandled":        "NCH",        # alternate name
    "aht":                  "AHT",
    "abn":                  "ABN",
    "asa":                  "ASA",
    "speedofanswer":        "SpeedOfAnswer",  # keep total separate — used for ASA_w
}

# Canonical SkillName column candidates, in priority order (first match wins)
_SKILL_COL_PRIORITY = [
    "skill name and number",   # "20980968: US_Hertz_VXI_REX_Decagon" — matches mapping keys
    "skill name and number (h)",
    "skillname",               # plain name without ID prefix — fallback only
]


def _normalise_columns(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df.columns = [str(c).strip() for c in df.columns]
    cols_lower = {c.lower(): c for c in df.columns}

    # 1. Resolve SkillName from priority list.
    #    Drop all lower-priority skill columns first so there's no duplicate after rename.
    for candidate in _SKILL_COL_PRIORITY:
        if candidate in cols_lower:
            winner = cols_lower[candidate]
            # Drop every other skill-candidate column (including the plain 'SkillName')
            to_drop = [
                cols_lower[p] for p in _SKILL_COL_PRIORITY
                if p != candidate and p in cols_lower
            ]
            df = df.drop(columns=to_drop, errors="ignore")
            # Now rename the winning column → canonical 'SkillName'
            if winner != "SkillName":
                df = df.rename(columns={winner: "SkillName"})
            break

    # 2. Apply standard column renames
    rename = {c: _RAW_COLS[c.lower()] for c in df.columns if c.lower() in _RAW_COLS}
    df = df.rename(columns=rename)

    # 3. Drop duplicate column names — keep the first occurrence of each
    df = df.loc[:, ~df.columns.duplicated()]

    return df


def _enrich(df: pd.DataFrame) -> pd.DataFrame:
    """Resolve SkillName → LOB and Vendor via the static mapping table."""
    def _lookup(row):
        skill = str(row.get("SkillName", ""))
        fallback_vendor = (
            str(row.get("SupplierName", ""))
            if pd.notna(row.get("SupplierName")) else "Unknown"
        )
        entry = SKILL_TO_LOB.get(skill, {})
        return entry.get("lob", "Unknown"), entry.get("vendor", fallback_vendor)

    results = df.apply(_lookup, axis=1, result_type="expand")
    df = df.copy()
    df["LOB"]    = results[0].values
    df["Vendor"] = results[1].values
    return df


def _aggregate(df: pd.DataFrame, group_cols: list) -> pd.DataFrame:
    return df.groupby(group_cols, dropna=False).agg(
        NCO   =("NCO",   "sum"),
        NCH   =("NCH",   "sum"),
        AHT_w =("AHT_w", "sum"),
        ASA_w =("ASA_w", "sum"),
        ABN   =("ABN",   "sum"),
    ).reset_index()


def _derive_metrics(agg: pd.DataFrame, lob_col: str = "LOB") -> pd.DataFrame:
    df = agg.copy()
    safe_nch = df["NCH"].replace(0, float("nan"))
    safe_nco = df["NCO"].replace(0, float("nan"))

    df["AHT"]  = (df["AHT_w"] / safe_nch).round(1)
    df["ASA"]  = (df["ASA_w"] / safe_nch).round(1)
    df["ABN%"] = (df["ABN"]   / safe_nco * 100).round(2)

    def tgt(lob, key):
        return TARGETS.get(str(lob), DEFAULT_TARGET)[key]

    df["Target AHT"]  = df[lob_col].map(lambda l: tgt(l, "aht"))
    df["Target ASA"]  = df[lob_col].map(lambda l: tgt(l, "asa"))
    df["Target ABN%"] = df[lob_col].map(lambda l: tgt(l, "abn") * 100)
    df["AHT Var%"]    = ((df["AHT"] - df["Target AHT"]) / df["Target AHT"] * 100).round(1)

    return df.drop(columns=["AHT_w", "ASA_w"])


def prepare(raw: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Returns (summary_df, interval_df).

    summary_df  — one row per LOB + Grand Total row
    interval_df — one row per (LOB, Vendor, 30-min interval)
    """
    _EMPTY_COLS = [
        "LOB", "NCO", "NCH", "Target AHT", "AHT", "AHT Var%",
        "ABN", "Target ABN%", "ABN%", "Target ASA", "ASA",
    ]
    if raw.empty:
        return pd.DataFrame(columns=_EMPTY_COLS), pd.DataFrame(columns=_EMPTY_COLS)

    # 1. Normalise column names
    df = _normalise_columns(raw)

    # 2. Coerce numerics (default missing columns to 0)
    for col in ("NCO", "NCH", "AHT", "ASA"):
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)
        else:
            df[col] = 0

    # ABN: use column if present, otherwise derive from NCO - NCH
    if "ABN" in df.columns:
        df["ABN"] = pd.to_numeric(df["ABN"], errors="coerce").fillna(0)
    else:
        df["ABN"] = (df["NCO"] - df["NCH"]).clip(lower=0)

    # 3. Parse interval into 30-min buckets
    if "Interval" in df.columns:
        df["Interval"] = pd.to_datetime(df["Interval"], errors="coerce")
        df["Interval30"] = df["Interval"].dt.floor("30min")
    else:
        df["Interval30"] = pd.NaT

    # 4. Enrich with LOB / Vendor via skill mapping
    df = _enrich(df)
    df = df[df["LOB"].notna() & (df["LOB"] != "") & (df["LOB"] != "Unknown")]

    if df.empty:
        empty = pd.DataFrame(columns=_EMPTY_COLS)
        return empty, {}, empty

    # 5. Pre-compute weighted columns for aggregation
    df["AHT_w"] = df["NCH"] * df["AHT"]
    # ASA_w: use SpeedOfAnswer total directly (includes abandoned-call wait time).
    # NCH×ASA drops rows where NCH=0 but callers still waited before abandoning.
    if "SpeedOfAnswer" in df.columns:
        df["ASA_w"] = pd.to_numeric(df["SpeedOfAnswer"], errors="coerce").fillna(0)
    else:
        df["ASA_w"] = df["NCH"] * df["ASA"]

    # ── Helper: build summary with grand total for any subset of rows ──────────
    def _make_summary(sub: pd.DataFrame) -> pd.DataFrame:
        agg = _derive_metrics(_aggregate(sub, ["LOB"]))
        order = {lob: i for i, lob in enumerate(LOB_DISPLAY_ORDER)}
        agg["_sort"] = agg["LOB"].map(lambda l: order.get(l, 999))
        agg = agg.sort_values("_sort").drop(columns=["_sort"]).reset_index(drop=True)
        nco = int(sub["NCO"].sum())
        nch = int(sub["NCH"].sum())
        abn = int(sub["ABN"].sum())
        gt_aht        = round(sub["AHT_w"].sum() / nch, 1) if nch > 0 else 0
        gt_target_aht = round(agg["Target AHT"].mean(), 1)
        gt_aht_var    = round((gt_aht - gt_target_aht) / gt_target_aht * 100, 1) if gt_target_aht else None
        gt_target_abn = round(agg["Target ABN%"].mean(), 2)
        gt = pd.DataFrame([{
            "LOB":         "Grand Total",
            "NCO":         nco,
            "NCH":         nch,
            "AHT":         gt_aht,
            "Target AHT":  gt_target_aht,
            "AHT Var%":    gt_aht_var,
            "ABN":         abn,
            "Target ABN%": gt_target_abn,
            "ABN%":        round(abn / nco * 100, 2) if nco > 0 else 0,
            "Target ASA":  round(agg["Target ASA"].mean(), 1),
            "ASA":         round(sub["ASA_w"].sum() / nch, 1) if nch > 0 else 0,
        }])
        return pd.concat([agg, gt], ignore_index=True)

    # ── Summary (all vendors combined) ────────────────────────────────────────
    summary = _make_summary(df)

    # ── Per-vendor summaries ──────────────────────────────────────────────────
    vendor_summaries: dict[str, pd.DataFrame] = {}
    for vendor in sorted(df["Vendor"].dropna().unique()):
        sub = df[df["Vendor"] == vendor]
        if not sub.empty:
            vendor_summaries[vendor] = _make_summary(sub)

    # ── Interval (by LOB + Vendor + 30-min slot) ──────────────────────────────
    interval = _derive_metrics(_aggregate(df, ["LOB", "Vendor", "Interval30"]))
    if pd.api.types.is_datetime64_any_dtype(interval["Interval30"]):
        interval["Interval30"] = interval["Interval30"].dt.strftime("%H:%M")
    interval["Interval30"] = interval["Interval30"].fillna("N/A").astype(str)
    interval = interval.rename(columns={"Interval30": "Interval"})
    interval = interval.sort_values(["Interval", "LOB", "Vendor"]).reset_index(drop=True)

    return summary, vendor_summaries, interval
