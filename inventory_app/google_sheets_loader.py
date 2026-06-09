import gspread
import os
import pandas as pd
import streamlit as st
from google.oauth2.service_account import Credentials

from inventory_app.config import SHEET_NAME_DEFAULTS
from inventory_app.excel_loader import BASE_COLUMNS, clean_base_sheet, clean_catalog_sheet


SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets.readonly",
    "https://www.googleapis.com/auth/drive.readonly",
]


@st.cache_resource
def get_gspread_client():
    if "gcp_service_account" not in st.secrets:
        raise RuntimeError(
            "Falta la seccion [gcp_service_account] en .streamlit/secrets.toml."
        )
    credentials = Credentials.from_service_account_info(
        dict(st.secrets["gcp_service_account"]),
        scopes=SCOPES,
    )
    return gspread.authorize(credentials)


def get_google_sheet_settings_from_secrets() -> dict[str, str]:
    settings = {
        "spreadsheet_id": "",
        "catalog_sheet": SHEET_NAME_DEFAULTS["catalog_sheet"],
        "entries_sheet": SHEET_NAME_DEFAULTS["entries_sheet"],
        "exits_sheet": SHEET_NAME_DEFAULTS["exits_sheet"],
    }
    if "google_sheets" not in st.secrets:
        return settings

    secret_values = st.secrets["google_sheets"]
    for key in settings:
        if key in secret_values:
            settings[key] = str(secret_values[key])
    return settings


def get_config_value(secret_section: str, key: str, env_key: str, default: str = "") -> str:
    try:
        if secret_section in st.secrets and key in st.secrets[secret_section]:
            return str(st.secrets[secret_section][key])
    except Exception:
        pass
    return str(os.getenv(env_key, default))


def get_google_sheet_settings(scope: str = "recuperacion") -> dict[str, str]:
    section_map = {
        "recuperacion": "google_sheets",
        "avimex": "google_sheets_avimex",
        "federal": "google_sheets_federal",
    }
    env_prefix_map = {
        "recuperacion": "RECOVERY",
        "avimex": "AVIMEX",
        "federal": "FEDERAL",
    }
    section = section_map.get(scope, "google_sheets")
    env_prefix = env_prefix_map.get(scope, scope.upper())
    defaults = {
        "spreadsheet_id": "",
        "catalog_sheet": SHEET_NAME_DEFAULTS["catalog_sheet"] if scope == "recuperacion" else "",
        "entries_sheet": SHEET_NAME_DEFAULTS["entries_sheet"] if scope == "recuperacion" else "",
        "exits_sheet": SHEET_NAME_DEFAULTS["exits_sheet"] if scope == "recuperacion" else "",
    }
    return {
        "spreadsheet_id": get_config_value(
            section, "spreadsheet_id", f"{env_prefix}_SPREADSHEET_ID", defaults["spreadsheet_id"]
        ),
        "catalog_sheet": get_config_value(
            section, "catalog_sheet", f"{env_prefix}_CATALOG_SHEET", defaults["catalog_sheet"]
        ),
        "entries_sheet": get_config_value(
            section, "entries_sheet", f"{env_prefix}_ENTRIES_SHEET", defaults["entries_sheet"]
        ),
        "exits_sheet": get_config_value(
            section, "exits_sheet", f"{env_prefix}_EXITS_SHEET", defaults["exits_sheet"]
        ),
    }


def load_sheet_dataframe(spreadsheet_id: str, worksheet_name: str) -> pd.DataFrame:
    if not worksheet_name:
        return pd.DataFrame()
    client = get_gspread_client()
    spreadsheet = client.open_by_key(spreadsheet_id)
    worksheet = spreadsheet.worksheet(worksheet_name)
    values = worksheet.get_all_values()
    if not values:
        return pd.DataFrame()
    header = values[0]
    rows = values[1:]
    if not rows:
        return pd.DataFrame(columns=header)
    return pd.DataFrame(rows, columns=header)


def load_sheet_matrix(spreadsheet_id: str, worksheet_name: str) -> pd.DataFrame:
    client = get_gspread_client()
    spreadsheet = client.open_by_key(spreadsheet_id)
    worksheet = spreadsheet.worksheet(worksheet_name)
    values = worksheet.get_all_values()
    if not values:
        return pd.DataFrame()
    return pd.DataFrame(values)


def list_google_worksheet_titles(spreadsheet_id: str) -> list[str]:
    client = get_gspread_client()
    spreadsheet = client.open_by_key(spreadsheet_id)
    return [worksheet.title for worksheet in spreadsheet.worksheets()]


def load_all_google_sheet_matrices(spreadsheet_id: str) -> dict[str, pd.DataFrame]:
    client = get_gspread_client()
    spreadsheet = client.open_by_key(spreadsheet_id)
    matrices: dict[str, pd.DataFrame] = {}
    for worksheet in spreadsheet.worksheets():
        values = worksheet.get_all_values()
        matrices[worksheet.title] = pd.DataFrame(values) if values else pd.DataFrame()
    return matrices


def load_google_sheet_frames(settings: dict[str, str]) -> dict[str, pd.DataFrame]:
    spreadsheet_id = settings.get("spreadsheet_id", "").strip()
    if not spreadsheet_id:
        raise RuntimeError("Falta el spreadsheet_id del Google Sheet.")

    catalog_raw = load_sheet_dataframe(spreadsheet_id, settings.get("catalog_sheet", ""))
    entries_raw = load_sheet_dataframe(spreadsheet_id, settings.get("entries_sheet", ""))
    exits_raw = load_sheet_dataframe(spreadsheet_id, settings.get("exits_sheet", ""))

    return {
        "catalogo": clean_catalog_sheet(catalog_raw) if not catalog_raw.empty else pd.DataFrame(),
        "entradas": clean_base_sheet(entries_raw) if not entries_raw.empty else pd.DataFrame(columns=BASE_COLUMNS),
        "salidas": clean_base_sheet(exits_raw) if not exits_raw.empty else pd.DataFrame(columns=BASE_COLUMNS),
    }
