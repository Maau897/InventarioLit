from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent.parent
RECOVERY_WORKBOOK_PATH = BASE_DIR / "INVENTARIO_DE_ RECUPERACION_20_MAY_2026.xlsm"
MATERIALS_WORKBOOK_PATH = BASE_DIR / "Inventario_material_y_reactivos_21_Enero_2026.xlsx"
INDICATORS_WORKBOOK_PATH = BASE_DIR / "Indicadores de desempo de los almacenes.xlsx"
LOCAL_DATA_DIR = BASE_DIR / "data"
LOCAL_MOVEMENTS_PATH = LOCAL_DATA_DIR / "movimientos_app.csv"
LOCAL_REGULARIZATIONS_PATH = LOCAL_DATA_DIR / "regularizaciones_iniciales.csv"

DEFAULT_SCOPE = "lit"

INVENTORY_SCOPES = {
    "lit": "LIT",
    "frontera": "Frontera",
}

SHEET_NAME_DEFAULTS = {
    "catalog_sheet": "Base Vlookup",
    "entries_sheet": "Recepcion",
    "exits_sheet": "Salidas",
}
