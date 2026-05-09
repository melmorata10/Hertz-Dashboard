import io
import streamlit as st
import msal
import requests
import pandas as pd

_GRAPH = "https://graph.microsoft.com/v1.0"
_SCOPE = ["https://graph.microsoft.com/.default"]


def _get_token() -> str:
    cfg = st.secrets["sharepoint"]
    app = msal.ConfidentialClientApplication(
        client_id=cfg["client_id"],
        client_credential=cfg["client_secret"],
        authority=f"https://login.microsoftonline.com/{cfg['tenant_id']}",
    )
    result = app.acquire_token_for_client(scopes=_SCOPE)
    if "access_token" not in result:
        raise RuntimeError(f"MSAL auth failed: {result.get('error_description')}")
    return result["access_token"]


def _get_site_id(token: str, hostname: str, site_path: str) -> str:
    url = f"{_GRAPH}/sites/{hostname}:{site_path}"
    r = requests.get(url, headers={"Authorization": f"Bearer {token}"}, timeout=30)
    r.raise_for_status()
    return r.json()["id"]


def _get_drive_id(token: str, site_id: str) -> str:
    url = f"{_GRAPH}/sites/{site_id}/drive"
    r = requests.get(url, headers={"Authorization": f"Bearer {token}"}, timeout=30)
    r.raise_for_status()
    return r.json()["id"]


def _list_csv_items(token: str, drive_id: str, folder_path: str) -> list[dict]:
    path = folder_path.strip("/")
    if path:
        url = f"{_GRAPH}/drives/{drive_id}/root:/{path}:/children"
    else:
        url = f"{_GRAPH}/drives/{drive_id}/root/children"
    headers = {"Authorization": f"Bearer {token}"}
    items = []
    while url:
        r = requests.get(url, headers=headers, timeout=30)
        r.raise_for_status()
        data = r.json()
        items.extend(
            i for i in data.get("value", [])
            if i.get("name", "").lower().endswith(".csv")
        )
        url = data.get("@odata.nextLink")
    return items


def _download_csv(token: str, drive_id: str, item_id: str) -> pd.DataFrame:
    url = f"{_GRAPH}/drives/{drive_id}/items/{item_id}/content"
    r = requests.get(
        url,
        headers={"Authorization": f"Bearer {token}"},
        allow_redirects=True,
        timeout=60,
    )
    r.raise_for_status()
    return pd.read_csv(io.BytesIO(r.content))


@st.cache_data(ttl=300, show_spinner="Refreshing data from SharePoint…")
def load_all_csvs() -> pd.DataFrame:
    """Download and concatenate all CSV files from the configured SharePoint folder."""
    cfg = st.secrets["sharepoint"]
    token = _get_token()
    site_id = _get_site_id(token, cfg["site_hostname"], cfg["site_path"])
    drive_id = _get_drive_id(token, site_id)
    items = _list_csv_items(token, drive_id, cfg.get("folder_path", "/"))
    if not items:
        return pd.DataFrame()
    frames = [_download_csv(token, drive_id, item["id"]) for item in items]
    return pd.concat(frames, ignore_index=True)
