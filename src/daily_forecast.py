"""Daily Forecast workbook parsing (Daily Forecast tab)."""

import pandas as pd

# Every sheet in the workbook is one site/vendor (Consolidated, VXI, TELUS,
# IGT, …). These columns describe the calendar; every remaining column is a
# line of business holding the forecast call volume for that date.
META_COLS = ["Year", "Month", "Week", "Date", "Weekday"]

# Dashboard LOB name → forecast workbook column(s) whose volumes make it up.
# LOBs missing here (BRST, CONFO, Roadside Lite, OPERATIONS) have no forecast
# column and show "—" for Forecast Volume / Forecast Variance.
FORECAST_LOB_MAP = {
    "Sales":                       ["Sales"],
    "CCM":                         ["CCM"],
    "International":               ["International"],
    "Languages":                   ["Multi-Language"],
    "Billing/Disputes":            ["CSCC"],
    "TNC Billing and Dispute":     ["CSCC TNC"],
    "FNOL":                        ["FNOL"],
    "HRD":                         ["HRD"],
    "Fleet Desk":                  ["Fleet"],
    "SPOC":                        ["SPOC"],
    "First Choice Offered":        ["First Choice"],
    "Roadside Services":           ["Roadside Hertz", "Roadside - Dollar Thrifty"],
    "Vehicle Control":             ["Vehicle Control"],
    "Rental Extensions":           ["REX Retail"],
    "TNC Rental Extension":        ["Rex TNC"],
    "Damage":                      ["Damage"],
    "MultiMonth":                  ["SRP"],
}

# Workbook sheet name → site/vendor name used on the dashboard.
# The IGT sheet is the ATAIN vendor's forecast.
SITE_RENAME = {"IGT": "ATAIN"}

# Vendor table on the dashboard → site in the parsed forecast (after
# SITE_RENAME). The main (all-vendor) table uses the Consolidated sheet;
# HERTZ has no sheet in the workbook so its table shows no forecast columns.
FORECAST_VENDOR_SHEETS = {
    "TELUS": "TELUS",
    "VXI":   "VXI",
    "ATAIN": "ATAIN",
}

# Vendor spelling variants seen in mappings → canonical site name.
_VENDOR_ALIASES = {"ATTAIN": "ATAIN", "IGT": "ATAIN"}


def resolve_vendor_site(vendor, sites) -> str | None:
    """Resolve a dashboard vendor label to a forecast site name.

    Tolerant of case and spelling variants (Atain / ATTAIN / IGT all reach the
    ATAIN sheet), and any vendor whose name matches a site outright links
    automatically. Returns the site exactly as it appears in ``sites``, or
    None when the workbook has no sheet for this vendor (e.g. HERTZ).
    """
    v = str(vendor).strip().upper()
    v = _VENDOR_ALIASES.get(v, v)
    explicit = {k.upper(): s.upper() for k, s in FORECAST_VENDOR_SHEETS.items()}
    target = explicit.get(v, v)
    lookup = {str(s).strip().upper(): s for s in sites}
    return lookup.get(target)


def parse_daily_forecast(file) -> pd.DataFrame:
    """Read the Daily Forecast workbook into tidy rows: Site / Date / LOB / Forecast.

    Duplicated LOB headers (pandas renames the second one "Name.1") are folded
    back into the base LOB by summing. Blank forecast cells count as 0.
    """
    xl = pd.ExcelFile(file)
    frames = []
    for sheet in xl.sheet_names:
        raw = xl.parse(sheet)
        raw.columns = [str(c).strip() for c in raw.columns]
        # Hand-editing a workbook in Excel often stretches its "used range"
        # with blank rows/columns; melting those phantom cells can balloon
        # into millions of rows and OOM the server. Strip them first:
        # headerless ("Unnamed: N") and all-empty columns, then rows with
        # no parseable Date.
        raw = raw.drop(columns=[c for c in raw.columns if c.startswith("Unnamed")])
        raw = raw.dropna(axis=1, how="all")
        missing = [c for c in META_COLS if c not in raw.columns]
        if missing:
            raise ValueError(
                f"Sheet '{sheet}' doesn't look like a Daily Forecast sheet — "
                "missing column(s): " + ", ".join(missing)
            )
        raw = raw[pd.to_datetime(raw["Date"], errors="coerce").notna()]
        lob_cols = [c for c in raw.columns if c not in META_COLS]
        tidy = raw.melt(
            id_vars=META_COLS, value_vars=lob_cols,
            var_name="LOB", value_name="Forecast",
        )
        _site = sheet.strip()
        tidy["Site"] = SITE_RENAME.get(_site, _site)
        frames.append(tidy)

    df = pd.concat(frames, ignore_index=True)
    # Belt-and-braces: a plausible workbook is a few sites × ~1 year of days
    # × ~30 LOBs ≈ 50k rows. Anything far beyond that is a malformed file —
    # reject it cleanly rather than saving a poison pill to shared state.
    if len(df) > 250_000:
        raise ValueError(
            "This file expands to an implausible number of forecast rows "
            f"({len(df):,}). It is likely corrupted by stray cells — please "
            "copy the data into a fresh workbook and re-upload."
        )
    df["Date"] = pd.to_datetime(df["Date"], errors="coerce").dt.date
    df = df[df["Date"].notna()].copy()
    df["Week"] = pd.to_datetime(df["Week"], errors="coerce").dt.date
    df["Forecast"] = pd.to_numeric(df["Forecast"], errors="coerce").fillna(0.0)
    df["LOB"] = df["LOB"].str.replace(r"\.\d+$", "", regex=True).str.strip()

    df = df.groupby(["Site", "Date", "LOB"], as_index=False, sort=False).agg(
        Week=("Week", "first"),
        Weekday=("Weekday", "first"),
        Forecast=("Forecast", "sum"),
    )
    return df[["Site", "Date", "Week", "Weekday", "LOB", "Forecast"]]


def add_forecast_cols(
    df: pd.DataFrame,
    fc_df: pd.DataFrame,
    report_date,
    site: str,
    with_variance: bool = True,
    lob_map: dict = None,
) -> pd.DataFrame:
    """Add "Forecast Volume" and "Forecast Variance" columns.

    Forecast Volume is the forecast call volume itself for ``report_date``;
    Forecast Variance is how far actual offered ran over/under that volume,
    (NCO ÷ forecast − 1) × 100 — so +5% means 5% above forecast, −5% below.
    ``report_date`` may be a single date or a collection of dates: the actuals
    (NCO) are aggregated over every day in the loaded data, so when a
    multi-day range (e.g. a whole month) is loaded the forecast is summed
    across the same days — otherwise a month of actuals would be compared
    against a single day's forecast. ``fc_df`` is the tidy frame from
    :func:`parse_daily_forecast`; volumes come from ``site``'s sheet. LOBs with
    no forecast column (or zero forecast) show NaN. Pass ``with_variance=False``
    on a partial (intraday) day — the volume still shows but the variance
    column is left out. Columns that end up with no values at all (no forecast
    for the date, or variance withheld) are NOT added, so the tables only ever
    show them with real data. The Grand Total variance compares only the LOBs
    that have a forecast, so numerator and denominator cover the same lines of
    business.
    """
    if lob_map is None:
        lob_map = FORECAST_LOB_MAP
    out = df.copy()
    out["Forecast Volume"] = float("nan")
    out["Forecast Variance"] = float("nan")

    # ``report_date`` is either one date or a collection of them (the full set
    # of days the loaded actuals span). Normalise to a set so a month-long load
    # sums the forecast across every day, matching the aggregated actuals.
    if isinstance(report_date, str) or not hasattr(report_date, "__iter__"):
        report_dates = {report_date}
    else:
        report_dates = set(report_date)
    sel = fc_df[(fc_df["Site"] == site) & (fc_df["Date"].isin(report_dates))]
    if not sel.empty:
        # All name matching is case/whitespace-insensitive: "REX TNC",
        # "Rex TNC" and "rex tnc " are the same column, so nobody has to
        # hand-edit workbook headers to make them link up.
        vols: dict[str, float] = {}
        for _lob_name, _fc_val in zip(sel["LOB"], sel["Forecast"]):
            _k = str(_lob_name).strip().upper()
            vols[_k] = vols.get(_k, 0.0) + float(_fc_val)
        norm_map = {str(k).strip().upper(): v for k, v in lob_map.items()}
        vol_tot = var_fc = var_nco = 0.0
        for i, row in out.iterrows():
            lob = str(row.get("LOB", ""))
            if lob == "Grand Total":
                continue
            lob_key = lob.strip().upper()
            fc_cols = norm_map.get(lob_key)
            # Fallback: a forecast column with the LOB's name counts
            # toward it automatically — no mapping entry or link rule needed.
            if not fc_cols and lob_key in vols:
                fc_cols = [lob]
            if not fc_cols:
                continue
            fc = sum(vols.get(str(c).strip().upper(), 0.0) for c in fc_cols)
            if fc <= 0:
                continue
            out.at[i, "Forecast Volume"] = fc
            vol_tot += fc
            nco = row.get("NCO")
            if with_variance and pd.notna(nco):
                out.at[i, "Forecast Variance"] = (nco / fc - 1) * 100
                var_fc += fc
                var_nco += nco
        gt_mask = out["LOB"] == "Grand Total"
        if vol_tot > 0:
            out.loc[gt_mask, "Forecast Volume"] = vol_tot
        if var_fc > 0:
            out.loc[gt_mask, "Forecast Variance"] = (var_nco / var_fc - 1) * 100

    # Only keep columns that actually carry data; place them right after NCH
    keep = [c for c in ("Forecast Volume", "Forecast Variance") if out[c].notna().any()]
    out = out.drop(columns=[c for c in ("Forecast Volume", "Forecast Variance") if c not in keep])
    if keep:
        cols = list(out.columns)
        for c in keep:
            cols.remove(c)
        at = cols.index("NCH") + 1 if "NCH" in cols else len(cols)
        cols[at:at] = keep
        out = out[cols]
    return out


def forecast_pivot(df: pd.DataFrame) -> pd.DataFrame:
    """Date rows × LOB columns (workbook order) with a Total column and row."""
    lob_order = list(dict.fromkeys(df["LOB"]))
    pv = df.pivot_table(index="Date", columns="LOB", values="Forecast", aggfunc="sum")
    pv = pv.reindex(columns=lob_order).fillna(0.0)
    # Drop LOBs with no volume at all in the current selection
    pv = pv.loc[:, pv.sum() > 0]
    pv["Total"] = pv.sum(axis=1)
    pv = pv.round(0).sort_index()

    total_row = pv.sum().to_frame().T
    total_row.index = ["Total"]
    out = pv.copy()
    out.index = [d.strftime("%b %d, %Y (%a)") for d in out.index]
    out = pd.concat([out, total_row])
    out.insert(0, "Date", out.index)
    return out.reset_index(drop=True)
