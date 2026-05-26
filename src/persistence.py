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


def clear_custom_mapping() -> None:
    """Remove persisted mapping (revert to built-in)."""
    with _LOCK:
        _MAPPING_FILE.unlink(missing_ok=True)
        _MAPPING_DF_FILE.unlink(missing_ok=True)


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
