"""Agent-level AHT views for the Roadside AHT export (Agent AHT tab)."""

import pandas as pd

# LineOfBusiness value in the export → site label shown on the dashboard.
# ROADSIDEPH teams are the Philippines site; all US roadside teams are Lubbock.
SITE_MAP = {
    "ROADSIDEPH": "Philippines",
    "ROADSIDE": "Lubbock, US",
    "US ROADSIDE": "Lubbock, US",
    "US RS": "Lubbock, US",
}

_REQUIRED = ["AgentName", "LineOfBusiness", "CallDate", "AHT-Inbound", "Handled", "No AHT"]


def parse_agent_aht(files) -> pd.DataFrame:
    """Read one or more Roadside AHT CSVs into tidy rows: Site / Agent / Date / Handled / HandleTime.

    Accepts a single file or a list of files; identical rows appearing in more
    than one upload (overlapping exports) are counted once. Rows flagged
    "Exclude" in the "No AHT" column carry no inbound AHT and are dropped, as
    are rows with zero handled calls.
    """
    if not isinstance(files, (list, tuple)):
        files = [files]

    frames = []
    for f in files:
        raw = pd.read_csv(f)
        raw.columns = raw.columns.str.strip()
        missing = [c for c in _REQUIRED if c not in raw.columns]
        if missing:
            raise ValueError(
                f"{getattr(f, 'name', 'File')} doesn't look like a Roadside AHT export — "
                "missing column(s): " + ", ".join(missing)
            )
        frames.append(raw)

    df = pd.concat(frames, ignore_index=True).drop_duplicates()

    df = df[df["No AHT"].astype(str).str.strip().str.lower() == "include"].copy()
    df["Handled"] = pd.to_numeric(df["Handled"], errors="coerce").fillna(0)
    df["AHT-Inbound"] = pd.to_numeric(df["AHT-Inbound"], errors="coerce")
    df = df[(df["Handled"] > 0) & df["AHT-Inbound"].notna()].copy()

    df["Date"] = pd.to_datetime(df["CallDate"], errors="coerce").dt.date
    df = df[df["Date"].notna()].copy()

    _lob = df["LineOfBusiness"].astype(str).str.strip()
    df["Site"] = _lob.str.upper().map(SITE_MAP).fillna(_lob)
    df["Agent"] = df["AgentName"].astype(str).str.strip().str.title()
    df["HandleTime"] = df["AHT-Inbound"] * df["Handled"]
    return df[["Site", "Agent", "Date", "Handled", "HandleTime"]]


def _pivot(df: pd.DataFrame, index_cols: list) -> pd.DataFrame:
    """Weighted AHT pivot: one row per index_cols combo, one column per date."""
    grp = (
        df.groupby(index_cols + ["Date"], as_index=False)
        .agg(Handled=("Handled", "sum"), HandleTime=("HandleTime", "sum"))
    )
    grp["AHT"] = grp["HandleTime"] / grp["Handled"]

    pivot = grp.pivot_table(index=index_cols, columns="Date", values="AHT")
    pivot = pivot.reindex(columns=sorted(df["Date"].unique()))
    pivot.columns = [d.strftime("%b %d") for d in pivot.columns]

    totals = df.groupby(index_cols).agg(
        Handled=("Handled", "sum"), HandleTime=("HandleTime", "sum")
    )
    pivot["Overall AHT"] = totals["HandleTime"] / totals["Handled"]
    pivot["Calls"] = totals["Handled"].astype(int)
    return pivot.round(1).reset_index()


def agent_aht_pivot(df: pd.DataFrame) -> pd.DataFrame:
    """AHT per agent per date, grouped by site."""
    return _pivot(df, ["Site", "Agent"]).sort_values(["Site", "Agent"]).reset_index(drop=True)


def site_aht_pivot(df: pd.DataFrame) -> pd.DataFrame:
    """AHT per site per date, with an All Sites total row."""
    out = _pivot(df, ["Site"])
    total = df.copy()
    total["Site"] = "All Sites"
    return pd.concat([out, _pivot(total, ["Site"])], ignore_index=True)
