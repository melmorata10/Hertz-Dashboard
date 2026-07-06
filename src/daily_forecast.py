"""Daily Forecast workbook parsing (Daily Forecast tab)."""

import pandas as pd

# Every sheet in the workbook is one site/vendor (Consolidated, VXI, TELUS,
# IGT, …). These columns describe the calendar; every remaining column is a
# line of business holding the forecast call volume for that date.
META_COLS = ["Year", "Month", "Week", "Date", "Weekday"]

# Dashboard LOB name → forecast workbook column(s) whose volumes make it up.
# LOBs missing here (BRST, CONFO, Roadside Lite, OPERATIONS) have no forecast
# column and show "—" for OTF % / HTF %.
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
    "Executive Customer Services": ["CUSTOMER SPECIAL SERVICES DEPARTMENT"],
    "Roadside Services":           ["Roadside Hertz", "Roadside - Dollar Thrifty"],
    "Vehicle Control":             ["Vehicle Control"],
    "Rental Extensions":           ["REX Retail"],
    "TNC Rental Extension":        ["Rex TNC"],
    "Damage":                      ["Damage"],
    "MultiMonth":                  ["SRP"],
}

# Vendor table on the dashboard → sheet in the forecast workbook.
# The main (all-vendor) table uses the Consolidated sheet; ATAIN and HERTZ
# have no sheet in the workbook so their tables show "—".
FORECAST_VENDOR_SHEETS = {
    "TELUS": "TELUS",
    "VXI":   "VXI",
}


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
        missing = [c for c in META_COLS if c not in raw.columns]
        if missing:
            raise ValueError(
                f"Sheet '{sheet}' doesn't look like a Daily Forecast sheet — "
                "missing column(s): " + ", ".join(missing)
            )
        lob_cols = [c for c in raw.columns if c not in META_COLS]
        tidy = raw.melt(
            id_vars=META_COLS, value_vars=lob_cols,
            var_name="LOB", value_name="Forecast",
        )
        tidy["Site"] = sheet.strip()
        frames.append(tidy)

    df = pd.concat(frames, ignore_index=True)
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


def add_forecast_pct(df: pd.DataFrame, fc_df: pd.DataFrame, report_date, site: str) -> pd.DataFrame:
    """Add "OTF %" and "HTF %" columns: actual volume ÷ forecast volume × 100.

    OTF = Offered-to-Forecast (NCO ÷ forecast), HTF = Handled-to-Forecast
    (NCH ÷ forecast). ``fc_df`` is the tidy frame from
    :func:`parse_daily_forecast`; the forecast volume for each LOB is taken
    from ``site``'s sheet on ``report_date``. LOBs with no forecast column
    (or zero forecast) show NaN. The Grand Total row compares only the LOBs
    that have a forecast, so numerator and denominator cover the same lines
    of business.
    """
    out = df.copy()
    out["OTF %"] = float("nan")
    out["HTF %"] = float("nan")

    sel = fc_df[(fc_df["Site"] == site) & (fc_df["Date"] == report_date)]
    if not sel.empty:
        vols = dict(zip(sel["LOB"], sel["Forecast"]))
        tot_fc = tot_nco = tot_nch = 0.0
        for i, row in out.iterrows():
            lob = str(row.get("LOB", ""))
            fc_cols = FORECAST_LOB_MAP.get(lob)
            if lob == "Grand Total" or not fc_cols:
                continue
            fc = sum(vols.get(c, 0.0) for c in fc_cols)
            nco, nch = row.get("NCO"), row.get("NCH")
            if fc <= 0 or pd.isna(nco):
                continue
            out.at[i, "OTF %"] = nco / fc * 100
            tot_fc += fc
            tot_nco += nco
            if pd.notna(nch):
                out.at[i, "HTF %"] = nch / fc * 100
                tot_nch += nch
        if tot_fc > 0:
            gt_mask = out["LOB"] == "Grand Total"
            out.loc[gt_mask, "OTF %"] = tot_nco / tot_fc * 100
            out.loc[gt_mask, "HTF %"] = tot_nch / tot_fc * 100

    # Keep the new columns right after NCH (matters for CSV export order)
    cols = list(out.columns)
    for c in ("OTF %", "HTF %"):
        cols.remove(c)
    if "NCH" in cols:
        at = cols.index("NCH") + 1
        cols[at:at] = ["OTF %", "HTF %"]
    else:
        cols += ["OTF %", "HTF %"]
    return out[cols]


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
