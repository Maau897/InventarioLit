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

ITEM_KEY_COLUMN = "clave_articulo"
RAW_ITEM_KEY_COLUMN = "clave_articulo_cruda"
CANONICAL_CATALOG_COLUMN = "catalogo_homologado"
CANONICAL_DESCRIPTION_COLUMN = "descripcion_homologada"

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


def _normalize_upper_text(value: object) -> str:
    text = "" if value is None else str(value)
    text = text.strip().upper().replace("\n", " ")
    text = unicodedata.normalize("NFKD", text)
    text = "".join(char for char in text if not unicodedata.combining(char))
    return " ".join(text.split())


def _concat_non_empty_frames(frames: list[pd.DataFrame]) -> pd.DataFrame:
    usable = [frame for frame in frames if frame is not None and not frame.empty]
    if not usable:
        return pd.DataFrame()
    return pd.concat(usable, ignore_index=True)


def _read_excel(workbook_source, **kwargs) -> pd.DataFrame:
    if hasattr(workbook_source, "seek"):
        workbook_source.seek(0)
    return pd.read_excel(workbook_source, **kwargs)


def _canonical_inventory_identity(
    codigo: object,
    catalogo: object,
    descripcion: object,
    marca: object,
) -> tuple[str, str]:
    raw_code = _raw_text(codigo)
    raw_catalog = _raw_text(catalogo)
    raw_desc = _raw_text(descripcion)
    raw_brand = _raw_text(marca)

    source_key = raw_catalog or raw_code
    source_norm = normalize_match_key(source_key)
    desc_upper = _normalize_upper_text(raw_desc)
    brand_upper = _normalize_upper_text(raw_brand)
    euro_norm = source_norm.replace("EI", "", 1) if source_norm.startswith("EI") else source_norm

    canonical_key = source_key
    canonical_desc = raw_desc

    if "EUROIMMUN" in brand_upper or euro_norm.startswith("26069601"):
        if "QUAANTIVAC" in desc_upper or euro_norm.endswith("10G"):
            canonical_key = "EI 2606-9601-10G"
            canonical_desc = "ANTI-SARS-CoV-2 QUAANTIVAC ELISA IgG"
        elif "IGA" in desc_upper or euro_norm in {"26069601A", "2606860A"}:
            canonical_key = "EI 2606-9601A"
            canonical_desc = "Anti SARS-CoV-2 ELISA (IgA)"
        elif "IGG" in desc_upper or euro_norm.endswith("G"):
            canonical_key = "EI 2606-9601G"
            canonical_desc = "Anti SARS-CoV-2 ELISA (IgG)"
    elif source_norm.startswith("L00847") or ("GENSCRIPT" in brand_upper and "CPASS" in desc_upper):
        canonical_key = "L00847-A"
        canonical_desc = "cPass SARS-CoV-2 Neutralization antibody Detection Kit"
    elif (
        ("NEW ENGLAND" in brand_upper or "NEB" in brand_upper)
        and "MLVI-HF-1000 UNITS" in desc_upper
    ) or source_norm.startswith("N01R3198"):
        canonical_key = "N01-R3198S"
        canonical_desc = "ENZIMA DE RESTRICCION MLVI-HF-1000 UNITS"
    elif "AMBIDERM" in brand_upper and "GUANTES DE NITRILO" in desc_upper:
        if any(token in desc_upper for token in ["TALLA M", "MEDIANA", "MEDIANO"]):
            canonical_key = "GUANTE NITRILO MEDIANO"
            canonical_desc = "GUANTES DE NITRILO TALLA M"
        elif any(token in desc_upper for token in ["TALLA CHICA", "TALLA CHICO", "CHICO", "CHICA"]):
            canonical_key = "GUANTE NITRILO CHICO"
            canonical_desc = "GUANTES DE NITRILO TALLA CHICA"
    elif "AMBIDERM" in brand_upper and "GUANTES DE LATEX" in desc_upper:
        canonical_key = "GUANTE LATEX UNITALLA"
        canonical_desc = "GUANTES DE LATEX"
    elif (
        source_norm in {"SLGSR33SS", "SLGSR33RS", "SLGV033RS"}
        or (
            "MILLIPORE" in brand_upper
            and "SYRINGE FILTER" in desc_upper
            and ("0.22" in desc_upper or "O.22" in desc_upper)
        )
    ):
        canonical_key = "FILTRO DE JERINGA 0.22 UM"
        canonical_desc = "FILTRO DE JERINGA 0.22 UM"
    elif (
        source_norm in {"06666A1", "0666A1"}
        or (
            "KIMTECH" in desc_upper
            and "KIMBER" in brand_upper
            and source_norm in {"06666A1", "0666A1"}
        )
    ):
        canonical_key = "06-666A-1"
        canonical_desc = "KIMBERLY-CLARK PROFESSIONAL KIMTECH"
    elif source_norm in {"10010031", "1001031"} and "PBS" in desc_upper:
        canonical_key = "10010-031"
        canonical_desc = "PBS PH 7, 4, 1,000 ML"
    elif source_norm == "P4417100TAB":
        canonical_key = "P44-17-100 TAB"
        canonical_desc = "PBS SALINO. TABLETAS"
    elif source_norm in {"F171300", "FF171300"} and "PIPETMAN" in desc_upper:
        canonical_key = "F171300"
        canonical_desc = "PIPETMAN PUNTAS DE 200 ML EN RACK"
    elif source_norm in {"CRM00100PH", "CRM0010PH"}:
        canonical_key = "CRM-00100PH"
        canonical_desc = "CHAROLA PARA PESAR DE PLASTICO, DESECHABLE 8X8"
    elif source_norm in {"25230054", "25300054"} and "TRIPSINA" in desc_upper:
        canonical_key = "25300-054"
        canonical_desc = "TRIPSINA- EDTA (0.05%) RED PHENOL"
    elif source_norm in {"300936", "3009636"} and "BRILLANT VIOLET 605 ANTI-HUMAN CD8A" in desc_upper:
        canonical_key = "300936"
        canonical_desc = "BRILLANT VIOLET 605 ANTI-HUMAN CD8A"
    elif source_norm.startswith("BR703411"):
        canonical_key = "BR703411-100"
        canonical_desc = "DEPOSITO DE REACTIVOS"
    elif "EPPENDORF" in brand_upper and "(" in source_key and any(
        token in desc_upper for token in ["PUNTA/MICROPIPETA", "PUNTAS EPT.I.P.S", "PUNTAS EPTIPS"]
    ):
        canonical_key = source_key.split("(", 1)[0].strip()
    elif (
        source_norm in {"T200YR", "T200YRS"}
        or (
            "AXYGEN" in brand_upper
            and "RACK" in desc_upper
            and ("1 A 200" in desc_upper or "200 ML 96" in desc_upper)
            and source_norm.startswith("T200YR")
        )
    ):
        canonical_key = "T-200-Y-R-S"
        canonical_desc = "PUNTA PARA MICROPIPETA DE 1 A 200 ML 96/ RACK"

    if canonical_key == "":
        canonical_key = source_key
    if canonical_desc == "":
        canonical_desc = raw_desc
    return canonical_key, canonical_desc


def _raw_text(value: object) -> str:
    if value is None or pd.isna(value):
        return ""
    return str(value).strip()


def ensure_item_key(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    if "codigo" not in df.columns:
        df["codigo"] = ""
    if "catalogo" not in df.columns:
        df["catalogo"] = ""
    if "codigo_local" not in df.columns:
        df["codigo_local"] = ""
    if "descripcion" not in df.columns:
        df["descripcion"] = ""
    if "marca" not in df.columns:
        df["marca"] = ""
    if df.empty:
        df[RAW_ITEM_KEY_COLUMN] = pd.Series(dtype="object")
        df[CANONICAL_CATALOG_COLUMN] = pd.Series(dtype="object")
        df[CANONICAL_DESCRIPTION_COLUMN] = pd.Series(dtype="object")
        df[ITEM_KEY_COLUMN] = pd.Series(dtype="object")
        return df
    df["codigo"] = df["codigo"].map(_raw_text)
    df["catalogo"] = df["catalogo"].map(_raw_text)
    df["codigo_local"] = df["codigo_local"].map(_raw_text)
    df["descripcion"] = df["descripcion"].map(_raw_text)
    df["marca"] = df["marca"].map(_raw_text)
    df[RAW_ITEM_KEY_COLUMN] = df["catalogo"].where(df["catalogo"] != "", df["codigo"])
    homologated = df.apply(
        lambda row: _canonical_inventory_identity(
            row.get("codigo", ""),
            row.get("catalogo", ""),
            row.get("descripcion", ""),
            row.get("marca", ""),
        ),
        axis=1,
        result_type="expand",
    )
    homologated.columns = [CANONICAL_CATALOG_COLUMN, CANONICAL_DESCRIPTION_COLUMN]
    df[CANONICAL_CATALOG_COLUMN] = homologated[CANONICAL_CATALOG_COLUMN].map(_raw_text)
    df[CANONICAL_DESCRIPTION_COLUMN] = homologated[CANONICAL_DESCRIPTION_COLUMN].map(_raw_text)
    df[ITEM_KEY_COLUMN] = df[CANONICAL_CATALOG_COLUMN].where(
        df[CANONICAL_CATALOG_COLUMN] != "",
        df[RAW_ITEM_KEY_COLUMN],
    )
    return df


def parse_mixed_datetime_series(series: pd.Series) -> pd.Series:
    normalized = series.copy()
    normalized = normalized.where(pd.notna(normalized), None)

    parsed = pd.Series(pd.NaT, index=normalized.index, dtype="datetime64[ns]")
    non_string_mask = normalized.map(lambda value: not isinstance(value, str))
    if non_string_mask.any():
        parsed.loc[non_string_mask] = pd.to_datetime(normalized.loc[non_string_mask], errors="coerce")

    string_mask = normalized.map(lambda value: isinstance(value, str))
    if not string_mask.any():
        return parsed

    text_values = normalized.loc[string_mask].astype(str).str.strip()
    empty_like = {"", "nan", "nat", "none", "sin fecha"}
    text_values = text_values.where(~text_values.str.lower().isin(empty_like), None)
    remaining = text_values.loc[text_values.notna()].index
    if len(remaining) == 0:
        return parsed

    candidate_formats = [
        "%m/%d/%Y",
        "%m/%d/%y",
        "%Y-%m-%d",
        "%Y-%m-%d %H:%M:%S",
        "%m/%d/%Y %H:%M:%S",
        "%m/%d/%y %H:%M:%S",
        "%d/%m/%Y",
        "%d/%m/%y",
    ]

    unresolved = pd.Index(remaining)
    for fmt in candidate_formats:
        if len(unresolved) == 0:
            break
        attempted = pd.to_datetime(text_values.loc[unresolved], format=fmt, errors="coerce")
        matched = attempted.loc[attempted.notna()]
        if not matched.empty:
            parsed.loc[matched.index] = matched
            unresolved = unresolved.difference(matched.index)

    if len(unresolved) > 0:
        fallback = pd.to_datetime(text_values.loc[unresolved], format="mixed", errors="coerce")
        parsed.loc[fallback.index] = fallback

    return parsed


def parse_single_datetime(value: object) -> pd.Timestamp:
    return parse_mixed_datetime_series(pd.Series([value])).iloc[0]


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
    df = ensure_item_key(df)
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
    df["fecha"] = parse_mixed_datetime_series(df["fecha"])
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
    df["descripcion"] = df[CANONICAL_DESCRIPTION_COLUMN].where(
        df[CANONICAL_DESCRIPTION_COLUMN] != "",
        df["descripcion"],
    )
    df = df.loc[df[ITEM_KEY_COLUMN] != ""].copy()
    return df


def clean_catalog_sheet(df: pd.DataFrame) -> pd.DataFrame:
    df = _normalize_columns(df.copy())
    if "catalogo" in df.columns and "codigo" not in df.columns:
        df["codigo"] = df["catalogo"]
    if "descripcion" not in df.columns and "descripcion_del_producto" in df.columns:
        df["descripcion"] = df["descripcion_del_producto"]
    df = _coerce_base_columns(df)
    df = ensure_item_key(df)
    df = _clean_strings(
        df,
        ["descripcion", "marca", "lote", "unidad", "caducidad", "ubicacion", "categoria"],
    )
    df["categoria"] = df["categoria"].str.upper().replace({"M": "MATERIAL", "R": "REACTIVO"})
    df["descripcion"] = df[CANONICAL_DESCRIPTION_COLUMN].where(
        df[CANONICAL_DESCRIPTION_COLUMN] != "",
        df["descripcion"],
    )
    df = df.loc[df[ITEM_KEY_COLUMN] != ""].copy()
    catalog = df[
        [
            ITEM_KEY_COLUMN,
            RAW_ITEM_KEY_COLUMN,
            CANONICAL_CATALOG_COLUMN,
            CANONICAL_DESCRIPTION_COLUMN,
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
    catalog = catalog.sort_values(["descripcion", "catalogo", "codigo"]).drop_duplicates(ITEM_KEY_COLUMN, keep="first")
    return catalog


def harmonize_transaction_keys(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    if df.empty:
        return _empty_base_df()
    df = ensure_item_key(df)
    return df.loc[df[ITEM_KEY_COLUMN] != ""].copy()


def _movement_rows(movements_df: pd.DataFrame, movement_type: str) -> pd.DataFrame:
    if movements_df.empty:
        return _empty_base_df()
    filtered = movements_df.loc[movements_df["movement_type"] == movement_type].copy()
    if filtered.empty:
        return _empty_base_df()
    filtered["fecha"] = parse_mixed_datetime_series(filtered["fecha"])
    filtered["cantidad"] = pd.to_numeric(filtered["cantidad"], errors="coerce").fillna(0)
    filtered["id_registro"] = filtered["id_registro"].fillna("").astype(str).str.strip()
    filtered = ensure_item_key(filtered)
    filtered = filtered.loc[filtered[ITEM_KEY_COLUMN] != ""].copy()
    for column in BASE_COLUMNS:
        if column not in filtered.columns:
            filtered[column] = None
    return filtered[[*BASE_COLUMNS, ITEM_KEY_COLUMN]]


def _catalog_from_movements(entry_df: pd.DataFrame, exit_df: pd.DataFrame) -> pd.DataFrame:
    frames = [df for df in [entry_df, exit_df] if df is not None and not df.empty]
    if not frames:
        return pd.DataFrame(
            columns=[
                ITEM_KEY_COLUMN,
                RAW_ITEM_KEY_COLUMN,
                CANONICAL_CATALOG_COLUMN,
                CANONICAL_DESCRIPTION_COLUMN,
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
    combined = ensure_item_key(combined)
    combined["fecha"] = parse_mixed_datetime_series(combined["fecha"])
    combined = combined.sort_values("fecha", ascending=False, na_position="last")
    catalog = combined.groupby(ITEM_KEY_COLUMN, as_index=False).first()
    return catalog[
        [
            ITEM_KEY_COLUMN,
            RAW_ITEM_KEY_COLUMN,
            CANONICAL_CATALOG_COLUMN,
            CANONICAL_DESCRIPTION_COLUMN,
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
    ].sort_values(["descripcion", "catalogo", "codigo"])


def build_catalog_options(catalog_df: pd.DataFrame) -> list[str]:
    options = ["Nuevo insumo"]
    for _, row in catalog_df.sort_values("descripcion").iterrows():
        description = row["descripcion"] or row.get(CANONICAL_DESCRIPTION_COLUMN, "") or row["catalogo"] or row["marca"] or "Sin descripcion"
        label_code = row.get(CANONICAL_CATALOG_COLUMN, "") or row["catalogo"] or row["codigo"]
        options.append(f"{label_code} - {description}")
    return options


def build_inventory_snapshot(
    source_entries: pd.DataFrame,
    source_exits: pd.DataFrame,
    app_movements: pd.DataFrame,
    catalog_df: pd.DataFrame | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    app_entries = _movement_rows(app_movements, "entrada")
    app_exits = _movement_rows(app_movements, "salida")

    entry_df = _concat_non_empty_frames([source_entries, app_entries])
    exit_df = _concat_non_empty_frames([source_exits, app_exits])
    if entry_df.empty:
        entry_df = _empty_base_df()
    if exit_df.empty:
        exit_df = _empty_base_df()
    entry_df = ensure_item_key(entry_df)
    exit_df = ensure_item_key(exit_df)
    entry_df["fecha"] = parse_mixed_datetime_series(entry_df["fecha"])
    exit_df["fecha"] = parse_mixed_datetime_series(exit_df["fecha"])
    entry_df["cantidad"] = pd.to_numeric(entry_df["cantidad"], errors="coerce").fillna(0)
    exit_df["cantidad"] = pd.to_numeric(exit_df["cantidad"], errors="coerce").fillna(0)
    movement_catalog_df = _catalog_from_movements(entry_df, exit_df)

    if catalog_df is None or catalog_df.empty:
        catalog_df = movement_catalog_df
    else:
        catalog_df = clean_catalog_sheet(catalog_df)
        catalog_df = ensure_item_key(catalog_df)
        catalog_df = catalog_df.merge(
            movement_catalog_df,
            on=ITEM_KEY_COLUMN,
            how="outer",
            suffixes=("", "_mov"),
        )
        for column in [
            "codigo_local",
            RAW_ITEM_KEY_COLUMN,
            CANONICAL_CATALOG_COLUMN,
            CANONICAL_DESCRIPTION_COLUMN,
            "descripcion",
            "catalogo",
            "marca",
            "lote",
            "unidad",
            "caducidad",
            "ubicacion",
            "categoria",
        ]:
            mov_column = f"{column}_mov"
            if mov_column not in catalog_df.columns:
                continue
            catalog_df[column] = catalog_df[column].where(
                catalog_df[column].fillna("").astype(str).str.strip() != "",
                catalog_df[mov_column],
            )
        drop_columns = [column for column in catalog_df.columns if column.endswith("_mov")]
        if drop_columns:
            catalog_df = catalog_df.drop(columns=drop_columns)
        catalog_df = catalog_df.drop_duplicates(ITEM_KEY_COLUMN, keep="first")
        catalog_df["catalogo"] = catalog_df[CANONICAL_CATALOG_COLUMN].where(
            catalog_df[CANONICAL_CATALOG_COLUMN].fillna("").astype(str).str.strip() != "",
            catalog_df["catalogo"],
        )
        catalog_df["descripcion"] = catalog_df[CANONICAL_DESCRIPTION_COLUMN].where(
            catalog_df[CANONICAL_DESCRIPTION_COLUMN].fillna("").astype(str).str.strip() != "",
            catalog_df["descripcion"],
        )

    entry_totals = entry_df.groupby(ITEM_KEY_COLUMN, as_index=False)["cantidad"].sum().rename(
        columns={"cantidad": "entrada"}
    )
    exit_totals = exit_df.groupby(ITEM_KEY_COLUMN, as_index=False)["cantidad"].sum().rename(
        columns={"cantidad": "salida"}
    )
    entry_dates = entry_df.groupby(ITEM_KEY_COLUMN, as_index=False)["fecha"].max().rename(
        columns={"fecha": "fecha_recepcion"}
    )
    entry_dates["fecha_recepcion"] = entry_dates["fecha_recepcion"].dt.strftime("%Y-%m-%d")
    inventory_df = catalog_df.merge(entry_totals, on=ITEM_KEY_COLUMN, how="left").merge(
        exit_totals, on=ITEM_KEY_COLUMN, how="left"
    ).merge(
        entry_dates, on=ITEM_KEY_COLUMN, how="left"
    )
    inventory_df["entrada"] = inventory_df["entrada"].fillna(0)
    inventory_df["salida"] = inventory_df["salida"].fillna(0)
    inventory_df["existencia"] = inventory_df["entrada"] - inventory_df["salida"]
    inventory_df = inventory_df[
        [
            ITEM_KEY_COLUMN,
            RAW_ITEM_KEY_COLUMN,
            CANONICAL_CATALOG_COLUMN,
            CANONICAL_DESCRIPTION_COLUMN,
            "codigo",
            "codigo_local",
            "descripcion",
            "catalogo",
            "marca",
            "lote",
            "unidad",
            "caducidad",
            "fecha_recepcion",
            "ubicacion",
            "categoria",
            "entrada",
            "salida",
            "existencia",
        ]
    ].sort_values(["categoria", "descripcion", "catalogo", "codigo"])
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
    df["fecha_conteo"] = parse_mixed_datetime_series(df["fecha_conteo"])
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
    merged[ITEM_KEY_COLUMN] = merged["codigo"].map(_raw_text)
    latest = merged.groupby(ITEM_KEY_COLUMN, as_index=False).first()
    latest[ITEM_KEY_COLUMN] = latest["codigo"].map(_raw_text)
    latest = latest.rename(
        columns={
            "ubicacion": "ubicacion_reducida",
            "lote": "lote_conteo",
            "caducidad": "caducidad_conteo",
        }
    )
    enriched = inventory_df.merge(
        latest[[ITEM_KEY_COLUMN, "ubicacion_reducida", "lote_conteo", "caducidad_conteo"]],
        on=ITEM_KEY_COLUMN,
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
            ITEM_KEY_COLUMN,
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
    codigo = str(row.get("catalogo", "") or row.get("codigo", "")).strip()
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
        df = ensure_item_key(df)
        frames.append(df.loc[df[ITEM_KEY_COLUMN] != ""])
    if not frames:
        return pd.DataFrame()
    combined = pd.concat(frames, ignore_index=True)
    combined = combined.sort_values(["descripcion", "catalogo", "codigo"]).drop_duplicates(ITEM_KEY_COLUMN, keep="first")
    return combined


def load_workbook_frames(workbook_path: Path) -> dict[str, pd.DataFrame]:
    entradas = _read_excel(workbook_path, sheet_name="Entradas", usecols="A:L")
    salidas = _read_excel(workbook_path, sheet_name="Salidas", usecols="A:L")
    entry_df = harmonize_transaction_keys(clean_base_sheet(entradas))
    exit_df = harmonize_transaction_keys(clean_base_sheet(salidas))
    catalog_df = _catalog_from_movements(entry_df, exit_df)
    return {
        "entradas": entry_df,
        "salidas": exit_df,
        "catalogo": catalog_df,
    }


def load_recovery_current_inventory_frames(workbook_path: Path) -> dict[str, pd.DataFrame]:
    inventory = _read_excel(workbook_path, sheet_name="Inventario", usecols="A:H")
    entries_source = harmonize_transaction_keys(
        clean_base_sheet(_read_excel(workbook_path, sheet_name="Entradas", usecols="A:L"))
    )
    exits_source = harmonize_transaction_keys(
        clean_base_sheet(_read_excel(workbook_path, sheet_name="Salidas", usecols="A:L"))
    )
    details = _catalog_from_movements(entries_source, exits_source)
    detail_by_key = details.set_index(ITEM_KEY_COLUMN).to_dict(orient="index") if not details.empty else {}

    records = []
    for _, row in inventory.iterrows():
        existencia = pd.to_numeric(pd.Series([row.get("Existencia")]), errors="coerce").fillna(0).iloc[0]
        if existencia <= 0:
            continue
        codigo = _raw_text(row.get("Código", ""))
        catalogo = _raw_text(row.get("Catálogo", "")) or codigo
        descripcion = _raw_text(row.get("Descripción", ""))
        marca = _raw_text(row.get("Marca ", ""))
        lote = _raw_text(row.get("Lote", ""))
        if not descripcion and not catalogo:
            continue

        provisional = harmonize_transaction_keys(
            _base_from_records(
                [
                    {
                        "codigo": codigo,
                        "codigo_local": codigo,
                        "descripcion": descripcion,
                        "catalogo": catalogo,
                        "marca": marca,
                        "lote": lote,
                        "cantidad": existencia,
                    }
                ]
            )
        )
        item_key = provisional.iloc[0][ITEM_KEY_COLUMN] if not provisional.empty else catalogo
        detail = detail_by_key.get(item_key, {})
        records.append(
            {
                "id_registro": "INVENTARIO_RECUPERACION",
                "codigo_local": codigo,
                "codigo": codigo,
                "descripcion": descripcion,
                "catalogo": catalogo,
                "marca": marca,
                "lote": lote,
                "cantidad": existencia,
                "unidad": detail.get("unidad", ""),
                "caducidad": detail.get("caducidad", ""),
                "ubicacion": detail.get("ubicacion", ""),
                "categoria": _normalize_inventory_category(detail.get("categoria", ""), "REACTIVO"),
                "fecha": pd.Timestamp("2026-07-01"),
                "responsable": "Inventario recuperacion",
            }
        )

    entry_df = harmonize_transaction_keys(_base_from_records(records))
    exit_df = _empty_base_df()
    catalog_df = _catalog_from_movements(entry_df, exit_df)
    return {"entradas": entry_df, "salidas": exit_df, "catalogo": catalog_df}


def load_recovery_template_frames(workbook_path: Path) -> dict[str, pd.DataFrame]:
    inventory = _read_excel(workbook_path, sheet_name="Inventario", usecols="A:H")
    entries_source = harmonize_transaction_keys(
        clean_base_sheet(_read_excel(workbook_path, sheet_name="Entradas", usecols="A:L"))
    )
    exits_source = harmonize_transaction_keys(
        clean_base_sheet(_read_excel(workbook_path, sheet_name="Salidas", usecols="A:L"))
    )
    historical_catalog = _catalog_from_movements(entries_source, exits_source)
    detail_by_key = historical_catalog.set_index(ITEM_KEY_COLUMN).to_dict(orient="index") if not historical_catalog.empty else {}

    records = []
    for _, row in inventory.iterrows():
        codigo = _raw_text(row.get("Código", ""))
        catalogo = _raw_text(row.get("Catálogo", "")) or codigo
        descripcion = _raw_text(row.get("Descripción", ""))
        marca = _raw_text(row.get("Marca ", ""))
        lote = _raw_text(row.get("Lote", ""))
        if not descripcion and not catalogo:
            continue

        provisional = harmonize_transaction_keys(
            _base_from_records(
                [
                    {
                        "codigo": codigo,
                        "codigo_local": codigo,
                        "descripcion": descripcion,
                        "catalogo": catalogo,
                        "marca": marca,
                        "lote": lote,
                    }
                ]
            )
        )
        item_key = provisional.iloc[0][ITEM_KEY_COLUMN] if not provisional.empty else catalogo
        detail = detail_by_key.get(item_key, {})
        records.append(
            {
                "id_registro": "PLANTILLA_RECUPERACION",
                "codigo_local": codigo,
                "codigo": codigo,
                "descripcion": descripcion,
                "catalogo": catalogo,
                "marca": marca,
                "lote": lote,
                "cantidad": 0,
                "unidad": detail.get("unidad", ""),
                "caducidad": detail.get("caducidad", ""),
                "ubicacion": detail.get("ubicacion", ""),
                "categoria": _normalize_inventory_category(detail.get("categoria", ""), "REACTIVO"),
                "fecha": pd.NaT,
                "responsable": "Plantilla recuperacion",
            }
        )

    inventory_catalog = _catalog_from_movements(harmonize_transaction_keys(_base_from_records(records)), _empty_base_df())
    catalog_df = combine_catalogs(inventory_catalog, historical_catalog)
    return {"entradas": _empty_base_df(), "salidas": _empty_base_df(), "catalogo": catalog_df}


def _extract_category_from_indicator(value: object) -> str:
    text = _normalize_upper_text(value)
    if "REACTIVO" in text:
        return "REACTIVO"
    if "MATERIAL" in text:
        return "MATERIAL PLASTICO"
    return "MATERIAL PLASTICO"


def _normalize_inventory_category(value: object, default: str = "REACTIVO") -> str:
    text = _normalize_upper_text(value)
    collapsed = normalize_match_key(text)
    if "REACTIVO" in collapsed or "REATIVO" in collapsed:
        return "REACTIVO"
    if "MATERIAL" in collapsed:
        return "MATERIAL"
    if "EQUIPO" in collapsed:
        return "EQUIPO"
    return default


def load_indicator_inventory_frames(workbook_path: Path, sheet_name: str = "JUL 26") -> dict[str, pd.DataFrame]:
    df = _read_excel(workbook_path, sheet_name=sheet_name)
    records = []
    for _, row in df.iterrows():
        catalogo = _raw_text(row.get("catálogo", "")) or _raw_text(row.get("catalogo", ""))
        descripcion = _raw_text(row.get("producto", ""))
        if not catalogo and not descripcion:
            continue
        cantidad = row.get("Unnamed: 11", row.get("cantidad", 0))
        if pd.isna(cantidad):
            cantidad = row.get("cantidad", 0)
        cantidad = pd.to_numeric(pd.Series([cantidad]), errors="coerce").fillna(0).iloc[0]
        if cantidad <= 0:
            continue
        records.append(
            {
                "id_registro": _raw_text(row.get("conteo", "")) or "JUL 26",
                "codigo_local": "",
                "codigo": catalogo,
                "descripcion": descripcion,
                "catalogo": catalogo,
                "marca": _raw_text(row.get("marca", "")),
                "lote": _raw_text(row.get("Unnamed: 13", "")),
                "cantidad": cantidad,
                "unidad": _raw_text(row.get("Unnamed: 12", "")) or _raw_text(row.get("presentación", "")),
                "caducidad": _raw_text(row.get("Unnamed: 14", "")),
                "ubicacion": _raw_text(row.get("ubicación", "")),
                "categoria": _extract_category_from_indicator(row.get("Unnamed: 15", "")),
                "fecha": pd.Timestamp("2026-07-01"),
                "responsable": "JUL 26",
            }
        )

    entry_df = harmonize_transaction_keys(_base_from_records(records))
    exit_df = _empty_base_df()
    catalog_df = _catalog_from_movements(entry_df, exit_df)
    return {"entradas": entry_df, "salidas": exit_df, "catalogo": catalog_df}


def load_lit_official_inventory_frames(workbook_path: Path, sheet_name: str | int = 0) -> dict[str, pd.DataFrame]:
    df = _read_excel(workbook_path, sheet_name=sheet_name)
    records = []
    for _, row in df.iterrows():
        catalogo = _raw_text(row.get("Referencia", ""))
        descripcion = _raw_text(row.get("Nombre del material", ""))
        if not catalogo and not descripcion:
            continue
        cantidad = pd.to_numeric(pd.Series([row.get("Existencia", 0)]), errors="coerce").fillna(0).iloc[0]
        records.append(
            {
                "id_registro": "LIT_01_07_2026",
                "codigo_local": _raw_text(row.get("NÃºmero", row.get("Número", ""))),
                "codigo": catalogo or descripcion,
                "descripcion": descripcion,
                "catalogo": catalogo,
                "marca": _raw_text(row.get("Marca", "")),
                "lote": "",
                "cantidad": cantidad,
                "unidad": _raw_text(row.get("PresentaciÃ³n", row.get("Presentación", ""))),
                "caducidad": "",
                "ubicacion": "",
                "categoria": "MATERIAL",
                "fecha": pd.Timestamp("2026-07-01"),
                "responsable": "Inventario LIT 01/07/2026",
            }
        )

    entry_df = harmonize_transaction_keys(_base_from_records(records))
    exit_df = _empty_base_df()
    catalog_df = _catalog_from_movements(entry_df, exit_df)
    return {"entradas": entry_df, "salidas": exit_df, "catalogo": catalog_df}


def merge_inventory_frames(*frames_list: dict[str, pd.DataFrame]) -> dict[str, pd.DataFrame]:
    entries = _concat_non_empty_frames([frames.get("entradas", pd.DataFrame()) for frames in frames_list])
    exits = _concat_non_empty_frames([frames.get("salidas", pd.DataFrame()) for frames in frames_list])
    catalogs = [frames.get("catalogo", pd.DataFrame()) for frames in frames_list]
    catalog = pd.DataFrame()
    for source_catalog in catalogs:
        catalog = combine_catalogs(catalog, source_catalog) if not catalog.empty else source_catalog
    if entries.empty:
        entries = _empty_base_df()
    if exits.empty:
        exits = _empty_base_df()
    if catalog is None or catalog.empty:
        catalog = _catalog_from_movements(entries, exits)
    return {"entradas": entries, "salidas": exits, "catalogo": catalog}


def load_seed_inventory_frames(seed_df: pd.DataFrame) -> dict[str, pd.DataFrame]:
    if seed_df is None or seed_df.empty:
        return {"entradas": _empty_base_df(), "salidas": _empty_base_df(), "catalogo": pd.DataFrame()}
    entries = seed_df.copy()
    if "id_registro" not in entries.columns:
        entries["id_registro"] = entries.get("source_label", "BASE_OFICIAL")
    if "fecha" not in entries.columns:
        entries["fecha"] = entries.get("loaded_at", pd.Timestamp.today().date())
    if "responsable" not in entries.columns:
        entries["responsable"] = "Base oficial"
    entry_df = harmonize_transaction_keys(_base_from_records(entries.to_dict(orient="records")))
    exit_df = _empty_base_df()
    catalog_df = _catalog_from_movements(entry_df, exit_df)
    return {"entradas": entry_df, "salidas": exit_df, "catalogo": catalog_df}


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
    avimex_df = _read_excel(workbook_path, sheet_name="Avimex")
    federal_df = _read_excel(workbook_path, sheet_name="Presupuesto federal")
    reactivos_df = _read_excel(workbook_path, sheet_name="Reactivos")
    final_df = _read_excel(workbook_path, sheet_name="Inventario Final")

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
