from pathlib import Path
import re
import unicodedata
from urllib.parse import quote_plus

import pandas as pd


BASE_COLUMNS = [
    "id_registro",
    "codigo_local",
    "codigo",
    "descripcion",
    "catalogo",
    "marca",
    "lote",
    "cantidad",
    "unidad",
    "caducidad",
    "ubicacion",
    "categoria",
    "fecha",
    "responsable",
]

CANONICAL_ALIASES = {
    "id_de_entrada": "id_registro",
    "id_de_salida": "id_registro",
    "codigo": "codigo",
    "sku": "codigo",
    "sku_catalogo": "codigo",
    "catalogo_de_producto_sku": "codigo",
    "clave": "codigo",
    "descripcion": "descripcion",
    "descripcion_del_producto": "descripcion",
    "descripcion_del_producto_": "descripcion",
    "producto": "descripcion",
    "nombre": "descripcion",
    "nombre_del_producto": "descripcion",
    "nombre_del_material": "descripcion",
    "nombre_del_reactivo": "descripcion",
    "material": "descripcion",
    "catalogo": "catalogo",
    "numero_de_catalogo": "codigo",
    "numero_de_catalogo_": "codigo",
    "numero_catalogo": "catalogo",
    "no_catalogo": "catalogo",
    "referencia": "catalogo",
    "marca": "marca",
    "lote": "lote",
    "cantidad": "cantidad",
    "cantidad_ingresada": "cantidad",
    "cantidad_retirada": "cantidad",
    "cantidad_inventario": "cantidad",
    "cantidad_contada": "cantidad",
    "cantidad_existencia": "cantidad",
    "existencia": "cantidad",
    "existencia_total": "cantidad",
    "existencia_por_marca": "cantidad",
    "unidad": "unidad",
    "unidad_ingresada": "unidad",
    "unidad_retirada": "unidad",
    "unidad_inventario": "unidad",
    "unidad_contada": "unidad",
    "unidad_de_medida": "unidad",
    "presentacion": "unidad",
    "caducidad": "caducidad",
    "fecha_de_caducidad": "caducidad",
    "fecha_de_caducidad_": "caducidad",
    "ubicacion": "ubicacion",
    "ubicacion_reducida": "ubicacion",
    "ubicacion_actual": "ubicacion",
    "categoria": "categoria",
    "material_reactivo": "categoria",
    "tipo": "categoria",
    "fecha": "fecha",
    "fecha_de_entrada": "fecha",
    "fecha_de_salida": "fecha",
    "fecha_de_conteo": "fecha",
    "id_del_conteo": "id_conteo",
    "almacen": "almacen",
    "recibio": "responsable",
    "registrado_por": "responsable",
    "responsable": "responsable",
    "realizo": "responsable",
    "nombre_del_contador": "responsable",
    "iniciales": "responsable",
    "numero": "codigo_local",
    "numero_": "codigo_local",
}


def normalize_label(value: object) -> str:
    text = "" if value is None else str(value)
    text = text.strip().lower().replace("\n", " ")
    text = unicodedata.normalize("NFKD", text)
    text = "".join(char for char in text if not unicodedata.combining(char))
    normalized = []
    for char in text:
        normalized.append(char if char.isalnum() else "_")
    text = "".join(normalized)
    while "__" in text:
        text = text.replace("__", "_")
    return text.strip("_")


def normalize_match_key(value: object) -> str:
    text = "" if value is None else str(value)
    text = text.strip().upper()
    normalized = []
    for char in text:
        if char.isalnum():
            normalized.append(char)
    return "".join(normalized)


def _normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    df.columns = [normalize_label(column) for column in df.columns]
    return df


def _coerce_base_columns(df: pd.DataFrame) -> pd.DataFrame:
    original_df = df.copy()
    original_columns_normalized = [normalize_label(column) for column in original_df.columns]

    rename_map = {}
    for column in df.columns:
        canonical = CANONICAL_ALIASES.get(column)
        if canonical:
            rename_map[column] = canonical
    df = df.rename(columns=rename_map)

    if "codigo" in original_columns_normalized and "codigo_local" not in df.columns:
        original_codigo_col = original_df.columns[original_columns_normalized.index("codigo")]
        df["codigo_local"] = original_df[original_codigo_col]

    if "catalogo" not in df.columns and "codigo" in df.columns:
        df["catalogo"] = df["codigo"]

    if "codigo" not in df.columns and "catalogo" in df.columns:
        df["codigo"] = df["catalogo"]

    missing = [column for column in BASE_COLUMNS if column not in df.columns]
    for column in missing:
        df[column] = None
    return df[BASE_COLUMNS].copy()


def _empty_base_df() -> pd.DataFrame:
    return pd.DataFrame(columns=BASE_COLUMNS)


def _clean_strings(df: pd.DataFrame, columns: list[str]) -> pd.DataFrame:
    for column in columns:
        df[column] = df[column].fillna("").astype(str).str.strip()
    return df


def clean_base_sheet(df: pd.DataFrame) -> pd.DataFrame:
    df = _normalize_columns(df.copy())
    df = _coerce_base_columns(df)
    df = df.dropna(how="all")
    df["codigo"] = df["codigo"].fillna("").astype(str).str.strip()
    df["catalogo"] = df["catalogo"].fillna("").astype(str).str.strip()
    df["codigo_local"] = df["codigo_local"].fillna("").astype(str).str.strip()
    df["id_registro"] = df["id_registro"].fillna("").astype(str).str.strip()
    df["cantidad"] = pd.to_numeric(df["cantidad"], errors="coerce").fillna(0)
    df["categoria"] = (
        df["categoria"]
        .fillna("")
        .astype(str)
        .str.upper()
        .str.strip()
        .replace({"M": "MATERIAL", "R": "REACTIVO"})
    )
    df["fecha"] = pd.to_datetime(df["fecha"], errors="coerce")
    df = _clean_strings(
        df,
        [
            "descripcion",
            "marca",
            "lote",
            "unidad",
            "caducidad",
            "ubicacion",
            "responsable",
        ],
    )
    df["codigo"] = df["catalogo"].where(df["catalogo"] != "", df["codigo"])
    df = df.loc[df["codigo"] != ""].copy()
    return df


def clean_catalog_sheet(df: pd.DataFrame) -> pd.DataFrame:
    df = _normalize_columns(df.copy())
    if "catalogo" in df.columns and "codigo" not in df.columns:
        df["codigo"] = df["catalogo"]
    if "descripcion" not in df.columns and "descripcion_del_producto" in df.columns:
        df["descripcion"] = df["descripcion_del_producto"]
    df = _coerce_base_columns(df)
    df["codigo"] = df["codigo"].fillna("").astype(str).str.strip()
    df["catalogo"] = df["catalogo"].fillna("").astype(str).str.strip()
    df["codigo_local"] = df["codigo_local"].fillna("").astype(str).str.strip()
    df = _clean_strings(
        df,
        ["descripcion", "marca", "lote", "unidad", "caducidad", "ubicacion", "categoria"],
    )
    df["categoria"] = df["categoria"].str.upper().replace({"M": "MATERIAL", "R": "REACTIVO"})
    df["codigo"] = df["catalogo"].where(df["catalogo"] != "", df["codigo"])
    df = df.loc[df["codigo"] != ""].copy()
    catalog = df[
        [
            "codigo",
            "codigo_local",
            "descripcion",
            "catalogo",
            "marca",
            "lote",
            "unidad",
            "caducidad",
            "ubicacion",
            "categoria",
        ]
    ].copy()
    catalog = catalog.sort_values(["descripcion", "codigo"]).drop_duplicates("codigo", keep="first")
    return catalog


def harmonize_transaction_keys(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    if df.empty:
        return _empty_base_df()
    catalog_key = df["catalogo"].fillna("").astype(str).map(normalize_match_key)
    code_key = df["codigo"].fillna("").astype(str).map(normalize_match_key)
    df["codigo"] = catalog_key.where(catalog_key != "", code_key)
    df["catalogo"] = df["catalogo"].fillna("").astype(str).str.strip().where(
        df["catalogo"].fillna("").astype(str).str.strip() != "",
        df["codigo"],
    )
    df["codigo_local"] = df["codigo_local"].fillna("").astype(str).str.strip()
    return df.loc[df["codigo"] != ""].copy()


def _movement_rows(movements_df: pd.DataFrame, movement_type: str) -> pd.DataFrame:
    if movements_df.empty:
        return _empty_base_df()
    filtered = movements_df.loc[movements_df["movement_type"] == movement_type].copy()
    if filtered.empty:
        return _empty_base_df()
    filtered["fecha"] = pd.to_datetime(filtered["fecha"], errors="coerce")
    filtered["cantidad"] = pd.to_numeric(filtered["cantidad"], errors="coerce").fillna(0)
    filtered["id_registro"] = filtered["id_registro"].fillna("").astype(str).str.strip()
    filtered["codigo_local"] = filtered["codigo_local"].fillna("").astype(str).str.strip()
    filtered["codigo"] = filtered["codigo"].fillna("").astype(str).str.strip()
    filtered["catalogo"] = filtered["catalogo"].fillna("").astype(str).str.strip()
    filtered = filtered.loc[filtered["codigo"] != ""].copy()
    for column in BASE_COLUMNS:
        if column not in filtered.columns:
            filtered[column] = None
    return filtered[BASE_COLUMNS]


def _catalog_from_movements(entry_df: pd.DataFrame, exit_df: pd.DataFrame) -> pd.DataFrame:
    frames = [df for df in [entry_df, exit_df] if df is not None and not df.empty]
    if not frames:
        return pd.DataFrame(
            columns=[
                "codigo",
                "codigo_local",
                "descripcion",
                "catalogo",
                "marca",
                "lote",
                "unidad",
                "caducidad",
                "ubicacion",
                "categoria",
            ]
        )
    combined = pd.concat(frames, ignore_index=True)
    combined["fecha"] = pd.to_datetime(combined["fecha"], errors="coerce")
    combined = combined.sort_values("fecha", ascending=False, na_position="last")
    catalog = combined.groupby("codigo", as_index=False).first()
    return catalog[
        [
            "codigo",
            "codigo_local",
            "descripcion",
            "catalogo",
            "marca",
            "lote",
            "unidad",
            "caducidad",
            "ubicacion",
            "categoria",
        ]
    ].sort_values("descripcion")


def build_catalog_options(catalog_df: pd.DataFrame) -> list[str]:
    options = ["Nuevo insumo"]
    for _, row in catalog_df.sort_values("descripcion").iterrows():
        description = row["descripcion"] or row["catalogo"] or row["marca"] or "Sin descripcion"
        options.append(f"{row['codigo']} - {description}")
    return options


def build_inventory_snapshot(
    source_entries: pd.DataFrame,
    source_exits: pd.DataFrame,
    app_movements: pd.DataFrame,
    catalog_df: pd.DataFrame | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    app_entries = _movement_rows(app_movements, "entrada")
    app_exits = _movement_rows(app_movements, "salida")

    entry_df = pd.concat([source_entries, app_entries], ignore_index=True)
    exit_df = pd.concat([source_exits, app_exits], ignore_index=True)
    entry_df["fecha"] = pd.to_datetime(entry_df["fecha"], errors="coerce")
    exit_df["fecha"] = pd.to_datetime(exit_df["fecha"], errors="coerce")
    entry_df["cantidad"] = pd.to_numeric(entry_df["cantidad"], errors="coerce").fillna(0)
    exit_df["cantidad"] = pd.to_numeric(exit_df["cantidad"], errors="coerce").fillna(0)
    movement_catalog_df = _catalog_from_movements(entry_df, exit_df)

    if catalog_df is None or catalog_df.empty:
        catalog_df = movement_catalog_df
    else:
        catalog_df = clean_catalog_sheet(catalog_df)
        catalog_df = catalog_df.merge(
            movement_catalog_df[
                [
                    "codigo",
                    "codigo_local",
                    "lote",
                    "unidad",
                    "caducidad",
                    "ubicacion",
                    "categoria",
                ]
            ],
            on="codigo",
            how="left",
            suffixes=("", "_mov"),
        )
        for column in ["codigo_local", "lote", "unidad", "caducidad", "ubicacion", "categoria"]:
            catalog_df[column] = catalog_df[column].where(
                catalog_df[column].fillna("").astype(str).str.strip() != "",
                catalog_df[f"{column}_mov"],
            )
        catalog_df = catalog_df.drop(
            columns=[
                "codigo_local_mov",
                "lote_mov",
                "unidad_mov",
                "caducidad_mov",
                "ubicacion_mov",
                "categoria_mov",
            ]
        )

    entry_totals = entry_df.groupby("codigo", as_index=False)["cantidad"].sum().rename(
        columns={"cantidad": "entrada"}
    )
    exit_totals = exit_df.groupby("codigo", as_index=False)["cantidad"].sum().rename(
        columns={"cantidad": "salida"}
    )
    inventory_df = catalog_df.merge(entry_totals, on="codigo", how="left").merge(
        exit_totals, on="codigo", how="left"
    )
    inventory_df["entrada"] = inventory_df["entrada"].fillna(0)
    inventory_df["salida"] = inventory_df["salida"].fillna(0)
    inventory_df["existencia"] = inventory_df["entrada"] - inventory_df["salida"]
    inventory_df = inventory_df[
        [
            "codigo",
            "codigo_local",
            "descripcion",
            "catalogo",
            "marca",
            "lote",
            "unidad",
            "caducidad",
            "ubicacion",
            "categoria",
            "entrada",
            "salida",
            "existencia",
        ]
    ].sort_values(["categoria", "descripcion", "codigo"])
    return inventory_df, entry_df, exit_df, catalog_df


def clean_registry_sheet(df: pd.DataFrame) -> pd.DataFrame:
    df = _normalize_columns(df.copy())
    df = df.rename(
        columns={
            "id_del_conteo": "id_conteo",
            "fecha_de_conteo": "fecha_conteo",
            "almacen": "almacen",
            "nombre_del_contador": "contador",
            "nombre_del_verificador": "verificador",
        }
    )
    expected = ["id_conteo", "fecha_conteo", "almacen", "contador", "verificador"]
    for column in expected:
        if column not in df.columns:
            df[column] = None
    df["id_conteo"] = df["id_conteo"].fillna("").astype(str).str.strip()
    df["fecha_conteo"] = pd.to_datetime(df["fecha_conteo"], errors="coerce")
    df = _clean_strings(df, ["almacen", "contador", "verificador"])
    return df.loc[df["id_conteo"] != "", expected].copy()


def clean_count_results_sheet(df: pd.DataFrame) -> pd.DataFrame:
    df = _normalize_columns(df.copy())
    df = df.rename(
        columns={
            "id_del_conteo": "id_conteo",
            "catalogo_de_producto_sku": "codigo",
            "descripcion": "descripcion",
            "marca": "marca",
            "ubicacion_reducida": "ubicacion",
            "cantidad_inventario": "cantidad_inventario",
            "cantidad_contada": "cantidad_contada",
            "unidad_contada": "unidad",
            "lote": "lote",
            "fecha_de_caducidad": "caducidad",
            "comentarios": "comentarios",
        }
    )
    expected = [
        "id_conteo",
        "codigo",
        "descripcion",
        "marca",
        "ubicacion",
        "cantidad_inventario",
        "cantidad_contada",
        "unidad",
        "lote",
        "caducidad",
        "comentarios",
    ]
    for column in expected:
        if column not in df.columns:
            df[column] = None
    df = _clean_strings(
        df,
        ["id_conteo", "codigo", "descripcion", "marca", "ubicacion", "unidad", "lote", "caducidad", "comentarios"],
    )
    df["cantidad_inventario"] = pd.to_numeric(df["cantidad_inventario"], errors="coerce")
    df["cantidad_contada"] = pd.to_numeric(df["cantidad_contada"], errors="coerce")
    return df.loc[df["codigo"] != "", expected].copy()


def enrich_inventory_with_counts(
    inventory_df: pd.DataFrame,
    registry_df: pd.DataFrame,
    results_df: pd.DataFrame,
) -> pd.DataFrame:
    if registry_df.empty or results_df.empty:
        return inventory_df.copy()

    merged = results_df.merge(registry_df, on="id_conteo", how="left")
    merged = merged.sort_values("fecha_conteo", ascending=False)
    latest = merged.groupby("codigo", as_index=False).first()
    latest = latest.rename(
        columns={
            "ubicacion": "ubicacion_reducida",
            "lote": "lote_conteo",
            "caducidad": "caducidad_conteo",
        }
    )
    enriched = inventory_df.merge(
        latest[["codigo", "ubicacion_reducida", "lote_conteo", "caducidad_conteo"]],
        on="codigo",
        how="left",
    )
    enriched["ubicacion_reducida"] = enriched["ubicacion_reducida"].fillna("")
    enriched["lote_conteo"] = enriched["lote_conteo"].fillna("")
    enriched["caducidad_conteo"] = enriched["caducidad_conteo"].fillna("")
    enriched["ubicacion"] = enriched["ubicacion_reducida"].where(
        enriched["ubicacion_reducida"] != "",
        enriched["ubicacion"],
    )
    enriched["lote"] = enriched["lote_conteo"].where(
        enriched["lote_conteo"] != "",
        enriched["lote"],
    )
    enriched["caducidad"] = enriched["caducidad_conteo"].where(
        enriched["caducidad_conteo"] != "",
        enriched["caducidad"],
    )
    return enriched[
        [
            "codigo",
            "codigo_local",
            "descripcion",
            "catalogo",
            "marca",
            "lote",
            "unidad",
            "caducidad",
            "ubicacion",
            "categoria",
            "entrada",
            "salida",
            "existencia",
        ]
    ]


def build_product_search_links(row: pd.Series) -> dict[str, str]:
    codigo = str(row.get("codigo", "")).strip()
    descripcion = str(row.get("descripcion", "")).strip()
    marca = str(row.get("marca", "")).strip()
    terms = " ".join(part for part in [codigo, descripcion, marca] if part)
    query = quote_plus(terms)
    official_query = quote_plus(" ".join(part for part in [marca, codigo] if part))
    return {
        "google": f"https://www.google.com/search?q={query}",
        "proveedor": f"https://www.google.com/search?q={official_query}+site%3A.com",
    }


def combine_catalogs(preferred_catalog: pd.DataFrame, secondary_catalog: pd.DataFrame) -> pd.DataFrame:
    frames = []
    for source_df in [preferred_catalog, secondary_catalog]:
        if source_df is None or source_df.empty:
            continue
        df = clean_catalog_sheet(source_df.copy())
        df["codigo"] = df["codigo"].map(normalize_match_key)
        df["catalogo"] = df["catalogo"].fillna("").astype(str).str.strip().where(
            df["catalogo"].fillna("").astype(str).str.strip() != "",
            df["codigo"],
        )
        frames.append(df.loc[df["codigo"] != ""])
    if not frames:
        return pd.DataFrame()
    combined = pd.concat(frames, ignore_index=True)
    combined = combined.sort_values(["descripcion", "codigo"]).drop_duplicates("codigo", keep="first")
    return combined


def load_workbook_frames(workbook_path: Path) -> dict[str, pd.DataFrame]:
    entradas = pd.read_excel(workbook_path, sheet_name="Entradas", usecols="A:L")
    salidas = pd.read_excel(workbook_path, sheet_name="Salidas", usecols="A:L")
    entry_df = harmonize_transaction_keys(clean_base_sheet(entradas))
    exit_df = harmonize_transaction_keys(clean_base_sheet(salidas))
    catalog_df = _catalog_from_movements(entry_df, exit_df)
    return {
        "entradas": entry_df,
        "salidas": exit_df,
        "catalogo": catalog_df,
    }


def _base_from_records(records: list[dict[str, object]]) -> pd.DataFrame:
    if not records:
        return _empty_base_df()
    df = pd.DataFrame(records)
    for column in BASE_COLUMNS:
        if column not in df.columns:
            df[column] = None
    df = df[BASE_COLUMNS]
    return clean_base_sheet(df)


def _parse_leading_quantity(value: object) -> float:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return 0.0
    text = str(value).strip().replace(",", ".")
    match = re.search(r"(\d+(?:\.\d+)?)", text)
    return float(match.group(1)) if match else 0.0


def _format_avimex_entries(df: pd.DataFrame) -> pd.DataFrame:
    records = []
    for _, row in df.iterrows():
        records.append(
            {
                "id_registro": "",
                "codigo_local": row.get("Número", ""),
                "codigo": row.get("Referencia", "") or row.get("Número", ""),
                "descripcion": row.get("Nombre del material", ""),
                "catalogo": row.get("Referencia", ""),
                "marca": row.get("Marca", ""),
                "lote": "",
                "cantidad": row.get("Existencia", 0),
                "unidad": row.get("Presentación", ""),
                "caducidad": "",
                "ubicacion": "",
                "categoria": "MATERIAL",
                "fecha": None,
                "responsable": "",
            }
        )
    return harmonize_transaction_keys(_base_from_records(records))


def _format_inventory_final_entries(df: pd.DataFrame, budget_mask: pd.Series, default_category: str = "MATERIAL") -> pd.DataFrame:
    filtered = df.loc[budget_mask].copy()
    records = []
    for _, row in filtered.iterrows():
        quantity = row.get("EXISTENCIA POR MARCA", 0)
        if pd.isna(quantity):
            quantity = row.get("EXISTENCIA TOTAL", 0)
        records.append(
            {
                "id_registro": "",
                "codigo_local": "",
                "codigo": row.get("CATALOGO", ""),
                "descripcion": row.get("MATERIAL", ""),
                "catalogo": row.get("CATALOGO", ""),
                "marca": row.get("MARCA", ""),
                "lote": "",
                "cantidad": quantity,
                "unidad": row.get("PRESENTACIÓN", ""),
                "caducidad": "",
                "ubicacion": "",
                "categoria": default_category,
                "fecha": None,
                "responsable": "",
            }
        )
    return harmonize_transaction_keys(_base_from_records(records))


def _format_federal_sheet_entries(df: pd.DataFrame) -> pd.DataFrame:
    filtered = df.loc[df["NUMERO"].notna()].copy()
    records = []
    for _, row in filtered.iterrows():
        presentation = row.get("Unnamed: 4", "")
        records.append(
            {
                "id_registro": "",
                "codigo_local": row.get("NUMERO", ""),
                "codigo": row.get("CATALOGO", "") or row.get("NUMERO", ""),
                "descripcion": row.get("MATERIAL", ""),
                "catalogo": row.get("CATALOGO", ""),
                "marca": row.get("MARCA", ""),
                "lote": "",
                "cantidad": _parse_leading_quantity(presentation),
                "unidad": presentation,
                "caducidad": "",
                "ubicacion": "",
                "categoria": "MATERIAL",
                "fecha": None,
                "responsable": "",
            }
        )
    return harmonize_transaction_keys(_base_from_records(records))


def _format_reactivos_entries(df: pd.DataFrame) -> pd.DataFrame:
    records = []
    for _, row in df.iterrows():
        quantity_text = row.get("Cantidad", "")
        records.append(
            {
                "id_registro": "",
                "codigo_local": row.get("Número", ""),
                "codigo": row.get("Referencia", "") or row.get("Número", ""),
                "descripcion": row.get("Nombre del reactivo", ""),
                "catalogo": row.get("Referencia", ""),
                "marca": row.get("Marca", ""),
                "lote": "",
                "cantidad": _parse_leading_quantity(quantity_text),
                "unidad": quantity_text,
                "caducidad": "",
                "ubicacion": "",
                "categoria": "REACTIVO",
                "fecha": None,
                "responsable": "",
            }
        )
    return harmonize_transaction_keys(_base_from_records(records))


def load_material_inventory_frames(workbook_path: Path, scope: str) -> dict[str, pd.DataFrame]:
    avimex_df = pd.read_excel(workbook_path, sheet_name="Avimex")
    federal_df = pd.read_excel(workbook_path, sheet_name="Presupuesto federal")
    reactivos_df = pd.read_excel(workbook_path, sheet_name="Reactivos")
    final_df = pd.read_excel(workbook_path, sheet_name="Inventario Final")

    final_budget = final_df["PRESUPUESTO"].fillna("").astype(str).str.upper().str.strip()
    avimex_base = _format_avimex_entries(avimex_df)
    avimex_final = _format_inventory_final_entries(
        final_df,
        final_budget.str.contains("AVIMEX", na=False),
    )
    avimex_missing = avimex_final.loc[~avimex_final["codigo"].isin(avimex_base["codigo"])].copy()
    avimex_entries = pd.concat([avimex_base, avimex_missing], ignore_index=True)

    federal_base = _format_federal_sheet_entries(federal_df)
    federal_final = _format_inventory_final_entries(
        final_df,
        final_budget.str.contains("FED", na=False),
    )
    reactivos_entries = _format_reactivos_entries(reactivos_df)
    federal_missing = federal_base.loc[~federal_base["codigo"].isin(federal_final["codigo"])].copy()
    federal_entries = pd.concat([federal_final, federal_missing, reactivos_entries], ignore_index=True)

    if scope == "avimex":
        entry_df = avimex_entries
    elif scope == "federal":
        entry_df = federal_entries
    else:
        raise ValueError(f"Scope no soportado para materiales: {scope}")

    exit_df = _empty_base_df()
    catalog_df = _catalog_from_movements(entry_df, exit_df)
    return {
        "entradas": entry_df,
        "salidas": exit_df,
        "catalogo": catalog_df,
    }
