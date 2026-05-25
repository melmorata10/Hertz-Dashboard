"""
SharePoint connector — ROPC (Resource Owner Password Credentials) flow.

The RTA enters their Microsoft 365 credentials in the sidebar.
A Graph API token is acquired and used to list/download CSV files
from the configured SharePoint folder.

No Azure AD app registration is needed — this uses Microsoft's own
Azure CLI public client ID, which is pre-consented in most M365 tenants.

Limitations:
  • MFA must be disabled on the account (or an App Password used).
  • The tenant's Conditional Access must allow ROPC flows.
  • If your org blocks this, ask IT to register an app and add client_id
    + client_secret + tenant_id to [sharepoint] in Streamlit secrets.
"""

import io
import time

import msal
import pandas as pd
import requests
import streamlit as st

# ── Site config — parsed from the SharePoint URL the team provided ────────────
HOSTNAME    = "callinsite.sharepoint.com"
SITE_PATH   = "/sites/HertzWFM"
FOLDER_PATH = "Shared Documents/New Raw Data/Intraday Raw"

# Microsoft Azure CLI public client — pre-consented in most M365 tenants.
# Override via st.secrets["sharepoint"]["client_id"] if IT registered an app.
_CLI_CLIENT_ID = "04b07795-8ddb-461a-bbee-02f9e1bf7b46"
_GRAPH         = "https://graph.microsoft.com/v1.0"
_SCOPES        = ["https://graph.microsoft.com/.default"]
_TOKEN_BUFFER  = 300   # refresh 5 min before expiry


# ── Tenant auto-discovery ─────────────────────────────────────────────────────

def _discover_tenant_id() -> str:
    """Auto-discover tenant ID from the SharePoint hostname."""
    for domain in (HOSTNAME, HOSTNAME.replace(".sharepoint.com", ".onmicrosoft.com")):
        try:
            url = (
                f"https://login.microsoftonline.com/{domain}"
                f"/.well-known/openid-configuration"
            )
            r = requests.get(url, timeout=10)
            r.raise_for_status()
            # token_endpoint: .../login.microsoftonline.com/{tenant_id}/oauth2/v2.0/token
            parts = r.json().get("token_endpoint", "").split("/")
            if len(parts) >= 5:
                return parts[4]
        except Exception:
            continue
    raise RuntimeError(f"Could not auto-discover tenant ID for {HOSTNAME}")


# ── Token acquisition (ROPC) ──────────────────────────────────────────────────

def acquire_token(username: str, password: str) -> dict:
    """
    Sign in with Microsoft 365 credentials and return token info dict:
      {"access_token": str, "expires_at": float, "username": str}

    Raises RuntimeError with a user-friendly message on failure.
    """
    sp_cfg    = st.secrets.get("sharepoint", {})
    client_id = sp_cfg.get("client_id", _CLI_CLIENT_ID)
    tenant_id = sp_cfg.get("tenant_id") or _discover_tenant_id()

    app = msal.PublicClientApplication(
        client_id=client_id,
        authority=f"https://login.microsoftonline.com/{tenant_id}",
    )
    result = app.acquire_token_by_username_password(
        username=username,
        password=password,
        scopes=_SCOPES,
    )

    if "access_token" not in result:
        err = result.get("error_description") or result.get("error") or "Unknown error"
        # Surface a cleaner message for the most common failure modes
        if "AADSTS50076" in err or "MFA" in err.upper():
            raise RuntimeError(
                "Multi-factor authentication (MFA) is required for this account. "
                "Use an App Password instead of your regular password, or ask IT "
                "to register a service account without MFA for this tool."
            )
        if "AADSTS70011" in err:
            raise RuntimeError(
                "The requested scope is not supported. Ask IT to register an "
                "Azure AD app and provide Client ID + Client Secret."
            )
        if "AADSTS50126" in err:
            raise RuntimeError("Incorrect username or password. Please try again.")
        raise RuntimeError(err)

    return {
        "access_token": result["access_token"],
        "expires_at":   time.time() + result.get("expires_in", 3600),
        "username":     username,
    }


def get_valid_token() -> str | None:
    """Return current access token from session state if still valid, else None."""
    info = st.session_state.get("sp_token_info")
    if not info:
        return None
    if time.time() > info["expires_at"] - _TOKEN_BUFFER:
        return None   # expired — caller must re-authenticate
    return info["access_token"]


# ── Graph API helpers ─────────────────────────────────────────────────────────

def _hdr(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _get_site_id(token: str) -> str:
    r = requests.get(
        f"{_GRAPH}/sites/{HOSTNAME}:{SITE_PATH}",
        headers=_hdr(token), timeout=30,
    )
    r.raise_for_status()
    return r.json()["id"]


def _get_drive_id(token: str, site_id: str) -> str:
    r = requests.get(
        f"{_GRAPH}/sites/{site_id}/drive",
        headers=_hdr(token), timeout=30,
    )
    r.raise_for_status()
    return r.json()["id"]


def _list_csv_items(token: str, drive_id: str, folder_path: str) -> list[dict]:
    path = folder_path.strip("/")
    url  = f"{_GRAPH}/drives/{drive_id}/root:/{path}:/children"
    items = []
    while url:
        r = requests.get(url, headers=_hdr(token), timeout=30)
        r.raise_for_status()
        data = r.json()
        items.extend(
            i for i in data.get("value", [])
            if i.get("name", "").lower().endswith(".csv")
        )
        url = data.get("@odata.nextLink")
    return items


def _download_csv(token: str, drive_id: str, item_id: str) -> pd.DataFrame:
    r = requests.get(
        f"{_GRAPH}/drives/{drive_id}/items/{item_id}/content",
        headers=_hdr(token), allow_redirects=True, timeout=60,
    )
    r.raise_for_status()
    return pd.read_csv(io.BytesIO(r.content))


# ── Public loader ─────────────────────────────────────────────────────────────

def load_all_csvs(token: str, folder_path: str = FOLDER_PATH) -> pd.DataFrame:
    """
    Download and concatenate all CSV files from the SharePoint folder.
    Pass the access_token from session state (acquired via acquire_token()).
    """
    site_id  = _get_site_id(token)
    drive_id = _get_drive_id(token, site_id)
    items    = _list_csv_items(token, drive_id, folder_path)
    if not items:
        return pd.DataFrame()
    frames = [_download_csv(token, drive_id, i["id"]) for i in items]
    return pd.concat(frames, ignore_index=True)
