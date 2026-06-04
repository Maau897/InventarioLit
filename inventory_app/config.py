from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent.parent
RECOVERY_WORKBOOK_PATH = BASE_DIR / "INVENTARIO_DE_ RECUPERACION_20_MAY_2026.xlsm"
MATERIALS_WORKBOOK_PATH = BASE_DIR / "Inventario_material_y_reactivos_21_Enero_2026.xlsx"
LOCAL_DATA_DIR = BASE_DIR / "data"
LOCAL_MOVEMENTS_PATH = LOCAL_DATA_DIR / "movimientos_app.csv"

DEFAULT_SCOPE = "recuperacion"

INVENTORY_SCOPES = {
    "recuperacion": "Recuperacion",
    "avimex": "Avimex",
    "federal": "Federal / general",
}

SHEET_NAME_DEFAULTS = {
    "catalog_sheet": "Base Vlookup",
    "entries_sheet": "Recepcion",
    "exits_sheet": "Salidas",
}
