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
    "totalservicelevelcalls":     "SLCalls",  # calls answered within SL threshold
    "total service level calls":  "SLCalls",
    "servicelevelcalls":          "SLCalls",
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


def _enrich(df: pd.DataFrame, mapping: dict = None) -> pd.DataFrame:
    """Resolve SkillName → LOB and Vendor via the mapping table.

    Parameters
    ----------
    mapping : dict | None
        Custom mapping dict ``{skill_name: {"lob": ..., "vendor": ...}}``.
        When *None* (default) the built-in ``SKILL_TO_LOB`` from mapping.py is used.
    """
    if mapping is None:
        mapping = SKILL_TO_LOB

    def _lookup(row):
        skill = str(row.get("SkillName", ""))
        fallback_vendor = (
            str(row.get("SupplierName", ""))
            if pd.notna(row.get("SupplierName")) else "Unknown"
        )
        entry = mapping.get(skill, {})
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
        # min_count=1 keeps SLC as NaN (not 0) when the raw file lacks the column
        SLC   =("SLCalls", lambda s: s.sum(min_count=1)),
    ).reset_index()


def _derive_metrics(
    agg: pd.DataFrame,
    lob_col: str = "LOB",
    custom_targets: dict = None,
) -> pd.DataFrame:
    df = agg.copy()
    safe_nch = df["NCH"].replace(0, float("nan"))
    safe_nco = df["NCO"].replace(0, float("nan"))

    df["AHT"]  = (df["AHT_w"] / safe_nch).round(1)
    df["ASA"]  = (df["ASA_w"] / safe_nch).round(1)
    df["ABN%"] = (df["ABN"]   / safe_nco * 100).round(2)
    df["SL%"]  = (df["SLC"]   / safe_nco * 100).round(1)

    _targets = custom_targets if custom_targets is not None else TARGETS

    def tgt(lob, key):
        return _targets.get(str(lob), DEFAULT_TARGET)[key]

    df["Target AHT"]  = df[lob_col].map(lambda l: tgt(l, "aht"))
    df["Target ASA"]  = df[lob_col].map(lambda l: tgt(l, "asa"))
    df["Target ABN%"] = df[lob_col].map(lambda l: tgt(l, "abn") * 100)
    df["AHT Var%"]    = ((df["AHT"] - df["Target AHT"]) / df["Target AHT"] * 100).round(1)

    return df.drop(columns=["AHT_w", "ASA_w", "SLC"])


def prepare(
    raw: pd.DataFrame,
    custom_mapping: dict = None,
    custom_targets: dict = None,
    hidden_lobs: set = None,
) -> tuple[pd.DataFrame, dict, pd.DataFrame]:
    """
    Returns (summary_df, vendor_summaries, interval_df).

    summary_df       — one row per LOB + Grand Total row
    vendor_summaries — dict of {vendor: summary_df}
    interval_df      — one row per (LOB, Vendor, 30-min interval)

    Parameters
    ----------
    custom_mapping : dict | None
        Override skill→LOB+Vendor mapping. None = use built-in.
    custom_targets : dict | None
        Override per-LOB targets {lob: {"aht", "asa", "abn"}}. None = use built-in.
    hidden_lobs : set | None
        LOB labels excluded from ALL outputs — their calls do not count
        toward Grand Total, KPI tiles, vendor tables, or intervals.
    """
    _EMPTY_COLS = [
        "LOB", "NCO", "NCH", "SL%", "Target AHT", "AHT", "AHT Var%",
        "ABN", "Target ABN%", "ABN%", "Target ASA", "ASA",
    ]
    if raw.empty:
        empty = pd.DataFrame(columns=_EMPTY_COLS)
        return empty, {}, empty

    # 1. Normalise column names
    df = _normalise_columns(raw)

    # 2. Coerce numerics (default missing columns to 0)
    for col in ("NCO", "NCH", "AHT", "ASA"):
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)
        else:
            df[col] = 0

    # SLCalls: calls answered within the SL threshold. NaN (not 0) when the
    # column is missing entirely so SL% renders as "—" instead of a false 0%.
    if "SLCalls" in df.columns:
        df["SLCalls"] = pd.to_numeric(df["SLCalls"], errors="coerce").fillna(0)
    else:
        df["SLCalls"] = float("nan")

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
    df = _enrich(df, mapping=custom_mapping)
    df = df[df["LOB"].notna() & (df["LOB"] != "") & (df["LOB"] != "Unknown")]
    if hidden_lobs:
        df = df[~df["LOB"].isin(hidden_lobs)]

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
        agg = _derive_metrics(
            _aggregate(sub, ["LOB"]),
            custom_targets=custom_targets,
        )
        order = {lob: i for i, lob in enumerate(LOB_DISPLAY_ORDER)}
        agg["_sort"] = agg["LOB"].map(lambda l: order.get(l, 999))
        agg = agg.sort_values("_sort").drop(columns=["_sort"]).reset_index(drop=True)
        nco = int(sub["NCO"].sum())
        nch = int(sub["NCH"].sum())
        abn = int(sub["ABN"].sum())
        slc = sub["SLCalls"].sum(min_count=1)
        gt_aht        = round(sub["AHT_w"].sum() / nch, 1) if nch > 0 else 0
        gt_target_aht = round(agg["Target AHT"].mean(), 1)
        gt_aht_var    = round((gt_aht - gt_target_aht) / gt_target_aht * 100, 1) if gt_target_aht else None
        gt_target_abn = round(agg["Target ABN%"].mean(), 2)
        gt = pd.DataFrame([{
            "LOB":         "Grand Total",
            "NCO":         nco,
            "NCH":         nch,
            "SL%":         round(slc / nco * 100, 1) if nco > 0 and pd.notna(slc) else float("nan"),
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
    interval = _derive_metrics(
        _aggregate(df, ["LOB", "Vendor", "Interval30"]),
        custom_targets=custom_targets,
    )
    if pd.api.types.is_datetime64_any_dtype(interval["Interval30"]):
        interval["Interval30"] = interval["Interval30"].dt.strftime("%H:%M")
    interval["Interval30"] = interval["Interval30"].fillna("N/A").astype(str)
    interval = interval.rename(columns={"Interval30": "Interval"})
    interval = interval.sort_values(["Interval", "LOB", "Vendor"]).reset_index(drop=True)

    return summary, vendor_summaries, interval
