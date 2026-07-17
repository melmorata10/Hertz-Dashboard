"""Continuous off-container backup of shared dashboard state.

Streamlit Cloud wipes the app's disk on every deploy/reboot. Every save of
shared state (mapping, targets, forecast, rules, comments) is therefore
mirrored to the Supabase project already used by the knowledge base, and a
fresh container restores any missing file at boot — making the wipe
invisible to users.

Fail-open by design: if the supabase package, the secrets, or the network
are unavailable, every call quietly no-ops and the app behaves exactly as
the old disk-only version. The backup layer must never be able to crash
the dashboard.

One-time setup (already agreed):
  - Supabase SQL editor:
        create table if not exists dashboard_state (
          app text not null, key text not null, payload jsonb,
          updated_at timestamptz default now(),
          primary key (app, key)
        );
  - The app's Streamlit secrets must contain the same [supabase] block the
    knowledge base uses (url + service_role_key).
"""

import json

# Backup namespace. The RTA dashboard (main branch) uses "rta"; the WBR
# variant (wbr branch) uses "wbr". They MUST differ so the two deployments
# never overwrite each other's state.
APP_ID = "wbr"

_TABLE = "dashboard_state"

_client_cache = None
_client_failed = False


def _client():
    """Lazily build (and cache) the Supabase client; None when unavailable."""
    global _client_cache, _client_failed
    if _client_cache is not None or _client_failed:
        return _client_cache
    try:
        import streamlit as st
        from supabase import create_client

        cfg = st.secrets["supabase"]
        _client_cache = create_client(cfg["url"], cfg["service_role_key"])
    except Exception:
        _client_failed = True
    return _client_cache


def backup_file(key: str, path) -> None:
    """Mirror one saved JSON state file to the backup table. Never raises."""
    try:
        c = _client()
        if c is None:
            return
        payload = json.loads(path.read_text(encoding="utf-8"))
        c.table(_TABLE).upsert(
            {"app": APP_ID, "key": key, "payload": payload}
        ).execute()
    except Exception:
        pass


def restore_file(key: str, path) -> bool:
    """Write the backed-up payload to ``path`` if a backup exists.

    Returns True when a file was restored. Never raises.
    """
    try:
        c = _client()
        if c is None:
            return False
        r = (
            c.table(_TABLE)
            .select("payload")
            .eq("app", APP_ID)
            .eq("key", key)
            .limit(1)
            .execute()
        )
        if not r.data or r.data[0].get("payload") is None:
            return False
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(r.data[0]["payload"], ensure_ascii=False),
            encoding="utf-8",
        )
        return True
    except Exception:
        return False


def delete_backup(key: str) -> None:
    """Remove a state blob from the backup — the user deleted it on purpose,
    so a later boot must not resurrect it. Never raises."""
    try:
        c = _client()
        if c is None:
            return
        c.table(_TABLE).delete().eq("app", APP_ID).eq("key", key).execute()
    except Exception:
        pass
