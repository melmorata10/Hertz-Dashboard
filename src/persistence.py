"""
Shared server-side persistence for the Hertz Dashboard.

All browser sessions read from and write to the same JSON files on disk.
This lets changes made by one RTA (mapping edits, analysis comments) be
visible to any other RTA who opens the app in a different browser tab.

Files live in  <repo-root>/data/  which is git-ignored so runtime state is
never committed.  The directory is created automatically on first write.
"""

import json
import threading
from pathlib import Path

import pandas as pd

_DATA_DIR = Path(__file__).resolve().parent.parent / "data"
_LOCK = threading.Lock()          # guard concurrent reads/writes

_COMMENTS_FILE   = _DATA_DIR / "lob_comments.json"
_MAPPING_FILE    = _DATA_DIR / "custom_mapping.json"
_MAPPING_DF_FILE = _DATA_DIR / "mapping_df.json"
_TARGETS_FILE    = _DATA_DIR / "custom_targets.json"
_FORECAST_FILE   = _DATA_DIR / "daily_forecast.json"
_RULES_FILE      = _DATA_DIR / "exception_rules.json"


def _ensure_dir() -> None:
    _DATA_DIR.mkdir(parents=True, exist_ok=True)


# ── Comments ──────────────────────────────────────────────────────────────────

def load_comments() -> dict:
    """Return saved lob_comments dict, or {} if none saved yet."""
    try:
        return json.loads(_COMMENTS_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_comments(comments: dict) -> None:
    """Persist the full lob_comments dict to disk."""
    _ensure_dir()
    with _LOCK:
        _COMMENTS_FILE.write_text(
            json.dumps(comments, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )


def clear_comments() -> None:
    """Remove persisted comments (e.g. when Clear Data is clicked)."""
    with _LOCK:
        _COMMENTS_FILE.unlink(missing_ok=True)


# ── Custom mapping ────────────────────────────────────────────────────────────

def load_custom_mapping() -> dict | None:
    """Return saved custom mapping dict, or None if not set."""
    try:
        data = json.loads(_MAPPING_FILE.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else None
    except Exception:
        return None


def save_custom_mapping(mapping: dict) -> None:
    """Persist the custom mapping dict to disk."""
    _ensure_dir()
    with _LOCK:
        _MAPPING_FILE.write_text(
            json.dumps(mapping, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )


def clear_custom_mapping() -> None:
    """Remove the persisted custom mapping (revert to built-in)."""
    with _LOCK:
        _MAPPING_FILE.unlink(missing_ok=True)


def load_mapping_df() -> pd.DataFrame | None:
    """Return the saved editable mapping DataFrame, or None."""
    try:
        records = json.loads(_MAPPING_DF_FILE.read_text(encoding="utf-8"))
        df = pd.DataFrame(records)
        for col in ("Skill ID", "Queue Name", "LOB", "Vendor"):
            if col not in df.columns:
                df[col] = ""
        return df[["Skill ID", "Queue Name", "LOB", "Vendor"]]
    except Exception:
        return None


def save_mapping_df(df: pd.DataFrame) -> None:
    """Persist the editable mapping DataFrame to disk."""
    _ensure_dir()
    with _LOCK:
        _MAPPING_DF_FILE.write_text(
            json.dumps(df.to_dict("records"), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )


def clear_mapping_df() -> None:
    """Remove the persisted editable mapping table (revert to built-in)."""
    with _LOCK:
        _MAPPING_DF_FILE.unlink(missing_ok=True)


def load_mapping_mtime() -> float:
    """Newest modification time across the two mapping files, or 0.0 if none
    exist — lets a session detect that another user applied, imported, or
    deleted the mapping and live-reload it."""
    mtime = 0.0
    for f in (_MAPPING_FILE, _MAPPING_DF_FILE):
        try:
            mtime = max(mtime, f.stat().st_mtime)
        except Exception:
            pass
    return mtime


# ── Custom targets ─────────────────────────────────────────────────────────────

def load_targets() -> dict | None:
    """Return saved custom targets dict, or None if not set.

    Format: {lob: {"aht": float, "asa": float, "abn": float (ratio 0–1)}}
    """
    try:
        data = json.loads(_TARGETS_FILE.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else None
    except Exception:
        return None


def save_targets(targets: dict) -> None:
    """Persist the custom targets dict to disk."""
    _ensure_dir()
    with _LOCK:
        _TARGETS_FILE.write_text(
            json.dumps(targets, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )


def clear_targets() -> None:
    """Remove persisted targets (revert to built-in)."""
    with _LOCK:
        _TARGETS_FILE.unlink(missing_ok=True)


def load_exception_rules() -> dict | None:
    """Return {"text": str | None, "rules": list} for the saved exception
    rules, or None if nothing is saved. Accepts the older list-only format."""
    try:
        data = json.loads(_RULES_FILE.read_text(encoding="utf-8"))
        if isinstance(data, dict) and isinstance(data.get("rules"), list):
            return {"text": data.get("text"), "rules": data["rules"]}
        if isinstance(data, list):
            return {"text": None, "rules": data}
        return None
    except Exception:
        return None


def save_exception_rules(text: str, rules: list) -> None:
    """Persist the rules text and its parsed form so every session shares them."""
    _ensure_dir()
    with _LOCK:
        _RULES_FILE.write_text(
            json.dumps({"text": text, "rules": rules}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )


def load_exception_rules_mtime() -> float:
    """Modification time of the saved rules, or 0.0 if absent — lets a session
    detect that another user applied new rules and live-reload them."""
    try:
        return _RULES_FILE.stat().st_mtime
    except Exception:
        return 0.0


def save_daily_forecast(df: pd.DataFrame, name: str) -> None:
    """Persist the parsed Daily Forecast frame so every session shares it."""
    _ensure_dir()
    payload = {
        "name": name,
        "records": df.assign(
            Date=df["Date"].astype(str),
            Week=df["Week"].astype(str),
        ).to_dict("records"),
    }
    with _LOCK:
        _FORECAST_FILE.write_text(
            json.dumps(payload, ensure_ascii=False),
            encoding="utf-8",
        )


def load_daily_forecast() -> tuple[pd.DataFrame, str] | None:
    """Return (forecast_df, source_filename) from disk, or None if not saved."""
    try:
        payload = json.loads(_FORECAST_FILE.read_text(encoding="utf-8"))
        df = pd.DataFrame(payload["records"])
        df["Date"] = pd.to_datetime(df["Date"], errors="coerce").dt.date
        df["Week"] = pd.to_datetime(df["Week"], errors="coerce").dt.date
        df["Forecast"] = pd.to_numeric(df["Forecast"], errors="coerce").fillna(0.0)
        df = df[df["Date"].notna()].reset_index(drop=True)
        if df.empty:
            return None
        return df, str(payload.get("name", "Daily Forecast"))
    except Exception:
        return None


def clear_daily_forecast() -> None:
    """Remove the persisted Daily Forecast."""
    with _LOCK:
        _FORECAST_FILE.unlink(missing_ok=True)


def load_daily_forecast_mtime() -> float:
    """Modification time of the saved forecast, or 0.0 if absent — lets a
    session detect that another user uploaded a new forecast and live-reload."""
    try:
        return _FORECAST_FILE.stat().st_mtime
    except Exception:
        return 0.0


def load_targets_mtime() -> float:
    """Return the file-modification time of the targets file, or 0.0 if absent.

    Used by app.py to detect when another session has saved new targets so the
    current session can live-reload without requiring a browser refresh.
    """
    try:
        return _TARGETS_FILE.stat().st_mtime
    except Exception:
        return 0.0


# ── Full-state backup / restore ────────────────────────────────────────────────
# Every piece of persisted state EXCEPT the raw daily CSVs (which live only in
# per-session memory and are never written to disk).  Lets an operator snapshot
# all shared configuration before a deploy and restore it afterward, so a
# container rebuild on Streamlit Cloud can never lose mapping/targets/comments/
# rules/forecast.

BACKUP_VERSION = 1

_BACKUP_FILES = {
    "lob_comments":    _COMMENTS_FILE,
    "custom_mapping":  _MAPPING_FILE,
    "mapping_df":      _MAPPING_DF_FILE,
    "custom_targets":  _TARGETS_FILE,
    "daily_forecast":  _FORECAST_FILE,
    "exception_rules": _RULES_FILE,
}


def export_all() -> dict:
    """Bundle all persisted state into one JSON-serialisable dict.

    Keys with no saved file are recorded as None.  Raw CSV data is never
    included — it is not persisted to disk in the first place.
    """
    bundle: dict = {"_backup_version": BACKUP_VERSION}
    with _LOCK:
        for key, f in _BACKUP_FILES.items():
            try:
                bundle[key] = json.loads(f.read_text(encoding="utf-8"))
            except Exception:
                bundle[key] = None
    return bundle


def import_all(bundle: dict) -> list[str]:
    """Restore persisted state from a dict produced by :func:`export_all`.

    Only keys that are present and non-null are written, so a partial backup
    never clobbers state it does not mention.  Returns the list of restored
    keys.  Raises ``ValueError`` if the payload is not a recognised backup.
    """
    if not isinstance(bundle, dict):
        raise ValueError("Backup must be a JSON object.")
    if not (set(bundle) & set(_BACKUP_FILES)):
        raise ValueError("File does not look like a dashboard backup.")

    _ensure_dir()
    restored: list[str] = []
    with _LOCK:
        for key, f in _BACKUP_FILES.items():
            if key not in bundle or bundle[key] is None:
                continue
            f.write_text(
                json.dumps(bundle[key], ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            restored.append(key)
    return restored
