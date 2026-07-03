from pathlib import Path
from io import BytesIO

import pandas as pd
import streamlit as st

from inventory_app.config import (
    DEFAULT_SCOPE,
    INDICATORS_WORKBOOK_PATH,
    INVENTORY_SCOPES,
    MATERIALS_WORKBOOK_PATH,
    RECOVERY_WORKBOOK_PATH,
    SHEET_NAME_DEFAULTS,
)
from inventory_app.excel_loader import (
    BASE_COLUMNS,
    CANONICAL_CATALOG_COLUMN,
    CANONICAL_DESCRIPTION_COLUMN,
    ITEM_KEY_COLUMN,
    RAW_ITEM_KEY_COLUMN,
    build_catalog_options,
    build_inventory_snapshot,
    build_product_search_links,
    clean_count_results_sheet,
    clean_registry_sheet,
    combine_catalogs,
    ensure_item_key,
    enrich_inventory_with_counts,
    harmonize_transaction_keys,
    load_indicator_inventory_frames,
    load_material_inventory_frames,
    load_recovery_template_frames,
    load_seed_inventory_frames,
    merge_inventory_frames,
    normalize_match_key,
    parse_mixed_datetime_series,
    parse_single_datetime,
)
from inventory_app.repositories import MOVEMENT_COLUMNS, REGULARIZATION_COLUMNS, get_repository
from inventory_app.config import LOCAL_DATA_DIR


st.set_page_config(page_title="Inventario General INER", layout="wide")

ENTRY_COLUMNS = [
    "id_registro",
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
    "temperatura",
    "observaciones",
    "verificado_por",
]

SUMMARY_COLUMNS = [
    "codigo",
    "descripcion",
    "marca",
    "categoria",
    "ubicacion",
    "lote",
    "caducidad",
    "entrada",
    "salida",
    "existencia",
]

NEGATIVE_COLUMNS = [
    ITEM_KEY_COLUMN,
    "codigo",
    "codigo_local",
    "descripcion",
    "marca",
    "categoria",
    "ubicacion",
    "lote",
    "caducidad",
    "entrada",
    "salida",
    "existencia",
]

NEGATIVE_DIAGNOSTIC_COLUMNS = [
    ITEM_KEY_COLUMN,
    "codigo",
    "catalogo",
    "descripcion",
    "marca",
    "entrada",
    "salida",
    "existencia",
    "catalog_variants_count",
    "description_family_count",
    "same_norm_entry_count",
    "same_norm_exit_count",
    "recommended_action",
    "diagnosis_flags",
]

TABLE_COLUMNS = [
    "id_registro",
    "codigo",
    "descripcion",
    "marca",
    "catalogo",
    "lote",
    "caducidad",
    "cantidad",
    "unidad",
    "responsable",
    "fecha",
]

EDITABLE_MOVEMENT_COLUMNS = [
    "movement_uid",
    "id_registro",
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
    "temperatura",
    "observaciones",
    "verificado_por",
]

NEGATIVE_REVIEW_COLUMNS = [
    "id_registro",
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

CONFLICT_COLUMNS = [
    "created_at",
    "inventory_scope",
    "codigo_reportado",
    "codigo_sugerido",
    "descripcion",
    "marca",
    "motivo",
    "detalle",
]

CONFLICTS_PATH = LOCAL_DATA_DIR / "conflictos_homologacion.csv"
REGULARIZATION_DISPLAY_COLUMNS = [
    "tipo_regularizacion",
    "fecha_corte",
    "fecha_validacion",
    "codigo",
    "catalogo",
    "descripcion",
    "marca",
    "lote",
    "cantidad",
    "unidad",
    "caducidad",
    "ubicacion",
    "categoria",
    "soporte_disponible",
    "folio_origen",
    "comentario_regularizacion",
    "validado_por",
    "inventory_scope",
]


def init_state() -> None:
    if "selected_code" not in st.session_state:
        st.session_state.selected_code = ""


def get_item_key(row: pd.Series) -> str:
    return str(row.get(ITEM_KEY_COLUMN, "") or row.get("catalogo", "") or row.get("codigo", "")).strip()


def filter_by_item_key(df: pd.DataFrame, item_key: str) -> pd.DataFrame:
    if df.empty:
        return df.copy()
    prepared = ensure_item_key(df)
    return prepared.loc[prepared[ITEM_KEY_COLUMN] == item_key].copy()


def normalize_text_key(value: object) -> str:
    return " ".join(str(value or "").strip().upper().split())


def add_diagnostic_keys(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return ensure_item_key(df)
    prepared = ensure_item_key(df)
    prepared["catalog_norm"] = prepared["catalogo"].map(normalize_match_key)
    prepared["code_norm"] = prepared["codigo"].map(normalize_match_key)
    prepared["item_norm"] = prepared[ITEM_KEY_COLUMN].map(normalize_match_key)
    prepared["description_brand_key"] = (
        prepared["descripcion"].map(normalize_text_key) + "||" + prepared["marca"].map(normalize_text_key)
    )
    return prepared


def build_negative_diagnostics(
    inventory_df: pd.DataFrame,
    entry_df: pd.DataFrame,
    exit_df: pd.DataFrame,
) -> pd.DataFrame:
    inventory = add_diagnostic_keys(inventory_df)
    entries = add_diagnostic_keys(entry_df)
    exits = add_diagnostic_keys(exit_df)
    negatives = inventory.loc[inventory["existencia"] < 0].copy()
    if negatives.empty:
        return negatives

    rows: list[dict[str, object]] = []
    for _, row in negatives.iterrows():
        item_norm = row.get("item_norm", "")
        desc_brand_key = row.get("description_brand_key", "")
        item_key = str(row.get(ITEM_KEY_COLUMN, "") or "").strip()
        family_inventory = inventory.loc[inventory["description_brand_key"] == desc_brand_key].copy()
        same_norm_inventory = inventory.loc[
            (inventory["item_norm"] == item_norm) | (inventory["catalog_norm"] == row.get("catalog_norm", ""))
        ].copy()
        same_norm_entries = entries.loc[
            (entries["item_norm"] == item_norm) | (entries["catalog_norm"] == row.get("catalog_norm", ""))
        ].copy()
        same_norm_exits = exits.loc[
            (exits["item_norm"] == item_norm) | (exits["catalog_norm"] == row.get("catalog_norm", ""))
        ].copy()

        raw_variants = sorted(
            {
                str(value).strip()
                for value in pd.concat(
                    [
                        same_norm_inventory["catalogo"],
                        same_norm_entries["catalogo"],
                        same_norm_exits["catalogo"],
                    ],
                    ignore_index=True,
                ).fillna("")
                if str(value).strip() != ""
            }
        )
        family_keys = sorted({get_item_key(candidate) for _, candidate in family_inventory.iterrows() if get_item_key(candidate)})

        flags: list[str] = []
        if len(raw_variants) > 1:
            flags.append("variantes_catalogo")
        if len(family_keys) > 1:
            flags.append("misma_descripcion_marca")
        if float(row.get("entrada", 0) or 0) <= 0 and len(same_norm_entries) > 0:
            flags.append("entrada_en_variante_hermana")
        if float(row.get("entrada", 0) or 0) <= 0 and float(row.get("salida", 0) or 0) > 0:
            flags.append("sin_entrada_directa")
        if float(row.get("salida", 0) or 0) > float(row.get("entrada", 0) or 0) and len(same_norm_entries) > 0:
            flags.append("salida_supera_entrada_local")
        if item_key == "T-200-Y":
            flags = [flag for flag in flags if flag not in {"variantes_catalogo", "misma_descripcion_marca"}]
            flags.append("negativo_real_confirmado")

        recommended_action = "revisar_manual"
        if "negativo_real_confirmado" in flags:
            recommended_action = "negativo_real"
        elif "variantes_catalogo" in flags or "misma_descripcion_marca" in flags:
            recommended_action = "revisar_homologacion"
        elif "sin_entrada_directa" in flags or "entrada_en_variante_hermana" in flags:
            recommended_action = "buscar_entrada_faltante"
        elif float(row.get("salida", 0) or 0) > 0:
            recommended_action = "revisar_salidas"

        record = row.to_dict()
        record.update(
            {
                "catalog_variants_count": len(raw_variants),
                "catalog_variants": " | ".join(raw_variants),
                "description_family_count": len(family_keys),
                "description_family_keys": " | ".join(family_keys),
                "same_norm_entry_count": len(same_norm_entries),
                "same_norm_exit_count": len(same_norm_exits),
                "recommended_action": recommended_action,
                "diagnosis_flags": " | ".join(flags) if flags else "sin_bandera",
            }
        )
        rows.append(record)

    return pd.DataFrame(rows).sort_values(["recommended_action", "existencia"])


def build_related_variant_rows(
    selected_item_key: str,
    inventory_df: pd.DataFrame,
    entry_df: pd.DataFrame,
    exit_df: pd.DataFrame,
) -> pd.DataFrame:
    inventory = add_diagnostic_keys(inventory_df)
    entries = add_diagnostic_keys(entry_df)
    exits = add_diagnostic_keys(exit_df)
    selected_inventory = filter_by_item_key(inventory, selected_item_key)
    if selected_inventory.empty:
        return pd.DataFrame()

    selected_row = selected_inventory.iloc[0]
    item_norm = selected_row.get("item_norm", "")
    desc_brand_key = selected_row.get("description_brand_key", "")

    inventory_matches = inventory.loc[
        (inventory["item_norm"] == item_norm)
        | (inventory["catalog_norm"] == selected_row.get("catalog_norm", ""))
        | (inventory["description_brand_key"] == desc_brand_key)
    ].copy()
    inventory_matches["source_type"] = "inventario_actual"

    entry_matches = entries.loc[
        (entries["item_norm"] == item_norm)
        | (entries["catalog_norm"] == selected_row.get("catalog_norm", ""))
        | (entries["description_brand_key"] == desc_brand_key)
    ].copy()
    entry_matches["source_type"] = "entrada_fuente"

    exit_matches = exits.loc[
        (exits["item_norm"] == item_norm)
        | (exits["catalog_norm"] == selected_row.get("catalog_norm", ""))
        | (exits["description_brand_key"] == desc_brand_key)
    ].copy()
    exit_matches["source_type"] = "salida_fuente"

    combined = pd.concat([inventory_matches, entry_matches, exit_matches], ignore_index=True, sort=False)
    if combined.empty:
        return combined
    combined = apply_canonical_display(combined)
    preferred = [
        "source_type",
        ITEM_KEY_COLUMN,
        RAW_ITEM_KEY_COLUMN,
        "codigo",
        "catalogo",
        "catalogo_original",
        "descripcion",
        "descripcion_original",
        "marca",
        "lote",
        "cantidad",
        "unidad",
        "fecha",
        "caducidad",
        "ubicacion",
        "categoria",
        "entrada",
        "salida",
        "existencia",
    ]
    return combined[order_columns(combined, preferred)].sort_values(
        ["source_type", "catalogo", "codigo", "lote", "fecha"],
        na_position="last",
    )


def prefill_values(selected_label: str, catalog_df: pd.DataFrame) -> dict[str, object]:
    defaults = {column: "" for column in ENTRY_COLUMNS}
    defaults["cantidad"] = 1
    defaults["fecha"] = pd.Timestamp.today().date()
    defaults["categoria"] = "REACTIVO"
    if selected_label == "Nuevo insumo" or catalog_df.empty:
        return defaults

    selected_code = selected_label.split(" - ", 1)[0]
    match = filter_by_item_key(catalog_df, selected_code)
    if match.empty:
        return defaults

    row = match.iloc[0]
    defaults.update(
        {
            "id_registro": row.get("id_registro", ""),
            "codigo": row.get("codigo", ""),
            "descripcion": row.get("descripcion", ""),
            "catalogo": row.get("catalogo", ""),
            "marca": row.get("marca", ""),
            "lote": row.get("lote", ""),
            "unidad": row.get("unidad", ""),
            "caducidad": row.get("caducidad", ""),
            "ubicacion": row.get("ubicacion", ""),
            "categoria": row.get("categoria", "OTRO"),
        }
    )
    return defaults


def render_full_table(title: str, df: pd.DataFrame, search_key: str) -> None:
    st.subheader(title)
    if df.empty:
        st.info("No hay datos disponibles en esta tabla.")
        return

    search = st.text_input(f"Buscar en {title.lower()}", key=search_key)
    filtered = df.copy()
    if search:
        pattern = search.strip().lower()
        filtered = filtered.loc[
            filtered.astype(str)
            .apply(lambda col: col.str.lower().str.contains(pattern, na=False))
            .any(axis=1)
        ]
    st.dataframe(filtered, use_container_width=True, hide_index=True)


def order_columns(df: pd.DataFrame, preferred: list[str]) -> list[str]:
    existing_preferred = [column for column in preferred if column in df.columns]
    remaining = [column for column in df.columns if column not in existing_preferred]
    return existing_preferred + remaining


def rename_display_columns(df: pd.DataFrame, rename_map: dict[str, str]) -> pd.DataFrame:
    available = {key: value for key, value in rename_map.items() if key in df.columns}
    return df.rename(columns=available)


def apply_canonical_display(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df.copy()
    prepared = ensure_item_key(df)
    prepared = prepared.copy()
    prepared["catalogo_original"] = prepared.get("catalogo", "")
    prepared["descripcion_original"] = prepared.get("descripcion", "")
    if CANONICAL_CATALOG_COLUMN in prepared.columns:
        prepared["catalogo"] = prepared[CANONICAL_CATALOG_COLUMN].where(
            prepared[CANONICAL_CATALOG_COLUMN].fillna("").astype(str).str.strip() != "",
            prepared["catalogo"],
        )
    if CANONICAL_DESCRIPTION_COLUMN in prepared.columns:
        prepared["descripcion"] = prepared[CANONICAL_DESCRIPTION_COLUMN].where(
            prepared[CANONICAL_DESCRIPTION_COLUMN].fillna("").astype(str).str.strip() != "",
            prepared["descripcion"],
        )
    return prepared


def normalize_tab_key(value: str) -> str:
    return value.lower().replace(" ", "_")


def get_scope_filter_values(inventory_scope: str) -> list[str]:
    if inventory_scope == "lit":
        return ["lit"]
    if inventory_scope == "frontera":
        return ["frontera"]
    return [inventory_scope]


def filter_app_scope_rows(app_movements: pd.DataFrame, inventory_scope: str, selected_code: str | None = None) -> pd.DataFrame:
    if app_movements.empty:
        return pd.DataFrame(columns=app_movements.columns)
    filtered = app_movements.loc[app_movements["inventory_scope"].isin(get_scope_filter_values(inventory_scope))].copy()
    filtered = ensure_item_key(filtered)
    if selected_code is not None:
        filtered = filtered.loc[filtered[ITEM_KEY_COLUMN] == selected_code].copy()
    return filtered


def load_conflict_flags() -> pd.DataFrame:
    LOCAL_DATA_DIR.mkdir(parents=True, exist_ok=True)
    if not CONFLICTS_PATH.exists():
        return pd.DataFrame(columns=CONFLICT_COLUMNS)
    df = pd.read_csv(CONFLICTS_PATH)
    for column in CONFLICT_COLUMNS:
        if column not in df.columns:
            df[column] = None
    return df[CONFLICT_COLUMNS]


def save_conflict_flag(payload: dict[str, object]) -> None:
    existing = load_conflict_flags()
    updated = pd.concat([existing, pd.DataFrame([payload])], ignore_index=True)
    updated.to_csv(CONFLICTS_PATH, index=False)


def render_negative_item_card(row: pd.Series) -> None:
    col1, col2, col3 = st.columns(3)
    with col1:
        st.markdown(f"**Codigo:** {row.get('codigo', '')}")
        st.markdown(f"**Descripcion:** {row.get('descripcion', '')}")
        st.markdown(f"**Marca:** {row.get('marca', '')}")
        st.markdown(f"**Catalogo:** {row.get('catalogo', '')}")
    with col2:
        st.markdown(f"**Categoria:** {row.get('categoria', '')}")
        st.markdown(f"**Ubicacion:** {row.get('ubicacion', '')}")
        st.markdown(f"**Lote:** {row.get('lote', '')}")
        st.markdown(f"**Caducidad:** {row.get('caducidad', '')}")
    with col3:
        st.metric("Entradas", f"{float(row.get('entrada', 0) or 0):,.0f}")
        st.metric("Salidas", f"{float(row.get('salida', 0) or 0):,.0f}")
        st.metric("Diferencia final", f"{float(row.get('existencia', 0) or 0):,.0f}")


def render_add_missing_entry_form(row: pd.Series, repository, inventory_scope: str) -> None:
    st.markdown("#### Agregar entrada faltante")
    with st.form(f"missing_entry_{inventory_scope}_{row['codigo']}"):
        form_col1, form_col2, form_col3 = st.columns(3)
        with form_col1:
            id_registro = st.text_input("ID de entrada", value="")
            codigo = st.text_input("Codigo", value=str(row.get("codigo", "")))
            descripcion = st.text_input("Descripcion", value=str(row.get("descripcion", "")))
            catalogo = st.text_input("Catalogo", value=str(row.get("catalogo", "")))
            marca = st.text_input("Marca", value=str(row.get("marca", "")))
        with form_col2:
            lote = st.text_input("Lote", value=str(row.get("lote", "")))
            cantidad = st.number_input("Cantidad a ingresar", min_value=0.0, step=1.0, value=1.0)
            unidad = st.text_input("Unidad", value=str(row.get("unidad", "")))
            caducidad = st.text_input("Caducidad", value="" if pd.isna(row.get("caducidad")) else str(row.get("caducidad", "")))
        with form_col3:
            ubicacion = st.text_input("Ubicacion", value=str(row.get("ubicacion", "")))
            categoria = st.selectbox("Categoria", options=["REACTIVO", "MATERIAL", "OTRO"], index=0 if str(row.get("categoria", "")).upper() == "REACTIVO" else 1 if str(row.get("categoria", "")).upper() == "MATERIAL" else 2)
            fecha = st.date_input("Fecha", value=pd.Timestamp.today().date())
            responsable = st.text_input("Responsable", value="")
            temperatura = st.text_input("Temperatura (C)", value="")
        observaciones = st.text_area("Observaciones", value="Entrada agregada desde Corregir negativos.", height=80)
        submitted = st.form_submit_button("Guardar entrada faltante", use_container_width=True)
        if submitted:
            errors = []
            if not codigo.strip():
                errors.append("El codigo es obligatorio.")
            if not descripcion.strip():
                errors.append("La descripcion es obligatoria.")
            if cantidad <= 0:
                errors.append("La cantidad debe ser mayor a cero.")
            if not responsable.strip():
                errors.append("El responsable es obligatorio.")
            if not temperatura.strip():
                errors.append("La temperatura es obligatoria para entradas.")
            if errors:
                for error in errors:
                    st.error(error)
            else:
                repository.save_movement(
                    {
                        "inventory_scope": inventory_scope,
                        "movement_type": "entrada",
                        "id_registro": id_registro.strip(),
                        "codigo": codigo.strip(),
                        "descripcion": descripcion.strip(),
                        "catalogo": catalogo.strip(),
                        "marca": marca.strip(),
                        "lote": lote.strip(),
                        "cantidad": cantidad,
                        "unidad": unidad.strip(),
                        "caducidad": caducidad.strip(),
                        "ubicacion": ubicacion.strip(),
                        "categoria": categoria.strip(),
                        "fecha": parse_single_datetime(fecha).strftime("%Y-%m-%d"),
                        "responsable": responsable.strip(),
                        "temperatura": temperatura.strip(),
                        "observaciones": observaciones.strip(),
                        "verificado_por": "",
                    }
                )
                st.success("Entrada faltante guardada.")
                st.rerun()


def render_conflict_flag_form(row: pd.Series, inventory_scope: str) -> None:
    st.markdown("#### Marcar conflicto de homologacion")
    conflicts_df = load_conflict_flags()
    current_conflicts = conflicts_df.loc[
        (conflicts_df["inventory_scope"] == inventory_scope) & (conflicts_df["codigo_reportado"] == row["codigo"])
    ].copy()
    if not current_conflicts.empty:
        st.caption("Conflictos ya registrados para este codigo")
        st.dataframe(current_conflicts.sort_values("created_at", ascending=False), use_container_width=True, hide_index=True)

    with st.form(f"homologation_conflict_{inventory_scope}_{row['codigo']}"):
        codigo_sugerido = st.text_input("Codigo sugerido", value="")
        motivo = st.selectbox(
            "Motivo",
            options=[
                "Codigo duplicado",
                "Codigo distinto para el mismo producto",
                "Catalogo inconsistente",
                "Marca o descripcion no homologada",
                "Otro",
            ],
        )
        detalle = st.text_area("Detalle", height=100)
        submitted = st.form_submit_button("Guardar conflicto", use_container_width=True)
        if submitted:
            save_conflict_flag(
                {
                    "created_at": pd.Timestamp.now().isoformat(),
                    "inventory_scope": inventory_scope,
                    "codigo_reportado": row.get("codigo", ""),
                    "codigo_sugerido": codigo_sugerido.strip(),
                    "descripcion": row.get("descripcion", ""),
                    "marca": row.get("marca", ""),
                    "motivo": motivo,
                    "detalle": detalle.strip(),
                }
            )
            st.success("Conflicto de homologacion guardado.")
            st.rerun()


def render_movement_form(
    movement_type: str,
    catalog_df: pd.DataFrame,
    repository,
    inventory_scope: str,
) -> None:
    title = "Registrar entrada" if movement_type == "entrada" else "Registrar salida"
    st.subheader(title)
    st.caption("Este movimiento se guarda en la app y se suma al inventario del scope activo.")

    if movement_type == "salida":
        search_catalog = st.text_input(
            "Buscar por catalogo",
            key=f"search_catalog_{inventory_scope}_{movement_type}",
            help="Busca por codigo, catalogo, descripcion o marca.",
        )
        filtered_catalog = catalog_df.copy()
        if search_catalog.strip():
            pattern = search_catalog.strip().lower()
            filtered_catalog = filtered_catalog.loc[
                filtered_catalog[["codigo", "catalogo", "descripcion", "marca"]]
                .astype(str)
                .apply(lambda col: col.str.lower().str.contains(pattern, na=False))
                .any(axis=1)
            ]
        option_source = filtered_catalog if not filtered_catalog.empty else catalog_df
    else:
        option_source = catalog_df

    selected_label = st.selectbox(
        "Selecciona un insumo",
        options=build_catalog_options(option_source),
        key=f"selector_{inventory_scope}_{movement_type}",
    )
    defaults = prefill_values(selected_label, catalog_df)

    with st.form(f"form_{inventory_scope}_{movement_type}", clear_on_submit=False):
        col1, col2, col3 = st.columns(3)
        with col1:
            id_registro = st.text_input(
                "ID de entrada" if movement_type == "entrada" else "ID de salida",
                value=str(defaults["id_registro"]),
            )
            codigo = st.text_input("Codigo", value=str(defaults["codigo"]))
            descripcion = st.text_input("Descripcion", value=str(defaults["descripcion"]))
            catalogo = st.text_input("Catalogo", value=str(defaults["catalogo"]))
            marca = st.text_input("Marca", value=str(defaults["marca"]))
        with col2:
            lote = st.text_input("Lote", value=str(defaults["lote"]))
            cantidad = st.number_input("Cantidad", min_value=0.0, step=1.0, value=float(defaults["cantidad"]))
            unidad = st.text_input("Unidad", value=str(defaults["unidad"]))
            caducidad = st.text_input(
                "Caducidad",
                value="" if pd.isna(defaults["caducidad"]) else str(defaults["caducidad"]),
            )
        with col3:
            ubicacion = st.text_input("Ubicacion", value=str(defaults["ubicacion"]))
            category_options = ["REACTIVO", "MATERIAL", "OTRO"]
            default_category = str(defaults["categoria"]).upper()
            if default_category not in category_options:
                default_category = "OTRO"
            categoria = st.selectbox(
                "Categoria",
                options=category_options,
                index=category_options.index(default_category),
            )
            fecha = st.date_input("Fecha", value=defaults["fecha"])
            responsable = st.text_input("Responsable", value=str(defaults["responsable"]))
        extra_col1, extra_col2 = st.columns(2)
        with extra_col1:
            temperatura = st.text_input(
                "Temperatura (C)" if movement_type == "entrada" else "Temperatura (opcional)",
                value=str(defaults["temperatura"]),
            )
            verificado_por = st.text_input("Verificado por (opcional)", value=str(defaults["verificado_por"]))
        with extra_col2:
            observaciones = st.text_area("Observaciones", value=str(defaults["observaciones"]), height=120)

        submitted = st.form_submit_button("Guardar movimiento", use_container_width=True)
        if submitted:
            errors = []
            if not codigo.strip():
                errors.append("El codigo es obligatorio.")
            if not descripcion.strip():
                errors.append("La descripcion es obligatoria.")
            if cantidad <= 0:
                errors.append("La cantidad debe ser mayor a cero.")
            if not responsable.strip():
                errors.append("El responsable es obligatorio.")
            if movement_type == "entrada" and not temperatura.strip():
                errors.append("La temperatura es obligatoria para el formato de entrada.")

            if errors:
                for error in errors:
                    st.error(error)
            else:
                repository.save_movement(
                    {
                        "inventory_scope": inventory_scope,
                        "movement_type": movement_type,
                        "id_registro": id_registro.strip(),
                        "codigo": codigo.strip(),
                        "descripcion": descripcion.strip(),
                        "catalogo": catalogo.strip(),
                        "marca": marca.strip(),
                        "lote": lote.strip(),
                        "cantidad": cantidad,
                        "unidad": unidad.strip(),
                        "caducidad": caducidad.strip(),
                        "ubicacion": ubicacion.strip(),
                        "categoria": categoria.strip(),
                        "fecha": parse_single_datetime(fecha).strftime("%Y-%m-%d"),
                        "responsable": responsable.strip(),
                        "temperatura": temperatura.strip(),
                        "observaciones": observaciones.strip(),
                        "verificado_por": verificado_por.strip(),
                    }
                )
                st.success("Movimiento guardado correctamente.")
                st.rerun()


def build_regularization_as_movements(regularizations_df: pd.DataFrame) -> pd.DataFrame:
    if regularizations_df.empty:
        return pd.DataFrame(columns=MOVEMENT_COLUMNS)
    df = regularizations_df.copy()
    payload = pd.DataFrame(
        {
            "movement_uid": df["regularization_uid"],
            "inventory_scope": df["inventory_scope"],
            "movement_type": "entrada",
            "id_registro": "REG-" + df["regularization_uid"].astype(str).str[:8],
            "codigo": df["codigo"],
            "descripcion": df["descripcion"],
            "catalogo": df["catalogo"],
            "marca": df["marca"],
            "lote": df["lote"],
            "cantidad": pd.to_numeric(df["cantidad"], errors="coerce").fillna(0),
            "unidad": df["unidad"],
            "caducidad": df["caducidad"],
            "ubicacion": df["ubicacion"],
            "categoria": df["categoria"],
            "fecha": df["fecha_corte"],
            "responsable": df["validado_por"],
            "temperatura": "",
            "observaciones": "Regularizacion inicial: " + df["tipo_regularizacion"].fillna("").astype(str),
            "verificado_por": df["validado_por"],
            "captured_at": df["captured_at"],
        }
    )
    return payload[MOVEMENT_COLUMNS]


def render_regularization_form(catalog_df: pd.DataFrame, repository, inventory_scope: str) -> None:
    st.subheader("Regularizacion inicial")
    st.caption("Usa este formulario solo para material fisico sin remision o para ajuste de conteo inicial. No sustituye una entrada normal.")

    selected_label = st.selectbox(
        "Selecciona un insumo",
        options=build_catalog_options(catalog_df),
        key=f"selector_{inventory_scope}_regularizacion",
    )
    defaults = prefill_values(selected_label, catalog_df)

    with st.form(f"form_{inventory_scope}_regularizacion", clear_on_submit=False):
        col1, col2, col3 = st.columns(3)
        with col1:
            codigo = st.text_input("Codigo", value=str(defaults["codigo"]))
            descripcion = st.text_input("Descripcion", value=str(defaults["descripcion"]))
            catalogo = st.text_input("Catalogo", value=str(defaults["catalogo"]))
            marca = st.text_input("Marca", value=str(defaults["marca"]))
            tipo_regularizacion = st.selectbox(
                "Tipo de regularizacion",
                options=["sin_remision", "donacion", "material_heredado", "ajuste_conteo_inicial"],
            )
        with col2:
            lote = st.text_input("Lote", value=str(defaults["lote"]))
            cantidad = st.number_input("Cantidad validada", min_value=0.0, step=1.0, value=1.0)
            unidad = st.text_input("Unidad", value=str(defaults["unidad"]))
            caducidad = st.text_input(
                "Caducidad",
                value="" if pd.isna(defaults["caducidad"]) else str(defaults["caducidad"]),
            )
            ubicacion = st.text_input("Ubicacion", value=str(defaults["ubicacion"]))
        with col3:
            category_options = ["REACTIVO", "MATERIAL", "OTRO"]
            default_category = str(defaults["categoria"]).upper()
            if default_category not in category_options:
                default_category = "OTRO"
            categoria = st.selectbox("Categoria", options=category_options, index=category_options.index(default_category))
            soporte_disponible = st.selectbox("Soporte disponible", options=["no", "parcial", "si"], index=0)
            fecha_corte = st.date_input("Fecha de corte", value=pd.Timestamp.today().date(), key=f"fecha_corte_{inventory_scope}")
            fecha_validacion = st.date_input("Fecha de validacion", value=pd.Timestamp.today().date(), key=f"fecha_validacion_{inventory_scope}")
            validado_por = st.text_input("Validado por")

        folio_origen = st.text_input("Folio o referencia origen (opcional)")
        comentario_regularizacion = st.text_area(
            "Comentario de regularizacion",
            height=120,
            placeholder="Ejemplo: material existente en fisico sin remision localizada.",
        )

        submitted = st.form_submit_button("Guardar regularizacion", use_container_width=True)
        if submitted:
            errors = []
            if not codigo.strip():
                errors.append("El codigo es obligatorio.")
            if not descripcion.strip():
                errors.append("La descripcion es obligatoria.")
            if cantidad <= 0:
                errors.append("La cantidad debe ser mayor a cero.")
            if not validado_por.strip():
                errors.append("La persona que valida es obligatoria.")
            if not comentario_regularizacion.strip():
                errors.append("El comentario de regularizacion es obligatorio.")
            if errors:
                for error in errors:
                    st.error(error)
            else:
                repository.save_regularization(
                    {
                        "inventory_scope": inventory_scope,
                        "tipo_regularizacion": tipo_regularizacion,
                        "fecha_corte": parse_single_datetime(fecha_corte).strftime("%Y-%m-%d"),
                        "fecha_validacion": parse_single_datetime(fecha_validacion).strftime("%Y-%m-%d"),
                        "codigo": codigo.strip(),
                        "descripcion": descripcion.strip(),
                        "catalogo": catalogo.strip(),
                        "marca": marca.strip(),
                        "lote": lote.strip(),
                        "cantidad": cantidad,
                        "unidad": unidad.strip(),
                        "caducidad": caducidad.strip(),
                        "ubicacion": ubicacion.strip(),
                        "categoria": categoria.strip(),
                        "soporte_disponible": soporte_disponible,
                        "folio_origen": folio_origen.strip(),
                        "comentario_regularizacion": comentario_regularizacion.strip(),
                        "validado_por": validado_por.strip(),
                    }
                )
                st.success("Regularizacion guardada correctamente.")
                st.rerun()


def render_regularization_table(regularizations_df: pd.DataFrame, inventory_scope: str) -> None:
    st.subheader("Regularizaciones iniciales")
    st.caption("Estas regularizaciones se guardan por separado de entradas y salidas normales. Solo se deben aplicar al inventario oficial cuando autoricen el corte.")
    if regularizations_df.empty:
        st.info("No hay regularizaciones capturadas.")
        return
    filtered = regularizations_df.loc[regularizations_df["inventory_scope"].isin(get_scope_filter_values(inventory_scope))].copy()
    if filtered.empty:
        st.info("No hay regularizaciones para este scope.")
        return
    st.dataframe(filtered[order_columns(filtered, REGULARIZATION_DISPLAY_COLUMNS)], use_container_width=True, hide_index=True)


def render_editable_captured_rows(
    selected_code: str,
    inventory_scope: str,
    app_movements: pd.DataFrame,
    repository,
) -> None:
    scope_rows = filter_app_scope_rows(app_movements, inventory_scope, selected_code)
    if scope_rows.empty:
        st.info("No hay movimientos capturados en la app para este catalogo.")
        return

    for movement_type, title in [("entrada", "Entradas capturadas"), ("salida", "Salidas capturadas")]:
        subset = scope_rows.loc[scope_rows["movement_type"] == movement_type].copy()
        st.markdown(f"#### {title}")
        if subset.empty:
            st.caption("No hay registros editables de este tipo para el catalogo seleccionado.")
            continue

        editor_source = subset[EDITABLE_MOVEMENT_COLUMNS].copy().set_index("movement_uid")
        edited = st.data_editor(
            editor_source,
            hide_index=True,
            use_container_width=True,
            key=f"editor_{inventory_scope}_{movement_type}_{selected_code}",
        )
        if st.button(
            f"Guardar cambios de {movement_type}",
            key=f"save_editor_{inventory_scope}_{movement_type}_{selected_code}",
            use_container_width=True,
        ):
            updated = edited.reset_index().rename(columns={"index": "movement_uid"})
            updated["inventory_scope"] = inventory_scope
            updated["movement_type"] = movement_type
            updated["captured_at"] = updated["movement_uid"].map(
                subset.set_index("movement_uid")["captured_at"].to_dict()
            )
            updated["fecha"] = parse_mixed_datetime_series(updated["fecha"]).dt.strftime("%Y-%m-%d")
            updated["cantidad"] = pd.to_numeric(updated["cantidad"], errors="coerce").fillna(0)
            repository.upsert_movements(updated[MOVEMENT_COLUMNS])
            st.success(f"Se actualizaron las {movement_type}s capturadas.")
            st.rerun()


def render_catalog_search(
    general_inventory_df: pd.DataFrame,
    app_movements: pd.DataFrame,
    repository,
    inventory_scope: str,
) -> None:
    st.subheader("Buscador por catalogo")
    st.caption(
        "Busca por catalogo, codigo, descripcion o marca. Desde aqui puedes localizar el activo y editar movimientos capturados para corregir negativos."
    )
    search = st.text_input("Buscar activo", key=f"catalog_search_{inventory_scope}")
    if not search:
        st.info("Escribe un catalogo, descripcion o marca para buscar.")
        return

    pattern = search.strip().lower()
    matches = general_inventory_df.loc[
        general_inventory_df.astype(str)
        .apply(lambda col: col.str.lower().str.contains(pattern, na=False))
        .any(axis=1)
    ].copy()

    if matches.empty:
        st.warning("No encontre coincidencias.")
        return

    options = [f"{get_item_key(row)} - {row['descripcion']}" for _, row in matches.head(50).iterrows()]
    selected = st.selectbox("Selecciona un activo", options=options, key=f"selected_asset_{inventory_scope}")
    selected_code = selected.split(" - ", 1)[0]
    row = filter_by_item_key(matches, selected_code).iloc[0]
    links = build_product_search_links(row)

    card_left, card_right = st.columns([2, 1])
    with card_left:
        st.markdown("### Ficha del activo")
        st.markdown(f"**Codigo:** {row['codigo']}")
        st.markdown(f"**Catalogo:** {row['catalogo']}")
        st.markdown(f"**Descripcion:** {row['descripcion']}")
        st.markdown(f"**Marca:** {row['marca']}")
        st.markdown(f"**Categoria:** {row.get('categoria', '')}")
        st.markdown(f"**Ubicacion:** {row.get('ubicacion', '')}")
        st.markdown(f"**Lote:** {row.get('lote', '')}")
        st.markdown(f"**Caducidad:** {row.get('caducidad', '')}")
        st.markdown(f"**Entradas acumuladas:** {row.get('entrada', '')}")
        st.markdown(f"**Salidas acumuladas:** {row.get('salida', '')}")
        st.markdown(f"**Existencia estimada:** {row.get('existencia', '')}")
    with card_right:
        st.markdown("### Links")
        st.markdown(f"[Buscar en Google]({links['google']})")
        st.markdown(f"[Buscar proveedor / producto]({links['proveedor']})")

    render_editable_captured_rows(selected_code, inventory_scope, app_movements, repository)


def render_negative_correction_tab(
    general_inventory_df: pd.DataFrame,
    source_entry_df: pd.DataFrame,
    source_exit_df: pd.DataFrame,
    app_movements: pd.DataFrame,
    repository,
    inventory_scope: str,
) -> None:
    st.subheader("Corregir negativos")
    diagnostics_df = build_negative_diagnostics(general_inventory_df, source_entry_df, source_exit_df)
    if diagnostics_df.empty:
        st.success("No hay claves negativas para corregir.")
        return

    st.caption("Busca por codigo o descripcion y revisa entradas, salidas y movimientos capturados antes de corregir.")
    search = st.text_input("Buscar por codigo", key=f"negative_fix_search_{inventory_scope}")
    filtered_negatives = diagnostics_df.copy()
    if search.strip():
        pattern = search.strip().lower()
        filtered_negatives = filtered_negatives.loc[
            filtered_negatives.astype(str)
            .apply(lambda col: col.str.lower().str.contains(pattern, na=False))
            .any(axis=1)
        ].copy()
    if filtered_negatives.empty:
        st.warning("No encontre negativos con ese criterio.")
        return

    options = [
        f"{get_item_key(row)} - {row['descripcion']} ({float(row['existencia']):,.0f})"
        for _, row in filtered_negatives.sort_values("existencia").head(200).iterrows()
    ]
    selected = st.selectbox("Selecciona una clave negativa", options=options, key=f"negative_fix_code_{inventory_scope}")
    selected_code = selected.split(" - ", 1)[0]
    row = filter_by_item_key(filtered_negatives, selected_code).iloc[0]

    render_negative_item_card(row)

    source_entries = apply_canonical_display(filter_by_item_key(source_entry_df, selected_code))
    source_exits = apply_canonical_display(filter_by_item_key(source_exit_df, selected_code))
    related_variants = build_related_variant_rows(selected_code, general_inventory_df, source_entry_df, source_exit_df)
    app_rows = filter_app_scope_rows(app_movements, inventory_scope, selected_code)

    source_entries = source_entries.sort_values("fecha", ascending=False, na_position="last")
    source_exits = source_exits.sort_values("fecha", ascending=False, na_position="last")
    app_rows = app_rows.sort_values("fecha", ascending=False, na_position="last") if not app_rows.empty else app_rows

    tab_related, tab_entries, tab_exits, tab_app, tab_actions = st.tabs(
        ["Variantes relacionadas", "Entradas fuente", "Salidas fuente", "Movimientos capturados en app", "Acciones"]
    )

    with tab_related:
        st.caption("Aqui se agrupan registros que podrian corresponder al mismo producto por catalogo parecido o misma descripcion/marca.")
        if related_variants.empty:
            st.info("No encontre variantes relacionadas para esta clave.")
        else:
            render_full_table(
                "Variantes relacionadas",
                related_variants,
                f"search_negative_related_{inventory_scope}_{selected_code}",
            )

    with tab_entries:
        if source_entries.empty:
            st.info("No hay entradas fuente para este codigo.")
        else:
            render_full_table(
                "Entradas fuente",
                source_entries[
                    order_columns(
                        source_entries,
                        [
                            "id_registro",
                            "codigo",
                            "catalogo",
                            "catalogo_original",
                            "descripcion",
                            "descripcion_original",
                            "cantidad",
                            "unidad",
                            "fecha",
                            "responsable",
                            "marca",
                            "lote",
                            "caducidad",
                            "ubicacion",
                            "categoria",
                        ],
                    )
                ],
                f"search_negative_entries_{inventory_scope}_{selected_code}",
            )

    with tab_exits:
        if source_exits.empty:
            st.info("No hay salidas fuente para este codigo.")
        else:
            render_full_table(
                "Salidas fuente",
                source_exits[
                    order_columns(
                        source_exits,
                        [
                            "id_registro",
                            "codigo",
                            "catalogo",
                            "catalogo_original",
                            "descripcion",
                            "descripcion_original",
                            "cantidad",
                            "unidad",
                            "fecha",
                            "responsable",
                            "marca",
                            "lote",
                            "caducidad",
                            "ubicacion",
                            "categoria",
                        ],
                    )
                ],
                f"search_negative_exits_{inventory_scope}_{selected_code}",
            )

    with tab_app:
        if app_rows.empty:
            st.info("No hay movimientos capturados en app para este codigo.")
        else:
            render_full_table(
                "Movimientos capturados en app",
                app_rows[
                    order_columns(
                        app_rows,
                        ["movement_type", "id_registro", "codigo", "descripcion", "catalogo", "marca", "lote", "cantidad", "unidad", "caducidad", "ubicacion", "categoria", "fecha", "responsable", "temperatura", "observaciones", "verificado_por", "inventory_scope"],
                    )
                ],
                f"search_negative_app_{inventory_scope}_{selected_code}",
            )

    with tab_actions:
        action_tab1, action_tab2, action_tab3 = st.tabs(
            ["Agregar entrada faltante", "Corregir salida capturada", "Marcar conflicto de homologacion"]
        )
        with action_tab1:
            render_add_missing_entry_form(row, repository, inventory_scope)
        with action_tab2:
            render_editable_captured_rows(selected_code, inventory_scope, app_movements, repository)
        with action_tab3:
            render_conflict_flag_form(row, inventory_scope)


def load_inventory_bundle(
    inventory_scope: str,
    recovery_workbook_source,
    indicators_workbook_source,
    materials_workbook_source,
    repository,
    prefer_seed: bool = True,
) -> tuple[dict[str, pd.DataFrame], pd.DataFrame, pd.DataFrame]:
    if prefer_seed:
        seed_df = repository.load_seed_entries(inventory_scope)
        if not seed_df.empty:
            return load_seed_inventory_frames(seed_df), pd.DataFrame(), pd.DataFrame()

    if inventory_scope == "lit":
        if indicators_workbook_source is None:
            raise RuntimeError("No hay base oficial sembrada y tampoco existe el archivo de indicadores de desempeño de los almacenes.")
        if recovery_workbook_source is None:
            raise RuntimeError("No hay base oficial sembrada y tampoco existe el inventario de recuperacion.")
        indicator_frames = load_indicator_inventory_frames(indicators_workbook_source, "JUL 26")
        recovery_frames = load_recovery_template_frames(recovery_workbook_source)
        return merge_inventory_frames(indicator_frames, recovery_frames), pd.DataFrame(), pd.DataFrame()

    if inventory_scope == "frontera":
        if materials_workbook_source is None:
            raise RuntimeError("No hay base oficial sembrada y tampoco existe el archivo local para Frontera/Federal.")
        return load_material_inventory_frames(materials_workbook_source, "federal"), pd.DataFrame(), pd.DataFrame()

    raise RuntimeError(f"Inventario no soportado: {inventory_scope}")


def explain_load_error(exc: Exception, inventory_scope: str) -> None:
    st.error(f"No pude cargar el inventario `{INVENTORY_SCOPES[inventory_scope]}`: {exc}")
    if inventory_scope == "lit":
        st.info("Verifica que existan el archivo de indicadores y el inventario de recuperacion.")
    else:
        st.info("Verifica que exista el Excel local de Frontera/Federal.")


def resolve_workbook_source(local_path: str, uploaded_file=None):
    if uploaded_file is not None:
        return BytesIO(uploaded_file.getvalue())
    path = Path(local_path)
    if path.exists():
        return path
    return None


def main() -> None:
    init_state()
    st.title("Inventario General INER")
    st.caption("Inventarios operativos: LIT y Frontera.")

    repository = get_repository()

    inventory_scope = st.sidebar.radio(
        "Inventario activo",
        options=list(INVENTORY_SCOPES.keys()),
        index=list(INVENTORY_SCOPES.keys()).index(DEFAULT_SCOPE),
        format_func=lambda key: INVENTORY_SCOPES[key],
    )

    seed_available = not repository.load_seed_entries(inventory_scope).empty
    if seed_available:
        st.sidebar.success("Base oficial cargada.")
    else:
        st.sidebar.warning("No hay base oficial sembrada; se usaran Excel como respaldo.")

    recovery_workbook_path = str(RECOVERY_WORKBOOK_PATH)
    indicators_workbook_path = str(INDICATORS_WORKBOOK_PATH)
    materials_workbook_path = str(MATERIALS_WORKBOOK_PATH)
    recovery_upload = None
    indicators_upload = None
    materials_upload = None
    use_excel_fallback = False
    with st.sidebar.expander("Reconstruir desde Excel", expanded=not seed_available):
        use_excel_fallback = st.checkbox(
            "Usar Excel temporalmente en lugar de la base oficial",
            value=not seed_available,
            help="Activalo solo para revisar o reconstruir la base oficial.",
        )
        recovery_workbook_path = st.text_input(
            "Excel de recuperacion",
            value=recovery_workbook_path,
        )
        recovery_upload = st.file_uploader(
            "Subir Excel de recuperacion",
            type=["xlsx", "xlsm", "xls"],
            key="recovery_upload",
        )
        indicators_workbook_path = st.text_input(
            "Indicadores de almacenes",
            value=indicators_workbook_path,
        )
        indicators_upload = st.file_uploader(
            "Subir indicadores de almacenes",
            type=["xlsx", "xlsm", "xls"],
            key="indicators_upload",
        )
        materials_workbook_path = st.text_input(
            "Excel Frontera/Federal",
            value=materials_workbook_path,
        )
        materials_upload = st.file_uploader(
            "Subir Excel Frontera/Federal",
            type=["xlsx", "xlsm", "xls"],
            key="materials_upload",
        )

    st.sidebar.markdown("**Fuente configurada**")
    if inventory_scope == "lit":
        st.sidebar.caption("LIT usa la base oficial si ya esta sembrada. Los Excel quedan como respaldo para reconstruirla.")
    else:
        st.sidebar.caption("Frontera usa la base oficial si ya esta sembrada. El Excel local queda como respaldo.")
    recovery_workbook_source = None
    indicators_workbook_source = None
    materials_workbook_source = None
    if inventory_scope == "lit":
        recovery_workbook_source = resolve_workbook_source(recovery_workbook_path, recovery_upload)
        indicators_workbook_source = resolve_workbook_source(indicators_workbook_path, indicators_upload)
    else:
        materials_workbook_source = resolve_workbook_source(materials_workbook_path, materials_upload)

    try:
        frames, registry_df, results_df = load_inventory_bundle(
            inventory_scope,
            recovery_workbook_source,
            indicators_workbook_source,
            materials_workbook_source,
            repository,
            prefer_seed=not use_excel_fallback,
        )
    except Exception as exc:
        explain_load_error(exc, inventory_scope)
        return

    app_movements = repository.load_movements()
    regularizations_df = repository.load_regularizations()
    apply_regularizations = st.sidebar.checkbox(
        "Aplicar regularizaciones al inventario actual",
        value=False,
        help="Activalo solo cuando autoricen formalmente el borrón y cuenta nueva.",
    )
    if apply_regularizations and not regularizations_df.empty:
        app_movements = pd.concat(
            [app_movements, build_regularization_as_movements(regularizations_df)],
            ignore_index=True,
        )

    scope_movements = app_movements.loc[app_movements["inventory_scope"] == inventory_scope].copy()
    inventory_df, entry_df, exit_df, catalog_df = build_inventory_snapshot(
        frames["entradas"],
        frames["salidas"],
        scope_movements,
        catalog_df=frames.get("catalogo"),
    )

    general_inventory_df = inventory_df.copy()
    active_inventory_df = general_inventory_df.loc[general_inventory_df["existencia"].fillna(0) > 0].copy()

    st.markdown(f"### Inventario: {INVENTORY_SCOPES[inventory_scope]}")
    using_seed = seed_available and not use_excel_fallback
    if using_seed:
        st.caption("Fuente: base oficial sembrada. Los Excel ya no son necesarios para operar.")
    elif inventory_scope == "lit":
        st.caption("Fuente: base oficial LIT. Si no existe semilla, se reconstruye con JUL 26 + plantilla de recuperacion.")
    else:
        st.caption("Fuente: base oficial Frontera. Si no existe semilla, se reconstruye con el listado federal local.")

    total_items = len(active_inventory_df)
    total_stock = float(active_inventory_df["existencia"].fillna(0).sum()) if not active_inventory_df.empty else 0
    total_entries = float(entry_df["cantidad"].fillna(0).sum()) if not entry_df.empty else 0
    total_exits = float(exit_df["cantidad"].fillna(0).sum()) if not exit_df.empty else 0

    kpi1, kpi2, kpi3, kpi4 = st.columns(4)
    kpi1.metric("Claves activas", f"{total_items}")
    kpi2.metric("Existencia total", f"{total_stock:,.0f}")
    kpi3.metric("Entradas acumuladas", f"{total_entries:,.0f}")
    kpi4.metric("Salidas acumuladas", f"{total_exits:,.0f}")

    resumen_tab, negativos_tab, corregir_negativos_tab, buscador_tab, recepcion_tab, salidas_tab, entrada_form_tab, salida_form_tab, regularizaciones_tab = st.tabs(
        [
            "Resumen general",
            "Negativos por revisar",
            "Corregir negativos",
            "Buscador catalogo",
            "Recepcion",
            "Salidas",
            "Registrar entrada",
            "Registrar salida",
            "Regularizaciones",
        ]
    )

    with resumen_tab:
        st.subheader("Inventario general")
        if inventory_scope == "lit":
            st.info(
                f"Mostrando {len(active_inventory_df)} claves con existencia real. "
                f"Las claves de plantilla quedan disponibles para busqueda y captura, pero no suman existencia."
            )
        show_template_rows = st.checkbox(
            "Mostrar tambien claves de plantilla sin existencia",
            value=False,
            key=f"show_template_rows_{inventory_scope}",
        )
        categoria_filtro = st.multiselect(
            "Filtrar por categoria",
            options=sorted(general_inventory_df["categoria"].dropna().unique().tolist()),
            key=f"cat_filter_{inventory_scope}",
        )
        search = st.text_input(
            "Buscar por codigo, descripcion, marca o ubicacion",
            key=f"search_inventario_{inventory_scope}",
        )
        filtered = general_inventory_df.copy() if show_template_rows else active_inventory_df.copy()
        if categoria_filtro:
            filtered = filtered.loc[filtered["categoria"].isin(categoria_filtro)]
        if search:
            pattern = search.strip().lower()
            filtered = filtered.loc[
                filtered.astype(str)
                .apply(lambda col: col.str.lower().str.contains(pattern, na=False))
                .any(axis=1)
            ]
        visible_columns = [column for column in SUMMARY_COLUMNS if column in filtered.columns]
        st.dataframe(
            filtered[order_columns(filtered, visible_columns)],
            use_container_width=True,
            hide_index=True,
        )

    with negativos_tab:
        st.subheader("Negativos por revisar")
        negativos_df = build_negative_diagnostics(general_inventory_df, frames["entradas"], frames["salidas"])
        if negativos_df.empty:
            st.success("No hay claves con existencia negativa.")
        else:
            st.caption("Esta tabla ya intenta marcar cuando el negativo podria venir de variantes de escritura, entradas faltantes o mezcla de claves para la misma descripcion.")
            visible_columns = [column for column in NEGATIVE_DIAGNOSTIC_COLUMNS if column in negativos_df.columns]
            st.dataframe(
                negativos_df[order_columns(negativos_df, visible_columns)].sort_values("existencia"),
                use_container_width=True,
                hide_index=True,
            )

    with corregir_negativos_tab:
        render_negative_correction_tab(
            general_inventory_df=general_inventory_df,
            source_entry_df=frames["entradas"],
            source_exit_df=frames["salidas"],
            app_movements=app_movements,
            repository=repository,
            inventory_scope=inventory_scope,
        )

    with buscador_tab:
        render_catalog_search(general_inventory_df, app_movements, repository, inventory_scope)

    with recepcion_tab:
        recepcion_df = entry_df.sort_values("fecha", ascending=False, na_position="last").copy()
        visible_columns = [column for column in TABLE_COLUMNS + ["temperatura"] if column in recepcion_df.columns]
        render_full_table(
            "Recepcion",
            rename_display_columns(
                recepcion_df[order_columns(recepcion_df, visible_columns)],
                {
                    "responsable": "Recibio",
                },
            ),
            f"search_recepcion_{inventory_scope}",
        )

    with salidas_tab:
        salidas_df = exit_df.sort_values("fecha", ascending=False, na_position="last").copy()
        visible_columns = [column for column in TABLE_COLUMNS if column in salidas_df.columns]
        render_full_table(
            "Salidas",
            rename_display_columns(
                salidas_df[order_columns(salidas_df, visible_columns)],
                {
                    "responsable": "Iniciales",
                },
            ),
            f"search_salidas_{inventory_scope}",
        )

    with entrada_form_tab:
        render_movement_form("entrada", catalog_df, repository, inventory_scope)

    with salida_form_tab:
        render_movement_form("salida", catalog_df, repository, inventory_scope)

    with regularizaciones_tab:
        regularization_view_tab, regularization_form_tab = st.tabs(["Ver regularizaciones", "Registrar regularizacion"])
        with regularization_view_tab:
            render_regularization_table(regularizations_df, inventory_scope)
        with regularization_form_tab:
            render_regularization_form(catalog_df, repository, inventory_scope)


if __name__ == "__main__":
    main()
